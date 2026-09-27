"""Configuration centrale du pipeline de generation video IA."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SCRIPTS_DIR = os.path.join(OUTPUT_DIR, "scripts")
AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")
VIDEO_DIR = os.path.join(OUTPUT_DIR, "video")  # fichiers de travail intermediaires
STOCK_DIR = os.path.join(BASE_DIR, "assets", "stock")
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")

# Dossier unique et facile d'acces regroupant toutes les videos finies, nommees d'apres leur sujet.
# Sur le disque 2To (D:) pour ne pas remplir le disque systeme avec des videos qui s'accumulent chaque jour.
# Surchargeable via env var : sur un runner GitHub Actions, D:\ n'existe pas et la video est de toute
# facon deja publiee sur YouTube a la fin du run (le workflow pointe vers un dossier jetable du runner).
PUBLISHED_DIR = os.environ.get("PUBLISHED_DIR", r"D:\YouTube Videos")

# --- Generation de script (Ollama local, gratuit, sans cle API) ---
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

# --- Voix off (edge-tts, gratuit, sans compte) ---
# Script en anglais pour toucher l'audience internationale (marche pub plus grand, meilleur RPM).
# Voix "Multilingual" = generation plus recente et expressive que les neural classiques.
TTS_VOICE = "en-US-AndrewMultilingualNeural"   # masculin, "Warm/Confident" - alt: en-US-GuyNeural ("Passion")
TTS_RATE = "+12%"   # rythme plus soutenu, moins plat, plus "YouTube"

SCRIPT_LANGUAGE = "en"

# --- Visuels (Pexels API, gratuit avec cle API a creer sur pexels.com/api) ---
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_SEARCH_TERMS = [
    "nature landscape", "sunrise mountains", "ocean waves", "forest walk",
    "city timelapse", "person walking path", "clouds sky", "stars night sky",
]

# --- Video ---
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
TARGET_MINUTES_MIN = 15  # duree cible du format long (plage, variee chaque jour)
TARGET_MINUTES_MAX = 20
TARGET_MINUTES = 17  # valeur par defaut si --minutes non precise et hors tirage aleatoire
SECONDS_PER_CLIP = 90  # duree visee par clip stock affiche (plus la video est longue, plus on varie les visuels)
MAX_STOCK_CLIPS = 25

# --- Format Shorts (portrait, video courte) ---
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_TARGET_SECONDS = 50   # duree visee (marge de securite sous la limite Shorts)
SHORTS_MAX_SECONDS = 59      # au-dela, YouTube ne garantit plus le classement "Shorts" classique
SHORTS_WORDS_PER_SEGMENT = 15  # segments courts -> coupes visuelles frequentes malgre la duree reduite
SHORTS_MIN_SEGMENT_SECONDS = 2.5  # segments plus courts que ca sont fusionnes au voisin (evite le clignotement)

# --- Musique de fond (generee localement, gratuite, zero risque de droits d'auteur) ---
MUSIC_ENABLED = True
MUSIC_VOLUME = 0.08  # tres discret : ne doit jamais gener la comprehension de la voix off

# --- Sous-titres ---
# Nom de la police tel qu'enregistre dans le systeme (libass/fontconfig la resout par nom, pas par
# chemin). "Arial Black" est preinstallee sur Windows. Sur un runner Linux (GitHub Actions), cette
# police n'existe pas : le workflow installe une police de remplacement et surcharge cette variable.
SUBTITLE_FONT_NAME = os.environ.get("SUBTITLE_FONT_NAME", "Arial Black")

# --- Chaine / niche ---
NICHE = "motivation et developpement personnel"

# --- YouTube upload (necessite client_secret.json, voir README) ---
YOUTUBE_CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
YOUTUBE_TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
YOUTUBE_CATEGORY_ID = "22"  # People & Blogs
YOUTUBE_PRIVACY_STATUS = "public"  # active le 24/09/2026 apres validation de la bonne chaine
