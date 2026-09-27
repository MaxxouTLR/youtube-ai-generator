"""Backend TTS alternatif via ElevenLabs (palier gratuit tres limite : ~10 000 caracteres/mois).

A UTILISER PONCTUELLEMENT SEULEMENT (pas dans la tache quotidienne automatique) :
une seule video de 15-20 min consomme deja la quasi-totalite du quota gratuit mensuel.

Prerequis :
1. Compte gratuit sur https://elevenlabs.io/
2. Recuperer la cle API dans Profil -> API Keys.
3. setx ELEVENLABS_API_KEY "ta_cle"  (puis rouvrir le terminal)
"""
import os
import urllib.request
import json

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel", voix par defaut
ELEVENLABS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"


def generate_voice_elevenlabs(text: str, out_path: str) -> str:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY manquante. Cree un compte gratuit sur elevenlabs.io, "
            "recupere ta cle API, puis: setx ELEVENLABS_API_KEY \"ta_cle\""
        )

    if len(text) > 9000:
        raise RuntimeError(
            f"Texte trop long ({len(text)} caracteres) pour le palier gratuit ElevenLabs "
            "(~10 000 caracteres/mois au total). Reduis la duree de la video pour ce test."
        )

    payload = json.dumps({
        "text": text,
        "model_id": "eleven_turbo_v2_5",  # modele inclus dans le palier gratuit (multilingual_v2 = payant)
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True},
    }).encode("utf-8")

    req = urllib.request.Request(
        ELEVENLABS_URL, data=payload, method="POST",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        audio_bytes = resp.read()

    with open(out_path, "wb") as f:
        f.write(audio_bytes)
    return out_path


if __name__ == "__main__":
    import sys
    script_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not script_path:
        print("Usage: python voice_generator_elevenlabs.py <chemin_script.txt>")
        raise SystemExit(1)
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    if content.startswith("SUJET:"):
        content = content.split("\n\n", 1)[1]
    out = generate_voice_elevenlabs(content, "output/audio/voiceover_elevenlabs.mp3")
    print(f"Audio ElevenLabs genere -> {out}")
