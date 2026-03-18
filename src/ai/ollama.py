"""Ollama client adapter with graceful fallbacks."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from loguru import logger

from src.ai.prompts import PROMPT_ASSESS_QUALITY as _PROMPT_ASSESS_QUALITY
from src.ai.prompts import PROMPT_EXTRACT_ACTIVITIES as _PROMPT_EXTRACT_ACTIVITIES
from src.ai.prompts import PROMPT_GENERATE_INSIGHT as _PROMPT_GENERATE_INSIGHT
from src.ai.runtime_config import get_ollama_defaults
from src.ai.tx_guard import assert_network_allowed

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds


class OllamaClient:
    """Client for Ollama LLM integration with sync and async interfaces."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialise Ollama client, loading defaults from runtime config.

        Args:
            base_url: Ollama API root URL (overrides config/env).
            model: Model identifier (overrides config/env).
            timeout: Request timeout in seconds (overrides config/env).
        """
        default_base_url, default_model, default_timeout = get_ollama_defaults()
        self.base_url = (base_url or default_base_url).rstrip("/")
        self.model = model or default_model
        self.timeout = timeout if timeout is not None else default_timeout

        logger.info(f"Ollama client initialised: {self.base_url}, model={self.model}")

    # ------------------------------------------------------------------ #
    # Synchronous helpers (kept for backward compatibility)               #
    # ------------------------------------------------------------------ #

    def health(self) -> dict[str, Any]:
        """Synchronous health check against /api/tags.

        Returns:
            Dict with keys: connected, model_available, models (and error on failure).
        """
        assert_network_allowed("ollama.health")
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                payload = resp.json()
                model_names = [m.get("name", "") for m in payload.get("models", [])]
                return {
                    "connected": True,
                    "model_available": any(self.model in n for n in model_names),
                    "models": model_names,
                }
        except Exception as exc:
            return {
                "connected": False,
                "error": str(exc),
                "model_available": False,
                "models": [],
            }

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Synchronous JSON generation via /api/generate.

        Args:
            prompt:      User-facing prompt text.
            system:      Optional system prompt.
            temperature: Sampling temperature (0.0–1.0).  Passed as
                         ``options.temperature`` in the Ollama request body.

        Returns:
            Dict with keys: raw (full Ollama payload), response (text).
        """
        assert_network_allowed("ollama.generate_json")
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if system:
            body["system"] = system
        if temperature is not None:
            body["options"] = {"temperature": temperature}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/generate", json=body)
            resp.raise_for_status()
            payload = resp.json()
            return {
                "raw": payload,
                "response": payload.get("response", "{}"),
            }

    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        assert_network_allowed("ollama.embed")
        body = {"model": self.model, "prompt": text}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/embeddings", json=body)
            resp.raise_for_status()
            payload = resp.json()
            vector = payload.get("embedding", [])
            return [float(v) for v in vector]

    # ------------------------------------------------------------------ #
    # Async public interface                                               #
    # ------------------------------------------------------------------ #

    async def is_available(self) -> bool:
        """Check asynchronously whether the Ollama service is reachable.

        Returns:
            True if the service responds to a health probe, False otherwise.
        """
        assert_network_allowed("ollama.is_available")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                logger.debug("Ollama health check passed")
                return True
        except Exception as exc:
            logger.warning(f"Ollama unavailable: {exc}")
            return False

    async def extract_activities(self, raw_text: str) -> list[dict[str, Any]]:
        """Extract structured activities from a journal entry.

        Args:
            raw_text: Raw journal entry text.

        Returns:
            List of activity dicts, each with keys:
            ``activity``, ``duration_minutes``, ``notes``.
            Returns ``[]`` on any failure.
        """
        prompt = _PROMPT_EXTRACT_ACTIVITIES.format(raw_text=raw_text)
        try:
            raw = await self._call_ollama(prompt)
            cleaned = self._clean_json_response(raw)
            result = json.loads(cleaned)
            if isinstance(result, list):
                logger.debug(f"Extracted {len(result)} activities")
                return result
            logger.warning("extract_activities: unexpected JSON shape, returning []")
            return []
        except Exception as exc:
            logger.warning(f"extract_activities failed ({exc}), returning fallback")
            return []

    async def assess_quality(self, activity: str, description: str) -> dict[str, Any]:
        """Assess the deliberate practice quality of a described activity.

        Args:
            activity: Activity name (e.g. "Python Programming").
            description: Activity description as written in the journal.

        Returns:
            Dict with keys ``quality_multiplier`` (float, 0.5–2.0) and
            ``reasoning`` (str). Falls back to multiplier 1.0 on any failure.
        """
        _FALLBACK: dict[str, Any] = {
            "quality_multiplier": 1.0,
            "reasoning": "Default (Ollama unavailable)",
        }
        prompt = _PROMPT_ASSESS_QUALITY.format(
            activity_name=activity,
            activity_description=description,
        )
        try:
            raw = await self._call_ollama(prompt)
            cleaned = self._clean_json_response(raw)
            result = json.loads(cleaned)
            if isinstance(result, dict) and "quality_multiplier" in result:
                logger.debug(f"Quality assessed: {result.get('quality_multiplier')}")
                return result
            logger.warning("assess_quality: unexpected JSON shape, returning fallback")
            return _FALLBACK
        except Exception as exc:
            logger.warning(f"assess_quality failed ({exc}), returning fallback")
            return _FALLBACK

    async def generate_insight(
        self,
        entry_summary: str,
        rag_context: list[str],
    ) -> dict[str, Any]:
        """Generate a personalised coaching insight using RAG context.

        Args:
            entry_summary: Short summary of the user's journal entry.
            rag_context: Relevant passages retrieved from the knowledge base.

        Returns:
            Dict with keys ``insight_text``, ``category``, ``confidence``.
            Falls back to a generic encouragement string on any failure.
        """
        _FALLBACK: dict[str, Any] = {
            "insight_text": "Keep practicing consistently.",
            "category": "general",
            "confidence": 0.5,
        }
        rag_formatted = (
            "\n".join(f"- {c}" for c in rag_context)
            if rag_context
            else "No prior context available."
        )
        prompt = _PROMPT_GENERATE_INSIGHT.format(
            entry_summary=entry_summary,
            rag_context=rag_formatted,
        )
        try:
            raw = await self._call_ollama(prompt)
            cleaned = self._clean_json_response(raw)
            result = json.loads(cleaned)
            if isinstance(result, dict) and "insight_text" in result:
                logger.debug("Insight generated successfully")
                return result
            logger.warning(
                "generate_insight: unexpected JSON shape, returning fallback"
            )
            return _FALLBACK
        except Exception as exc:
            logger.warning(f"generate_insight failed ({exc}), returning fallback")
            return _FALLBACK

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _call_ollama(self, prompt: str) -> str:
        """POST a prompt to Ollama with retry and exponential back-off.

        Args:
            prompt: Fully rendered prompt string.

        Returns:
            Raw ``response`` string from the Ollama payload.

        Raises:
            httpx.RequestError: When all retry attempts are exhausted.
        """
        assert_network_allowed("ollama._call_ollama")
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(f"{self.base_url}/api/generate", json=body)
                    resp.raise_for_status()
                    payload = resp.json()
                    return payload.get("response", "{}")
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_exc = exc
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"Ollama attempt {attempt}/{_MAX_RETRIES} failed: {exc}. "
                    f"Retrying in {wait:.1f}s…"
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(wait)
            except Exception as exc:
                logger.error(f"Ollama non-retriable error: {exc}")
                raise

        raise httpx.RequestError(
            f"Ollama unreachable after {_MAX_RETRIES} attempts"
        ) from last_exc

    def _clean_json_response(self, response: str) -> str:
        """Strip markdown fences from an Ollama response to obtain raw JSON.

        Handles both ` ```json … ``` ` and plain ` ``` … ``` ` fences.

        Args:
            response: Raw string returned by Ollama.

        Returns:
            Cleaned string suitable for ``json.loads()``.
        """
        cleaned = re.sub(r"^```(?:json)?\s*", "", response.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()
