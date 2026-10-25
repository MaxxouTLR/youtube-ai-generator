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
import subprocess
import xml.sax.saxutils as saxutils

import azure.cognitiveservices.speech as speechsdk
import imageio_ffmpeg

import config
import net_retry

TICKS_PER_SECOND = 10_000_000


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
    hint = "Cle et region se trouvent dans le portail Azure, ressource Speech > Keys and Endpoint."
    speech_config = speechsdk.SpeechConfig(
        subscription=net_retry.require_env("AZURE_SPEECH_KEY", hint),
        region=net_retry.require_env("AZURE_SPEECH_REGION", hint),
    )
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz96KBitRateMonoMp3
    )
    return speech_config


class SpeechSynthesisError(RuntimeError):
    def __init__(self, message: str, transient: bool):
        super().__init__(message)
        self.transient = transient


# Erreurs Azure passageres (quota/seconde du tier F0, coupure reseau, service surcharge) : on reessaie.
# AuthenticationFailure/Forbidden/BadRequest ne se corrigeront pas toutes seules : echec immediat.
_TRANSIENT_CANCELLATION_CODES = {"TooManyRequests", "ConnectionFailure", "ServiceTimeout",
                                 "ServiceError", "ServiceUnavailable", "ServiceRedirectTemporary"}


def _raise_if_failed(result: speechsdk.SpeechSynthesisResult) -> None:
    if result.reason == speechsdk.ResultReason.Canceled:
        details = speechsdk.SpeechSynthesisCancellationDetails(result)
        code = getattr(details.error_code, "name", str(details.error_code))
        message = f"Azure Speech synthesis annulee : {details.reason} / {code} - {details.error_details}"
        if code in ("AuthenticationFailure", "Forbidden"):
            message += (" -> verifie AZURE_SPEECH_KEY et AZURE_SPEECH_REGION (la cle doit correspondre a la"
                        " region de la ressource Speech)")
        raise SpeechSynthesisError(message, transient=code in _TRANSIENT_CANCELLATION_CODES)


def _is_transient_speech_error(exc: BaseException) -> bool:
    return isinstance(exc, SpeechSynthesisError) and exc.transient


def _synthesize(text: str, out_path: str, voice: str, rate: str) -> None:
    def _once():
        audio_config = speechsdk.audio.AudioOutputConfig(filename=out_path)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=_speech_config(), audio_config=audio_config)
        result = synthesizer.speak_ssml_async(_build_ssml(text, voice, rate)).get()
        _raise_if_failed(result)

    net_retry.with_retry(_once, what="synthese Azure Speech", attempts=4, base_delay=5,
                         retry_on=_is_transient_speech_error)


def generate_voice(text: str, out_path: str | None = None) -> str:
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    voice, rate = _pick_voice()
    _synthesize(text, out_path, voice, rate)
    return out_path


def _synthesize_with_timing(text: str, out_path: str, voice: str, rate: str) -> list[dict]:
    def _once() -> list[dict]:
        # Liste neuve a chaque essai : un essai interrompu ne doit pas laisser de timings fantomes.
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

    return net_retry.with_retry(_once, what="synthese Azure Speech", attempts=4, base_delay=5,
                                retry_on=_is_transient_speech_error)


def _trim_long_silences(audio_path: str, word_boundaries: list[dict], max_gap_seconds: float = 0.45) -> list[dict]:
    """Raccourcit a max_gap_seconds tout silence plus long entre deux mots consecutifs, en
    recoupant physiquement l'audio (ffmpeg atrim+concat) et en decalant les timings en consequence.
    Voix-agnostique : certaines voix (notamment les voix HD Azure pilotees par LLM, voir config.py)
    peuvent inserer des pauses dramatiques de plusieurs secondes - ce filet de securite s'applique
    quelle que soit la voix utilisee, sans dependre d'un reglage specifique a un moteur TTS."""
    max_gap_ticks = int(max_gap_seconds * TICKS_PER_SECOND)

    removed_ranges = []  # (debut, fin) en ticks, portions a retirer de l'audio d'origine
    for i in range(len(word_boundaries) - 1):
        cur_end = word_boundaries[i]["offset"] + word_boundaries[i]["duration"]
        next_start = word_boundaries[i + 1]["offset"]
        gap = next_start - cur_end
        if gap > max_gap_ticks:
            removed_ranges.append((cur_end + max_gap_ticks, next_start))

    if not removed_ranges:
        return word_boundaries

    from moviepy import AudioFileClip
    clip = AudioFileClip(audio_path)
    total_ticks = int(clip.duration * TICKS_PER_SECOND)
    clip.close()
    del clip
    import gc
    gc.collect()

    kept_segments = []  # (debut, fin) en secondes, portions a garder
    cursor = 0
    for start, end in removed_ranges:
        if start > cursor:
            kept_segments.append((cursor / TICKS_PER_SECOND, start / TICKS_PER_SECOND))
        cursor = end
    if cursor < total_ticks:
        kept_segments.append((cursor / TICKS_PER_SECOND, total_ticks / TICKS_PER_SECOND))

    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    filter_parts = [f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}]" for i, (s, e) in enumerate(kept_segments)]
    labels = "".join(f"[a{i}]" for i in range(len(kept_segments)))
    filter_complex = ";".join(filter_parts) + ";" + labels + f"concat=n={len(kept_segments)}:v=0:a=1[outa]"

    tmp_path = f"{audio_path}.trimmed.mp3"
    cmd = [ffmpeg_bin, "-y", "-i", audio_path, "-filter_complex", filter_complex, "-map", "[outa]", tmp_path]
    subprocess.run(cmd, check=True, capture_output=True)
    with open(tmp_path, "rb") as src, open(audio_path, "wb") as dst:
        dst.write(src.read())
    os.remove(tmp_path)

    new_boundaries = []
    for wb in word_boundaries:
        removed_before = sum(end - start for start, end in removed_ranges if end <= wb["offset"])
        new_boundaries.append({**wb, "offset": wb["offset"] - removed_before})
    return new_boundaries


def generate_voice_with_timing(text: str, out_path: str | None = None, timing_path: str | None = None) -> tuple[str, str]:
    """Genere la voix off ET un fichier JSON des timings mot-par-mot (pour les sous-titres dynamiques)."""
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    timing_path = timing_path or f"{out_path}.words.json"
    voice, rate = _pick_voice()
    print(f"    Voix off : {voice} ({rate})")
    boundaries = _synthesize_with_timing(text, out_path, voice, rate)
    boundaries = _trim_long_silences(out_path, boundaries)
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
