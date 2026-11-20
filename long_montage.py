"""Montage dynamique du format long (16:9), 100 % ffmpeg : rapide, aucun compositing Python image par image.

Ce qui change par rapport a l'ancien montage (video_assembler.assemble_video_from_segments : un clip
fixe par paragraphe, ~25 s chacun, coupes seches, aucun mouvement) :
- rythme : un nouveau plan toutes les ~2,5-4,5 s, coupe calee sur le debut d'un mot (jamais au milieu) ;
- variete : 2-3 clips differents par paragraphe, et quand un clip revient on en montre un autre passage ;
- mouvement permanent : chaque plan zoome (avant/arriere) ou panote lentement, facon Ken Burns ;
  certaines coupes ont un leger "punch" (zoom bref + flash) pour relancer l'attention ;
- transitions variees (glisse, zoom, cercle, flash blanc...) a chaque changement de paragraphe ;
- etalonnage : contraste/saturation releves, vignette, leger grain -> rendu moins "stock brut" ;
- son : musique qui s'efface sous la voix (ducking), whoosh discret a chaque transition, volume
  normalise a -18 LUFS (21/10/2026 : -14 LUFS juge trop fort par l'utilisateur sur les Shorts).

Les textes animes (mots-cles qui s'affichent, sous-titres mot par mot, barre de progression) sont
generes par subtitles.build_long_dynamic_ass et graves a l'etape sous-titres du pipeline, comme avant.

Toute erreur remonte en exception : run_pipeline.py retombe alors sur l'ancien montage.
"""
import os
import random
import re
import shutil
import subprocess

import imageio_ffmpeg

import config

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = config.VIDEO_WIDTH, config.VIDEO_HEIGHT, config.VIDEO_FPS
XFADE = 0.5  # duree d'une transition entre paragraphes (s)
TRANSITIONS = ["smoothleft", "zoomin", "circleopen", "smoothright", "fadewhite", "slideleft",
               "smoothup", "radial", "fadeblack", "hlslice"]
MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "push_left", "push_right"]


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        errs = [l for l in r.stderr.splitlines() if re.search(r"error|invalid|unable|no such|failed|cannot", l, re.I)]
        raise RuntimeError("ffmpeg a echoue : " + (" | ".join(errs[-6:]) or r.stderr[-800:]))


def probe_duration(path: str) -> float:
    r = subprocess.run([FFMPEG, "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise RuntimeError(f"Duree illisible : {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ---------- decoupage en plans ----------

def plan_shots(scenes: list[dict], word_starts: list[float], total: float, seed: int | None = None,
               min_len: float | None = None, max_len: float | None = None) -> list[dict]:
    """scenes : [{"start": s, "clips": [chemins]}] dans l'ordre du script (une scene = un paragraphe).
    Retourne les plans [{"scene", "start", "end", "clip", "motion", "punch"}] couvrant [0, total] sans trou.

    Chaque scene est redecoupee en plans de min_len..max_len secondes ; chaque coupe est deplacee sur
    le debut de mot le plus proche (une coupe en plein mot se voit). Un reste trop court est fusionne
    au plan precedent pour eviter les plans "flash"."""
    rnd = random.Random(seed)
    min_len = min_len or config.LONG_SHOT_MIN_SECONDS
    max_len = max_len or config.LONG_SHOT_MAX_SECONDS
    starts = sorted(word_starts)

    def snap(t: float, lo: float, hi: float) -> float:
        best, best_d = t, 0.6  # on ne deplace jamais une coupe de plus de 0,6 s
        for s in starts:
            if lo < s < hi and abs(s - t) < best_d:
                best, best_d = s, abs(s - t)
        return best

    bounds = [0.0] + [max(0.0, sc["start"]) for sc in scenes[1:]] + [total]
    shots, prev_motion = [], None
    for si, sc in enumerate(scenes):
        a, b = bounds[si], bounds[si + 1]
        if b - a <= 0.05:
            continue
        cuts, t = [a], a
        first = si == 0
        while True:
            # tout premier plan plus court : l'accroche doit bouger tout de suite
            step = rnd.uniform(1.6, 2.4) if first and len(cuts) == 1 else rnd.uniform(min_len, max_len)
            nxt = snap(t + step, t + min_len * 0.7, b - min_len * 0.7)
            if nxt >= b - min_len * 0.7 or nxt <= t:
                break
            cuts.append(nxt)
            t = nxt
        cuts.append(b)
        clips = sc["clips"]
        for k in range(len(cuts) - 1):
            motion = rnd.choice([m for m in MOTIONS if m != prev_motion])
            prev_motion = motion
            shots.append({
                "scene": si, "start": cuts[k], "end": cuts[k + 1], "clip": clips[k % len(clips)],
                "motion": motion,
                # punch (zoom bref + flash) sur ~1 coupe interne sur 3, jamais au 1er plan d'une scene
                # (la transition entre scenes fait deja l'effet)
                "punch": k > 0 and rnd.random() < 0.33,
            })
    return shots


# ---------- rendu d'un plan ----------

def _motion_filter(motion: str, frames: int, punch: bool) -> str:
    """Cover-fit sur une image 2x plus grande (precision sous-pixel du mouvement -> pas de tremblote),
    puis zoompan : zoom/pano lent sur toute la duree du plan."""
    n = max(1, frames - 1)
    p = f"(on/{n})"
    z0, z1 = {"zoom_in": (1.0, 1.14), "zoom_out": (1.14, 1.0), "push_left": (1.06, 1.18),
              "push_right": (1.06, 1.18)}.get(motion, (1.16, 1.16))
    z = f"({z0}+{z1 - z0:.3f}*{p})"
    if punch:  # zoom bref qui retombe en ~0,25 s
        z += "+0.10*max(0,1-on/8)"
    px = {"pan_left": f"(0.85-0.7*{p})", "pan_right": f"(0.15+0.7*{p})",
          "push_left": f"(0.7-0.4*{p})", "push_right": f"(0.3+0.4*{p})"}.get(motion, "0.5")
    py = f"(0.8-0.6*{p})" if motion == "pan_up" else "0.5"
    cover = f"fps={FPS},scale={2 * W}:{2 * H}:force_original_aspect_ratio=increase,crop={2 * W}:{2 * H},setsar=1"
    zp = (f"zoompan=z='{z}':x='(iw-iw/zoom)*{px}':y='(ih-ih/zoom)*{py}':d=1:s={W}x{H}:fps={FPS}")
    flash = "0.22*max(0\\,1-t/0.12)" if punch else "0"
    # 20/11/2026 : image jugee trop sombre sur l'extrait -> gamma releve, contraste et vignette adoucis
    grade = (f"eq=contrast=1.04:saturation=1.15:gamma=1.10:brightness='0.03+{flash}':eval=frame,"
             "vignette=angle=PI/7,noise=alls=3:allf=t")
    return f"{cover},{zp},{grade},format=yuv420p"


def render_shot(src: str, start: float, frames: int, out: str, motion: str, punch: bool = False) -> str:
    _run([FFMPEG, "-y", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", src, "-an",
          "-vf", _motion_filter(motion, frames, punch), "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
          "-r", str(FPS), "-video_track_timescale", str(FPS * 512), out])
    return out


# ---------- audio ----------

def _pick_music() -> str | None:
    import glob
    if not config.MUSIC_ENABLED:
        return None
    tracks = sorted(glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3")))
    return random.choice(tracks) if tracks else None


def mix_audio(voice: str, transitions: list[float], total: float, out_path: str, music: str | None = None) -> str:
    """Voix + musique en ducking + whoosh discret a chaque transition, normalise a -18 LUFS."""
    music = music if music is not None else _pick_music()
    fmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    inputs = ["-i", voice] + (["-stream_loop", "-1", "-i", music] if music else [])
    fc = [f"[0:a]{fmt},asplit=2[voice][sc]"]
    mix = ["[voice]"]
    if music:
        fc += [f"[1:a]{fmt},volume=0.24,afade=t=in:d=1.0[mus]",
               "[mus][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]"]
        mix.append("[duck]")
    else:
        fc.append("[sc]anullsink")
    if transitions:
        fc.append(f"anoisesrc=d=0.6:c=pink:r=44100:a=0.6,highpass=f=300,lowpass=f=5000,afade=t=in:d=0.25,"
                  f"afade=t=out:st=0.25:d=0.35,volume=0.10,{fmt},asplit={len(transitions)}"
                  + "".join(f"[w{i}]" for i in range(len(transitions))))
        for i, c in enumerate(transitions):
            ms = max(0, int((c - 0.15) * 1000))
            fc.append(f"[w{i}]adelay={ms}|{ms}[wd{i}]")
            mix.append(f"[wd{i}]")
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
              f"loudnorm=I=-18:TP=-2:LRA=11,aresample=44100[a]")
    _run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[a]", "-t", f"{total:.3f}",
          "-c:a", "aac", "-b:a", "192k", out_path])
    return out_path


# ---------- assemblage ----------

def assemble_dynamic(voice_path: str, scenes: list[dict], word_starts: list[float], out_path: str,
                     work_dir: str, seed: int | None = None, max_seconds: float | None = None) -> dict:
    """Monte la video longue (sans sous-titres) a partir de la voix brute et des scenes
    [{"start": s, "clips": [...]}]. max_seconds limite la duree (extraits de demonstration).
    Retourne {"video": out_path, "shots": [...], "scene_starts": [...]} : les debuts de scene servent
    ensuite a placer les textes animes."""
    os.makedirs(work_dir, exist_ok=True)
    total = probe_duration(voice_path)
    if max_seconds:
        total = min(total, max_seconds)
        scenes = [sc for i, sc in enumerate(scenes) if i == 0 or sc["start"] < total - 1.0]
    shots = plan_shots(scenes, word_starts, total, seed=seed)
    if not shots:
        raise RuntimeError("Aucun plan a monter.")
    rnd = random.Random(seed)

    def fr(t: float) -> int:  # grille d'images commune : aucune derive audio/video sur 20 min
        return int(round(t * FPS))

    clip_len, cursor = {}, {}
    scene_ids = sorted({s["scene"] for s in shots})
    last_of_scene = {si: max(i for i, s in enumerate(shots) if s["scene"] == si) for si in scene_ids}
    ext = fr(XFADE)
    scene_files: dict[int, list[str]] = {si: [] for si in scene_ids}
    for i, sh in enumerate(shots):
        frames = fr(sh["end"]) - fr(sh["start"])
        # le dernier plan d'une scene deborde de la duree de la transition (recouverte par le xfade)
        if i == last_of_scene[sh["scene"]] and sh["scene"] != scene_ids[-1]:
            frames += ext
        if frames <= 0:
            continue
        src = sh["clip"]
        if src not in clip_len:
            clip_len[src] = probe_duration(src)
            cursor[src] = rnd.uniform(0, max(0.0, clip_len[src] * 0.3))
        # quand le meme clip revient, on en montre un autre passage
        start = cursor[src] % max(0.5, clip_len[src] - 0.5)
        cursor[src] = start + frames / FPS
        f = os.path.join(work_dir, f"shot_{i:04d}.mp4")
        render_shot(src, start, frames, f, sh["motion"], sh["punch"])
        scene_files[sh["scene"]].append(f)

    # 1) chaque scene = ses plans colles bout a bout (copie de flux, aucun re-encodage)
    scene_paths, scene_starts = [], []
    for si in [s for s in scene_ids if scene_files[s]]:
        lst = os.path.join(work_dir, f"scene_{si:03d}.txt")
        with open(lst, "w", encoding="utf-8") as fh:
            for f in scene_files[si]:
                fh.write(f"file '{os.path.abspath(f).replace(os.sep, '/')}'\n")
        sp = os.path.join(work_dir, f"scene_{si:03d}.mp4")
        _run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", sp])
        scene_paths.append(sp)
        scene_starts.append(min(s["start"] for s in shots if s["scene"] == si))

    # 2) transitions entre scenes ; chaque transition commence pile au debut de la scene suivante
    silent = os.path.join(work_dir, "video_muette.mp4")
    if len(scene_paths) == 1:
        shutil.copyfile(scene_paths[0], silent)
    else:
        inputs, fc, last = [], [], "[0:v]"
        for p in scene_paths:
            inputs += ["-i", p]
        prev_tr = None
        for k in range(1, len(scene_paths)):
            tr = rnd.choice([t for t in TRANSITIONS if t != prev_tr])
            prev_tr = tr
            lab = f"[x{k}]"
            fc.append(f"{last}[{k}:v]xfade=transition={tr}:duration={XFADE}:offset={fr(scene_starts[k]) / FPS:.4f}{lab}")
            last = lab
        fc.append(f"{last}format=yuv420p[v]")
        _run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]",
              "-frames:v", str(fr(total)), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", silent])

    # 3) son + multiplexage
    audio = mix_audio(voice_path, scene_starts[1:], total, os.path.join(work_dir, "audio.m4a"))
    _run([FFMPEG, "-y", "-i", silent, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
          "-t", f"{total:.3f}", "-movflags", "+faststart", out_path])
    return {"video": out_path, "shots": shots, "scene_starts": scene_starts, "duration": total}


# ---------- extrait de demonstration ----------

DEMO_TEXT = (
    "Most people think motivation is the key to success. It is not. Motivation is a feeling, and feelings change "
    "every single day. Discipline is different. Discipline is a system you build once, and follow even when you do "
    "not feel like it. Here is the truth nobody tells you. Ninety percent of your results come from boring habits, "
    "repeated for years. The alarm at six in the morning. The ten pages you read before bed. The phone you leave "
    "in another room. Small actions, every single day. That is how a new identity is built. Not in one big moment, "
    "but in a thousand quiet ones that nobody sees."
)


def demo(out_path: str, seconds: float = 45.0) -> str:
    """Rend un extrait de ~45 s avec le vrai pipeline (voix Azure, clips Pexels, mots-cles Ollama si dispo)
    pour juger le montage sans lancer une video complete. Usage : python long_montage.py --demo"""
    import json
    import tempfile
    import run_pipeline
    import script_generator
    import subtitles
    import video_assembler
    import visuals_fetcher
    import voice_generator

    work = tempfile.mkdtemp(prefix="_tmp_demo_long_", dir=config.VIDEO_DIR if os.path.isdir(config.VIDEO_DIR) else None)
    voice, timing = voice_generator.generate_voice_with_timing(DEMO_TEXT, out_path=os.path.join(work, "voice.mp3"))
    with open(timing, encoding="utf-8") as f:
        words = json.load(f)
    scenes, idx = [], 0
    for i, para in enumerate(run_pipeline.chunk_script(DEMO_TEXT, target_words=28)):
        pw = words[idx: idx + len(para.split())]
        idx += len(para.split())
        if not pw:
            break
        kw = script_generator.generate_visual_keyword(para)
        clips = visuals_fetcher.fetch_clips_for_query(kw, config.LONG_CLIPS_PER_SEGMENT, work, f"seg_{i:03d}")
        print(f"  scene {i}: '{kw}' -> {len(clips)} clip(s)")
        if clips:
            scenes.append({"start": pw[0]["offset"] / 1e7, "clips": clips})
    raw = os.path.join(work, "raw.mp4")
    info = assemble_dynamic(voice, scenes, [w["offset"] / 1e7 for w in words], raw, os.path.join(work, "m"),
                            max_seconds=seconds)
    ass = subtitles.build_long_dynamic_ass(words, os.path.join(work, "s.ass"), info["scene_starts"], info["duration"])
    video_assembler.burn_subtitles(raw, ass, out_path)
    shutil.rmtree(work, ignore_errors=True)
    return out_path


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        out = os.path.join(config.OUTPUT_DIR, "demo_montage_long.mp4")
        print("Extrait ->", demo(out))
