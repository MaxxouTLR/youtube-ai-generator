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

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_credentials():
    creds = None
    if os.path.exists(config.YOUTUBE_TOKEN_FILE):
        with open(config.YOUTUBE_TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
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
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"Video publiee: https://youtu.be/{video_id}")
    return video_id


def set_thumbnail(video_id: str, thumbnail_path: str) -> None:
    """Definit la miniature personnalisee. Necessite un compte YouTube verifie par telephone
    (limite imposee par YouTube, pas par ce script) — leve une exception explicite sinon."""
    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python youtube_uploader.py <video.mp4> [titre]")
        raise SystemExit(1)
    video_path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else "Automatically generated video"
    upload_video(video_path, title, "Automatically generated.", tags=["motivation", "self improvement"])
