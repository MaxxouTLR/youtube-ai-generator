"""Convertit une histoire (histoires/<slug>.json, moteur v1) en plans pour le montage dynamique v2.

02/11/2026 : l'utilisateur valide le montage v2 cale sur « The Scooby Snacks » (Napoleon et les lapins) et demande
de preparer les prochains TikTok ainsi. Ce script donne un premier decoupage (~1 plan pour 3 mots) a partir des
champs v1 (img, icon, led, array, stamp, title *rouge*, flash) et des autres photos du dossier assets/archives/<slug>.
Le resultat est a relire (cadrages, choix d'images) avant rendu.

    python v2_convert.py <slug> [<slug> ...]      -> histoires/<slug>_v2.json
"""
import glob
import json
import os
import re
import sys

from PIL import Image

BPM = 175.75   # « The Scooby Snacks » (p3b3), mesure le 02/11/2026


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def _mode(path: str) -> str:
    """fond clair tout autour (gravure, objet detoure) -> "key" ; sinon fondu en ovale."""
    im = Image.open(path).convert("L")
    w, h = im.size
    px = [im.getpixel((x, y)) for x in range(0, w, max(1, w // 40)) for y in (2, h - 3)]
    px += [im.getpixel((x, y)) for y in range(0, h, max(1, h // 40)) for x in (2, w - 3)]
    return "key" if sum(p > 225 for p in px) / len(px) > 0.85 else "fade"


def _crop(path: str, k: int) -> list:
    im = Image.open(path)
    portrait = im.height >= im.width
    opts = [[.18, .04, .64, .5], [.25, .15, .5, .45]] if portrait else [[.2, .1, .6, .8], [.05, .2, .5, .7], [.45, .2, .5, .7]]
    return opts[k % len(opts)]


def _red(title: str) -> str | None:
    m = re.search(r"\*([^*]+)\*", title or "")
    return m.group(1).strip(" .?!…") if m else None


def convert(slug: str) -> dict:
    src = json.load(open(f"histoires/{slug}.json", encoding="utf-8"))
    pool = sorted(glob.glob(f"assets/archives/{slug}/*.jpg"))
    used_beat_imgs = {b["img"] for b in src["beats"] if b.get("img")}
    extra = [p.replace(os.sep, "/") for p in pool if p.replace(os.sep, "/") not in used_beat_imgs] or [p.replace(os.sep, "/") for p in pool]
    modes = {p.replace(os.sep, "/"): _mode(p) for p in pool}
    pi, ci = 0, 0
    out_beats = []
    nb = len(src["beats"])
    for bi, b in enumerate(src["beats"]):
        words = [w for w in b["say"].split() if _norm(w)]
        n = max(1, min(6, round(len(words) / 3)))
        red = _red(b.get("title"))
        flash = bool(b.get("flash")) and bi > 0
        if bi == nb - 1:   # Abonne-toi
            out_beats.append({"say": b["say"], "shots": [{"text": "*Abonne-toi.*", "bg": "red"}]}); continue
        if bi == nb - 2:   # question finale
            img = b.get("img") or extra[pi % len(extra)] if extra else None
            sh = {"text": b.get("title", "").strip() or "Et toi ?"}
            if img:
                sh.update(img=img, mode=modes.get(img, "fade"), rings=True)
            out_beats.append({"say": b["say"], "shots": [sh]}); continue
        prim = []
        if b.get("img"):
            prim.append({"img": b["img"], "mode": modes.get(b["img"], "fade"), "label": b.get("img_label"), "focus": bi == 0})
        if b.get("led"):
            prim.append({"led": "*" + b["led"] + "*"})
        if b.get("array"):
            prim.append({"array": b["array"]})
        if b.get("icon"):
            prim.append({"icon": b["icon"], "rings": True})
        if not prim:
            prim.append({"text": b.get("title") or "…", "bg": "red" if flash else None, "hit": flash})
        if flash:
            prim[0].update(bg="red", hit=True)
        fill = []
        if b.get("img"):
            fill.append({"img": b["img"], "mode": modes.get(b["img"], "fade"), "crop": _crop(b["img"], ci), "rings": ci % 2 == 0}); ci += 1
        if red and not any(s.get("text") for s in prim):
            fill.append({"text": "*" + red + "*", "bg": "red", "hit": True, "_red": red})
        while len(prim) + len(fill) < n and extra:
            img = extra[pi % len(extra)]; pi += 1
            sh = {"img": img, "mode": modes.get(img, "fade"), "flip": pi % 2 == 0}
            if modes.get(img) != "key" and pi % 3 == 0:
                sh["crop"] = _crop(img, pi)
            fill.append(sh)
            if len(fill) > 6:
                break
        shots = (prim + fill)[:max(n, len(prim))]
        # repartition sur les mots ; le plan "mot rouge" tombe sur ce mot
        for k, sh in enumerate(shots[1:], 1):
            j = min(len(words) - 1, round(k * len(words) / len(shots)))
            sh["on"] = words[j]
            if sh.get("_red"):   # mot le plus long du passage rouge, compare sur 4 lettres (accords, pluriels)
                for rw in sorted(sh["_red"].split(), key=len, reverse=True):
                    key = _norm(rw)[:4]
                    hit = next((w for w in words if len(key) >= 3 and _norm(w).startswith(key)), None)
                    if hit:
                        sh["on"] = hit; break
        # ordre chronologique des "on" (le plan rouge peut tomber plus tot)
        if len(shots) > 1:
            pos = {id(s): next((i for i, w in enumerate(words) if w == s["on"]), 0) for s in shots[1:]}
            shots = shots[:1] + sorted(shots[1:], key=lambda s: pos[id(s)])
        if b.get("stamp"):
            (shots[1] if len(shots) > 1 else shots[0])["stamp"] = b["stamp"].upper()
        for s in shots:
            s.pop("_red", None)
            for k in [k for k, v in s.items() if v in (None, False)]:
                s.pop(k)
        out_beats.append({"say": b["say"], "shots": shots})
    return {"slug": slug + "_v2", "num": src.get("num"), "source": src.get("source"), "caption": src["caption"],
            "note": "Montage dynamique v2 (v2_convert.py, 02/11/2026) : coupes sur le tempo de « The Scooby Snacks », voix seule. "
                    "A publier depuis TikTok avec le son, demarre sur un kick.",
            "bpm": BPM, "nappe": False, "bruitages": False, "beats": out_beats}


if __name__ == "__main__":
    for s in sys.argv[1:]:
        d = convert(s)
        json.dump(d, open(f"histoires/{s}_v2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(s, sum(len(b["shots"]) for b in d["beats"]), "plans")
