"""Genere une musique de fond ambiante procedurale (nappes synthetiques douces).

Generee localement (aucun telechargement, aucune API) : zero risque de droits d'auteur, gratuit,
disponible hors-ligne. Chaque piste boucle parfaitement (les frequences sont calees sur des
multiples de 1/LOOP_SECONDS) pour etre repetee par ffmpeg sans coupure audible.
"""
import math
import os
import subprocess

import numpy as np
import imageio_ffmpeg

SAMPLE_RATE = 44100
LOOP_SECONDS = 60

# Quelques accords doux et lents (frequences en Hz : fondamentale grave + tierce/quinte + octave).
CHORDS = [
    [130.81, 164.81, 196.00, 261.63],   # Cmaj (C3 E3 G3 C4)
    [146.83, 174.61, 220.00, 293.66],   # Dm (D3 F3 A3 D4)
    [174.61, 220.00, 261.63, 349.23],   # F (F3 A3 C4 F4)
]


def _snap_to_loop(freq: float) -> float:
    """Arrondit une frequence au multiple de 1/LOOP_SECONDS le plus proche : le signal devient
    exactement periodique sur LOOP_SECONDS, donc bouclable sans clic ni coupure."""
    step = 1.0 / LOOP_SECONDS
    return round(freq / step) * step


def _generate_wave(chord: list[float], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * LOOP_SECONDS)
    t = np.arange(n) / SAMPLE_RATE
    wave = np.zeros(n)

    for freq in chord:
        f = _snap_to_loop(freq)
        phase = rng.uniform(0, 2 * math.pi)
        wave += np.sin(2 * math.pi * f * t + phase) / len(chord)
        # Octave superieure discrete, pour une texture "nappe" plutot qu'un simple accord plat.
        wave += 0.2 * np.sin(2 * math.pi * (2 * f) * t + phase) / len(chord)

    # Respiration lente du volume (LFO periodique lui aussi sur la boucle).
    lfo_freq = _snap_to_loop(1 / 8)
    lfo = 0.75 + 0.25 * np.sin(2 * math.pi * lfo_freq * t)
    wave *= lfo

    wave /= np.max(np.abs(wave)) + 1e-9
    return wave.astype(np.float32)


def generate_all(out_dir: str, force: bool = False) -> list[str]:
    """Genere les pistes ambiantes dans out_dir (une seule fois : ne regenere pas si deja presentes,
    sauf force=True)."""
    os.makedirs(out_dir, exist_ok=True)
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    paths = []

    for i, chord in enumerate(CHORDS):
        out_path = os.path.join(out_dir, f"ambient_{i}.mp3")
        if os.path.exists(out_path) and not force:
            paths.append(out_path)
            continue

        wave = _generate_wave(chord, seed=i)
        raw_path = os.path.join(out_dir, f"_ambient_{i}.raw")
        wave.tofile(raw_path)
        cmd = [
            ffmpeg_bin, "-y", "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-i", raw_path, "-b:a", "128k", out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        os.remove(raw_path)
        paths.append(out_path)

    return paths


if __name__ == "__main__":
    import config
    generated = generate_all(config.MUSIC_DIR, force=True)
    print(f"{len(generated)} piste(s) ambiante(s) generee(s) dans {config.MUSIC_DIR}")
