"""Genere les assets de marque de la chaine (nom, photo de profil, banniere) :
- nom : via Ollama (gratuit, local)
- visuels : via l'API gratuite et sans compte Pollinations.ai (generation d'image IA),
  puis composites/recadres avec Pillow pour un rendu propre (le watermark pollinations.ai
  tombe dans le coin qui sera recadre / masque).
"""
import os
import re
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from script_generator import _call_ollama

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true"

CHANNEL_NAME_PROMPT = """You run a faceless YouTube channel about motivation and self-improvement,
in English, targeting an international audience.

Suggest 8 short, catchy, memorable channel names (2-3 words max each). They should sound premium and
modern, NOT cheesy or generic. Avoid the words "Motivation" and "Success" if possible (overused).
Reply with ONLY a numbered list of 8 names, nothing else.
"""

FONT_PATH = r"C:\Windows\Fonts\impact.ttf"
FONT_PATH_FALLBACK = r"C:\Windows\Fonts\arialbd.ttf"


def generate_channel_name() -> list[str]:
    raw = _call_ollama(CHANNEL_NAME_PROMPT)
    names = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip().strip('."\'')
        if line:
            names.append(line)
    return names[:8] if names else ["Quiet Ascent"]


def _download_pollinations(prompt: str, width: int, height: int, seed: int, out_path: str) -> str:
    url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt), w=width, h=height, seed=seed)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(out_path, "wb") as f:
        f.write(resp.read())
    return out_path


def generate_profile_picture(out_path: str, seed: int = 42) -> str:
    """Photo de profil carree (YouTube la recadre en cercle : le watermark pollinations,
    place dans le coin, tombe hors du cercle et devient invisible)."""
    prompt = (
        "minimalist flat vector logo icon, mountain peak and rising sun, bold geometric shapes, "
        "orange and deep navy blue color palette, clean simple design, centered composition, "
        "no text, no watermark, icon for a motivation brand"
    )
    tmp = out_path + "_raw.jpg"
    _download_pollinations(prompt, 1024, 1024, seed, tmp)
    # Pollinations peut livrer une resolution plus faible que demandee : on force une taille fixe.
    img = Image.open(tmp).convert("RGB").resize((1024, 1024), Image.LANCZOS)
    img.save(out_path, quality=95)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return out_path


def generate_banner_background(out_path: str, seed: int = 7) -> str:
    prompt = (
        "cinematic wide landscape, silhouette of a person standing on a mountain summit at sunrise, "
        "epic scale, warm orange and deep blue gradient sky, minimalist, inspirational, no text"
    )
    # Genere plus large que necessaire pour pouvoir recadrer et exclure le watermark du coin.
    return _download_pollinations(prompt, 2688, 1512, seed, out_path)


def build_banner(channel_name: str, out_path: str, background_seed: int = 7) -> str:
    tmp_bg = out_path + "_bg.jpg"
    generate_banner_background(tmp_bg, seed=background_seed)

    bg = Image.open(tmp_bg).convert("RGB")
    # Pollinations plafonne parfois la resolution reellement livree en dessous de ce qui est demande :
    # on redimensionne toujours en "cover" (avec une marge) avant de recadrer, jamais l'inverse.
    target_w, target_h = 2560, 1440
    scale = max(target_w / bg.width, target_h / bg.height) * 1.15
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.LANCZOS)
    # Recadre au format banniere YouTube en partant du coin haut-gauche : le watermark pollinations
    # (bas-droite de l'image source) se retrouve dans la marge coupee et disparait.
    bg = bg.crop((0, 0, target_w, target_h))

    # Assombrit legerement la zone centrale "safe area" pour que le nom de chaine ressorte.
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    safe_top, safe_bottom = (1440 - 423) // 2, (1440 + 423) // 2
    draw_overlay.rectangle([0, safe_top - 40, 2560, safe_bottom + 40], fill=(0, 0, 0, 90))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)
    font_path = FONT_PATH if os.path.exists(FONT_PATH) else FONT_PATH_FALLBACK
    font = ImageFont.truetype(font_path, 140)
    text = channel_name.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((2560 - text_w) / 2, (1440 - text_h) / 2 - 30)

    outline_w = 6
    for dx in range(-outline_w, outline_w + 1, 2):
        for dy in range(-outline_w, outline_w + 1, 2):
            draw.text((pos[0] + dx, pos[1] + dy), text, font=font, fill=(0, 0, 0))
    draw.text(pos, text, font=font, fill=(255, 255, 255))

    bg.save(out_path, quality=95)
    try:
        os.remove(tmp_bg)
    except OSError:
        pass
    return out_path


PROFILE_PICTURE_PROMPTS = [
    "minimalist flat vector logo icon, mountain peak and rising sun, bold geometric shapes, "
    "orange and deep navy blue color palette, clean simple design, centered composition, "
    "no text, no watermark, icon for a motivation brand",
    "minimalist flat vector logo icon, an upward arrow merging into a flame, bold geometric shapes, "
    "orange and dark charcoal color palette, clean simple design, centered composition, "
    "no text, no watermark, icon for a motivation brand",
    "minimalist flat vector logo icon, single letter E monogram made of ascending steps, "
    "gold and deep navy blue color palette, clean modern design, centered composition, "
    "no text besides the letter, no watermark, icon for a premium motivation brand",
    "minimalist flat vector logo icon, abstract phoenix wing rising, bold geometric shapes, "
    "deep red and black color palette, clean simple design, centered composition, "
    "no text, no watermark, icon for a motivation brand",
]

BANNER_PROMPTS = [
    "cinematic wide landscape, silhouette of a person standing on a mountain summit at sunrise, "
    "epic scale, warm orange and deep blue gradient sky, minimalist, inspirational, no text",
    "cinematic wide landscape, lone figure walking on an empty road toward a bright horizon at dawn, "
    "epic scale, warm gold and deep purple gradient sky, minimalist, inspirational, no text",
    "cinematic wide landscape, silhouette of a person climbing a steep rocky cliff, dramatic clouds, "
    "epic scale, deep orange and charcoal color palette, minimalist, inspirational, no text",
    "cinematic wide landscape, silhouette of a person with arms raised on top of a hill at sunrise, "
    "epic scale, warm orange and navy gradient sky, minimalist, inspirational, no text",
]

CHANNEL_DESCRIPTION_PROMPT = """You run a faceless YouTube channel called "{channel_name}" about motivation
and self-improvement, in English, targeting an international audience, posting daily long-form videos
(15-20 minutes) about discipline, resilience, habits and personal growth.

Write the "About" section for this YouTube channel: 3 short paragraphs (upload schedule, what viewers will
get, a call to subscribe). Plain text, no markdown, no hashtags.
"""


def generate_channel_description(channel_name: str) -> str:
    try:
        return _call_ollama(CHANNEL_DESCRIPTION_PROMPT.format(channel_name=channel_name)).strip()
    except Exception:
        return (
            f"Welcome to {channel_name}. New videos every day on discipline, resilience and personal growth. "
            "Subscribe for daily motivation that actually helps you change."
        )


def generate_profile_picture_variants(out_dir: str, count: int = 4) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i in range(min(count, len(PROFILE_PICTURE_PROMPTS))):
        tmp = os.path.join(out_dir, f"_raw_{i}.jpg")
        _download_pollinations(PROFILE_PICTURE_PROMPTS[i], 1024, 1024, seed=100 + i, out_path=tmp)
        img = Image.open(tmp).convert("RGB").resize((1024, 1024), Image.LANCZOS)
        out_path = os.path.join(out_dir, f"profile_picture_{i + 1}.jpg")
        img.save(out_path, quality=95)
        os.remove(tmp)
        paths.append(out_path)
    return paths


def generate_banner_variants(channel_name: str, out_dir: str, count: int = 4) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i in range(min(count, len(BANNER_PROMPTS))):
        out_path = os.path.join(out_dir, f"banner_{i + 1}.jpg")
        _build_banner_from_prompt(BANNER_PROMPTS[i], channel_name, out_path, seed=200 + i)
        paths.append(out_path)
    return paths


def _build_banner_from_prompt(prompt: str, channel_name: str, out_path: str, seed: int) -> str:
    tmp_bg = out_path + "_bg.jpg"
    _download_pollinations(prompt, 2688, 1512, seed, tmp_bg)

    bg = Image.open(tmp_bg).convert("RGB")
    target_w, target_h = 2560, 1440
    scale = max(target_w / bg.width, target_h / bg.height) * 1.15
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.LANCZOS)
    bg = bg.crop((0, 0, target_w, target_h))

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    safe_top, safe_bottom = (1440 - 423) // 2, (1440 + 423) // 2
    draw_overlay.rectangle([0, safe_top - 40, 2560, safe_bottom + 40], fill=(0, 0, 0, 90))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)
    font_path = FONT_PATH if os.path.exists(FONT_PATH) else FONT_PATH_FALLBACK
    font = ImageFont.truetype(font_path, 140)
    text = channel_name.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((2560 - text_w) / 2, (1440 - text_h) / 2 - 30)

    outline_w = 6
    for dx in range(-outline_w, outline_w + 1, 2):
        for dy in range(-outline_w, outline_w + 1, 2):
            draw.text((pos[0] + dx, pos[1] + dy), text, font=font, fill=(0, 0, 0))
    draw.text(pos, text, font=font, fill=(255, 255, 255))

    bg.save(out_path, quality=95)
    os.remove(tmp_bg)
    return out_path


if __name__ == "__main__":
    out_dir = os.path.join(config.BASE_DIR, "branding")
    os.makedirs(out_dir, exist_ok=True)

    names = generate_channel_name()
    print("Suggestions de noms de chaine :")
    for n in names:
        print(f"  - {n}")

    pfp_path = generate_profile_picture(os.path.join(out_dir, "profile_picture.jpg"))
    print(f"Photo de profil -> {pfp_path}")

    banner_path = build_banner(names[0], os.path.join(out_dir, "banner.jpg"))
    print(f"Banniere -> {banner_path}")
