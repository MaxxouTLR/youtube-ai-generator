"""Genere les musiques de fond (6 pistes) : de vrais morceaux instrumentaux, composes et synthetises ici.

20/11/2026 : remplace les anciennes nappes (accords tenus en sinus purs), percues comme un "bruit sourd"
par l'utilisateur. Chaque piste est maintenant un petit morceau "lo-fi / cinematique motivant" :
piano en arpege + nappe + basse, puis une 2e partie avec batterie douce et melodie. Toujours genere
localement (numpy + ffmpeg) : zero droit d'auteur, aucun telechargement.

Bouclage parfait : tous les filtres et la reverb sont appliques par FFT (convolution circulaire) et
les notes qui depassent la fin repartent au debut, donc la piste se repete sans coupure ni clic
(ffmpeg -stream_loop -1 dans le mixage).
"""
import os
import subprocess

import imageio_ffmpeg
import numpy as np

SR = 44100

# (nom, tempo, accords [(note MIDI fondamentale, "maj"/"min")], avec batterie en 2e partie)
TRACKS = [
    ("rise", 90, [(57, "min"), (53, "maj"), (48, "maj"), (55, "maj")], True),      # Am F C G
    ("bright", 100, [(48, "maj"), (55, "maj"), (57, "min"), (53, "maj")], True),   # C G Am F
    ("cinematic", 84, [(50, "min"), (46, "maj"), (53, "maj"), (48, "maj")], True), # Dm Bb F C
    ("drive", 96, [(52, "min"), (48, "maj"), (55, "maj"), (50, "maj")], True),     # Em C G D
    ("hope", 88, [(53, "maj"), (57, "min"), (46, "maj"), (48, "maj")], True),      # F Am Bb C
    ("calm", 80, [(55, "maj"), (50, "maj"), (52, "min"), (48, "maj")], False),     # G D Em C
]
BARS = 16  # 8 mesures calmes + 8 mesures avec batterie et melodie, en boucle


def _hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _add(buf: np.ndarray, start: int, sig: np.ndarray) -> None:
    """Ajoute sig a buf a partir de start, en repartant au debut si on depasse (boucle sans couture)."""
    n = len(buf)
    start %= n
    end = start + len(sig)
    if end <= n:
        buf[start:end] += sig
    else:
        k = n - start
        buf[start:] += sig[:k]
        _add(buf, 0, sig[k:])


def _piano(f: float, dur: float, vel: float = 1.0) -> np.ndarray:
    """Piano electrique/doux : harmoniques qui s'eteignent d'autant plus vite qu'elles sont aigues."""
    tail = dur + 1.2
    t = np.arange(int(tail * SR)) / SR
    s = np.zeros_like(t)
    for k in range(1, 9):
        fk = f * k * (1 + 0.0003 * k * k)
        if fk > 12000:
            break
        decay = (1.1 + 0.8 * k) * (f / 262) ** 0.25
        s += (1 / k ** 1.4) * np.sin(2 * np.pi * fk * t) * np.exp(-decay * t)
    s += 0.25 * np.sin(2 * np.pi * f * 1.003 * t) * np.exp(-1.4 * t)  # leger desaccord : chaleur
    env = np.minimum(1, t / 0.004)
    rel = np.clip((tail - t) / 0.08, 0, 1) * np.where(t > dur, np.exp(-(t - dur) * 5), 1)
    return vel * s * env * rel


def _pad(freqs: list[float], dur: float) -> np.ndarray:
    """Nappe : dents de scie desaccordees (adoucies ensuite par le passe-bas), attaque/relache lentes."""
    tail = dur + 1.5
    t = np.arange(int(tail * SR)) / SR
    s = np.zeros_like(t)
    for f in freqs:
        for det in (-0.004, 0.004):
            for k in range(1, 10):
                s += np.sin(2 * np.pi * f * (1 + det) * k * t + k) / k
    env = np.minimum(1, t / 1.2) * np.where(t > dur, np.exp(-(t - dur) * 2.5), 1)
    return s * env / (len(freqs) * 6)


def _bass(f: float, dur: float) -> np.ndarray:
    t = np.arange(int((dur + 0.3) * SR)) / SR
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    env = np.minimum(1, t / 0.01) * np.exp(-t * 1.6) * np.where(t > dur, np.exp(-(t - dur) * 20), 1)
    return s * env


def _kick() -> np.ndarray:
    t = np.arange(int(0.45 * SR)) / SR
    freq = 48 + 95 * np.exp(-t * 28)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * np.exp(-t * 7) * np.minimum(1, t / 0.002)


def _noise_hit(rng, length: float, decay: float) -> np.ndarray:
    t = np.arange(int(length * SR)) / SR
    return rng.standard_normal(len(t)) * np.exp(-t * decay)


def _fft_filter(x: np.ndarray, lo: float | None = None, hi: float | None = None, order: int = 2) -> np.ndarray:
    """Passe-haut/passe-bas par FFT (circulaire -> la boucle reste parfaite)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    h = np.ones_like(f)
    if hi:
        h /= np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        with np.errstate(divide="ignore"):
            h /= np.sqrt(1 + (lo / np.maximum(f, 1e-6)) ** (2 * order))
    return np.fft.irfft(X * h, n=len(x))


def _reverb(x: np.ndarray, rng, seconds: float = 2.2, wet: float = 0.28) -> np.ndarray:
    """Reverb par convolution avec une reponse impulsionnelle synthetique (bruit qui decroit)."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t * 6.9 / seconds)
    ir = _fft_filter(np.pad(ir, (0, len(x) - n)), hi=5000)  # reverb sombre, pas metallique
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    y = np.fft.irfft(np.fft.rfft(x) * np.fft.rfft(ir), n=len(x))
    return (1 - wet) * x + wet * y * 3


def _chord_notes(root: int, kind: str) -> list[int]:
    third = 3 if kind == "min" else 4
    return [root, root + third, root + 7]


def compose(index: int) -> np.ndarray:
    """Retourne la piste stereo (n, 2) float32 du morceau TRACKS[index]."""
    name, bpm, prog, drums = TRACKS[index]
    rng = np.random.default_rng(1000 + index)
    beat = 60 / bpm
    bar = 4 * beat
    n = int(round(BARS * bar * SR))
    piano, pad, bass, kick, snare, hats, melody = (np.zeros(n) for _ in range(7))
    arp = [[0, 1, 2, 3, 2, 1, 2, 3], [0, 2, 1, 3, 0, 2, 1, 3], [0, 1, 2, 1, 3, 1, 2, 1]][index % 3]
    mel_rhythm = [[0, 1.5, 3], [0, 2, 2.5, 3.5], [0.5, 1.5, 2.5], [0, 3]]

    for b in range(BARS):
        root, kind = prog[b % len(prog)]
        notes = _chord_notes(root, kind)
        t0 = int(round(b * bar * SR))
        section_b = b >= BARS // 2
        # nappe : accord complet tenu sur la mesure
        _add(pad, t0, _pad([_hz(m) for m in notes + [root + 12]], bar))
        # piano : arpege en croches (voicing autour du Do central)
        voicing = [notes[0] + 12, notes[1] + 12, notes[2] + 12, notes[0] + 24]
        for i, idx in enumerate(arp):
            vel = 0.85 if i % 2 == 0 else 0.6
            vel *= 1.0 + 0.05 * rng.standard_normal()
            _add(piano, t0 + int(i * beat / 2 * SR), _piano(_hz(voicing[idx]), beat / 2 * 1.6, vel))
        # basse : fondamentale sur les temps 1 et 3, petite anticipation en 2e partie
        bass_hits = [(0, 1.8), (2, 1.4)] + ([(3.5, 0.45)] if section_b else [])
        for pos, d in bass_hits:
            _add(bass, t0 + int(pos * beat * SR), _bass(_hz(root - 12 if root >= 48 else root), d * beat))
        # batterie douce (2e partie) : grosse caisse 1 et 3 (+ "et" du 3), caisse claire 2 et 4
        if drums and section_b:
            for pos in (0, 2, 2.5):
                _add(kick, t0 + int(pos * beat * SR), _kick())
            for pos in (1, 3):
                _add(snare, t0 + int(pos * beat * SR), _noise_hit(rng, 0.25, 18))
        # charleston en croches legerement swinguees (tout le morceau si pas de batterie)
        if section_b or not drums:
            for i in range(8):
                swing = 0.06 * beat if i % 2 else 0
                _add(hats, t0 + int((i * beat / 2 + swing) * SR),
                     _noise_hit(rng, 0.06, 70) * (0.9 if i % 2 == 0 else 0.55))
        # melodie (2e partie) : notes de l'accord, une octave au-dessus
        if section_b:
            for k, pos in enumerate(mel_rhythm[(b + index) % len(mel_rhythm)]):
                m = notes[(k + b) % 3] + 24
                _add(melody, t0 + int(pos * beat * SR), _piano(_hz(m), beat * 1.2, 0.7))

    pad = _fft_filter(pad, lo=120, hi=1400)
    hats = _fft_filter(hats, lo=7000)
    snare = _fft_filter(snare, lo=900, hi=7000)
    bass = _fft_filter(bass, hi=900)
    kick = _fft_filter(kick, hi=4000)

    def norm(x):
        return x / (np.sqrt(np.mean(x ** 2)) + 1e-9)

    # niveaux relatifs (RMS) puis placement stereo
    stems = {
        "piano": (norm(_reverb(piano, rng, 2.4, 0.30)) * 0.30, -0.15),
        "melody": (norm(_reverb(melody, rng, 2.8, 0.35)) * 0.16 if melody.any() else melody, 0.25),
        "pad": (norm(_reverb(pad, rng, 3.0, 0.40)) * 0.16, 0.0),
        "bass": (norm(bass) * 0.22, 0.0),
        "kick": (norm(kick) * 0.20 if kick.any() else kick, 0.0),
        "snare": (norm(_reverb(snare, rng, 1.2, 0.30)) * 0.07 if snare.any() else snare, 0.05),
        "hats": (norm(hats) * 0.035, 0.3),
    }
    left, right = np.zeros(n), np.zeros(n)
    for sig, pan in stems.values():
        left += sig * np.sqrt((1 - pan) / 2) * np.sqrt(2)
        right += sig * np.sqrt((1 + pan) / 2) * np.sqrt(2)
    mix = np.stack([left, right], axis=1)
    # master : RMS vise ~ -15 dBFS, crêtes adoucies (tanh) sous 0 dBFS
    mix *= 10 ** (-15 / 20) / (np.sqrt(np.mean(mix ** 2)) + 1e-9)
    mix = np.tanh(mix * 1.1) / 1.1
    return mix.astype(np.float32)


def generate_all(out_dir: str, force: bool = False) -> list[str]:
    """Genere les pistes dans out_dir (une seule fois : ne regenere pas si deja presentes, sauf force=True)."""
    os.makedirs(out_dir, exist_ok=True)
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    paths = []
    for i, (name, *_rest) in enumerate(TRACKS):
        out_path = os.path.join(out_dir, f"music_{i}_{name}.mp3")
        if os.path.exists(out_path) and not force:
            paths.append(out_path)
            continue
        raw_path = os.path.join(out_dir, f"_music_{i}.raw")
        compose(i).tofile(raw_path)
        subprocess.run([ffmpeg_bin, "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", raw_path,
                        "-b:a", "160k", out_path], check=True, capture_output=True)
        os.remove(raw_path)
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    import config
    generated = generate_all(config.MUSIC_DIR, force=True)
    print(f"{len(generated)} piste(s) generee(s) dans {config.MUSIC_DIR}")
