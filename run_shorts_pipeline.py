"""Pipeline Shorts : script court -> voix -> visuels portrait -> montage vertical -> (option) publication.

Usage:
    python run_shorts_pipeline.py                     # genere un short, ne publie pas
    python run_shorts_pipeline.py --publish            # genere ET publie sur YouTube
    python run_shorts_pipeline.py --topic "un sujet"    # impose le sujet
    python run_shorts_pipeline.py --seconds 45          # impose la duree cible (secondes)
"""
import argparse
import datetime
import json
import os
import shutil

import config
import script_generator
import voice_generator
import visuals_fetcher
import video_assembler
import subtitles
import youtube_uploader
from run_pipeline import slugify, chunk_script, write_metadata_note


def _merge_short_segments(segments: list[tuple[str, float]], min_seconds: float) -> list[tuple[str, float]]:
    """Fusionne les segments plus courts que min_seconds avec le precedent (duree cumulee, le clip
    court est retire) : evite le clignotement de coupes visuelles de moins de ~2s sur un Short."""
    if not segments:
        return segments

    merged = [list(segments[0])]
    for clip_path, duration in segments[1:]:
        if merged[-1][1] < min_seconds:
            merged[-1][1] += duration
        else:
            merged.append([clip_path, duration])

    if len(merged) > 1 and merged[-1][1] < min_seconds:
        merged[-2][1] += merged[-1][1]
        merged.pop()

    return [(c, d) for c, d in merged]


def make_output_folder_name(topic: str) -> str:
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"{date_str}_short_{slugify(topic)}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=None, help="Sujet impose du script")
    parser.add_argument("--seconds", type=int, default=None, help="Duree cible en secondes")
    parser.add_argument("--publish", action="store_true", help="Publie automatiquement sur YouTube")
    args = parser.parse_args()

    # Identifiant unique de run (voir run_pipeline.py pour le pourquoi : deux pipelines lances en
    # parallele ne doivent jamais partager un nom de fichier de travail fixe).
    run_id = f"short_{datetime.datetime.now():%Y%m%d_%H%M%S}_{os.getpid()}"

    video_assembler.cleanup_stale_temp_files()

    print("1/6 - Generation du script court (Ollama local)...")
    topic, script = script_generator.generate_short_script(topic=args.topic, seconds=args.seconds)
    print(f"    Sujet: {topic} ({len(script.split())} mots)")

    print("    Generation du titre/description/tags optimises (Ollama)...")
    metadata = script_generator.generate_metadata(topic, script)
    if "#shorts" not in metadata["title"].lower():
        metadata["title"] = f"{metadata['title']} #Shorts"[:100]
    if "#shorts" not in metadata["description"].lower():
        metadata["description"] = f"{metadata['description']}\n\n#Shorts"[:5000]
    if "shorts" not in [t.lower() for t in metadata["tags"]]:
        metadata["tags"] = (metadata["tags"] + ["shorts"])[:15]
    print(f"    Titre: {metadata['title']}")

    print("2/6 - Generation de la voix off (edge-tts) + timings mot par mot...")
    raw_audio_path, timing_path = voice_generator.generate_voice_with_timing(
        script, out_path=os.path.join(config.AUDIO_DIR, f"voiceover_{run_id}.mp3")
    )
    print(f"    Audio -> {raw_audio_path}")

    print("    Mixage d'une musique de fond discrete...")
    audio_path = video_assembler.mix_background_music(raw_audio_path)
    print(f"    Audio (avec musique) -> {audio_path}")

    with open(timing_path, "r", encoding="utf-8") as f:
        word_boundaries = json.load(f)
    if word_boundaries:
        total_seconds = (word_boundaries[-1]["offset"] + word_boundaries[-1]["duration"]) / 10_000_000
        print(f"    Duree audio: {total_seconds:.1f}s")
        if total_seconds > config.SHORTS_MAX_SECONDS:
            print(f"    [warn] Duree ({total_seconds:.1f}s) au-dela de {config.SHORTS_MAX_SECONDS}s : "
                  "YouTube pourrait ne plus classer cette video comme Short.")

    print("3/6 - Recherche de visuels portrait pertinents (Pexels)...")
    paragraphs = chunk_script(script, target_words=config.SHORTS_WORDS_PER_SEGMENT)
    run_stock_dir = os.path.join(config.STOCK_DIR, f"_shorts_run_{run_id}")
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
        clip_path = visuals_fetcher.fetch_one_clip(keyword, dest, orientation="portrait")
        print(f"    Segment {i + 1}/{len(paragraphs)}: \"{keyword}\" ({duration:.1f}s)"
              + ("" if clip_path else " -> ECHEC, ignore"))
        if clip_path:
            segments.append((clip_path, duration))

    if not segments:
        raise RuntimeError("Aucun visuel n'a pu etre recupere pour aucun segment du script.")

    segments = _merge_short_segments(segments, config.SHORTS_MIN_SEGMENT_SECONDS)
    print(f"    {len(segments)} segments visuels apres fusion des coupes trop courtes")

    os.makedirs(config.VIDEO_DIR, exist_ok=True)
    raw_video_path = video_assembler.assemble_video_from_segments(
        audio_path, segments, out_path=os.path.join(config.VIDEO_DIR, f"_tmp_short_sans_sous_titres_{run_id}.mp4"),
        width=config.SHORTS_WIDTH, height=config.SHORTS_HEIGHT,
    )
    print(f"    Video (sans sous-titres) -> {raw_video_path}")
    shutil.rmtree(run_stock_dir, ignore_errors=True)

    folder_name = make_output_folder_name(topic)
    video_folder = os.path.join(config.PUBLISHED_DIR, folder_name)
    os.makedirs(video_folder, exist_ok=True)
    print(f"    Dossier de la video -> {video_folder}")

    print("4/6 - Generation et gravure des sous-titres dynamiques (format vertical)...")
    ass_path = subtitles.build_ass_from_timing_file(
        timing_path, os.path.join(config.VIDEO_DIR, f"_tmp_short_subtitles_{run_id}.ass"), shorts=True
    )
    video_path = video_assembler.burn_subtitles(
        raw_video_path, ass_path, os.path.join(video_folder, "short.mp4")
    )
    print(f"    Video finale (avec sous-titres) -> {video_path}")

    for tmp_file in (raw_video_path, ass_path, raw_audio_path, audio_path, timing_path):
        try:
            os.remove(tmp_file)
        except OSError:
            pass

    print("5/6 - Ecriture de la note titre/description/tags...")
    note_path = os.path.join(video_folder, "metadata.txt")
    write_metadata_note(metadata, note_path)
    print(f"    Note -> {note_path}")

    if args.publish:
        print("6/6 - Publication sur YouTube...")
        video_id = youtube_uploader.upload_video(
            video_path, metadata["title"], metadata["description"], tags=metadata["tags"],
        )
        print(f"    Video publiee: https://youtu.be/{video_id}")
    else:
        print("6/6 - Publication ignoree (ajoute --publish pour publier automatiquement).")

    print("Termine.")


if __name__ == "__main__":
    main()
