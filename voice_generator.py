"""Genere la voix off a partir du script via Azure Cognitive Services Speech.

Remplace edge-tts le 12/10/2026 : edge-tts detourne la fonction "Lire a voix haute" d'Edge (jamais
prevue pour l'automatisation) et a commence a etre bloque par Microsoft (403 WSServerHandshakeError
sur speech.platform.bing.com) specifiquement sur les IP de datacenter/cloud, dont les runners GitHub
Actions - confirme non temporaire par un run de test le meme jour. Azure Speech expose les MEMES
voix neurales (Andrew/Guy/Christopher/Brian) via une API officiellement supportee pour ce genre
d'usage, avec un tier gratuit (Free F0, ~500k caracteres/mois) largement suffisant pour ce volume.
Necessite les variables d'environnement AZURE_SPEECH_KEY et AZURE_SPEECH_REGION.
"""
import json
import os
import random
import xml.sax.saxutils as saxutils

import azure.cognitiveservices.speech as speechsdk

import config


def _pick_voice() -> tuple[str, str]:
    """Tire une (voix, rythme) au hasard dans config.TTS_VOICE_POOL, pondere pour garder la voix
    principale dominante. Un choix par appel = une seule voix pour toute la duree d'UNE video
    (coherence narrative), mais pas la meme voix a chaque video."""
    choice = random.choices(
        config.TTS_VOICE_POOL, weights=[v["weight"] for v in config.TTS_VOICE_POOL], k=1
    )[0]
    return choice["voice"], choice["rate"]


def _build_ssml(text: str, voice: str, rate: str) -> str:
    escaped = saxutils.escape(text)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{voice}"><prosody rate="{rate}">{escaped}</prosody></voice>'
        "</speak>"
    )


def _speech_config() -> speechsdk.SpeechConfig:
    speech_config = speechsdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"],
        region=os.environ["AZURE_SPEECH_REGION"],
    )
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz96KBitRateMonoMp3
    )
    return speech_config


def _raise_if_failed(result: speechsdk.SpeechSynthesisResult) -> None:
    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.SpeechSynthesisCancellationDetails(result)
        raise RuntimeError(f"Azure Speech synthesis annulee : {details.reason} - {details.error_details}")


def _synthesize(text: str, out_path: str, voice: str, rate: str) -> None:
    audio_config = speechsdk.audio.AudioOutputConfig(filename=out_path)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=_speech_config(), audio_config=audio_config)
    result = synthesizer.speak_ssml_async(_build_ssml(text, voice, rate)).get()
    _raise_if_failed(result)


def generate_voice(text: str, out_path: str | None = None) -> str:
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    voice, rate = _pick_voice()
    _synthesize(text, out_path, voice, rate)
    return out_path


def _synthesize_with_timing(text: str, out_path: str, voice: str, rate: str) -> list[dict]:
    word_boundaries: list[dict] = []

    audio_config = speechsdk.audio.AudioOutputConfig(filename=out_path)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=_speech_config(), audio_config=audio_config)

    def _on_word_boundary(evt: speechsdk.SpeechSynthesisWordBoundaryEventArgs) -> None:
        word_boundaries.append({
            "text": evt.text,
            "offset": evt.audio_offset,  # deja en ticks (100ns), meme unite que l'ancien edge-tts
            "duration": int(evt.duration.total_seconds() * 10_000_000),  # timedelta -> ticks (100ns)
        })

    synthesizer.synthesis_word_boundary.connect(_on_word_boundary)
    result = synthesizer.speak_ssml_async(_build_ssml(text, voice, rate)).get()
    _raise_if_failed(result)
    return word_boundaries


def generate_voice_with_timing(text: str, out_path: str | None = None, timing_path: str | None = None) -> tuple[str, str]:
    """Genere la voix off ET un fichier JSON des timings mot-par-mot (pour les sous-titres dynamiques)."""
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    timing_path = timing_path or f"{out_path}.words.json"
    voice, rate = _pick_voice()
    print(f"    Voix off : {voice} ({rate})")
    boundaries = _synthesize_with_timing(text, out_path, voice, rate)
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(boundaries, f, ensure_ascii=False)
    return out_path, timing_path


if __name__ == "__main__":
    import sys
    script_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not script_path:
        print("Usage: python voice_generator.py <chemin_script.txt>")
        raise SystemExit(1)
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Retire la ligne "SUJET: ..." si presente
    if content.startswith("SUJET:"):
        content = content.split("\n\n", 1)[1]
    out = generate_voice(content)
    print(f"Audio genere -> {out}")
