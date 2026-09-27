"""Pipeline complet : script -> voix -> visuels -> montage -> (option) publication YouTube.

Usage:
    python run_pipeline.py                     # genere tout, ne publie pas
    python run_pipeline.py --publish            # genere tout ET publie sur YouTube
    python run_pipeline.py --topic "un sujet"   # impose le sujet du script
"""
import argparse
import datetime
import json
import os
import re
import shutil

import config
import script_generator
import voice_generator
import visuals_fetcher
import video_assembler
import subtitles
import thumbnail_generator
import youtube_uploader


def slugify(text: str, max_len: int = 60) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug[:max_len].rstrip("-") or "video"


def make_output_folder_name(topic: str) -> str:
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"{date_str}_{slugify(topic)}"


def chunk_script(script: str, target_words: int = 60) -> list[str]:
    """Decoupe le script en groupes de phrases de taille reguliere (~25s a l'oral),
    plutot que par bloc de generation (tres inegaux, parfois 60+ secondes sur un seul visuel)."""
    flat = script.replace("\n", " ")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]

    chunks = []
    current, current_words = [], 0
    for sent in sentences:
        w = len(sent.split())
        if current and current_words + w > target_words:
            chunks.append(" ".join(current))
            current, current_words = [], 0
        current.append(sent)
        current_words += w
    if current:
        chunks.append(" ".join(current))
    return chunks


def write_metadata_note(metadata: dict, note_path: str) -> None:
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(f"TITLE:\n{metadata['title']}\n\n")
        f.write(f"DESCRIPTION:\n{metadata['description']}\n\n")
        f.write(f"TAGS:\n{', '.join(metadata['tags'])}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=None, help="Sujet impose du script")
    parser.add_argument("--minutes", type=int, default=None, help="Duree cible en minutes")
    parser.add_argument("--publish", action="store_true", help="Publie automatiquement sur YouTube")
    args = parser.parse_args()

    # Identifiant unique de run : les fichiers de travail intermediaires (audio, video brute, .ass)
    # en portent le nom pour qu'un run long et un run short lances en parallele (ou deux runs du meme
    # type) ne puissent jamais s'ecraser mutuellement - cause du bug du 25/09/2026 ou l'audio d'un
    # Short avait ecrase celui d'une video longue en cours (meme nom de fichier fixe "voiceover.mp3").
    run_id = f"long_{datetime.datetime.now():%Y%m%d_%H%M%S}_{os.getpid()}"

    video_assembler.cleanup_stale_temp_files()

    print("1/7 - Generation du script (Ollama local)...")
    topic, script = script_generator.generate_script(topic=args.topic, minutes=args.minutes)
    print(f"    Sujet: {topic} ({len(script.split())} mots)")

    print("    Generation du titre/description/tags optimises (Ollama)...")
    metadata = script_generator.generate_metadata(topic, script)
    print(f"    Titre: {metadata['title']}")

    print("2/7 - Generation de la voix off (edge-tts) + timings mot par mot...")
    raw_audio_path, timing_path = voice_generator.generate_voice_with_timing(
        script, out_path=os.path.join(config.AUDIO_DIR, f"voiceover_{run_id}.mp3")
    )
    print(f"    Audio -> {raw_audio_path}")

    print("    Mixage d'une musique de fond discrete...")
    audio_path = video_assembler.mix_background_music(raw_audio_path)
    print(f"    Audio (avec musique) -> {audio_path}")

    print("3/7 - Analyse du script par segment + recherche de visuels pertinents (Pexels)...")
    with open(timing_path, "r", encoding="utf-8") as f:
        word_boundaries = json.load(f)

    paragraphs = chunk_script(script)
    run_stock_dir = os.path.join(config.STOCK_DIR, f"_run_{run_id}")
    os.makedirs(run_stock_dir, exist_ok=True)

    segments = []
    word_idx = 0
    total_boundary_words = len(word_boundaries)
    for i, para in enumerate(paragraphs):
        n_words = len(para.split())
        if word_idx >= total_boundary_words:
            break
        para_words = word_boundaries[word_idx: word_idx + n_words]
        word_idx += n_words
        if not para_words:
            continue

        start = para_words[0]["offset"] / 10_000_000
        end = (para_words[-1]["offset"] + para_words[-1]["duration"]) / 10_000_000
        duration = max(1.0, end - start)

        keyword = script_generator.generate_visual_keyword(para)
        dest = os.path.join(run_stock_dir, f"seg_{i:03d}.mp4")
        clip_path = visuals_fetcher.fetch_one_clip(keyword, dest)
        print(f"    Segment {i + 1}/{len(paragraphs)}: \"{keyword}\" ({duration:.1f}s)"
              + ("" if clip_path else " -> ECHEC, ignore"))
        if clip_path:
            segments.append((clip_path, duration))

    if not segments:
        raise RuntimeError("Aucun visuel n'a pu etre recupere pour aucun segment du script.")

    os.makedirs(config.VIDEO_DIR, exist_ok=True)
    raw_video_path = video_assembler.assemble_video_from_segments(
        audio_path, segments, out_path=os.path.join(config.VIDEO_DIR, f"_tmp_sans_sous_titres_{run_id}.mp4")
    )
    print(f"    Video (sans sous-titres) -> {raw_video_path}")
    shutil.rmtree(run_stock_dir, ignore_errors=True)

    folder_name = make_output_folder_name(topic)
    video_folder = os.path.join(config.PUBLISHED_DIR, folder_name)
    os.makedirs(video_folder, exist_ok=True)

    print(f"    Dossier de la video -> {video_folder}")

    print("4/7 - Generation de la miniature (avant sous-titres, pour un fond propre)...")
    thumb_path = os.path.join(video_folder, "thumbnail.jpg")
    hook = thumbnail_generator.make_hook_text(metadata["title"])
    thumbnail_generator.generate_thumbnail(raw_video_path, hook, thumb_path, topic=topic)
    print(f"    Miniature -> {thumb_path}")

    print("5/7 - Generation et gravure des sous-titres dynamiques...")
    ass_path = subtitles.build_ass_from_timing_file(timing_path, os.path.join(config.VIDEO_DIR, f"_tmp_subtitles_{run_id}.ass"))
    video_path = video_assembler.burn_subtitles(
        raw_video_path, ass_path, os.path.join(video_folder, "video.mp4")
    )
    print(f"    Video finale (avec sous-titres) -> {video_path}")

    # Nettoyage des fichiers de travail intermediaires (le dossier de la video ne garde que le resultat fini)
    for tmp_file in (raw_video_path, ass_path, raw_audio_path, audio_path, timing_path):
        try:
            os.remove(tmp_file)
        except OSError:
            pass

    print("6/7 - Ecriture de la note titre/description/tags...")
    note_path = os.path.join(video_folder, "metadata.txt")
    write_metadata_note(metadata, note_path)
    print(f"    Note -> {note_path}")

    if args.publish:
        print("7/7 - Publication sur YouTube...")
        video_id = youtube_uploader.upload_video(
            video_path, metadata["title"], metadata["description"], tags=metadata["tags"],
        )
        try:
            youtube_uploader.set_thumbnail(video_id, thumb_path)
            print("    Miniature appliquee sur YouTube.")
        except Exception as exc:
            print(f"    [warn] Miniature non appliquee (verification telephonique du compte requise "
                  f"par YouTube pour les miniatures personnalisees ?) : {exc}")
    else:
        print("7/7 - Publication ignoree (ajoute --publish pour publier automatiquement).")

    print("Termine.")


if __name__ == "__main__":
    main()
