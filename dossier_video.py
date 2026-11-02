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
# 02/11/2026 : montage "dynamique" (1 visuel toutes les ~0,6 s, cf. motion/dossier_v2.html), active par "shots" dans les beats
ENGINE_V2 = os.path.join(config.BASE_DIR, "motion", "dossier_v2.html")


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


def time_shots(beats: list[dict], words: list[dict], total: float, bpm: float | None = None) -> list[dict]:
    """Moteur v2 : chaque beat porte une liste "shots" (plans). Un plan commence sur le mot "on" (debut de mot,
    cherche dans le texte lu du beat apres le plan precedent) ; sans "on", les plans se repartissent le beat."""
    toks = [w for w in sorted(words, key=lambda w: w["offset"]) if _norm(w["text"])]
    starts = lambda i: toks[min(i, len(toks) - 1)]["offset"] / 1e7 if toks else 0.0
    shots, gi = [], 0
    for b in beats:
        bw = [_norm(w) for w in b["say"].split() if _norm(w)]
        plan = b.get("shots") or [{}]
        idx, last = [], 0
        for k, sh in enumerate(plan):
            if k == 0:
                idx.append(0); continue
            on = _norm(sh.get("on", ""))
            j = next((i for i in range(last + 1, len(bw)) if on and bw[i].startswith(on)), None)
            if j is None:
                j = min(len(bw) - 1, max(last + 1, round(k * len(bw) / len(plan))))
            idx.append(j); last = j
        for k, sh in enumerate(plan):
            x = {kk: v for kk, v in sh.items() if kk != "on"}
            x["start"] = 0.0 if (gi == 0 and k == 0) else max(0.0, starts(gi + idx[k]) - 0.06)
            shots.append(x)
        gi += len(bw)
    if bpm:   # 02/11/2026 : coupes calees sur le tempo du son TikTok (grille demarrant a t = 0)
        g = 60.0 / bpm
        for k, x in enumerate(shots):
            if k == 0:
                continue
            snap = round(x["start"] / g) * g
            prev = shots[k - 1]["start"]
            if snap <= prev + 1e-6:
                snap = prev + g
            x["start"] = min(snap, total - 0.05)
    for k, x in enumerate(shots):
        x["end"] = shots[k + 1]["start"] if k + 1 < len(shots) else total
    return shots


def render(beats: list[dict], total: float, out_path: str, num: int | None = None, words: list[dict] | None = None,
           bpm: float | None = None) -> str:
    # words : timings mot par mot de la voix, pour les sous-titres karaoke (t = debut, e = fin, en secondes)
    caps = [{"w": w["text"], "t": w["offset"] / 1e7, "e": (w["offset"] + w.get("duration", 0)) / 1e7}
            for w in sorted(words or [], key=lambda w: w["offset"]) if _norm(w["text"])]
    # photos d'archive (champ "img", chemin relatif au depot) : integrees en data URI, la page est chargee par set_content
    v2 = any(b.get("shots") for b in beats)
    shots = time_shots(beats, words or [], total, bpm) if v2 else []
    images = {}
    for b in (shots if v2 else beats):
        if b.get("img") and b["img"] not in images:
            with open(os.path.join(config.BASE_DIR, b["img"]), "rb") as f:
                images[b["img"]] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    data = {"duration": total, "beats": beats, "shots": shots, "bpm": bpm, "num": num, "words": caps, "images": images}
    from playwright.sync_api import sync_playwright
    html = open(ENGINE_V2 if v2 else ENGINE, encoding="utf-8").read().replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
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
               num: int | None = None, nappe: bool = True, sfx: bool = True, bpm: float | None = None) -> str:
    os.makedirs(work_dir, exist_ok=True)
    total = motion_video._probe_duration(voice_path)
    beats = time_beats(beats, words, total)
    with open(os.path.join(work_dir, "beats.json"), "w", encoding="utf-8") as f:
        json.dump(beats, f, ensure_ascii=False, indent=1)
    silent = render(beats, total, os.path.join(work_dir, "video.mp4"), num, words, bpm)
    # habillage sonore dedie (25/10/2026) : nappe de suspense, impacts, montees, tampons, voix traitee
    # moteur v2 : les bruitages suivent les plans (impact sur chaque aplat rouge / secousse, son de tampon)
    snd = beats
    if any(b.get("shots") for b in beats):
        snd = [{"start": x["start"], "end": x["end"], "flash": x.get("bg") == "red" or bool(x.get("hit")),
                "stamp": x.get("stamp"), "stamp_at": x.get("stamp_at", 0.12)} for x in time_shots(beats, words, total, bpm)]
    audio = dossier_audio.mix(voice_path, snd, total, os.path.join(work_dir, "audio.m4a"), work_dir, num,
                              bed_volume=0.16 if nappe else 0.0, sfx=sfx)
    r = subprocess.run([motion_video.FFMPEG, "-y", "-i", silent, "-i", audio, "-map", "0:v", "-map", "1:a", "-c", "copy",
                        "-shortest", "-movflags", "+faststart", out_path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg mux : " + r.stderr[-400:])
    return out_path
