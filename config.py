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
# Delai max d'UN appel (une section de script sur CPU de runner peut prendre plusieurs minutes).
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "600"))
# Modeles de repli (deja telecharges via `ollama pull`) essayes dans l'ordre si OLLAMA_MODEL echoue
# (modele absent, erreurs serveur repetees). Vide par defaut -> aucun changement de comportement.
# Ex : OLLAMA_FALLBACK_MODELS="llama3.2:1b,qwen2.5:3b"
OLLAMA_FALLBACK_MODELS = [m.strip() for m in os.environ.get("OLLAMA_FALLBACK_MODELS", "").split(",") if m.strip()]

# --- Voix off (Azure Cognitive Services Speech, tier gratuit Free F0, ~500k caracteres/mois) ---
# Remplace edge-tts le 12/10/2026 (bloque par Microsoft sur les IP de datacenter/cloud dont GitHub
# Actions - voir voice_generator.py). Memes noms de voix neurales, l'API officielle les expose aussi.
# Script en anglais pour toucher l'audience internationale (marche pub plus grand, meilleur RPM).
# Essai des voix "HD" (DragonHDLatestNeural) le 12/10/2026 suite a un retour "pas assez naturel" -
# ANNULE le meme jour (retour utilisateur : pauses de plusieurs secondes entre certaines phrases,
# le LLM derriere ces voix HD decide lui-meme du rythme et insere des silences dramatiques pas
# toujours voulus - voir _trim_long_silences dans voice_generator.py, garde-fou ajoute independamment
# de ce choix de voix). Revenu ensuite (meme jour, demande explicite "les meme voix qu'il y avait
# sur les videos precedentes qui ont atteint plusieurs centaines de vues") a la configuration
# UNIQUE-VOIX d'avant le 27/09/2026 : seulement Andrew Multilingual, rate +12% (le defaut +0%
# sonnait "plat, aucun rythme" - retour utilisateur du 23/09/2026). La rotation a 4 voix introduite
# le 27/09/2026 (Guy/Christopher/Brian en plus) visait a reduire le risque de contenu percu comme
# "mass-produced/repetitive" par la politique de monetisation YouTube Partner Program - compromis
# explicitement abandonne ici au profit de la voix dont la performance est confirmee. A rediscuter
# avec l'utilisateur si ce risque YPP redevient une priorite.
TTS_VOICE_POOL = [
    {"voice": "en-US-AndrewMultilingualNeural", "rate": "+12%", "weight": 1},
]

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
SHORTS_TARGET_SECONDS = 20   # duree visee - reduit de 50 a 20 le 17/10/2026 : les Shorts qui ont le
# mieux performe historiquement (200 a 1000+ vues) duraient tous 11-26s, alors que ceux generes a la
# cible de 50s (37-51s en pratique) sont tombes a 0 vue des le 14/10/2026 - l'algorithme Shorts
# favorise nettement le format court/swipe rapide sur une petite chaine. Voir [[project_youtube_ai_generator]].
SHORTS_MAX_SECONDS = 59      # au-dela, YouTube ne garantit plus le classement "Shorts" classique
SHORTS_WORDS_PER_SEGMENT = 7   # 20/10/2026 : 15 -> 7, un clip different par phrase pour le montage dynamique (montage.py)
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

# --- Produits / affiliation (27/09/2026) ---
# Bloc optionnel insere en fin de description de CHAQUE video (avant les hashtags). Vide par defaut :
# n'a aucun effet tant que non rempli. Une fois un lien pret (produit vendu directement ou lien
# d'affiliation), le remplir ici applique le CTA automatiquement a toutes les prochaines videos, sans
# toucher au reste du pipeline. Exemple :
# PRODUCT_CTA = "Free discipline system + tracker: https://votre-lien-gumroad.com"
PRODUCT_CTA = "Want the full system? Get The Discipline Reset (ebook + weekly tracker): https://payhip.com/b/WZtyq"

# Version courte et parlable du CTA ci-dessus, ajoutee par script_generator.py a la toute fin du texte
# lu par la voix off (pas d'URL : une URL prononcee a voix haute est illisible/inutile a l'oral, le lien
# complet reste dans la description ecrite via PRODUCT_CTA). Vide par defaut -> aucun effet.
PRODUCT_CTA_SPOKEN = "If you want the full system, the link is in the description."

# --- YouTube upload (necessite client_secret.json, voir README) ---
YOUTUBE_CLIENT_SECRET_FILE = os.path.join(BASE_DIR, "client_secret.json")
YOUTUBE_TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
YOUTUBE_CATEGORY_ID = "22"  # People & Blogs
YOUTUBE_PRIVACY_STATUS = "public"  # active le 24/09/2026 apres validation de la bonne chaine
