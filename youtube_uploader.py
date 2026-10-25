"""Publie automatiquement la video sur YouTube via l'API officielle (gratuite).

Prerequis (gratuit, une seule fois) :
1. Aller sur https://console.cloud.google.com/ , creer un projet.
2. Activer "YouTube Data API v3".
3. Creer des identifiants OAuth (type "Application de bureau"), telecharger le JSON.
4. Enregistrer ce fichier sous : client_secret.json (a la racine du projet).
La premiere execution ouvrira une fenetre de connexion Google dans le navigateur.
"""
import os
import pickle
import config

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import net_retry

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# Nombre de reessais internes de googleapiclient (backoff exponentiel sur 5xx/429 et coupures reseau)
# par chunk d'upload : un upload coupe a 90% reprend la ou il en etait au lieu de tout relancer.
API_NUM_RETRIES = 5


def _is_non_interactive() -> bool:
    """Sur GitHub Actions (ou tout CI), personne ne peut cliquer dans une fenetre de connexion Google :
    run_local_server attendrait jusqu'au timeout du job (5h) au lieu d'echouer clairement."""
    return bool(os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"))


def _load_token():
    if not os.path.exists(config.YOUTUBE_TOKEN_FILE):
        return None
    try:
        with open(config.YOUTUBE_TOKEN_FILE, "rb") as f:
            return pickle.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"{config.YOUTUBE_TOKEN_FILE} illisible ({type(exc).__name__}). Sur GitHub Actions, le secret "
            "YOUTUBE_TOKEN_B64 est probablement vide ou mal encode : regenere token.json en local "
            "(python youtube_uploader.py une fois) puis `base64 -w0 token.json` dans le secret."
        ) from exc


def _refresh(creds) -> None:
    try:
        net_retry.with_retry(
            lambda: creds.refresh(Request()), what="rafraichissement du token YouTube", attempts=3,
            retry_on=lambda exc: isinstance(exc, TransportError),
        )
    except RefreshError as exc:
        raise RuntimeError(
            f"Token YouTube refuse par Google ({exc}). Le refresh token a expire ou ete revoque "
            "(frequent si l'app OAuth est en mode 'Test' : expiration apres 7 jours). Supprime token.json, "
            "relance `python youtube_uploader.py` en local pour te reconnecter, puis mets a jour le secret "
            "YOUTUBE_TOKEN_B64."
        ) from exc


def _get_credentials():
    creds = _load_token()

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            _refresh(creds)
        else:
            if _is_non_interactive():
                raise RuntimeError(
                    "Aucun token YouTube valide et connexion interactive impossible ici (CI). "
                    "Verifie le secret YOUTUBE_TOKEN_B64 (token.json genere en local, encode en base64)."
                )
            if not os.path.exists(config.YOUTUBE_CLIENT_SECRET_FILE):
                raise RuntimeError(
                    f"Fichier manquant: {config.YOUTUBE_CLIENT_SECRET_FILE}. "
                    "Voir les instructions en haut de youtube_uploader.py."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(config.YOUTUBE_TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return creds


def _explain_http_error(exc: HttpError, action: str) -> RuntimeError:
    status = getattr(exc.resp, "status", "?")
    reason = exc.reason if hasattr(exc, "reason") else str(exc)
    hint = ""
    if "quotaExceeded" in str(exc) or "uploadLimitExceeded" in str(exc):
        hint = " Quota YouTube Data API (ou limite d'uploads du jour) atteint : reessaie demain."
    elif status == 401:
        hint = " Token invalide : regenere token.json et le secret YOUTUBE_TOKEN_B64."
    return RuntimeError(f"{action} refuse par YouTube (HTTP {status}) : {reason}.{hint}")


def upload_video(video_path: str, title: str, description: str, tags: list[str] | None = None) -> str:
    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": config.YOUTUBE_CATEGORY_ID,
            "defaultLanguage": config.SCRIPT_LANGUAGE,
            "defaultAudioLanguage": config.SCRIPT_LANGUAGE,
        },
        "status": {
            "privacyStatus": config.YOUTUBE_PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    try:
        while response is None:
            status, response = request.next_chunk(num_retries=API_NUM_RETRIES)
            if status:
                print(f"Upload: {int(status.progress() * 100)}%")
    except HttpError as exc:
        raise _explain_http_error(exc, "Upload de la video") from exc

    video_id = response["id"]
    print(f"Video publiee: https://youtu.be/{video_id}")
    return video_id


def set_thumbnail(video_id: str, thumbnail_path: str) -> None:
    """Definit la miniature personnalisee. Necessite un compte YouTube verifie par telephone
    (limite imposee par YouTube, pas par ce script) — leve une exception explicite sinon."""
    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute(num_retries=API_NUM_RETRIES)
    except HttpError as exc:
        raise _explain_http_error(exc, "Miniature") from exc


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python youtube_uploader.py <video.mp4> [titre]")
        raise SystemExit(1)
    video_path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else "Automatically generated video"
    upload_video(video_path, title, "Automatically generated.", tags=["motivation", "self improvement"])
