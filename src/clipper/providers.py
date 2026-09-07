"""Swappable transcript-only ranking providers."""

import json
import os
import urllib.request
from typing import Protocol

from clipper.models import Candidate, RankedCandidate, Score
from clipper.ranking import HeuristicRanker, choose_diverse


class Ranker(Protocol):
    def rank(self, candidates: list[Candidate]) -> list[RankedCandidate]: ...


_SCORE_FIELDS = (
    "humor",
    "punchline",
    "surprise",
    "quotability",
    "hook",
    "standalone",
    "pacing",
    "reaction",
    "retention",
    "overall",
)

_OLLAMA_FORMAT = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    **{
                        field: {"type": "number", "minimum": 0, "maximum": 1}
                        for field in _SCORE_FIELDS
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["id", *_SCORE_FIELDS, "explanation"],
            },
        }
    },
    "required": ["scores"],
}


class OllamaRanker:
    """Use a small local Ollama model, with bounded work and an offline fallback."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:1.7b",
        *,
        batch_size: int = 8,
        max_candidates: int = 24,
        timeout: float = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.max_candidates = max_candidates
        self.timeout = timeout

    def rank(self, candidates: list[Candidate]) -> list[RankedCandidate]:
        if not candidates:
            return []
        baseline = HeuristicRanker().rank(candidates)
        shortlist = choose_diverse(
            baseline,
            min(self.max_candidates, len(baseline)),
            minimum=min(8, len(baseline)),
        )
        if not shortlist:
            shortlist = baseline[: self.max_candidates]
        model_scores: dict[str, Score] = {}
        for offset in range(0, len(shortlist), self.batch_size):
            batch = [item.candidate for item in shortlist[offset : offset + self.batch_size]]
            try:
                model_scores.update(self._score_batch(batch))
            except (OSError, TimeoutError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        if not model_scores:
            return baseline
        ranked: list[RankedCandidate] = []
        for item in baseline:
            score = model_scores.get(item.candidate.id)
            if score is None:
                score = item.score.model_copy(
                    update={
                        "overall": round(item.score.overall * 0.5, 4),
                        "explanation": "Heuristic reserve candidate outside the Ollama shortlist.",
                    }
                )
            ranked.append(RankedCandidate(candidate=item.candidate, score=score))
        return sorted(ranked, key=lambda item: (-item.score.overall, item.candidate.start))

    def _score_batch(self, candidates: list[Candidate]) -> dict[str, Score]:
        compact = [
            {
                "id": candidate.id,
                "start": round(candidate.start, 3),
                "end": round(candidate.end, 3),
                "transcript": candidate.transcript,
                "signals": candidate.features,
            }
            for candidate in candidates
        ]
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": _OLLAMA_FORMAT,
            "keep_alive": "15m",
            "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a ruthless short-form comedy editor. Score every supplied clip "
                        "in the transcript's original language. Reward a fast hook, a complete "
                        "setup and payoff, genuine humor or surprise, quotability, clear "
                        "standalone context, reactions, pacing, and replay/retention potential. "
                        "Penalize filler, "
                        "exposition, clipped context, and weak endings. Each numeric score must be "
                        "between 0 and 1. Explanations must be one concrete sentence. Return only "
                        "the requested JSON and preserve every candidate id exactly."
                    ),
                },
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            response_payload = json.loads(response.read())
        content = response_payload["message"]["content"]
        returned = json.loads(content)["scores"]
        allowed_ids = {candidate.id for candidate in candidates}
        scores: dict[str, Score] = {}
        for values in returned:
            identifier = str(values.get("id", ""))
            if identifier in allowed_ids:
                scores[identifier] = _validated_score(values)
        return scores


class OpenAICompatibleRanker:
    """Call a compatible chat-completions endpoint with text/timestamps only."""

    def __init__(self, base_url: str, model: str, api_key_env: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env

    def rank(self, candidates: list[Candidate]) -> list[RankedCandidate]:
        if not candidates:
            return []
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"environment variable {self.api_key_env} is not set")
        compact = [
            {
                "id": candidate.id,
                "start": candidate.start,
                "end": candidate.end,
                "transcript": candidate.transcript,
                "timing_features": candidate.features,
            }
            for candidate in candidates
        ]
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Score each supplied short clip from 0..1 for humor, punchline, surprise, "
                        "quotability, hook, standalone, pacing, reaction, retention, and overall. "
                        "Return JSON {scores:[{id,...dimensions,explanation}]}. Never invent "
                        "context."
                    ),
                },
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            response_payload = json.loads(response.read())
        content = response_payload["choices"][0]["message"]["content"]
        score_payloads = {item["id"]: item for item in json.loads(content)["scores"]}
        fallback = HeuristicRanker()
        ranked: list[RankedCandidate] = []
        for candidate in candidates:
            values = score_payloads.get(candidate.id)
            if values is None:
                ranked.append(RankedCandidate(candidate=candidate, score=fallback.score(candidate)))
                continue
            dimensions = values.get("dimensions")
            score_values = (
                {**dimensions, "explanation": values.get("explanation", "")}
                if isinstance(dimensions, dict)
                else {key: value for key, value in values.items() if key != "id"}
            )
            score = _validated_score(score_values)
            ranked.append(RankedCandidate(candidate=candidate, score=score))
        return sorted(ranked, key=lambda item: (-item.score.overall, item.candidate.start))


def _validated_score(values: dict[str, object]) -> Score:
    dimensions = values.get("dimensions")
    raw = (
        {**dimensions, "explanation": values.get("explanation", "")}
        if isinstance(dimensions, dict)
        else values
    )
    normalized: dict[str, object] = {
        field: max(0.0, min(1.0, _as_float(raw[field]))) for field in _SCORE_FIELDS
    }
    normalized["explanation"] = str(raw.get("explanation", "Selected by the local judge."))
    return Score.model_validate(normalized)


def _as_float(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        raise TypeError("score values must be numeric")
    return float(value)
