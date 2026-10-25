import pytest

import config
import net_retry

speechsdk = pytest.importorskip("azure.cognitiveservices.speech")
pytest.importorskip("googleapiclient")

import voice_generator  # noqa: E402
import youtube_uploader  # noqa: E402


def test_missing_azure_key_has_clear_message(monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.setenv("AZURE_SPEECH_REGION", "westeurope")
    with pytest.raises(net_retry.MissingSecretError, match="AZURE_SPEECH_KEY"):
        voice_generator._speech_config()


def test_transient_speech_errors_are_retried(monkeypatch, tmp_path):
    attempts = []

    class FakeSynth:
        def __init__(self, **kw):
            self.synthesis_word_boundary = type("E", (), {"connect": lambda self, cb: None})()

        def speak_ssml_async(self, ssml):
            return type("F", (), {"get": lambda self: None})()

    def fake_raise(result):
        attempts.append(1)
        if len(attempts) < 3:
            raise voice_generator.SpeechSynthesisError("throttled", transient=True)

    monkeypatch.setattr(voice_generator, "_speech_config", lambda: None)
    monkeypatch.setattr(voice_generator.speechsdk.audio, "AudioOutputConfig", lambda filename: None)
    monkeypatch.setattr(voice_generator.speechsdk, "SpeechSynthesizer", FakeSynth)
    monkeypatch.setattr(voice_generator, "_raise_if_failed", fake_raise)
    assert voice_generator._synthesize_with_timing("hi", str(tmp_path / "a.mp3"), "v", "+0%") == []
    assert len(attempts) == 3


def test_auth_speech_error_is_not_retried():
    err = voice_generator.SpeechSynthesisError("auth", transient=False)
    assert voice_generator._is_transient_speech_error(err) is False


def test_no_browser_login_in_ci(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(RuntimeError, match="YOUTUBE_TOKEN_B64"):
        youtube_uploader._get_credentials()


def test_corrupt_token_has_clear_message(monkeypatch, tmp_path):
    token = tmp_path / "token.json"
    token.write_bytes(b"")  # secret base64 vide -> fichier vide
    monkeypatch.setattr(config, "YOUTUBE_TOKEN_FILE", str(token))
    with pytest.raises(RuntimeError, match="illisible"):
        youtube_uploader._get_credentials()
