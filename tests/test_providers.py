import json
from io import BytesIO

import pytest

from clipper.models import Candidate
from clipper.providers import OllamaRanker, OpenAICompatibleRanker


def _candidate(identifier: str = "clip-one", start: float = 10) -> Candidate:
    return Candidate(
        id=identifier,
        start=start,
        end=start + 21,
        transcript="You replaced the mayor with a robot? Nobody noticed for weeks!",
        segment_indices=(0, 1),
    )


def test_openai_ranker_accepts_dimensions_object_returned_by_small_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    dimensions = {
        "humor": 0.9,
        "punchline": 0.9,
        "surprise": 0.8,
        "quotability": 0.7,
        "hook": 0.8,
        "standalone": 0.9,
        "pacing": 0.7,
        "reaction": 0.6,
        "retention": 0.8,
        "overall": 0.85,
    }
    content = json.dumps(
        {"scores": [{"id": "clip-one", "dimensions": dimensions, "explanation": "Clear joke."}]}
    )
    response = {"choices": [{"message": {"role": "assistant", "content": content}}]}

    class FakeResponse(BytesIO):
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    monkeypatch.setenv("TEST_LLM_KEY", "ollama")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse(json.dumps(response).encode()),
    )

    ranked = OpenAICompatibleRanker("http://127.0.0.1:11434/v1", "qwen3:1.7b", "TEST_LLM_KEY").rank(
        [candidate]
    )

    assert ranked[0].score.overall == 0.85
    assert ranked[0].score.explanation == "Clear joke."


def test_ollama_ranker_calls_native_chat_api_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    values = {
        "id": "clip-one",
        "humor": 0.92,
        "punchline": 0.88,
        "surprise": 0.8,
        "quotability": 0.72,
        "hook": 0.84,
        "standalone": 0.9,
        "pacing": 0.76,
        "reaction": 0.65,
        "retention": 0.82,
        "overall": 0.86,
        "explanation": "Fast setup and a clean absurd payoff.",
    }
    response = {"message": {"content": json.dumps({"scores": [values]})}}
    captured: dict[str, object] = {}

    class FakeResponse(BytesIO):
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    def fake_open(request: object, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url  # type: ignore[attr-defined]
        captured["payload"] = json.loads(request.data)  # type: ignore[attr-defined]
        captured["timeout"] = timeout
        return FakeResponse(json.dumps(response).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_open)

    ranked = OllamaRanker("http://127.0.0.1:11434", "qwen3:1.7b").rank([candidate])

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "qwen3:1.7b"  # type: ignore[index]
    assert captured["payload"]["think"] is False  # type: ignore[index]
    assert ranked[0].score.overall == 0.86
    assert ranked[0].score.explanation == "Fast setup and a clean absurd payoff."


def test_ollama_ranker_falls_back_to_heuristics_when_local_service_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()

    def fail_open(request: object, timeout: float) -> None:
        del request, timeout
        raise OSError("Ollama offline")

    monkeypatch.setattr("urllib.request.urlopen", fail_open)

    ranked = OllamaRanker("http://127.0.0.1:11434", "qwen3:1.7b").rank([candidate])

    assert len(ranked) == 1
    assert ranked[0].candidate == candidate
    assert 0 <= ranked[0].score.overall <= 1
