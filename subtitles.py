"""Genere des sous-titres dynamiques (surbrillance mot par mot, style karaoke)
a partir des timings de mots fournis par Azure Speech. Rendu ensuite par ffmpeg/libass
(rapide, natif) plutot que par un compositing image-par-image en Python."""
import json
import re

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



# ---------- format long dynamique (montage long_montage.py) ----------

_STOP = set("""a an the and or but so to of in on at for with from by is are was were be been being am i you your
yours he she it we they them his her its our their my me us this that these those there here what which who whom
whose when where why how not no do does did don't doesn't can can't will would should could just than then very
really too also only into out up down over about as if because while all any some more most much many one ever even
it's you're i'm that's what's let's get got have has had thing things something someone way make made know like
going go want say said tell told every each own same other another back still again never always""".split())

_POWER = set("""fail failure quit win success brain habit habits fear money rich discipline focus dream goal goals
confidence lazy energy time truth secret mistake power control pain growth change life future stop start ready
motivation proof wins broke anxiety stress love alone happy happiness mindset consistency comfort excuse excuses
results progress purpose identity system systems dopamine willpower""".split())


def _word_tokens(word_boundaries: list[dict]) -> list[tuple[str, float, float]]:
    toks = []
    for wb in sorted(word_boundaries, key=lambda w: w["offset"]):
        word = _clean_word(wb["text"])
        if not word or not re.search(r"[A-Za-z0-9]", word):
            continue
        s = wb["offset"] / 10_000_000
        toks.append((word, s, s + wb["duration"] / 10_000_000))
    return toks


def _bare(word: str) -> str:
    return re.sub(r"[^\w'%$-]", "", word).lower()


def pick_keywords(word_boundaries: list[dict], scene_starts: list[float], total: float,
                  min_gap: float = 7.0) -> list[tuple[str, float]]:
    """Mots a faire jaillir a l'ecran : le mot fort du debut de chaque paragraphe, plus les mots "forts"
    (POWER) et les nombres prononces ailleurs, jamais deux a moins de min_gap secondes."""
    toks = _word_tokens(word_boundaries)
    picked: list[tuple[str, float]] = []

    def ok(t: float) -> bool:
        return all(abs(t - p) >= min_gap for _, p in picked) and t < total - 1.5

    # 1) un mot fort au debut de chaque paragraphe (dans ses ~6 premieres secondes)
    for st in scene_starts:
        window = [(w, s) for w, s, _ in toks if st - 0.2 <= s <= st + 6.0]
        cands = [(w, s) for w, s in window if _bare(w) not in _STOP and len(_bare(w)) >= 4]
        if not cands:
            continue
        power = [(w, s) for w, s in cands if _bare(w) in _POWER or _bare(w).rstrip("s") in _POWER]
        w, s = (power or [max(cands, key=lambda c: len(_bare(c[0])))])[0]
        if ok(s):
            picked.append((w, s))
    # 2) nombres et mots forts prononces ailleurs
    for w, s, _ in toks:
        b = _bare(w)
        if (re.match(r"^\$?\d[\d,.]*%?$", b) or b in _POWER) and ok(s):
            picked.append((w, s))
    return sorted(picked, key=lambda p: p[1])


def build_long_dynamic_ass(word_boundaries: list[dict], out_path: str, scene_starts: list[float], total: float,
                           play_res_x: int = 1920, play_res_y: int = 1080) -> str:
    """Sous-titres + textes animes du format long :
    - sous-titres 3-5 mots en bas, le mot prononce passe en jaune avec un petit "pop" ;
    - mots-cles qui jaillissent en grand en haut de l'ecran (arrivee rebondie, sortie en fondu) ;
    - fine barre de progression en haut (incite a regarder jusqu'au bout)."""
    font = config.SUBTITLE_FONT_NAME
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,2,2,120,120,90,1
Style: Kicker,{font},120,&H00111111,&H00111111,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,3,22,0,8,100,100,110,1
Style: Bar,{font},10,&H0000D4FF,&H0000D4FF,&H0000D4FF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    toks = _word_tokens(word_boundaries)

    # sous-titres : 3 a 5 mots, coupe sur la ponctuation et les silences
    lines, cur = [], []
    for i, t in enumerate(toks):
        cur.append(t)
        gap = toks[i + 1][1] - t[2] if i + 1 < len(toks) else 9
        chars = sum(len(c[0]) + 1 for c in cur)
        if len(cur) >= 5 or chars >= 26 or (len(cur) >= 3 and re.search(r"[.,!?;:]$", t[0])) or gap > 0.4:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    for li, line in enumerate(lines):
        start = line[0][1]
        nxt = lines[li + 1][0][1] if li + 1 < len(lines) else total
        end = min(nxt, line[-1][2] + 0.3)
        parts = []
        for w, s, e in line:
            a = int((s - start) * 1000)
            b = int((e - start) * 1000)
            # \\r a chaque mot : en ASS les balises s'appliquent a tout le texte qui suit, sans lui le
            # surlignage d'un mot "deborderait" sur les mots suivants de la ligne
            parts.append(r"{\r\t(" + f"{a},{a + 1}" + r",\c&H00D7FF&)\t(" + f"{a},{a + 90}" + r",\fscx112\fscy112)"
                         r"\t(" + f"{b},{b + 120}" + r",\fscx100\fscy100\c&HFFFFFF&)}" + w)
        ev.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{{\\fad(90,60)}}" + " ".join(parts))

    # mots-cles animes : arrivee "slam" (grand -> taille normale avec rebond), petite rotation, sortie fondu
    for i, (word, s) in enumerate(pick_keywords(word_boundaries, scene_starts, total)):
        dur = 1.9
        rot = (-3, 2, -2, 3)[i % 4]
        accent = ("&H0000D4FF&", "&H00FFE500&", "&H006B2EFF&")[i % 3]  # jaune, cyan, rose (BGR)
        txt = re.sub(r"[^\w'%$-]", "", word).upper()
        ev.append(f"Dialogue: 1,{_ts(s)},{_ts(min(total, s + dur))},Kicker,,0,0,0,,"
                  r"{\3c" + accent + r"\frz" + str(rot) + r"\fscx170\fscy170\alpha&HFF&"
                  r"\t(0,120,\alpha&H00&\fscx92\fscy92)\t(120,220,\fscx100\fscy100)"
                  r"\fad(0,220)}" + txt)

    # barre de progression : un rectangle dont la zone visible s'agrandit sur toute la video
    ms = int(total * 1000)
    ev.append(f"Dialogue: 2,{_ts(0)},{_ts(total)},Bar,,0,0,0,,"
              r"{\pos(0,0)\clip(0,0,0,8)\t(0," + str(ms) + r",\clip(0,0," + str(play_res_x) + r",8))\p1}"
              f"m 0 0 l {play_res_x} 0 {play_res_x} 8 0 8{{\\p0}}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")
    return out_path

if __name__ == "__main__":
    import sys
    timing_path = sys.argv[1] if len(sys.argv) > 1 else None
    out_path = sys.argv[2] if len(sys.argv) > 2 else "output/video/subtitles.ass"
    if not timing_path:
        print("Usage: python subtitles.py <timings.json> [out.ass]")
        raise SystemExit(1)
    path = build_ass_from_timing_file(timing_path, out_path)
    print(f"Sous-titres generes -> {path}")
