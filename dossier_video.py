"""Shorts d'histoire en style "dossier" (motion design pixel/LED rouge et noir, cf. motion/dossier.html).

Entree : une liste de "beats" (un moment de narration chacun) :
    {"say": "texte lu par la voix",
     "title": "phrase a l'ecran, *mots en rouge*",       (optionnel)
     "led": "1518",          gros chiffre/mot en matrice de points (optionnel)
     "led_sub": "habitants", legende sous le chiffre (optionnel)
     "icon": "💃",           emoji converti en pixel art rouge (optionnel)
     "stamp": "STRASBOURG",  tampon incline (optionnel)
     "array": {"icon": "💃", "n": 34},  compteur d'icones qui se remplit (optionnel)
     "strike": 1.2,          barre le chiffre LED apres 1,2 s (optionnel)
     "sub": "texte gris",    petite ligne (optionnel)
     "flash": true,          flash rouge a l'ouverture du beat (optionnel)
     "img": "assets/archives/<sujet>/x.jpg"}  photo d'archive au centre, remplace icone/LED (optionnel)
Le texte lu (say) et le texte affiche sont separes : a l'ecran, seulement la phrase-cle ou le chiffre-cle.
"""
import base64
import json
import os
import re
import subprocess

import config
import dossier_audio
import motion_video

ENGINE = os.path.join(config.BASE_DIR, "motion", "dossier.html")


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def time_beats(beats: list[dict], words: list[dict], total: float) -> list[dict]:
    """Cale chaque beat sur la voix : on consomme dans les timings mot par mot autant de mots que le beat en contient."""
    toks = [w for w in sorted(words, key=lambda w: w["offset"]) if _norm(w["text"])]
    i = 0
    for b in beats:
        n = len([w for w in b["say"].split() if _norm(w)])
        b["start"] = 0.0 if b is beats[0] else (toks[min(i, len(toks) - 1)]["offset"] / 1e7 - 0.08 if toks else 0)
        i += n
    for k, b in enumerate(beats):
        b["end"] = beats[k + 1]["start"] if k + 1 < len(beats) else total
    return beats


def render(beats: list[dict], total: float, out_path: str, num: int | None = None, words: list[dict] | None = None) -> str:
    # words : timings mot par mot de la voix, pour les sous-titres karaoke (t = debut, e = fin, en secondes)
    caps = [{"w": w["text"], "t": w["offset"] / 1e7, "e": (w["offset"] + w.get("duration", 0)) / 1e7}
            for w in sorted(words or [], key=lambda w: w["offset"]) if _norm(w["text"])]
    # photos d'archive (champ "img", chemin relatif au depot) : integrees en data URI, la page est chargee par set_content
    images = {}
    for b in beats:
        if b.get("img") and b["img"] not in images:
            with open(os.path.join(config.BASE_DIR, b["img"]), "rb") as f:
                images[b["img"]] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    data = {"duration": total, "beats": beats, "num": num, "words": caps, "images": images}
    from playwright.sync_api import sync_playwright
    html = open(ENGINE, encoding="utf-8").read().replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    n = int(round(total * motion_video.FPS))
    ff = subprocess.Popen([motion_video.FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(motion_video.FPS),
                           "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                           out_path], stdin=subprocess.PIPE)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--disable-gpu"])
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            page.set_content(html)
            page.wait_for_function("window.ready === true")
            for k in range(n):
                page.evaluate(f"render({k / motion_video.FPS:.4f})")
                ff.stdin.write(page.locator("#c").screenshot(type="jpeg", quality=93))
            browser.close()
    finally:
        ff.stdin.close()
        ff.wait()
    return out_path


def make_short(voice_path: str, words: list[dict], beats: list[dict], out_path: str, work_dir: str,
               num: int | None = None) -> str:
    os.makedirs(work_dir, exist_ok=True)
    total = motion_video._probe_duration(voice_path)
    beats = time_beats(beats, words, total)
    with open(os.path.join(work_dir, "beats.json"), "w", encoding="utf-8") as f:
        json.dump(beats, f, ensure_ascii=False, indent=1)
    silent = render(beats, total, os.path.join(work_dir, "video.mp4"), num, words)
    # habillage sonore dedie (25/10/2026) : nappe de suspense, impacts, montees, tampons, voix traitee
    audio = dossier_audio.mix(voice_path, beats, total, os.path.join(work_dir, "audio.m4a"), work_dir, num)
    r = subprocess.run([motion_video.FFMPEG, "-y", "-i", silent, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy",
                        "-shortest", "-movflags", "+faststart", out_path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg mux : " + r.stderr[-400:])
    return out_path
