import io
import json
import urllib.error

import pytest

import config
import script_generator as sg


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def ollama_server(monkeypatch, behaviours):
    """behaviours: dict modele -> liste d'exceptions/reponses successives."""
    calls = []

    def fake_urlopen(req, timeout):
        model = json.loads(req.data)["model"]
        calls.append(model)
        outcome = behaviours[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(json.dumps(outcome).encode())

    monkeypatch.setattr(sg.urllib.request, "urlopen", fake_urlopen)
    return calls


def not_found():
    return urllib.error.HTTPError(config.OLLAMA_URL, 404, "model not found", None, io.BytesIO(b""))


def test_call_ollama_retries_transient_errors(monkeypatch):
    calls = ollama_server(monkeypatch, {config.OLLAMA_MODEL: [TimeoutError(), {"response": " hello "}]})
    assert sg._call_ollama("p") == "hello"
    assert calls == [config.OLLAMA_MODEL, config.OLLAMA_MODEL]


def test_call_ollama_falls_back_to_next_model(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_FALLBACK_MODELS", ["backup:1b"])
    calls = ollama_server(monkeypatch, {
        config.OLLAMA_MODEL: [not_found()],
        "backup:1b": [{"response": "from backup"}],
    })
    assert sg._call_ollama("p") == "from backup"
    assert calls == [config.OLLAMA_MODEL, "backup:1b"]


def test_call_ollama_error_field_triggers_fallback(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_FALLBACK_MODELS", ["backup:1b"])
    ollama_server(monkeypatch, {
        config.OLLAMA_MODEL: [{"error": "out of memory"}],
        "backup:1b": [{"response": "ok"}],
    })
    assert sg._call_ollama("p") == "ok"


def test_call_ollama_model_missing_gives_pull_hint(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_FALLBACK_MODELS", [])
    ollama_server(monkeypatch, {config.OLLAMA_MODEL: [not_found()]})
    with pytest.raises(sg.OllamaError, match="ollama pull"):
        sg._call_ollama("p")


def test_call_ollama_unreachable_server_does_not_try_fallbacks(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_FALLBACK_MODELS", ["backup:1b"])
    calls = ollama_server(monkeypatch, {config.OLLAMA_MODEL: [urllib.error.URLError("refused")] * 3})
    with pytest.raises(sg.OllamaError, match="ollama serve"):
        sg._call_ollama("p")
    assert "backup:1b" not in calls


def test_generate_short_script_surfaces_ollama_error(monkeypatch):
    def boom(prompt):
        raise sg.OllamaError("Impossible de contacter Ollama")
    monkeypatch.setattr(sg, "_call_ollama", boom)
    with pytest.raises(sg.OllamaError, match="Impossible de contacter Ollama"):
        sg.generate_short_script(topic="discipline")


def test_clean_script_strips_markdown():
    assert sg._clean_script("# Title\n**Bold** and _it_\n1. Step") == "Bold and it\nStep"


def test_truncate_to_target_keeps_last_sentence():
    script = " ".join(f"Sentence number {i} here." for i in range(20)) + " Final reveal."
    out = sg._truncate_to_target(script, target_words=12)
    assert out.endswith("Final reveal.")
    assert len(out.split()) < len(script.split())


def test_truncate_to_target_leaves_short_script_untouched():
    assert sg._truncate_to_target("Short. Script.", target_words=50) == "Short. Script."
