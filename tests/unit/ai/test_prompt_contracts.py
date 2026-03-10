"""Smoke contract tests for prompt JSON shape and deterministic parsing."""

from __future__ import annotations

import json

import pytest

from src.ai.ollama import OllamaClient


def _required_sections(prompt: str) -> None:
    for section in (
        "# Mission",
        "# INSTRUCTIONS AND STEPS",
        "# FORMAT OF ELEMENTS",
        "# PERSONALITY",
        "# RULES",
    ):
        assert section in prompt


@pytest.mark.asyncio
async def test_extract_activities_prompt_contract_and_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    captured = {"prompt": ""}

    async def _fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            [{"activity": "Running", "duration_minutes": 30, "notes": "easy pace"}],
            separators=(",", ":"),
        )

    monkeypatch.setattr(client, "_call_ollama", _fake_call)
    first = await client.extract_activities("Today I ran.")
    second = await client.extract_activities("Today I ran.")

    _required_sections(captured["prompt"])
    assert first == second
    assert first[0]["activity"] == "Running"


@pytest.mark.asyncio
async def test_assess_quality_prompt_contract_and_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    captured = {"prompt": ""}

    async def _fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            {
                "quality_multiplier": 1.5,
                "reasoning": "Clear goals and immediate feedback.",
            },
            separators=(",", ":"),
        )

    monkeypatch.setattr(client, "_call_ollama", _fake_call)
    out = await client.assess_quality("Coding", "Practiced with test feedback")

    _required_sections(captured["prompt"])
    assert set(out.keys()) == {"quality_multiplier", "reasoning"}


@pytest.mark.asyncio
async def test_generate_insight_prompt_contract_and_deterministic_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OllamaClient(base_url="http://localhost:11434", model="llama3.2:latest")
    captured = {"prompt": ""}

    response = {
        "insight_text": "You are consistent. Add one weekly review checkpoint.",
        "category": "skill_development",
        "confidence": 0.87,
    }

    async def _fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return "```json\n" + json.dumps(response, separators=(",", ":")) + "\n```"

    monkeypatch.setattr(client, "_call_ollama", _fake_call)
    first = await client.generate_insight("summary", ["context A", "context B"])
    second = await client.generate_insight("summary", ["context A", "context B"])

    _required_sections(captured["prompt"])
    assert first == second == response
