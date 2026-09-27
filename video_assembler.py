"""Assemble la voix off et les clips stock en une video finale (via moviepy/ffmpeg, gratuit)."""
import glob
import os
import random
import shutil
import subprocess
import imageio_ffmpeg
from moviepy import AudioFileClip, VideoFileClip, concatenate_videoclips, CompositeVideoClip
import config


def cleanup_stale_temp_files() -> None:
    """Supprime les fichiers de travail intermediaires laisses par un run precedent qui a plante
    avant d'atteindre son propre nettoyage (ex: Ollama en panne en plein montage, coupure du PC).
    Sans danger a appeler en debut de run : le verrou Mutex de run_pipeline_safe.ps1 garantit qu'un
    seul run tourne a la fois, donc tout ce qui traine ici ne peut venir que d'un run precedent fini
    ou avorte, jamais d'un run en cours. Couvre aussi le residu moviepy `..TEMP_MPY_wvf_snd.mp4`
    ecrit dans le repertoire courant (pas a cote de out_path) sur cette version de moviepy."""
    patterns = [
        os.path.join(config.VIDEO_DIR, "_tmp_*"),
        os.path.join(config.AUDIO_DIR, "*"),
        os.path.join(config.BASE_DIR, "_tmp_*TEMP_MPY_wvf_snd.mp4"),
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                os.remove(path)
            except OSError:
                pass

    for prefix in ("_run_", "_shorts_run_"):
        for path in glob.glob(os.path.join(config.STOCK_DIR, f"{prefix}*")):
            shutil.rmtree(path, ignore_errors=True)

    # Dossier de video publiee cree (os.makedirs) avant un plantage en cours de montage : un run
    # fini contient toujours video.mp4 (longue) ou short.mp4 (Short). Un dossier qui n'a ni l'un ni
    # l'autre (vide, ou juste une thumbnail.jpg si le plantage arrive apres l'etape miniature) ne
    # peut etre qu'un residu d'un run avorte, jamais une video publiee.
    if os.path.isdir(config.PUBLISHED_DIR):
        for name in os.listdir(config.PUBLISHED_DIR):
            path = os.path.join(config.PUBLISHED_DIR, name)
            if not os.path.isdir(path):
                continue
            has_final_video = os.path.exists(os.path.join(path, "video.mp4")) or \
                os.path.exists(os.path.join(path, "short.mp4"))
            if not has_final_video:
                shutil.rmtree(path, ignore_errors=True)


def _write_videofile_safe(clip, out_path: str, **kwargs) -> None:
    """write_videofile() sur Windows : le nettoyage interne de moviepy (suppression du fichier
    audio temporaire apres remux) echoue parfois avec PermissionError si un antivirus ou le systeme
    de fichiers garde brievement un verrou dessus. A ce stade la video finale (out_path) est deja
    ecrite avec succes ('MoviePy - Done!' deja affiche) : l'erreur ne concerne que le fichier
    temporaire, donc on l'ignore apres verification que out_path existe bien."""
    try:
        clip.write_videofile(out_path, **kwargs)
    except PermissionError as exc:
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"    [warn] Nettoyage temporaire moviepy ignore (fichier verrouille) : {exc}")
        else:
            raise


def mix_background_music(voice_path: str, out_path: str | None = None) -> str:
    """Mixe une nappe ambiante generee localement sous la voix off, en boucle et a bas volume.
    Ne modifie ni la duree ni le timing de la voix (indispensable pour les sous-titres synchronises).
    Retombe silencieusement sur la voix seule si aucune piste n'est disponible ou si MUSIC_ENABLED=False."""
    if not config.MUSIC_ENABLED:
        return voice_path

    tracks = sorted(glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3")))
    if not tracks:
        return voice_path

    music_path = random.choice(tracks)
    out_path = out_path or os.path.splitext(voice_path)[0] + "_mixed.mp3"
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_bin, "-y",
        "-i", voice_path,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex",
        f"[1:a]volume={config.MUSIC_VOLUME}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "[aout]", out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _prepare_clip(path: str, duration: float, width: int | None = None, height: int | None = None):
    width = width or config.VIDEO_WIDTH
    height = height or config.VIDEO_HEIGHT
    clip = VideoFileClip(path)

    # Boucle le clip si trop court avant tout retraitement (evite de redimensionner
    # plusieurs fois la meme source).
    if clip.duration < duration:
        n_loops = int(duration // clip.duration) + 1
        clip = concatenate_videoclips([clip] * n_loops)
    clip = clip.subclipped(0, duration)

    # Cover-fit en une seule passe (plus rapide que deux resize successifs), puis crop centre.
    scale = max(width / clip.w, height / clip.h)
    clip = clip.resized(scale)
    x_center, y_center = clip.w / 2, clip.h / 2
    clip = clip.cropped(
        x_center=x_center, y_center=y_center,
        width=width, height=height,
    )
    return clip.without_audio()


def assemble_video(audio_path: str, clip_paths: list[str], out_path: str | None = None) -> str:
    if not clip_paths:
        raise RuntimeError("Aucun clip stock disponible. Lance visuals_fetcher.py d'abord.")

    os.makedirs(config.VIDEO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.VIDEO_DIR, "video_finale.mp4")

    audio = AudioFileClip(audio_path)
    total_duration = audio.duration

    random.shuffle(clip_paths)
    per_clip_duration = max(6.0, total_duration / len(clip_paths))

    segments = []
    elapsed = 0.0
    idx = 0
    while elapsed < total_duration:
        clip_path = clip_paths[idx % len(clip_paths)]
        idx += 1
        remaining = total_duration - elapsed
        seg_duration = min(per_clip_duration, remaining)
        segments.append(_prepare_clip(clip_path, seg_duration))
        elapsed += seg_duration

    # method="chain" (par defaut) suffit et est bien plus rapide que "compose":
    # tous les segments ont deja ete redimensionnes/rognes a la meme taille.
    final = concatenate_videoclips(segments)
    final = final.with_audio(audio)
    _write_videofile_safe(
        final, out_path, fps=config.VIDEO_FPS, codec="libx264", audio_codec="aac",
        threads=os.cpu_count() or 4, preset="veryfast",
        ffmpeg_params=["-crf", "23"],
    )

    for s in segments:
        s.close()
    audio.close()
    final.close()
    return out_path


def assemble_video_from_segments(
    audio_path: str, segments: list[tuple[str, float]], out_path: str | None = None,
    width: int | None = None, height: int | None = None,
) -> str:
    """Assemble la video en respectant l'ordre et la duree de chaque segment (clip, duree_secondes),
    pour que le visuel corresponde au passage du script effectivement narre a ce moment-la."""
    if not segments:
        raise RuntimeError("Aucun segment visuel disponible pour l'assemblage.")

    os.makedirs(config.VIDEO_DIR, exist_ok=True)
    out_path = out_path or os.path.join(config.VIDEO_DIR, "video_finale.mp4")

    audio = AudioFileClip(audio_path)
    total_duration = audio.duration

    prepared = []
    running = 0.0
    n = len(segments)
    for i, (clip_path, duration) in enumerate(segments):
        if i == n - 1:
            # Le dernier segment absorbe l'ecart residuel pour coller exactement a la duree audio.
            duration = max(1.0, total_duration - running)
        else:
            duration = max(1.0, duration)
        prepared.append(_prepare_clip(clip_path, duration, width=width, height=height))
        running += duration

    final = concatenate_videoclips(prepared)
    final = final.with_audio(audio)
    _write_videofile_safe(
        final, out_path, fps=config.VIDEO_FPS, codec="libx264", audio_codec="aac",
        threads=os.cpu_count() or 4, preset="veryfast",
        ffmpeg_params=["-crf", "23"],
    )

    for c in prepared:
        c.close()
    audio.close()
    final.close()
    return out_path


def burn_subtitles(video_path: str, ass_path: str, out_path: str) -> str:
    """Grave les sous-titres via le filtre ffmpeg/libass natif (rapide, pas de compositing Python)."""
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    # Echappement requis par la syntaxe des filtres ffmpeg pour le chemin du fichier .ass
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    cmd = [
        ffmpeg_bin, "-y", "-i", video_path,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


if __name__ == "__main__":
    import glob
    audio_file = os.path.join(config.AUDIO_DIR, "voiceover.mp3")
    clips = sorted(glob.glob(os.path.join(config.STOCK_DIR, "*.mp4")))
    out = assemble_video(audio_file, clips)
    print(f"Video assemblee -> {out}")
