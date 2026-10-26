"""Photos d'archive libres pour les dossiers (champ "img" des beats, cf. dossier_video.py).

26/10/2026 : la video test Onoda (photo des l'image 0) retient nettement mieux que les versions texte sur fond noir.
Source unique : Wikimedia Commons, licences libres seulement (domaine public, CC0, CC BY, CC BY-SA),
credits ecrits dans assets/archives/<slug>/CREDITS.md (obligatoires pour CC BY / CC BY-SA).

    python archives.py search "Napoleon portrait" ["autre recherche" ...]   candidats : titre, taille, licence
    python archives.py get <slug> <nom.jpg> "File:Titre exact.jpg"          telecharge (1400 px max) + credit
"""
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

import config

API = "https://commons.wikimedia.org/w/api.php?"
HEADERS = {"User-Agent": "dossiers-histoire/1.0 (https://github.com/MaxxouTLR/youtube-ai-generator)"}
FREE = ("public domain", "pd", "cc0", "cc by", "cc-by", "no restrictions", "attribution")


def _api(**params) -> dict:
    params.update(format="json", action="query")
    req = urllib.request.Request(API + urllib.parse.urlencode(params), headers=HEADERS)
    return json.load(urllib.request.urlopen(req, timeout=30))


def _license(meta: dict) -> str:
    return meta.get("LicenseShortName", {}).get("value", "?")


def search(query: str, n: int = 10) -> list[dict]:
    r = _api(generator="search", gsrsearch=query + " filetype:bitmap", gsrnamespace=6, gsrlimit=n,
             prop="imageinfo", iiprop="size|extmetadata")
    out = []
    for p in (r.get("query", {}).get("pages") or {}).values():
        ii = p["imageinfo"][0]
        lic = _license(ii.get("extmetadata", {}))
        if lic.lower().startswith(FREE):
            out.append({"title": p["title"], "w": ii["width"], "h": ii["height"], "license": lic})
    return out


def get(slug: str, name: str, title: str) -> str:
    from PIL import Image
    r = _api(titles=title, prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=1400)
    ii = list(r["query"]["pages"].values())[0]["imageinfo"][0]
    meta = ii["extmetadata"]
    lic = _license(meta)
    if not lic.lower().startswith(FREE):
        raise SystemExit(f"Licence non libre ({lic}) : {title}")
    data = urllib.request.urlopen(urllib.request.Request(ii.get("thumburl") or ii["url"], headers=HEADERS), timeout=60).read()
    folder = os.path.join(config.BASE_DIR, "assets", "archives", slug)
    os.makedirs(folder, exist_ok=True)
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((1400, 1400))
    path = os.path.join(folder, name)
    im.save(path, quality=86)
    artist = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", "?"))).strip()
    cred = os.path.join(folder, "CREDITS.md")
    lines = open(cred, encoding="utf-8").read().splitlines() if os.path.exists(cred) else ["# Crédits images (Wikimedia Commons)", ""]
    lines = [l for l in lines if not l.startswith(f"- {name} :")] + [f"- {name} : {title[5:]} — {artist} — {lic} — {ii['descriptionurl']}"]
    open(cred, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return f"assets/archives/{slug}/{name}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "search":
        for q in sys.argv[2:]:
            print("==", q)
            for c in search(q):
                print(f"  {c['title']}  {c['w']}x{c['h']}  {c['license']}")
    elif len(sys.argv) == 5 and sys.argv[1] == "get":
        print(get(*sys.argv[2:]))
    else:
        print(__doc__)
