import io
import urllib.error

import pytest

import config
import net_retry
import visuals_fetcher


def test_missing_pexels_key_is_not_swallowed(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEXELS_API_KEY", "")
    with pytest.raises(net_retry.MissingSecretError, match="PEXELS_API_KEY"):
        visuals_fetcher.fetch_one_clip("mountains", str(tmp_path / "c.mp4"))


def test_rejected_pexels_key_fails_fast(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEXELS_API_KEY", "bad")
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, io.BytesIO(b""))

    monkeypatch.setattr(visuals_fetcher.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(net_retry.MissingSecretError, match="refusee par Pexels"):
        visuals_fetcher.fetch_clips(2, out_dir=str(tmp_path))
    assert len(calls) == 1


def test_best_file_picks_smallest_hd_file():
    video = {"video_files": [
        {"width": 640, "height": 360, "link": "sd"},
        {"width": 3840, "height": 2160, "link": "4k"},
        {"width": 1920, "height": 1080, "link": "hd"},
    ]}
    assert visuals_fetcher._best_file(video) == "hd"
    assert visuals_fetcher._best_file({"video_files": []}) is None
