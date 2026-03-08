"""Ollama client adapter with graceful fallbacks."""

from __future__ import annotations

from typing import Any

import httpx

from src.ai.runtime_config import get_ollama_defaults


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        default_base_url, default_model, default_timeout = get_ollama_defaults()
        self.base_url = (base_url or default_base_url).rstrip("/")
        self.model = model or default_model
        self.timeout = timeout if timeout is not None else default_timeout

    def health(self) -> dict[str, Any]:
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
        self, prompt: str, *, system: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if system:
            body["system"] = system
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/generate", json=body)
            resp.raise_for_status()
            payload = resp.json()
            return {
                "raw": payload,
                "response": payload.get("response", "{}"),
            }

    def embed(self, text: str) -> list[float]:
        body = {"model": self.model, "prompt": text}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/embeddings", json=body)
            resp.raise_for_status()
            payload = resp.json()
            vector = payload.get("embedding", [])
            return [float(v) for v in vector]
