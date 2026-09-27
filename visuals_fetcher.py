"""Recupere des videos stock libres de droits via l'API Pexels (gratuite).

Necessite une cle API gratuite : https://www.pexels.com/api/  (inscription gratuite, aucun cout)
A definir dans la variable d'environnement PEXELS_API_KEY.
"""
import os
import random
import urllib.request
import urllib.parse
import json
import config


def _search_videos(query: str, per_page: int = 5, orientation: str = "landscape") -> list[dict]:
    if not config.PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY manquante. Cree une cle gratuite sur pexels.com/api "
            "puis: setx PEXELS_API_KEY \"ta_cle\""
        )
    url = (f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}"
           f"&per_page={per_page}&orientation={orientation}")
    req = urllib.request.Request(url, headers={
        "Authorization": config.PEXELS_API_KEY,
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("videos", [])


def _best_file(video: dict) -> str | None:
    # max(width, height) plutot que width seul : en portrait la plus grande dimension est la hauteur.
    files = sorted(
        [f for f in video.get("video_files", []) if max(f.get("width") or 0, f.get("height") or 0) >= 1280],
        key=lambda f: max(f["width"], f["height"]),
    )
    return files[0]["link"] if files else None


def fetch_clips(count: int, out_dir: str | None = None, orientation: str = "landscape") -> list[str]:
    """Telecharge `count` clips stock repartis sur les termes de recherche configures."""
    out_dir = out_dir or config.STOCK_DIR
    os.makedirs(out_dir, exist_ok=True)

    paths = []
    terms = config.PEXELS_SEARCH_TERMS.copy()
    random.shuffle(terms)
    attempts = 0
    term_idx = 0

    while len(paths) < count and attempts < count * 3:
        attempts += 1
        term = terms[term_idx % len(terms)]
        term_idx += 1
        try:
            videos = _search_videos(term, per_page=5, orientation=orientation)
        except Exception as exc:
            print(f"[warn] recherche '{term}' echouee: {exc}")
            continue
        if not videos:
            continue
        video = random.choice(videos)
        link = _best_file(video)
        if not link:
            continue
        dest = os.path.join(out_dir, f"clip_{len(paths):03d}.mp4")
        try:
            dl_req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(dl_req, timeout=60) as resp, open(dest, "wb") as out_f:
                out_f.write(resp.read())
            paths.append(dest)
            print(f"[ok] {term} -> {dest}")
        except Exception as exc:
            print(f"[warn] telechargement echoue: {exc}")

    return paths


def fetch_one_clip(query: str, dest_path: str, orientation: str = "landscape") -> str | None:
    """Telecharge UN clip pertinent pour `query`, avec repli sur les termes generiques si rien trouve."""
    terms_to_try = [query] + random.sample(config.PEXELS_SEARCH_TERMS, len(config.PEXELS_SEARCH_TERMS))

    for term in terms_to_try:
        try:
            videos = _search_videos(term, per_page=5, orientation=orientation)
        except Exception as exc:
            print(f"[warn] recherche '{term}' echouee: {exc}")
            continue
        if not videos:
            continue
        video = random.choice(videos)
        link = _best_file(video)
        if not link:
            continue
        try:
            dl_req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(dl_req, timeout=60) as resp, open(dest_path, "wb") as out_f:
                out_f.write(resp.read())
            print(f"[ok] '{term}' -> {dest_path}")
            return dest_path
        except Exception as exc:
            print(f"[warn] telechargement echoue: {exc}")
            continue
    return None


if __name__ == "__main__":
    clips = fetch_clips(8)
    print(f"{len(clips)} clips telecharges dans {config.STOCK_DIR}")
