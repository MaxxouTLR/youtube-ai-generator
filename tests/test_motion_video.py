"""Montage Motion des Shorts : decoupage en scenes (pur, sans Chromium) et repli du pipeline."""
import os

import motion_video


def _words(text, start=0.2, step=0.36):
    out, t = [], start
    for tok in text.split():
        out.append({"text": tok.rstrip(".?!"), "offset": int(t * 1e7), "duration": int(0.3 * 1e7)})
        t += step
        if tok[-1] in ".?!":
            out.append({"text": tok[-1], "offset": int(t * 1e7), "duration": 0})
            t += 0.3
    return out, t


def test_build_scenes_covers_whole_voice_and_strips_hashtags():
    words, total = _words("Most people quit after three days. But winners keep going. Why do you stop? Start small today.")
    data = motion_video.build_scenes(words, total, "Why you quit #Shorts", seed=7)
    scenes = data["scenes"]
    assert data["hook"] == "Why you quit"
    assert scenes[0]["start"] == 0.0 and scenes[-1]["end"] == total
    for a, b in zip(scenes, scenes[1:]):
        assert a["end"] == b["start"]
    # chaque mot prononce apparait dans une scene, dans l'ordre (le texte du script n'est pas modifie)
    spoken = [w["text"] for w in words if w["text"] not in ".?!"]
    assert [w["w"] for sc in scenes for w in sc["words"]] == spoken


def test_build_scenes_picks_counter_and_question():
    words, total = _words("You need 3 habits. Why do you wait? Start now.")
    kinds = [sc["type"] for sc in motion_video.build_scenes(words, total, "", seed=1)["scenes"]]
    assert kinds[0] == "counter"
    assert "question" in kinds


def test_build_scenes_is_deterministic_for_a_seed():
    words, total = _words("Discipline beats motivation every single day.")
    assert motion_video.build_scenes(words, total, "h", seed=42) == motion_video.build_scenes(words, total, "h", seed=42)


def test_engine_html_is_shipped_and_exposes_render():
    html = open(motion_video.ENGINE, encoding="utf-8").read()
    assert "/*DATA*/null" in html
    assert "window.render" in html and "window.ready" in html
