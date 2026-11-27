import re

import long_montage
import subtitles


def _words(n, step=0.4):
    return [{"text": f"word{i}" + ("." if i % 9 == 8 else ""), "offset": int((0.2 + i * step) * 1e7),
             "duration": int(0.3 * 1e7)} for i in range(n)]


def test_plan_shots_covers_timeline_without_gaps():
    words = _words(150)
    starts = [w["offset"] / 1e7 for w in words]
    scenes = [{"start": 0.0, "clips": ["a", "b", "c"]}, {"start": 20.2, "clips": ["d"]}, {"start": 41.0, "clips": ["e", "f"]}]
    shots = long_montage.plan_shots(scenes, starts, 60.0, seed=1)
    assert shots[0]["start"] == 0.0 and shots[-1]["end"] == 60.0
    for a, b in zip(shots, shots[1:]):
        assert a["end"] == b["start"]
    # rythme : aucun plan interminable, aucun plan "flash"
    assert all(1.0 <= s["end"] - s["start"] <= 6.5 for s in shots)
    # les coupes internes tombent sur un debut de mot
    for s in shots[1:]:
        assert any(abs(s["start"] - w) < 1e-9 for w in starts) or s["start"] in (20.2, 41.0)
    # plusieurs clips par scene utilises a tour de role, jamais deux mouvements identiques de suite
    assert {s["clip"] for s in shots if s["scene"] == 0} == {"a", "b", "c"}
    assert all(a["motion"] != b["motion"] for a, b in zip(shots, shots[1:]))


def test_long_ass_word_highlight_does_not_leak_and_has_kickers(tmp_path):
    words = _words(80)
    words[12]["text"] = "discipline"
    out = subtitles.build_long_dynamic_ass(words, str(tmp_path / "s.ass"), [0.0, 15.0], 33.0)
    txt = open(out, encoding="utf-8").read()
    subs = [l for l in txt.splitlines() if l.startswith("Dialogue: 0,")]
    assert subs
    # chaque mot repart de l'etat de base (\r), sinon le jaune deborde sur les mots suivants
    for l in subs:
        assert l.count(r"{\r") == len(l.split(",,", 1)[1].split(" "))
    kick = [l for l in txt.splitlines() if l.startswith("Dialogue: 1,")]
    assert any("DISCIPLINE" in l for l in kick)
    assert any(l.startswith("Dialogue: 2,") for l in txt.splitlines())  # barre de progression


def test_pick_keywords_respects_min_gap():
    words = _words(200, step=0.3)
    for i in range(0, 200, 5):
        words[i]["text"] = "discipline"
    picked = subtitles.pick_keywords(words, [0.0], 60.0, min_gap=7.0)
    times = [t for _, t in picked]
    assert all(b - a >= 7.0 for a, b in zip(times, times[1:]))
