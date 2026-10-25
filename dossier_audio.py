"""Habillage sonore des Shorts "dossier" : nappe de suspense, impacts, montees et tampons, synthetises en numpy.

Genere localement a chaque rendu (aucun telechargement, aucun droit d'auteur). Remplace, pour la chaine FR
histoire, les nappes en accords majeurs et les "whoosh" de bruit rose de motion_video.mix_audio, juges
desagreables par l'utilisateur le 25/10/2026 ("le son n'est pas specialement agreable").

25/10/2026 (2e retour utilisateur : "DA top", mais fond "legerement trop fort, empeche d'etre a fond dans
l'histoire", et "varier les bruitages") : nappe nettement plus basse et plus ecrasee sous la voix, et plusieurs
variantes de chaque son, tirees au sort par histoire (graine = numero du dossier) :

    bed(total, rng)    nappe sombre : tonalite, tempo, battement de coeur ou horloge, notes isolees -> au hasard
    impact(rng)        boom grave / coup metallique / tambour de cinema
    riser(rng)         montee tonale / souffle qui enfle / pulsation qui accelere
    stamp(rng)         tampon sourd / machine a ecrire / claque de dossier
    mix(...)           voix traitee (EQ, de-esser, compresseur) + habillage, normalise a -16 LUFS
"""
import os
import subprocess
import wave

import numpy as np

import motion_video

SR = 44100


def _write(path: str, mono: np.ndarray) -> str:
    mono = np.clip(mono, -1, 1)
    st = (np.repeat(mono[:, None], 2, axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(SR), w.writeframes(st.tobytes())
    return path


def _lowpass(x: np.ndarray, taps: int) -> np.ndarray:
    k = np.hanning(taps)
    return np.convolve(x, k / k.sum(), mode="same")


def _sweep(f0: float, f1: float, dur: float) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    f = f0 * (f1 / f0) ** (t / dur)                 # glissando exponentiel
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    return x / max(1e-9, np.max(np.abs(x))) * peak


# ---------- impacts ----------
def _boom(rng, dur):
    n = int(SR * dur); t = np.arange(n) / SR
    return (_sweep(140, 34, dur) * np.exp(-t * 2.6) + np.sin(2 * np.pi * 42 * t) * np.exp(-t * 1.8) * 0.6
            + _lowpass(rng.standard_normal(n), 9) * np.exp(-t * 60) * 0.7
            + _lowpass(rng.standard_normal(n), 400) * np.exp(-t * 3.5) * 2.5)


def _metal(rng, dur):
    n = int(SR * dur); t = np.arange(n) / SR
    out = np.zeros(n)
    for f, d in ((187, 3.0), (431, 4.5), (623, 6.0), (1210, 9.0)):       # partiels inharmoniques : coup de metal sourd
        out += np.sin(2 * np.pi * f * t + rng.random() * 6) * np.exp(-t * d) / (1 + f / 400)
    return out + _sweep(90, 40, dur) * np.exp(-t * 4) * 0.8 + _lowpass(rng.standard_normal(n), 7) * np.exp(-t * 80) * 0.5


def _drum(rng, dur):
    n = int(SR * dur); t = np.arange(n) / SR
    skin = _sweep(110, 55, dur) * np.exp(-t * 5.5)
    room = _lowpass(rng.standard_normal(n), 120) * np.exp(-t * 6) * 1.6
    return skin + room + _lowpass(rng.standard_normal(n), 11) * np.exp(-t * 90) * 0.6


IMPACTS = (_boom, _metal, _drum)


def impact(rng, kind=None, dur: float = 1.8, strength: float = 1.0) -> np.ndarray:
    f = kind or IMPACTS[rng.integers(len(IMPACTS))]
    return _norm(f(rng, dur), 0.9 * strength)


# ---------- montees ----------
def riser(rng, dur: float = 1.2) -> np.ndarray:
    n = int(SR * dur); t = np.arange(n) / SR
    ramp = (t / dur) ** 2.2
    v = rng.integers(3)
    if v == 0:      # montee tonale, deux voix desaccordees
        out = (_sweep(180, 720, dur) + _sweep(181.5, 724, dur)) * 0.35 + _lowpass(rng.standard_normal(n), 25) * 0.5
    elif v == 1:    # souffle qui enfle (cymbale inversee)
        out = _lowpass(rng.standard_normal(n), 4) * (0.4 + 0.6 * t / dur)
    else:           # pulsation qui accelere
        rate = 3 + 14 * (t / dur) ** 1.5
        out = np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * np.cumsum(rate) / SR))) * 0.6
    out = out * ramp
    out[-int(SR * 0.01):] *= np.linspace(1, 0, int(SR * 0.01))           # coupe nette sur le retournement
    return _norm(out, 0.6)


# ---------- tampons ----------
def stamp(rng) -> np.ndarray:
    v = rng.integers(3)
    n = int(SR * 0.35); t = np.arange(n) / SR
    if v == 0:      # tampon sourd
        out = np.sin(2 * np.pi * 95 * t) * np.exp(-t * 22) + _lowpass(rng.standard_normal(n), 5) * np.exp(-t * 140) * 0.8
    elif v == 1:    # machine a ecrire : trois frappes
        out = np.zeros(n)
        for k, s in enumerate((0, 0.07, 0.15)):
            i = int(SR * s); m = n - i; tt = np.arange(m) / SR
            out[i:] += (_lowpass(rng.standard_normal(m), 3) * np.exp(-tt * 260) + np.sin(2 * np.pi * 1800 * tt) * np.exp(-tt * 300) * 0.3) * (1 - 0.15 * k)
    else:           # claque de dossier pose sur la table
        out = _lowpass(rng.standard_normal(n), 14) * np.exp(-t * 45) + np.sin(2 * np.pi * 70 * t) * np.exp(-t * 18) * 0.7
    return _norm(out, 0.8)


# ---------- nappe ----------
KEYS = {"re": (73.42, [293.66, 349.23, 392.0, 440.0, 523.25, 587.33]),
        "la": (55.0, [220.0, 261.63, 293.66, 329.63, 392.0, 440.0]),
        "mi": (82.41, [329.63, 392.0, 440.0, 493.88, 587.33, 659.25]),
        "do": (65.41, [261.63, 311.13, 349.23, 392.0, 466.16, 523.25])}   # gammes mineures pentatoniques


def bed(total: float, rng) -> np.ndarray:
    """Nappe de suspense : bourdon en tonalite mineure + pulsation (coeur ou horloge) + notes isolees aigues."""
    n = int(SR * (total + 0.5)); t = np.arange(n) / SR
    root, scale = KEYS[list(KEYS)[rng.integers(len(KEYS))]]
    drone = np.zeros(n)
    for f, a in ((root, 1.0), (root * 1.5, 0.4), (root * 2, 0.22)):      # fondamentale, quinte, octave
        for h in range(1, 5):
            drone += a / h ** 1.6 * np.sin(2 * np.pi * f * h * t + h)
    drone *= 0.55 + 0.45 * np.sin(2 * np.pi * (0.05 + 0.04 * rng.random()) * t) ** 2   # respiration lente
    pulse = np.zeros(n)
    bpm = 58 + rng.integers(16)
    step = int(SR * 60 / bpm)
    if rng.random() < 0.6:   # battement de coeur "lub-dub"
        m = int(SR * 0.25); k = np.arange(m) / SR
        hit, second = np.sin(2 * np.pi * 52 * k) * np.exp(-k * 18), 0.6
    else:                    # tic-tac d'horloge, plus discret
        m = int(SR * 0.05); k = np.arange(m) / SR
        hit, second = _lowpass(rng.standard_normal(m), 3) * np.exp(-k * 200) * 0.5, 0.0
    for s in range(int(SR * 0.4), n - m - int(SR * 0.3), step):
        pulse[s:s + m] += hit
        if second:
            d = s + int(SR * 0.22); pulse[d:d + m] += hit * second
    notes = np.zeros(n)
    gap = int(SR * (2.8 + 1.6 * rng.random()))
    for s in range(int(SR * 2.0), n - SR * 2, gap):
        f = scale[rng.integers(len(scale))]; k = np.arange(SR * 2) / SR
        notes[s:s + SR * 2] += (np.sin(2 * np.pi * f * k) + 0.3 * np.sin(4 * np.pi * f * k)) * np.exp(-k * 2.2)
    out = _norm(drone, 0.5) + _norm(pulse, 0.4) + notes * 0.09
    fade = np.ones(n)
    fade[:int(SR * 0.3)] = np.linspace(0, 1, int(SR * 0.3))
    fade[-int(SR * 1.5):] = np.linspace(1, 0, int(SR * 1.5))
    return _norm(out * fade, 0.8)


VOICE_CHAIN = ("highpass=f=75,equalizer=f=220:t=q:w=1:g=-2.5,equalizer=f=3200:t=q:w=1.3:g=3.5,"
               "equalizer=f=9000:t=q:w=1:g=1.5,deesser=i=0.35,"
               "acompressor=threshold=0.08:ratio=3.5:attack=4:release=90:makeup=1.8")


def mix(voice: str, beats: list[dict], total: float, out_path: str, work_dir: str, seed: int | None = None) -> str:
    """Voix traitee + nappe en ducking + impact d'ouverture + impacts/montees sur les retournements + tampons.
    seed : numero du dossier, pour que chaque histoire ait son propre habillage (reproductible)."""
    rng = np.random.default_rng(seed if seed is not None else int(total * 1000))
    open_kind = IMPACTS[rng.integers(len(IMPACTS))]
    files = {"bed": bed(total, rng), "impact": impact(rng, open_kind)}
    hits = [impact(rng, IMPACTS[(IMPACTS.index(open_kind) + 1 + i) % len(IMPACTS)], 1.2, 0.6) for i in range(2)]
    files.update({"hit0": hits[0], "hit1": hits[1], "riser0": riser(rng), "riser1": riser(rng),
                  "stamp0": stamp(rng), "stamp1": stamp(rng)})
    files = {k: _write(os.path.join(work_dir, f"sfx_{k}.wav"), v) for k, v in files.items()}
    events = [("impact", 0.0, 0.8)]                                      # coup d'ouverture sur l'accroche
    flashes = [b["start"] for b in beats[1:] if b.get("flash")]
    for i, s in enumerate(flashes):
        events.append((f"hit{i % 2}", s, 0.5))                           # on alterne deux sons differents
        if i >= len(flashes) - 2 and s > 2.5:                            # montee seulement avant les 2 derniers retournements
            events.append((f"riser{i % 2}", s - 1.2, 0.32))
    k = 0
    for b in beats:
        if b.get("stamp"):
            events.append((f"stamp{k % 2}", b["start"] + b.get("stamp_at", min(1.0, (b["end"] - b["start"]) * 0.5)), 0.55))
            k += 1
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    inputs = ["-i", voice, "-i", files["bed"]]
    # nappe nettement sous la voix (0.30 -> 0.16) et plus ecrasee quand la voix parle (ratio 7 -> 12)
    fc = [f"[0:a]{fmt},{VOICE_CHAIN},asplit=2[voice][sc]",
          f"[1:a]{fmt},volume=0.16[bed]",
          "[bed][sc]sidechaincompress=threshold=0.02:ratio=12:attack=15:release=450[duck]"]
    mixin = ["[voice]", "[duck]"]
    for i, (kind, at, vol) in enumerate(events):
        if at < 0 or at > total:
            continue
        inputs += ["-i", files[kind]]
        ms = int(at * 1000)
        fc.append(f"[{len(inputs) // 2 - 1}:a]{fmt},volume={vol},adelay={ms}|{ms}[e{i}]")
        mixin.append(f"[e{i}]")
    fc.append(f"{''.join(mixin)}amix=inputs={len(mixin)}:duration=first:normalize=0,"
              "alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=9,aresample=44100[a]")
    r = subprocess.run([motion_video.FFMPEG, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[a]",
                        "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "192k", out_path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("ffmpeg audio dossier : " + r.stderr[-800:])
    return out_path
