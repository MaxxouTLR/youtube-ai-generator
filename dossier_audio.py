"""Habillage sonore des Shorts "dossier" : nappe de suspense, impacts, montees et tampons, synthetises en numpy.

Genere localement a chaque rendu (aucun telechargement, aucun droit d'auteur). Remplace, pour la chaine FR
histoire, les nappes en accords majeurs et les "whoosh" de bruit rose de motion_video.mix_audio, juges
desagreables par l'utilisateur le 25/10/2026 ("le son n'est pas specialement agreable").

    bed(total)   nappe sombre en re mineur : bourdon grave + battement de coeur + notes isolees
    impact()     coup cinematique (descente grave + transitoire) : ouverture et retournements
    riser()      montee de tension d'1,2 s qui se termine pile sur un retournement
    stamp()      bruit sourd de tampon
    mix(...)     voix traitee (EQ, de-esser, compresseur) + habillage, normalise a -16 LUFS
"""
import os
import subprocess
import wave

import numpy as np

import motion_video

SR = 44100
RNG = np.random.default_rng(1518)


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


def impact(dur: float = 1.8, strength: float = 1.0) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    body = _sweep(140, 34, dur) * np.exp(-t * 2.6)                       # descente grave "boom"
    sub = np.sin(2 * np.pi * 42 * t) * np.exp(-t * 1.8) * 0.6           # queue sub
    click = _lowpass(RNG.standard_normal(n), 9) * np.exp(-t * 60) * 0.7  # transitoire d'attaque
    tail = _lowpass(RNG.standard_normal(n), 400) * np.exp(-t * 3.5) * 2.5  # souffle grave
    out = body + sub + click + tail
    return out / np.max(np.abs(out)) * 0.9 * strength


def riser(dur: float = 1.2) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    ramp = (t / dur) ** 2.2
    tone = _sweep(180, 720, dur) * 0.35 + _sweep(181.5, 724, dur) * 0.35   # deux voix legerement desaccordees
    air = _lowpass(RNG.standard_normal(n), 25) * 0.5
    out = (tone + air) * ramp
    out[-int(SR * 0.01):] *= np.linspace(1, 0, int(SR * 0.01))           # coupe nette sur le retournement
    return out / np.max(np.abs(out)) * 0.6


def stamp() -> np.ndarray:
    n = int(SR * 0.35)
    t = np.arange(n) / SR
    thud = np.sin(2 * np.pi * 95 * t) * np.exp(-t * 22)
    click = _lowpass(RNG.standard_normal(n), 5) * np.exp(-t * 140) * 0.8
    out = thud + click
    return out / np.max(np.abs(out)) * 0.8


def bed(total: float) -> np.ndarray:
    """Nappe de suspense en re mineur : bourdon + battement de coeur (66 bpm) + notes isolees aigues."""
    n = int(SR * (total + 0.5))
    t = np.arange(n) / SR
    drone = np.zeros(n)
    for f, a in ((73.42, 1.0), (110.0, 0.45), (146.83, 0.25)):          # re2, la2, re3
        for h in range(1, 5):                                            # quelques harmoniques douces
            drone += a / h ** 1.6 * np.sin(2 * np.pi * f * h * t + h)
    drone *= 0.55 + 0.45 * np.sin(2 * np.pi * 0.07 * t) ** 2          # respiration lente
    heart = np.zeros(n)
    beat = int(SR * 60 / 66)
    lub = np.sin(2 * np.pi * 52 * np.arange(int(SR * 0.25)) / SR) * np.exp(-np.arange(int(SR * 0.25)) / SR * 18)
    for s in range(int(SR * 0.4), n - len(lub) - int(SR * 0.2), beat):
        heart[s:s + len(lub)] += lub
        d = s + int(SR * 0.22)
        heart[d:d + len(lub)] += lub * 0.6                               # "lub-dub"
    notes = np.zeros(n)
    scale = [293.66, 349.23, 392.0, 440.0, 523.25, 587.33]               # re mineur pentatonique
    for s in range(int(SR * 2.0), n - SR * 2, int(SR * 3.3)):
        f = scale[RNG.integers(len(scale))]
        k = np.arange(SR * 2) / SR
        notes[s:s + SR * 2] += (np.sin(2 * np.pi * f * k) + 0.3 * np.sin(4 * np.pi * f * k)) * np.exp(-k * 2.2)
    out = drone / np.max(np.abs(drone)) * 0.5 + heart / max(1e-9, np.max(np.abs(heart))) * 0.55 + notes * 0.12
    fade = np.ones(n)
    fade[:int(SR * 0.3)] = np.linspace(0, 1, int(SR * 0.3))
    fade[-int(SR * 1.5):] = np.linspace(1, 0, int(SR * 1.5))
    return out * fade / np.max(np.abs(out)) * 0.8


VOICE_CHAIN = ("highpass=f=75,equalizer=f=220:t=q:w=1:g=-2.5,equalizer=f=3200:t=q:w=1.3:g=3.5,"
               "equalizer=f=9000:t=q:w=1:g=1.5,deesser=i=0.35,"
               "acompressor=threshold=0.08:ratio=3.5:attack=4:release=90:makeup=1.8")


def mix(voice: str, beats: list[dict], total: float, out_path: str, work_dir: str) -> str:
    """Voix traitee + nappe en ducking + impact d'ouverture + impacts/montees sur les retournements + tampons."""
    files = {k: _write(os.path.join(work_dir, f"sfx_{k}.wav"), v) for k, v in
             (("bed", bed(total)), ("impact", impact()), ("hit", impact(1.2, 0.6)), ("riser", riser()), ("stamp", stamp()))}
    events = [("impact", 0.0, 0.85)]                                     # coup d'ouverture sur l'accroche
    flashes = [b["start"] for b in beats[1:] if b.get("flash")]
    for i, s in enumerate(flashes):
        events.append(("hit", s, 0.55))
        if i >= len(flashes) - 2 and s > 2.5:                            # montee seulement avant les 2 derniers retournements
            events.append(("riser", s - 1.2, 0.38))
    for b in beats:
        if b.get("stamp"):
            events.append(("stamp", b["start"] + b.get("stamp_at", min(1.0, (b["end"] - b["start"]) * 0.5)), 0.6))
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    inputs = ["-i", voice, "-i", files["bed"]]
    fc = [f"[0:a]{fmt},{VOICE_CHAIN},asplit=2[voice][sc]",
          f"[1:a]{fmt},volume=0.30[bed]",
          "[bed][sc]sidechaincompress=threshold=0.03:ratio=7:attack=20:release=400[duck]"]
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
