"""Genere la voix off a partir du script via edge-tts (gratuit, sans compte)."""
import asyncio
import json
import os
import edge_tts
import config


async def _synthesize(text: str, out_path: str, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    await communicate.save(out_path)


def generate_voice(text: str, out_path: str | None = None) -> str:
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    asyncio.run(_synthesize(text, out_path, config.TTS_VOICE, config.TTS_RATE))
    return out_path


async def _synthesize_with_timing(text: str, out_path: str, voice: str, rate: str) -> list[dict]:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, boundary="WordBoundary")
    word_boundaries = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append({
                    "text": chunk["text"],
                    "offset": chunk["offset"],     # ticks 100ns
                    "duration": chunk["duration"], # ticks 100ns
                })
    return word_boundaries


def generate_voice_with_timing(text: str, out_path: str | None = None, timing_path: str | None = None) -> tuple[str, str]:
    """Genere la voix off ET un fichier JSON des timings mot-par-mot (pour les sous-titres dynamiques)."""
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    timing_path = timing_path or f"{out_path}.words.json"
    boundaries = asyncio.run(_synthesize_with_timing(text, out_path, config.TTS_VOICE, config.TTS_RATE))
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
