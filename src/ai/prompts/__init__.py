"""Versioned prompt registry for all LLM calls.

Prompts are stored as plain .md files under src/ai/prompts/{module}/{name}_v{N}.md.
All prompts are loaded eagerly at import time — a missing file raises FileNotFoundError
immediately so misconfiguration is caught before any request is processed.

Switching the active version for a prompt:
  Update the alias constant (e.g. PROMPT_DETECT_SKILLS) to point to the desired
  versioned constant (e.g. SIGNALS_DETECT_SKILLS_V1 instead of V2).

Adding a new prompt version:
  1. Create the .md file (copy previous version, make edits).
  2. Add a versioned constant below.
  3. Update the alias to point to the new version.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parent


def _load(relative_path: str) -> str:
    full = _ROOT / relative_path
    return full.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# signals — step 07 (skill + context detection)
# ---------------------------------------------------------------------------

# v1: unified prompt (pre-split, from commit HEAD~1 of architecture-migration)
#     includes themes, activities, emotions, energy, task_type in one call.
#     uses {theme_names} placeholder in addition to the v2 shared placeholders.
SIGNALS_DETECT_SKILLS_V1 = _load("signals/detect_skills_v1.md")

# v2: skills-only prompt (parallel split architecture, temperature=0.15)
SIGNALS_DETECT_SKILLS_V2 = _load("signals/detect_skills_v2.md")

# v2: context-only prompt (activities / emotions / energy / task_type, temperature=0.35)
SIGNALS_DETECT_CONTEXT_V2 = _load("signals/detect_context_v2.md")

# Active aliases — change these to switch versions
PROMPT_DETECT_SKILLS = SIGNALS_DETECT_SKILLS_V2
PROMPT_DETECT_CONTEXT = SIGNALS_DETECT_CONTEXT_V2

# ---------------------------------------------------------------------------
# ollama — async helpers (extract_activities, assess_quality, generate_insight)
# ---------------------------------------------------------------------------

OLLAMA_EXTRACT_ACTIVITIES_V1 = _load("ollama/extract_activities_v1.md")
OLLAMA_ASSESS_QUALITY_V1 = _load("ollama/assess_quality_v1.md")
OLLAMA_GENERATE_INSIGHT_V1 = _load("ollama/generate_insight_v1.md")

# Active aliases
PROMPT_EXTRACT_ACTIVITIES = OLLAMA_EXTRACT_ACTIVITIES_V1
PROMPT_ASSESS_QUALITY = OLLAMA_ASSESS_QUALITY_V1
PROMPT_GENERATE_INSIGHT = OLLAMA_GENERATE_INSIGHT_V1
