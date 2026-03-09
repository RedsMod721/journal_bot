# Journal Bot Project Memory

## Project Overview
RPG Life Tracker — journal entries → XP/skills via a 17-step AI pipeline.
Branch convention: feature work on named branches, `main` as base for PRs.
Current active branch: `architecture-migration`

## Key Files
- [src/ai/ollama.py](src/ai/ollama.py) — Ollama LLM client (sync + async interfaces)
- [src/ai/runtime_config.py](src/ai/runtime_config.py) — config loader, exposes `get_ollama_defaults() -> (base_url, model, timeout)`
- [config/dev.yaml](config/dev.yaml) — YAML config, ai.ollama section: base_url, model, timeout
- [PROMPT_TEMPLATE.md](PROMPT_TEMPLATE.md) — template structure for all prompts sent to Ollama

## Patterns & Conventions
- Prompts sent to Ollama must follow PROMPT_TEMPLATE.md structure (Mission, Instructions, Format, Personality, Rules required; optional sections only when needed)
- Ollama client: sync methods (`health`, `generate_json`, `embed`) kept for backward compat; async methods added on top
- Async retry: 3 attempts, exponential backoff base 1.0s; retriable = TimeoutException/RequestError
- Fallbacks: extract_activities → [], assess_quality → {multiplier:1.0}, generate_insight → generic string
- Dependencies: httpx==0.26.0, loguru, pyyaml

## User Preferences
- Keep optional PROMPT_TEMPLATE.md sections out unless necessary
