"""Unit tests for src.ai.ollama async interfaces and fallbacks."""

from __future__ import annotations

import json

import httpx
import pytest

import src.ai.ollama as ollama_module
from src.ai.ollama import OllamaClient


class _FakeResponse:
    def __init__(self, payload: dict, *, status_error: Exception | None = None) -> None:
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error:
            raise self._status_error

    def json(self) -> dict:
        return self._payload


class _SyncClient:
    def __init__(
        self,
        *,
        health_payload=None,
        gen_payload=None,
        emb_payload=None,
        fail=False,
        **kwargs,
    ):
        self.health_payload = health_payload or {
            "models": [{"name": "llama3.2:latest"}]
        }
        self.gen_payload = gen_payload or {"response": "{}"}
        self.emb_payload = emb_payload or {"embedding": [1, 2.5]}
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, _url: str):
        if self.fail:
            raise httpx.RequestError("offline")
        return _FakeResponse(self.health_payload)

    def post(self, url: str, json: dict):
        if self.fail:
            raise httpx.RequestError("offline")
        if url.endswith("/api/embeddings"):
            return _FakeResponse(self.emb_payload)
        return _FakeResponse(self.gen_payload)


@pytest.mark.asyncio
async def test_is_available_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url: str):
            return _FakeResponse({"models": []})

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", _Client)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    assert await client.is_available() is True


def test_sync_health_generate_json_and_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama_module.httpx, "Client", _SyncClient)
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")

    health = client.health()
    generated = client.generate_json("prompt", system="sys")
    embedding = client.embed("hello")

    assert health["connected"] is True
    assert health["model_available"] is True
    assert generated["response"] == "{}"
    assert embedding == [1.0, 2.5]


def test_sync_health_returns_disconnected_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ollama_module.httpx, "Client", lambda **kwargs: _SyncClient(fail=True)
    )
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    out = client.health()
    assert out["connected"] is False
    assert out["model_available"] is False


@pytest.mark.asyncio
async def test_is_available_returns_false_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url: str):
            raise httpx.RequestError("offline")

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", _Client)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    assert await client.is_available() is False


def test_clean_json_response_strips_markdown_fences() -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    raw = '```json\n{"ok": true}\n```'
    assert client._clean_json_response(raw) == '{"ok": true}'


@pytest.mark.asyncio
async def test_call_ollama_returns_response_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, json: dict):
            assert url.endswith("/api/generate")
            assert json["model"] == "llama3.2:latest"
            assert json["stream"] is False
            assert json["format"] == "json"
            return _FakeResponse({"response": '{"value": 1}'})

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", _Client)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    got = await client._call_ollama("hello")
    assert got == '{"value": 1}'


@pytest.mark.asyncio
async def test_call_ollama_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url: str, json: dict):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise httpx.TimeoutException("timeout")
            return _FakeResponse({"response": json_dumps({"ok": True})})

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(ollama_module.asyncio, "sleep", _fake_sleep)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    got = await client._call_ollama("retry")

    assert json.loads(got) == {"ok": True}
    assert attempts["count"] == 3
    assert sleeps == [1.0, 2.0]


@pytest.mark.asyncio
async def test_call_ollama_raises_after_retry_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url: str, json: dict):
            raise httpx.RequestError("connection refused")

    async def _fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(ollama_module.asyncio, "sleep", _fake_sleep)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    with pytest.raises(httpx.RequestError):
        await client._call_ollama("retry")


@pytest.mark.asyncio
async def test_call_ollama_non_retriable_http_error_is_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url: str, json: dict):
            req = httpx.Request("POST", "http://localhost:11434/api/generate")
            resp = httpx.Response(500, request=req)
            return _FakeResponse(
                {"response": "{}"},
                status_error=httpx.HTTPStatusError("bad", request=req, response=resp),
            )

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", _Client)

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    with pytest.raises(httpx.HTTPStatusError):
        await client._call_ollama("boom")


@pytest.mark.asyncio
async def test_extract_activities_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call(_prompt: str) -> str:
        return json_dumps(
            [
                {
                    "activity": "Python Programming",
                    "duration_minutes": 60,
                    "notes": "Focus",
                }
            ]
        )

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    monkeypatch.setattr(client, "_call_ollama", _fake_call)

    out = await client.extract_activities("I coded")
    assert out and out[0]["activity"] == "Python Programming"


@pytest.mark.asyncio
async def test_extract_activities_invalid_json_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_call(_prompt: str) -> str:
        return "not-json"

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    monkeypatch.setattr(client, "_call_ollama", _fake_call)

    assert await client.extract_activities("I coded") == []


@pytest.mark.asyncio
async def test_extract_activities_non_list_shape_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_call(_prompt: str) -> str:
        return json_dumps({"activity": "Coding"})

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    monkeypatch.setattr(client, "_call_ollama", _fake_call)
    assert await client.extract_activities("I coded") == []


@pytest.mark.asyncio
async def test_assess_quality_returns_fallback_on_bad_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_call(_prompt: str) -> str:
        return json_dumps({"reasoning": "missing multiplier"})

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    monkeypatch.setattr(client, "_call_ollama", _fake_call)

    assert await client.assess_quality("Coding", "Focused") == {
        "quality_multiplier": 1.0,
        "reasoning": "Default (Ollama unavailable)",
    }


@pytest.mark.asyncio
async def test_assess_quality_returns_fallback_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_call(_prompt: str) -> str:
        raise RuntimeError("boom")

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    monkeypatch.setattr(client, "_call_ollama", _fake_call)
    assert await client.assess_quality("Coding", "Focused") == {
        "quality_multiplier": 1.0,
        "reasoning": "Default (Ollama unavailable)",
    }


@pytest.mark.asyncio
async def test_generate_insight_success_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")

    async def _good_call(_prompt: str) -> str:
        return (
            "```json\n"
            + json_dumps(
                {
                    "insight_text": "Great momentum. Keep a daily review loop.",
                    "category": "skill_development",
                    "confidence": 0.88,
                }
            )
            + "\n```"
        )

    monkeypatch.setattr(client, "_call_ollama", _good_call)
    out = await client.generate_insight("summary", ["ctx1"])
    assert out["category"] == "skill_development"

    async def _bad_call(_prompt: str) -> str:
        return json_dumps({"category": "general", "confidence": 0.2})

    monkeypatch.setattr(client, "_call_ollama", _bad_call)
    fallback = await client.generate_insight("summary", [])
    assert fallback == {
        "insight_text": "Keep practicing consistently.",
        "category": "general",
        "confidence": 0.5,
    }


@pytest.mark.asyncio
async def test_generate_insight_returns_fallback_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_call(_prompt: str) -> str:
        raise RuntimeError("llm down")

    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    monkeypatch.setattr(client, "_call_ollama", _fake_call)
    out = await client.generate_insight("summary", ["ctx"])
    assert out == {
        "insight_text": "Keep practicing consistently.",
        "category": "general",
        "confidence": 0.5,
    }


def json_dumps(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"))
