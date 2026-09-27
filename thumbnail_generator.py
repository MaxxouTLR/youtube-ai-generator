"""Genere une miniature YouTube pour chaque video.

Fond : une image cinematique generee par IA (Pollinations.ai, gratuit, sans cle), avec un prompt
adapte au sujet exact de la video (via Ollama) pour un rendu personnalise et coherent avec l'identite
visuelle de la chaine (palette orange/bleu nuit, silhouette sans visage, cf. channel_branding.py).
Si la generation IA echoue (reseau, timeout...), on retombe sur une frame extraite de la video
elle-meme (methode precedente) pour ne jamais bloquer la publication.

Texte : accroche courte, un mot-cle fort mis en surbrillance dans la couleur de marque, contour
epais + ombre portee pour rester lisible sur fond varie et en petite taille (mobile)."""
import os
import random
import re
import subprocess
import textwrap
import urllib.parse
import urllib.request

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from script_generator import _call_ollama

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720
FONT_PATH = r"C:\Windows\Fonts\impact.ttf"
FONT_PATH_FALLBACK = r"C:\Windows\Fonts\arialbd.ttf"
# Ni l'un ni l'autre n'existe sur un runner Linux (GitHub Actions) - dernier recours
# installe via apt (paquet fonts-dejavu-core, present sur les images Ubuntu standard).
FONT_PATH_LINUX_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BRAND_ACCENT = (255, 122, 26)  # orange de marque, coherent avec channel_branding.py

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true"

THUMBNAIL_PROMPT_TEMPLATE = """You create background image prompts for YouTube thumbnails of a faceless
motivation / self-improvement channel.

Video topic: "{topic}"

Write ONE short image-generation prompt (max 25 words, English) for a cinematic, dramatic background
photo related to this topic specifically. Rules:
- Either a faceless silhouette of a person (never a visible face) OR a powerful symbolic landscape/object.
- Warm orange and deep navy blue color palette, epic scale, dramatic lighting, premium cinematic look.
- No text, no logo, no watermark in the image.
Reply with ONLY the prompt, nothing else."""

FALLBACK_BACKGROUND_PROMPTS = [
    "cinematic silhouette of a person standing on a mountain summit at sunrise, epic scale, warm "
    "orange and deep navy blue gradient sky, dramatic lighting, no text, no watermark",
    "cinematic silhouette of a person walking alone on an empty road toward a bright horizon at dawn, "
    "warm orange and deep navy blue palette, epic scale, no text, no watermark",
    "cinematic silhouette of a person climbing a steep rocky cliff against a dramatic sky, warm orange "
    "and deep navy blue palette, epic scale, no text, no watermark",
    "cinematic close-up of a clenched fist against a stormy dramatic sky, warm orange and deep navy "
    "blue palette, epic scale, no text, no watermark",
]

POWER_WORDS = {
    "never", "always", "stop", "will", "must", "now", "today", "change", "truth",
    "secret", "mistake", "discipline", "pain", "fear", "proof", "wrong", "real",
    "nobody", "everyone", "hard", "win", "lose", "why", "how",
}


def _extract_frame(video_path: str, out_path: str, at_fraction: float = 0.35) -> str:
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    probe = subprocess.run(
        [ffmpeg_bin, "-i", video_path], capture_output=True, text=True
    )
    duration = 10.0
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            duration = int(h) * 3600 + int(m) * 60 + float(s)
            break

    timestamp = max(1.0, duration * at_fraction)
    cmd = [
        ffmpeg_bin, "-y", "-ss", str(timestamp), "-i", video_path,
        "-frames:v", "1", "-q:v", "2", out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _generate_background_prompt(topic: str) -> str:
    try:
        raw = _call_ollama(THUMBNAIL_PROMPT_TEMPLATE.format(topic=topic[:200]))
        prompt = raw.strip().splitlines()[0].strip().strip('."\'')
        if prompt:
            return prompt[:200]
    except Exception:
        pass
    return random.choice(FALLBACK_BACKGROUND_PROMPTS)


def _generate_ai_background(topic: str, out_path: str) -> str:
    """Fond de miniature genere par IA, adapte au sujet. Leve une exception si ca echoue
    (reseau/timeout) - l'appelant retombe alors sur une frame video."""
    prompt = _generate_background_prompt(topic)
    seed = random.randint(1, 999_999)
    # Demande une image plus grande que necessaire : malgre nologo=true, Pollinations laisse parfois
    # un filigrane en bas-droite. On recadre ce coin a l'affichage (meme technique que la banniere
    # de chaine dans channel_branding.py).
    url = POLLINATIONS_URL.format(
        prompt=urllib.parse.quote(prompt), w=1568, h=882, seed=seed
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as resp, open(out_path, "wb") as f:
        f.write(resp.read())
    # Verifie que c'est bien une image exploitable (Pollinations peut renvoyer une erreur en JPEG factice)
    Image.open(out_path).verify()
    return out_path


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_path: str, max_width: int, start_size: int) -> ImageFont.FreeTypeFont:
    size = start_size
    while size > 30:
        font = ImageFont.truetype(font_path, size)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 4
    return ImageFont.truetype(font_path, 30)


def _draw_word_outlined(draw, xy, word, font, fill, outline_width=8):
    x, y = xy
    for dx in range(-outline_width, outline_width + 1, 2):
        for dy in range(-outline_width, outline_width + 1, 2):
            if dx * dx + dy * dy <= outline_width * outline_width:
                draw.text((x + dx, y + dy), word, font=font, fill=(0, 0, 0))
    # Ombre portee legere pour du relief supplementaire meme sur fond clair
    draw.text((x + 4, y + 6), word, font=font, fill=(0, 0, 0, 120))
    draw.text(xy, word, font=font, fill=fill)


def _pick_highlight_word(words: list[str]) -> int:
    for i, w in enumerate(words):
        if re.sub(r"[^a-zA-Z]", "", w).lower() in POWER_WORDS:
            return i
    return len(words) - 1  # a defaut, le dernier mot (souvent le plus percutant a l'oral)


def generate_thumbnail(video_path: str, hook_text: str, out_path: str, topic: str | None = None) -> str:
    tmp_bg = out_path + "_bg.jpg"

    used_ai_background = False
    if topic:
        try:
            _generate_ai_background(topic, tmp_bg)
            used_ai_background = True
        except Exception as exc:
            print(f"    [warn] Fond IA de la miniature indisponible ({exc}), frame video utilisee a la place.")

    if not used_ai_background:
        _extract_frame(video_path, tmp_bg)

    img = Image.open(tmp_bg).convert("RGB")
    if used_ai_background:
        # Recadre depuis le coin haut-gauche pour exclure le filigrane pollinations.ai (bas-droite).
        scale = max(THUMB_WIDTH / img.width, THUMB_HEIGHT / img.height) * 1.15
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
        img = img.crop((0, 0, THUMB_WIDTH, THUMB_HEIGHT))
    else:
        img = img.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.LANCZOS)

    # Rendu plus "premium" : legerement plus contraste/sature, avant l'assombrissement du bas.
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.15)

    # Assombrit le bas de l'image pour que le texte ressorte, sans cacher toute la scene.
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(overlay)
    for i in range(THUMB_HEIGHT // 2):
        alpha = int(160 * (i / (THUMB_HEIGHT / 2)))
        grad_draw.line([(0, THUMB_HEIGHT - i), (THUMB_WIDTH, THUMB_HEIGHT - i)], fill=(0, 0, 0, alpha))
    # Vignette legere sur les bords pour concentrer le regard au centre.
    for i in range(80):
        alpha = int(70 * (1 - i / 80))
        grad_draw.rectangle([i, i, THUMB_WIDTH - i, THUMB_HEIGHT - i], outline=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    text = textwrap.fill(hook_text.upper(), width=18)
    if os.path.exists(FONT_PATH):
        font_path = FONT_PATH
    elif os.path.exists(FONT_PATH_FALLBACK):
        font_path = FONT_PATH_FALLBACK
    else:
        font_path = FONT_PATH_LINUX_FALLBACK
    font = _fit_font(draw, text, font_path, max_width=THUMB_WIDTH - 120, start_size=110)

    lines = text.split("\n")
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
    text_h_total = bbox[3] - bbox[1]
    line_h = text_h_total / len(lines)
    y = THUMB_HEIGHT - text_h_total - 70

    all_words = [w for line in lines for w in line.split()]
    highlight_idx = _pick_highlight_word(all_words)
    word_counter = 0

    for line in lines:
        words = line.split()
        widths = [draw.textlength(w + " ", font=font) for w in words]
        space_w = draw.textlength(" ", font=font)
        line_w = sum(widths) - space_w
        x = (THUMB_WIDTH - line_w) / 2
        for w in words:
            color = BRAND_ACCENT if word_counter == highlight_idx else (255, 255, 255)
            _draw_word_outlined(draw, (x, y), w, font, fill=color, outline_width=8)
            x += draw.textlength(w + " ", font=font)
            word_counter += 1
        y += line_h

    # Bande de marque en bas, coherente sur toutes les miniatures quel que soit le fond.
    draw.rectangle([0, THUMB_HEIGHT - 10, THUMB_WIDTH, THUMB_HEIGHT], fill=BRAND_ACCENT)

    img.save(out_path, quality=94)
    try:
        os.remove(tmp_bg)
    except OSError:
        pass
    return out_path


def make_hook_text(title: str, max_words: int = 6) -> str:
    """Reduit le titre a une accroche courte et percutante pour la miniature."""
    words = title.replace("?", "").replace("!", "").split()
    return " ".join(words[:max_words])


if __name__ == "__main__":
    import sys
    video_path = sys.argv[1] if len(sys.argv) > 1 else None
    hook = sys.argv[2] if len(sys.argv) > 2 else "YOU WON'T BELIEVE THIS"
    topic_arg = sys.argv[3] if len(sys.argv) > 3 else None
    if not video_path:
        print("Usage: python thumbnail_generator.py <video.mp4> [hook text] [topic]")
        raise SystemExit(1)
    out = generate_thumbnail(video_path, hook, os.path.splitext(video_path)[0] + "_thumb.jpg", topic=topic_arg)
    print(f"Miniature -> {out}")
