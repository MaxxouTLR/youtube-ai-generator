"""Shorts en motion design (animations codees, plus de clips stock) : une scene animee par phrase.

Chaque image est calculee par motion/engine.html (HTML/CSS/canvas, fonction pure du temps), capturee par
un Chromium sans fenetre (Playwright) a 30 i/s et assemblee par ffmpeg avec la voix, une musique qui
s'efface sous la voix (ducking), un "whoosh" a chaque changement de scene et un volume normalise.

Types de scenes, choisis selon le contenu de la phrase :
  kinetic  - les mots jaillissent au rythme de la voix, mot-cle surligne
  emoji    - emoji geant qui rebondit + ondes, texte dessous
  slam     - le mot-cle percute l'ecran (tremblement, decalage de couleurs)
  counter  - un nombre cite s'affiche en compteur anime
  split    - "X but Y" : la 1re partie se fait barrer quand le mot pivot est prononce
  question - grand "?" en fond pour les questions
"""
import json
import os
import random
import re
import subprocess

import imageio_ffmpeg

import config

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = config.VIDEO_FPS
ENGINE = os.path.join(config.BASE_DIR, "motion", "engine.html")

PALETTES = [  # fond sombre + accent vif : lisible et "pop" sur mobile
    {"bg1": "#0b1026", "bg2": "#1b0b3a", "accent": "#FFD400", "accent2": "#00E5FF", "ink": "#111", "speak": "#FFE97A",
     "bad": "#ff3b5c", "blob1": "rgba(124,58,237,.55)", "blob2": "rgba(0,229,255,.35)", "blob3": "rgba(255,46,99,.30)", "grid": "rgba(255,255,255,.05)"},
    {"bg1": "#06201c", "bg2": "#0a0f1e", "accent": "#3DFFA2", "accent2": "#FF4FD8", "ink": "#06231a", "speak": "#B9FFE0",
     "bad": "#ff4f6d", "blob1": "rgba(61,255,162,.35)", "blob2": "rgba(255,79,216,.30)", "blob3": "rgba(0,140,255,.35)", "grid": "rgba(255,255,255,.05)"},
    {"bg1": "#1f0a06", "bg2": "#2a0b2e", "accent": "#FF7A1A", "accent2": "#FFE14D", "ink": "#1d0a00", "speak": "#FFD2A8",
     "bad": "#ff2e63", "blob1": "rgba(255,122,26,.45)", "blob2": "rgba(255,46,99,.35)", "blob3": "rgba(120,60,255,.35)", "grid": "rgba(255,255,255,.05)"},
    {"bg1": "#020617", "bg2": "#0f172a", "accent": "#38BDF8", "accent2": "#F472B6", "ink": "#04121c", "speak": "#BAE6FD",
     "bad": "#fb7185", "blob1": "rgba(56,189,248,.40)", "blob2": "rgba(244,114,182,.30)", "blob3": "rgba(250,204,21,.22)", "grid": "rgba(255,255,255,.045)"},
]

STOP = set("""a an the and or but so to of in on at for with from by is are was were be been being am i you your yours
he she it we they them his her its our their my me us this that these those there here what which who whom whose
when where why how not no do does did don't doesn't can can't will would should could just than then very really
too also only into out up down over about as if because while all any some more most much many one ever even
it's you're i'm that's what's let's get got have has had""".split())

POWER = set("""fail failure quit win success brain habit habits fear money rich discipline focus dream goal goals
confidence lazy energy time truth secret mistake power control pain growth change life future stop start ready
motivation proof wins power broke focus anxiety stress love alone happy happiness mindset""".split())

EMOJI = [  # (racine du mot, emoji) : premiere correspondance trouvee dans la phrase
    ("brain", "🧠"), ("mind", "🧠"), ("think", "🤔"), ("idea", "💡"), ("money", "💰"), ("rich", "💰"), ("cash", "💵"),
    ("broke", "💸"), ("time", "⏰"), ("clock", "⏰"), ("minute", "⏱️"), ("day", "📅"), ("week", "📅"), ("calendar", "📅"),
    ("habit", "🔁"), ("routine", "🔁"), ("goal", "🎯"), ("target", "🎯"), ("focus", "🎯"), ("win", "🏆"), ("success", "🏆"),
    ("champion", "🏆"), ("fail", "💥"), ("mistake", "❌"), ("wrong", "❌"), ("quit", "🏳️"), ("give up", "🏳️"),
    ("fear", "😨"), ("scared", "😨"), ("anxiety", "😰"), ("stress", "😰"), ("tired", "😴"), ("sleep", "😴"),
    ("lazy", "🦥"), ("energy", "⚡"), ("power", "⚡"), ("fire", "🔥"), ("motivat", "🔥"), ("burn", "🔥"),
    ("grow", "🌱"), ("seed", "🌱"), ("small", "🧩"), ("step", "👣"), ("walk", "🚶"), ("run", "🏃"), ("work", "💼"),
    ("job", "💼"), ("boss", "👔"), ("phone", "📱"), ("scroll", "📱"), ("social", "📱"), ("book", "📚"), ("read", "📚"),
    ("learn", "📚"), ("school", "🎓"), ("love", "❤️"), ("heart", "❤️"), ("friend", "🤝"), ("people", "👥"),
    ("alone", "🚶"), ("lonely", "🌧️"), ("sad", "🌧️"), ("happy", "😄"), ("smile", "😄"), ("laugh", "😂"),
    ("strong", "💪"), ("discipline", "💪"), ("gym", "🏋️"), ("body", "💪"), ("health", "🍎"), ("eat", "🍎"),
    ("food", "🍔"), ("dream", "✨"), ("magic", "✨"), ("future", "🚀"), ("launch", "🚀"), ("start", "🚀"),
    ("stop", "🛑"), ("wait", "⏳"), ("patience", "⏳"), ("slow", "🐢"), ("fast", "🐇"), ("key", "🔑"),
    ("secret", "🤫"), ("truth", "💯"), ("lie", "🤥"), ("question", "❓"), ("why", "❓"), ("path", "🛤️"),
    ("road", "🛤️"), ("mountain", "⛰️"), ("climb", "🧗"), ("top", "⛰️"), ("wall", "🧱"), ("build", "🏗️"),
    ("stack", "🧱"), ("lock", "🔒"), ("free", "🕊️"), ("peace", "🕊️"), ("light", "💡"), ("dark", "🌑"),
    ("night", "🌙"), ("morning", "🌅"), ("sun", "☀️"), ("world", "🌍"), ("eye", "👀"), ("see", "👀"),
    ("watch", "👀"), ("listen", "👂"), ("voice", "🗣️"), ("talk", "🗣️"), ("compare", "⚖️"), ("choice", "🔀"),
    ("change", "🔄"), ("new you", "🦋"), ("transform", "🦋"), ("proof", "📈"), ("progress", "📈"), ("result", "📈"),
    ("chance", "🎲"), ("luck", "🍀"), ("game", "🎮"), ("pain", "🩹"), ("hurt", "🩹"), ("comfort", "🛋️"),
    ("couch", "🛋️"), ("plan", "🗺️"), ("map", "🗺️"), ("child", "🧒"), ("kid", "🧒"), ("parent", "👪"), ("family", "👪"),
]
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "fifty": 50,
             "hundred": 100, "thousand": 1000, "million": 1000000}


def _alnum(w: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", w))


def _sentences(words: list[dict], total: float) -> list[dict]:
    """Groupe les mots (timings Azure, ponctuation incluse comme jetons separes) en phrases courtes."""
    toks = sorted(words, key=lambda w: w["offset"])
    out, cur, end_mark = [], [], ""
    for i, w in enumerate(toks):
        txt = w["text"].strip()
        s, e = w["offset"] / 1e7, (w["offset"] + w["duration"]) / 1e7
        if not _alnum(txt):
            if re.search(r"[.!?]", txt) and cur:
                out.append((cur, txt[-1]))
                cur = []
            continue
        mark = txt[-1] if txt[-1] in ".!?" else ""
        cur.append({"w": re.sub(r"[^\w'%$-]", "", txt), "s": s, "e": e})
        nxt = next((x for x in toks[i + 1:] if _alnum(x["text"])), None)
        gap = (nxt["offset"] / 1e7 - e) if nxt else 9
        if mark or gap > 0.45 or (len(cur) >= 8 and gap > 0.12) or len(cur) >= 10:
            out.append((cur, mark))
            cur = []
    if cur:
        out.append((cur, ""))
    return [{"words": ws, "mark": m} for ws, m in out if ws]


def _emph(ws: list[dict]) -> int:
    cands = [(j, w["w"].lower()) for j, w in enumerate(ws) if w["w"].lower() not in STOP]
    if not cands:
        return max(range(len(ws)), key=lambda j: len(ws[j]["w"]))
    for j, w in cands:
        if w in POWER or w.rstrip("s") in POWER:
            return j
    return max(cands, key=lambda c: len(c[1]))[0]


def _number(ws: list[dict]):
    for w in ws:
        t = w["w"].lower()
        m = re.match(r"^\$?(\d[\d,]*)(%?)$", t)
        if m:
            return int(m.group(1).replace(",", "")), m.group(2)
        if t in NUM_WORDS and t != "one":
            return NUM_WORDS[t], ""
    return None


def _emoji(text: str, used: set):
    t = text.lower()
    for root, e in EMOJI:
        if re.search(r"\b" + re.escape(root), t) and e not in used:
            return e
    return None


def build_scenes(words: list[dict], total: float, hook: str, seed: int | None = None) -> dict:
    seed = seed if seed is not None else random.randint(1, 10 ** 6)
    rnd = random.Random(seed)
    sents = _sentences(words, total)
    scenes, used_emoji, prev = [], set(), ""
    for i, s in enumerate(sents):
        ws = s["words"]
        text = " ".join(w["w"] for w in ws)
        emph = _emph(ws)
        num = _number(ws)
        low = [w["w"].lower() for w in ws]
        pivot = next((j for j, w in enumerate(low) if w in ("but", "instead") and 1 < j < len(ws) - 1), None)
        emo = _emoji(text, used_emoji)
        if num and prev != "counter":
            kind = "counter"
        elif pivot is not None and prev != "split":
            kind = "split"
        elif s["mark"] == "?" and prev != "question":
            kind = "question"
        elif emo and prev != "emoji" and rnd.random() < 0.75:
            kind = "emoji"
        elif prev != "slam" and len(ws[emph]["w"]) <= 11 and rnd.random() < 0.55:
            kind = "slam"
        else:
            kind = "kinetic" if prev != "kinetic" else ("emoji" if emo else "slam")
        if kind == "emoji" and not emo:
            kind = "kinetic"
        if kind == "emoji":
            used_emoji.add(emo)
        sc = {"type": kind, "words": ws, "emph": emph, "start": 0.0 if i == 0 else max(0.0, ws[0]["s"] - 0.12)}
        if kind == "counter":
            sc["number"], sc["suffix"] = num
        if kind == "split":
            sc["pivot"] = pivot
        if kind == "emoji":
            sc["emoji"] = emo
        scenes.append(sc)
        prev = kind
    for i, sc in enumerate(scenes):
        sc["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else total
    hook = re.sub(r"#\w+", "", hook or "").strip()
    return {"duration": total, "seed": seed, "palette": rnd.choice(PALETTES), "hook": hook, "scenes": scenes}


# ---------- rendu ----------

def _probe_duration(path: str) -> float:
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def render_frames(data: dict, out_path: str) -> str:
    from playwright.sync_api import sync_playwright

    html = open(ENGINE, encoding="utf-8").read().replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    n = int(round(data["duration"] * FPS))
    ff = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg",
                           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", out_path],
                          stdin=subprocess.PIPE)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--disable-gpu", "--font-render-hinting=none"])
            page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
            page.set_content(html)
            page.wait_for_function("window.ready === true")
            page.evaluate("document.fonts.ready.then(() => 1)")
            for k in range(n):
                page.evaluate(f"render({k / FPS:.4f})")
                ff.stdin.write(page.screenshot(type="jpeg", quality=93))
            browser.close()
    finally:
        ff.stdin.close()
        ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg : encodage des images echoue")
    return out_path


def mix_audio(voice: str, cuts: list[float], total: float, out_path: str, music: str | None = None) -> str:
    """Voix + musique en ducking + whoosh a chaque changement de scene, normalise a -18 LUFS
    (21/10/2026 : -14 LUFS jugé trop fort par l'utilisateur ; musique et whoosh baissés aussi)."""
    import glob
    if music is None:
        tracks = sorted(glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3")))
        music = random.choice(tracks) if tracks else None
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    inputs = ["-i", voice] + (["-stream_loop", "-1", "-i", music] if music else [])
    fc = [f"[0:a]{fmt},asplit=2[voice][sc]"]
    mix = ["[voice]"]
    if music:
        fc += [f"[1:a]{fmt},volume=0.22,afade=t=in:d=0.5[mus]",
               "[mus][sc]sidechaincompress=threshold=0.025:ratio=9:attack=15:release=320[duck]"]
        mix.append("[duck]")
    else:
        fc.append("[sc]anullsink")
    if cuts:
        fc.append(f"anoisesrc=d=0.45:c=pink:r=44100:a=0.6,highpass=f=350,lowpass=f=6000,afade=t=in:d=0.18,"
                  f"afade=t=out:st=0.18:d=0.27,volume=0.14,{fmt},asplit={len(cuts)}" + "".join(f"[w{i}]" for i in range(len(cuts))))
        for i, c in enumerate(cuts):
            ms = max(0, int((c - 0.2) * 1000))
            fc.append(f"[w{i}]adelay={ms}|{ms}[wd{i}]")
            mix.append(f"[wd{i}]")
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-18:TP=-2:LRA=11,aresample=44100[a]")
    r = subprocess.run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[a]", "-t", f"{total:.3f}",
                        "-c:a", "aac", "-b:a", "192k", out_path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg audio : " + r.stderr[-600:])
    return out_path


def make_short(voice_path: str, words: list[dict], hook: str, out_path: str, work_dir: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    total = _probe_duration(voice_path)
    data = build_scenes(words, total, hook)
    with open(os.path.join(work_dir, "scenes.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    silent = render_frames(data, os.path.join(work_dir, "video.mp4"))
    audio = mix_audio(voice_path, [s["start"] for s in data["scenes"][1:]], total, os.path.join(work_dir, "audio.m4a"))
    r = subprocess.run([FFMPEG, "-y", "-i", silent, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
                        "-shortest", "-movflags", "+faststart", out_path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg mux : " + r.stderr[-400:])
    return out_path
