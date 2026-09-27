"""Genere des sous-titres dynamiques (surbrillance mot par mot, style karaoke)
a partir des timings de mots fournis par edge-tts. Rendu ensuite par ffmpeg/libass
(rapide, natif) plutot que par un compositing image-par-image en Python."""
import json

import config


def _ass_header(play_res_x: int, play_res_y: int, fontsize: int, margin_v: int) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{config.SUBTITLE_FONT_NAME},{fontsize},&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
# PrimaryColour = blanc (mots pas encore prononces), SecondaryColour = jaune/or (mot en cours, via \kf)
# Alignment 2 = centre bas, MarginV = distance depuis le bas (plus grande en Shorts pour eviter
# le bandeau UI YouTube : legende/pastille d'abonnement en bas, boutons like/commentaire a droite).


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _clean_word(word: str) -> str:
    return word.replace("{", "").replace("}", "").replace("\\", "").replace("\n", " ").strip()


def build_ass(
    word_boundaries: list[dict], out_path: str, words_per_line: int = 4, max_line_seconds: float = 2.6,
    play_res_x: int = 1920, play_res_y: int = 1080, fontsize: int = 72, margin_v: int = 140,
) -> str:
    lines = []
    chunk = []
    chunk_start = None

    for wb in word_boundaries:
        start = wb["offset"] / 10_000_000
        dur = wb["duration"] / 10_000_000
        if chunk_start is None:
            chunk_start = start
        chunk.append(wb)
        elapsed = (start + dur) - chunk_start
        if len(chunk) >= words_per_line or elapsed >= max_line_seconds:
            lines.append(chunk)
            chunk = []
            chunk_start = None
    if chunk:
        lines.append(chunk)

    events = []
    for line in lines:
        line_start = line[0]["offset"] / 10_000_000
        line_end = (line[-1]["offset"] + line[-1]["duration"]) / 10_000_000

        text_parts = []
        for wb in line:
            k_centiseconds = max(1, round(wb["duration"] / 100_000))
            word = _clean_word(wb["text"])
            if not word:
                continue
            text_parts.append(f"{{\\kf{k_centiseconds}}}{word}")
        if not text_parts:
            continue
        text = " ".join(text_parts)
        events.append(f"Dialogue: 0,{_ts(line_start)},{_ts(line_end)},Default,,0,0,0,,{text}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_ass_header(play_res_x, play_res_y, fontsize, margin_v))
        f.write("\n".join(events))
        f.write("\n")
    return out_path


def build_ass_from_timing_file(timing_path: str, out_path: str, shorts: bool = False) -> str:
    with open(timing_path, "r", encoding="utf-8") as f:
        word_boundaries = json.load(f)
    if shorts:
        # Ecran plus etroit -> moins de mots par ligne ; police plus grande et marge basse
        # plus genereuse pour rester lisible et ne pas chevaucher l'UI Shorts (legende, boutons).
        return build_ass(
            word_boundaries, out_path, words_per_line=3,
            play_res_x=1080, play_res_y=1920, fontsize=90, margin_v=420,
        )
    return build_ass(word_boundaries, out_path)


if __name__ == "__main__":
    import sys
    timing_path = sys.argv[1] if len(sys.argv) > 1 else None
    out_path = sys.argv[2] if len(sys.argv) > 2 else "output/video/subtitles.ass"
    if not timing_path:
        print("Usage: python subtitles.py <timings.json> [out.ass]")
        raise SystemExit(1)
    path = build_ass_from_timing_file(timing_path, out_path)
    print(f"Sous-titres generes -> {path}")
