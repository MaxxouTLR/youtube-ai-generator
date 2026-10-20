"""Montage "pro" des Shorts, 100 % ffmpeg (rapide, aucun compositing Python image par image).

Ce qui change par rapport a l'ancien montage (clips fixes + coupes seches + sous-titres en bas) :
- mouvement permanent : chaque plan zoome lentement (avant/arriere) ou panote, jamais d'image figee ;
- coupes rapides calees sur la voix (un plan toutes les ~1,5-3 s) avec transitions courtes variees ;
- etalonnage : contraste/saturation releves, vignette, accentuation -> rendu moins "stock brut" ;
- accroche visuelle des la 1re seconde : la question du titre en gros, dans un bandeau, avec un "pop" ;
- sous-titres style Shorts : 1 a 3 mots en MAJUSCULES au milieu de l'ecran, le mot prononce en
  jaune et legerement agrandi (lisible sans le son, ce que fait la majorite du public mobile) ;
- barre de progression en haut (incite a regarder jusqu'au bout) ;
- son : musique plus presente mais qui s'efface automatiquement sous la voix (ducking), "whoosh" a
  chaque coupe, volume final normalise au standard des plateformes (-14 LUFS).
"""
import os
import random
import re
import subprocess

import imageio_ffmpeg

import config

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = config.SHORTS_WIDTH, config.SHORTS_HEIGHT, config.VIDEO_FPS
XFADE = 0.18                      # duree d'une transition (s)
TRANSITIONS = ["zoomin", "slideup", "slidedown", "smoothleft", "smoothright", "radial", "circleopen", "zoomin"]
FONT = os.environ.get("SHORTS_FONT_NAME", config.SUBTITLE_FONT_NAME)
FONTS_DIR = os.path.join(config.BASE_DIR, "assets", "fonts")


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        errs = [l for l in r.stderr.splitlines() if re.search(r"error|invalid|unable|no such|failed|cannot", l, re.I)]
        raise RuntimeError("ffmpeg a echoue : " + (" | ".join(errs[-6:]) or r.stderr[-800:]))


# ---------- plans ----------

def _motion_filter(kind: str, dur: float) -> str:
    """Cover-fit 1080x1920 puis camera tres vivante : clip accelere, zoom/pano marque, tremblement
    d'impact et flash lumineux au debut de chaque plan, grain film. Jamais d'image qui reste fixe."""
    d = f"{dur:.3f}"
    cover = f"setpts=PTS/1.18,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    # pas de zoom arriere : une taille qui decroit image par image fait planter ffmpeg 7.1 (scale eval=frame)
    z = {"zoom_in": f"(1.08+0.22*t/{d})", "punch_in": f"(1.12+0.40*t/{d})",
         "pan_left": "1.30", "pan_right": "1.30", "rise": "1.26"}[kind]
    xpos = {"pan_right": f"(0.1+0.8*t/{d})", "pan_left": f"(0.9-0.8*t/{d})"}.get(kind, "0.5")
    ypos = f"(0.85-0.7*t/{d})" if kind == "rise" else "0.5"
    shake = "max(0,1-t/0.28)"
    move = (f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,"
            f"crop={W}:{H}:x='(iw-{W})*{xpos}+16*sin(t*61)*{shake}':y='(ih-{H})*{ypos}+12*cos(t*47)*{shake}'")
    grade = (f"eq=contrast=1.10:saturation=1.28:brightness='0.02+0.28*max(0,1-t/0.11)':eval=frame,"
             "vignette=angle=PI/4.5,unsharp=5:5:0.5,noise=alls=6:allf=t+u")
    return f"{cover},{move},{grade},setsar=1,fps={FPS},format=yuv420p"


def prepare_shot(src: str, dur: float, out: str, kind: str, start: float = 0.0) -> str:
    _run([FFMPEG, "-y", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}", "-an",
          "-vf", _motion_filter(kind, dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", out])
    return out


# ---------- sous-titres + accroche ----------

def _ts(s: float) -> str:
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def _clean(w: str) -> str:
    return re.sub(r"[{}\\\n]", "", w).strip()


def build_ass(words: list[dict], hook: str, total: float, out_path: str) -> str:
    """words : timings mot par mot (offset/duration en unites de 100 ns, format Azure/edge-tts)."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},108,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,7,3,2,70,70,640,1
Style: Hook,{FONT},74,&H00000000,&H00000000,&H0000D7FF,&H00000000,-1,0,0,0,100,100,0,0,3,20,0,8,90,90,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if hook:
        hook = _clean(re.sub(r"#\w+", "", hook)).upper()
        ev.append(f"Dialogue: 1,{_ts(0)},{_ts(min(2.8, total))},Hook,,0,0,0,,"
                  r"{\fad(0,250)\fscx70\fscy70\t(0,160,\fscx106\fscy106)\t(160,250,\fscx100\fscy100)}" + hook)

    # regroupe 1 a 3 mots ; coupe aussi sur la ponctuation et sur les silences
    words = sorted(words, key=lambda w: w["offset"])
    toks = [(_clean(w["text"]), w["offset"] / 1e7, (w["offset"] + w["duration"]) / 1e7) for w in words]
    toks = [t for t in toks if t[0]]
    chunks, cur = [], []
    for i, t in enumerate(toks):
        # le mot suivant ferait deborder la ligne (texte en majuscules, police large) : on coupe avant
        if cur and sum(len(c[0]) + 1 for c in cur) + len(t[0]) > 15:
            chunks.append(cur)
            cur = []
        cur.append(t)
        gap = toks[i + 1][1] - t[2] if i + 1 < len(toks) else 9
        if len(cur) >= 3 or re.search(r"[.,!?;:]$", t[0]) or gap > 0.35:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0][1] if ci + 1 < len(chunks) else total
        chunk_end = min(nxt, ch[-1][2] + 0.25)
        for wi, (word, start, _) in enumerate(ch):
            end = ch[wi + 1][1] if wi + 1 < len(ch) else chunk_end
            parts = []
            for wj, (w2, _, _) in enumerate(ch):
                w2 = w2.upper()
                if wj == wi:
                    parts.append(r"{\c&H00E5FF&\fscx114\fscy114\t(0,90,\fscx106\fscy106)}" + w2 + r"{\r}")
                else:
                    parts.append(w2)
            rot = random.choice([-4, -3, 3, 4])
            pop = (r"{\fscx70\fscy70\frz" + str(rot) + r"\t(0,110,\fscx112\fscy112\frz0)\t(110,190,\fscx100\fscy100)}"
                   if wi == 0 else "")
            ev.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")
    return out_path


# ---------- assemblage final ----------

def _probe_duration(path: str) -> float:
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def plan_cuts(starts: list[float], total: float, min_len: float = 0.9, max_len: float = 2.0) -> list[tuple[float, float]]:
    """Points de coupe = debut de chaque passage narre ; fusionne les plans trop courts et
    redecoupe les trop longs (un plan de plus de ~3 s fait decrocher sur mobile)."""
    pts = sorted({0.0, *[s for s in starts if 0 < s < total]})
    spans = [(a, b) for a, b in zip(pts, pts[1:] + [total])]
    merged = []
    for a, b in spans:
        if merged and (b - a < min_len or merged[-1][1] - merged[-1][0] < min_len):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    out = []
    for a, b in merged:
        n = max(1, round((b - a) / max_len + 0.49))
        step = (b - a) / n
        out += [(a + k * step, a + (k + 1) * step) for k in range(n)]
    return out


def assemble_short(voice_path: str, shots: list[tuple[str, float]], words: list[dict], hook: str,
                   out_path: str, work_dir: str, music_path: str | None = None) -> str:
    """shots : [(clip_source, debut_du_passage_en_s)] dans l'ordre du script."""
    os.makedirs(work_dir, exist_ok=True)
    total = _probe_duration(voice_path)
    cuts = plan_cuts([s for _, s in shots], total)

    # chaque plan reutilise le clip du passage narre a ce moment-la (le dernier dont le debut <= coupe)
    srcs = []
    for a, _ in cuts:
        cand = [c for c, s in shots if s <= a + 0.01] or [shots[0][0]]
        srcs.append(cand[-1])

    kinds = ["punch_in", "pan_left", "zoom_in", "rise", "pan_right"]
    files, durs, used = [], [], {}
    for i, ((a, b), src) in enumerate(zip(cuts, srcs)):
        d = (b - a) + (XFADE if i < len(cuts) - 1 else 0)
        kind = kinds[(i + random.randint(0, 4)) % 5]
        # meme source reutilisee (passage long redecoupe) : on demarre plus loin dans le clip
        start = used.get(src, 0.0)
        used[src] = start + d
        start %= max(0.5, _probe_duration(src) - 0.5)
        f = os.path.join(work_dir, f"shot_{i:02d}.mp4")
        prepare_shot(src, d, f, kind, start)
        files.append(f)
        durs.append(b - a)

    ass = build_ass(words, hook, total, os.path.join(work_dir, "captions.ass"))
    ass_esc = ass.replace("\\", "/").replace(":", "\\:")
    fonts_opt = ""
    if os.path.isdir(FONTS_DIR):
        fonts_opt = ":fontsdir='" + FONTS_DIR.replace("\\", "/").replace(":", "\\:") + "'"

    inputs = []
    for f in files:
        inputs += ["-i", f]
    vi = len(files)
    inputs += ["-i", voice_path]
    music = music_path or _pick_music()
    if music:
        inputs += ["-stream_loop", "-1", "-i", music]

    fc = []
    # 1) chaine de transitions
    last, offset = "[0:v]", 0.0
    for i in range(1, len(files)):
        offset += durs[i - 1]
        tr = random.choice(TRANSITIONS)
        lab = f"[x{i}]"
        fc.append(f"{last}[{i}:v]xfade=transition={tr}:duration={XFADE}:offset={offset:.3f}{lab}")
        last = lab
    # 2) barre de progression + sous-titres/accroche
    fc.append(f"color=c=0xFFD400:s={W}x12:r={FPS}:d={total:.3f}[bar]")
    fc.append(f"{last}[bar]overlay=x='-w+w*t/{total:.3f}':y=0:eof_action=pass[vb]")
    fc.append(f"[vb]ass='{ass_esc}'{fonts_opt},format=yuv420p[vout]")
    # 3) audio : voix + musique qui s'efface sous la voix + whoosh a chaque coupe
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    fc.append(f"[{vi}:a]{fmt},asplit=2[voice][sc]")
    mix = ["[voice]"]
    if music:
        fc.append(f"[{vi + 1}:a]{fmt},volume=0.32,afade=t=in:d=0.6[mus]")
        fc.append("[mus][sc]sidechaincompress=threshold=0.025:ratio=9:attack=15:release=320[duck]")
        mix.append("[duck]")
    else:
        fc.append("[sc]anullsink")
    n_cuts = len(files) - 1
    if n_cuts:
        fc.append(f"anoisesrc=d=0.45:c=pink:r=44100:a=0.6,highpass=f=350,lowpass=f=5500,"
                  f"afade=t=in:d=0.16,afade=t=out:st=0.16:d=0.29,volume=0.20,{fmt},asplit={n_cuts}"
                  + "".join(f"[w{i}]" for i in range(n_cuts)))
        off = 0.0
        for i in range(n_cuts):
            off += durs[i]
            ms = max(0, int((off - 0.12) * 1000))
            fc.append(f"[w{i}]adelay={ms}|{ms}[wd{i}]")
            mix.append(f"[wd{i}]")
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
              f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[aout]")

    _run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
          "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path])
    return out_path


def _pick_music() -> str | None:
    import glob
    tracks = sorted(glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3")))
    return random.choice(tracks) if tracks else None
