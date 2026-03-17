"""Step 07 — Detect skills, activities, emotions, energy, and task type.

Rule-based pre-pass always runs first; results are fed as soft hints to the LLM
when Ollama is available.

LLM enrichment does two things the rule-based pass cannot:
  1. Matches the entry against the user's existing skill roster *with descriptions*
     so it understands what each skill represents.
  2. Searches the 600+ GlobalSkill knowledge base for skills the user does NOT yet
     have, enabling skill discovery (e.g. detecting "Philosophy" for an entry about
     studying philosophy, even if the user only tracks "Mental Wellbeing").

When Ollama is unavailable the step falls back to the rule-based output, extended
with empty values for the new fields so the result shape is always identical.

Extending signals
-----------------
To add a new activity keyword, append to ``_ACTIVITY_PATTERNS``.
To add a new emotion, append to ``_EMOTION_KEYWORDS``.
To add a new task-type branch, add an ``elif`` block to ``_classify_task_type``.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword registries (module-level constants for easy extension/testing)
# ---------------------------------------------------------------------------

_ACTIVITY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("run", ("run", "runs", "ran", "running", "jog", "jogging", "sprint")),
    (
        "study",
        (
            "study",
            "studied",
            "studying",
            "flashcard",
            "lecture",
            "tutorial",
            "course",
            "research",
            "review",
        ),
    ),
    (
        "code",
        ("code", "coded", "coding", "programming", "python", "javascript", "debug"),
    ),
    ("write", ("write", "wrote", "writing", "draft", "drafted", "journaled")),
    ("read", ("read", "reading", "book", "article", "chapter")),
    (
        "workout",
        ("workout", "exercise", "exercised", "exercising", "gym", "training session"),
    ),
    (
        "pushup",
        ("pushup", "pushups", "push-up", "push-ups", "push up", "push ups"),
    ),
    (
        "strength_training",
        (
            "strength training",
            "resistance training",
            "weights",
            "lifting",
            "lifted",
            "barbell",
            "dumbbell",
        ),
    ),
    ("meditate", ("meditate", "meditated", "meditation", "mindfulness", "breathing")),
    ("walk", ("walk", "walked", "walking", "hike", "hiking", "stroll", "strolled")),
    ("practice", ("practice", "practiced", "practise", "practised", "drill")),
    ("build", ("build", "built", "ship", "shipped", "create", "created")),
]

_EMOTION_KEYWORDS: list[str] = [
    "happy",
    "sad",
    "angry",
    "anxious",
    "calm",
    "excited",
]

_CREATIVE_TOKENS: frozenset[str] = frozenset(["draw", "paint", "design", "compose"])
_PHYSICAL_TOKENS: frozenset[str] = frozenset(
    [
        "run",
        "lift",
        "swim",
        "walk",
        "workout",
        "exercise",
        "pushup",
        "strength training",
        "weights",
    ]
)
_SOCIAL_TOKENS: frozenset[str] = frozenset(["talk", "friend", "team", "meeting"])
_PHYSICAL_ACTIVITY_KEYS: frozenset[str] = frozenset(
    ["run", "workout", "pushup", "strength_training", "walk"]
)
_LEARNING_ACTIVITY_KEYS: frozenset[str] = frozenset(["study", "read", "code"])
_UNMAPPED_ACTIVITY_HINTS: dict[str, tuple[str, ...]] = {
    "exercise": ("exercise", "exercising"),
    "gym": ("gym",),
    "pushup": ("pushup", "pushups", "push-up", "push-ups", "push up", "push ups"),
    "strength_training": (
        "strength training",
        "resistance training",
        "lifting",
        "lifted",
        "weights",
    ),
}

# ---------------------------------------------------------------------------
# LLM-related constants
# ---------------------------------------------------------------------------

_CANONICAL_THEMES: frozenset[str] = frozenset(
    {
        "Physical",
        "Mental",
        "Professional",
        "Social",
        "Creative",
        "Emotional",
        "Practical",
        "Intellectual",
        "Spiritual",
        "Adventure",
        "Discipline",
        "Rest",
    }
)

_VALID_TASK_TYPES: frozenset[str] = frozenset(
    {"analytical", "creative", "physical", "social", "intellectual"}
)

# difflib ratio threshold for fuzzy skill-name matching (0–1; higher = stricter)
_FUZZY_SKILL_CUTOFF: float = 0.72

# How many GlobalSkill rows to surface as discovery candidates in the prompt
_GLOBAL_SKILL_SEARCH_TOP_K: int = 15
# Pre-filter pool for keyword pass before optional embedding re-rank
_GLOBAL_SKILL_CANDIDATE_POOL: int = 40

_PROMPT_DETECT_SIGNALS = """\
# Mission

You are a world class personal-journal analysis specialist with 20 years of \
experience identifying skills, themes, activities, emotions, and energy signals \
from unstructured journal entries. Your task is to analyse the provided journal \
entry and produce a complete structured signal detection. Use a precise, factual, \
neutral tone.

# INSTRUCTIONS AND STEPS

1. Read the journal entry carefully.
2. For each skill in the USER SKILL ROSTER, decide whether the entry provides \
clear evidence the user practised or engaged with that skill. Assign a weight \
(importance) 0.0-1.0 — weights do not need to sum to 1.
3. For each skill in DISCOVERABLE SKILLS FROM KNOWLEDGE BASE, decide whether the \
entry clearly demonstrates engagement with that skill. If so, add it to \
"discovered_skills". These are skills the user does not yet track.
4. For each of the 12 life themes, decide if the entry is meaningfully related.
5. List every activity the user performed or mentions performing.
6. List every emotion explicitly or implicitly expressed.
7. Estimate energy level (1 = completely drained, 10 = full energy).
8. Classify the dominant task type.
9. Use the keyword detection hints as soft guidance — do not be limited by them.
10. Use the prior context snippets as additional evidence where relevant.
11. Rate your overall certainty in the detection from 0.0 to 1.0.

# FORMAT OF ELEMENTS

Return a JSON object with this exact structure:
{{
  "user_skills": [
    {{"name": "<skill name from USER SKILL ROSTER>", "weight": <float 0.0-1.0>}},
    ...
  ],
  "discovered_skills": [
    {{"name": "<canonical_name from DISCOVERABLE SKILLS>", "weight": <float 0.0-1.0>}},
    ...
  ],
  "themes": ["<theme name from list>", ...],
  "activities": ["<activity description>", ...],
  "emotions": ["<emotion>", ...],
  "energy_level": <integer 1-10>,
  "task_type": "<one of: analytical, creative, physical, social, intellectual>",
  "certainty": <float 0.0-1.0>
}}

# PERSONALITY

Be precise and conservative. Only include skills with unambiguous direct evidence \
in the entry. An empty "user_skills" or "discovered_skills" list is correct and \
expected when the entry does not clearly demonstrate those skills. Prefer \
"discovered_skills" when the entry clearly demonstrates a specific skill from the \
knowledge base that is more precise or relevant than anything in the user's current \
roster. When the entry explicitly mentions multiple distinct activities, list ALL \
matching roster skills — do not collapse multiple real activities into a single skill \
or discovered_skill.

# RULES

- Return ONLY valid JSON. No markdown, no explanation.
- Every "name" in "user_skills" MUST closely match a name from USER SKILL ROSTER.
- Every "name" in "discovered_skills" MUST closely match a canonical_name from \
DISCOVERABLE SKILLS FROM KNOWLEDGE BASE.
- If no skills/themes/activities/emotions are detected, return empty arrays.
- Use "discovered_skills" for new KB skills; use "user_skills" for existing roster skills.
- CRITICAL: Only include a skill in "user_skills" if it was DIRECTLY and explicitly \
practiced in this specific entry. Do NOT infer skills by analogy or association \
(e.g. for a philosophy/reading entry, NEVER include Physical Health, Cardio Endurance, \
Meditation, Strength Training, or any skill not explicitly referenced in the text).
- An empty "user_skills" array is correct and expected when the entry does not \
explicitly mention practicing any skill from your roster.
- When "discovered_skills" contains a precise match for the entry's main activity, \
prefer it and leave "user_skills" empty if roster skills are not explicitly practiced.

# EXAMPLES

Example 1 — only KB discovery (no roster match):
Journal entry: "10h of philosophy today"
Roster: [Physical Health, Cardio Endurance, Meditation, Mental Wellbeing]
KB candidates include: [Philosophy, Philosophy Of Mind]
Correct output:
  "user_skills": []         ← none of the roster skills were practiced today
  "discovered_skills": [{{"name": "Philosophy", "weight": 1.0}}]

Example 2 — multiple roster skills (compound entry):
Journal entry: "I did 30 min of meditation and then 50 pushups"
Roster: [Meditation, Strength Training, Physical Health]
KB candidates include: [Mindfulness, Calisthenics]
Correct output:
  "user_skills": [{{"name": "Meditation", "weight": 0.5}}, {{"name": "Strength Training", "weight": 0.5}}]
  "discovered_skills": []   ← both activities already covered by roster skills

# USER SKILL ROSTER
# (skills you already track — include in "user_skills" if genuinely involved)

{skill_roster}

# DISCOVERABLE SKILLS FROM KNOWLEDGE BASE
# (skills you do NOT yet track — include in "discovered_skills" if the entry \
clearly demonstrates engagement)

{global_skill_candidates}

# CANONICAL THEME NAMES

{theme_names}

# KEYWORD DETECTION HINTS (rule-based pre-pass, use as soft guidance)

{keyword_hints}

# PRIOR CONTEXT SNIPPETS (from knowledge base)

{rag_context}

# JOURNAL ENTRY

{canonical_text}
"""


# ---------------------------------------------------------------------------
# Internal helpers — rule-based
# ---------------------------------------------------------------------------


def _classify_task_type(lowered: str, detected_activities: list[str]) -> str:
    activity_set = set(detected_activities)
    if any(t in lowered for t in _CREATIVE_TOKENS):
        return "creative"
    if activity_set.intersection(_PHYSICAL_ACTIVITY_KEYS) or any(
        t in lowered for t in _PHYSICAL_TOKENS
    ):
        return "physical"
    if activity_set.intersection(_LEARNING_ACTIVITY_KEYS):
        return "intellectual"
    if any(t in lowered for t in _SOCIAL_TOKENS):
        return "social"
    return "analytical"


def _estimate_energy(lowered: str) -> int:
    if "exhausted" in lowered or "drained" in lowered:
        return 3
    if "energized" in lowered or "great" in lowered:
        return 8
    return 5


# ---------------------------------------------------------------------------
# Internal helpers — LLM support
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors (pure Python)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _search_global_skills(
    canonical_text: str,
    db: Session,
    top_k: int = _GLOBAL_SKILL_SEARCH_TOP_K,
    qdrant: Any = None,
) -> list:
    """Find the most relevant GlobalSkill entries for *canonical_text*.

    Two-pass:
    1. Keyword/token overlap against canonical_name + description → top-40 candidates.
    2. If ``qdrant.encode_text`` is available: re-rank candidates by embedding cosine
       similarity → top-10.  Falls back to pass-1 ranking on any error.
    """
    all_skills: list[GlobalSkill] = (
        db.query(GlobalSkill).filter(GlobalSkill.description.isnot(None)).all()
    )
    if not all_skills:
        return []

    entry_tokens = set(re.findall(r"\w+", canonical_text.lower()))

    # Pass 1: keyword token overlap
    scored: list[tuple[GlobalSkill, int]] = []
    for gs in all_skills:
        text = f"{gs.canonical_name or ''} {gs.description or ''}".lower()
        gs_tokens = set(re.findall(r"\w+", text))
        overlap = len(entry_tokens & gs_tokens)
        scored.append((gs, overlap))

    scored.sort(key=lambda x: -x[1])
    candidates = [gs for gs, sc in scored[:_GLOBAL_SKILL_CANDIDATE_POOL] if sc > 0]
    if not candidates:
        # Short entry with no keyword overlap — still surface top-k by name similarity
        candidates = [gs for gs, _ in scored[:top_k]]

    # Pass 2: optional embedding re-rank
    if qdrant is not None and hasattr(qdrant, "encode_text") and candidates:
        try:
            entry_vec = qdrant.encode_text(canonical_text)
            embed_scored: list[tuple[GlobalSkill, float]] = []
            for gs in candidates:
                gs_text = f"{gs.canonical_name or ''} {gs.description or ''}"
                gs_vec = qdrant.encode_text(gs_text)
                score = _cosine(entry_vec, gs_vec)
                embed_scored.append((gs, score))
            embed_scored.sort(key=lambda x: -x[1])
            return [gs for gs, _ in embed_scored[:top_k]]
        except Exception as exc:
            logger.warning(
                "[pipeline:signals] GlobalSkill embedding re-rank failed: %s", exc
            )

    return [gs for gs, _ in scored[:top_k]]


def _load_skill_descriptions(skills: list, db: Session) -> dict[str, str]:
    """Return ``{skill.name: description}`` for skills linked to a GlobalSkill."""
    global_ids = {s.global_skill_id for s in skills if s.global_skill_id}
    if not global_ids:
        return {}
    rows = db.query(GlobalSkill).filter(GlobalSkill.id.in_(global_ids)).all()
    gs_by_id = {str(row.id): row for row in rows}
    result: dict[str, str] = {}
    for skill in skills:
        if skill.global_skill_id:
            gs = gs_by_id.get(str(skill.global_skill_id))
            if gs and gs.description:
                result[skill.name] = str(gs.description)
    return result


def _build_roster_lines(skills: list, descriptions: dict[str, str]) -> str:
    """Format the user's skill roster with descriptions for the LLM prompt."""
    lines = []
    for skill in skills:
        desc = descriptions.get(skill.name, "")[:250].rstrip()
        lines.append(f"- {skill.name}: {desc}" if desc else f"- {skill.name}")
    return "\n".join(lines) if lines else "No skills in roster."


def _build_global_candidates_lines(global_skills: list) -> str:
    """Format GlobalSkill candidates with descriptions for the LLM prompt."""
    lines = []
    for gs in global_skills:
        desc = (gs.description or "")[:250].rstrip()
        lines.append(
            f"- {gs.canonical_name}: {desc}" if desc else f"- {gs.canonical_name}"
        )
    return "\n".join(lines) if lines else "No candidates found."


def _format_hints(rule_based: dict) -> str:
    """Format the rule-based result as a human-readable hint block for the LLM."""
    skills = rule_based.get("detected_skills", [])
    activities = rule_based.get("detected_activities", [])
    emotions = rule_based.get("dominant_emotions", [])
    energy = rule_based.get("energy_level")
    task = rule_based.get("task_type")
    if not any([skills, activities, emotions]):
        return "None"
    parts = []
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
    if activities:
        parts.append(f"Activities: {', '.join(activities)}")
    if emotions:
        parts.append(f"Emotions: {', '.join(emotions)}")
    if energy is not None:
        parts.append(f"Energy: {energy}/10")
    if task:
        parts.append(f"Task type: {task}")
    return "\n".join(parts)


def _format_rag(rag_hits: list[dict]) -> str:
    """Format top-3 RAG hit content snippets for the LLM prompt."""
    snippets = [
        h.get("content", "") for h in (rag_hits or []) if h.get("content")
    ][:3]
    if not snippets:
        return "No prior context available."
    return "\n".join(f"- {s.strip()}" for s in snippets)


def _fuzzy_match_skill(name: str, roster_by_lower: dict[str, str]) -> str | None:
    """Return canonical user skill name if *name* fuzzy-matches the roster.

    Tries exact lowercase first; falls back to difflib closest match.
    """
    lowered = name.lower().strip()
    if lowered in roster_by_lower:
        return roster_by_lower[lowered]
    matches = difflib.get_close_matches(
        lowered, roster_by_lower.keys(), n=1, cutoff=_FUZZY_SKILL_CUTOFF
    )
    if matches:
        return roster_by_lower[matches[0]]
    return None


def _fuzzy_match_global(
    name: str, candidates_by_lower: dict[str, Any]
) -> Any | None:
    """Return GlobalSkill if *name* fuzzy-matches the candidates dict, else None."""
    lowered = name.lower().strip()
    if lowered in candidates_by_lower:
        return candidates_by_lower[lowered]
    matches = difflib.get_close_matches(
        lowered, candidates_by_lower.keys(), n=1, cutoff=_FUZZY_SKILL_CUTOFF
    )
    if matches:
        return candidates_by_lower[matches[0]]
    return None


def _normalize_weights(skill_weights: dict[str, float]) -> dict[str, float]:
    """Scale weights so they sum to 1.0. Distributes equally when all are zero."""
    total = sum(skill_weights.values())
    if total <= 0:
        n = len(skill_weights)
        return {k: (1.0 / n if n else 0.0) for k in skill_weights}
    return {k: v / total for k, v in skill_weights.items()}


def _rule_based_as_llm_output(
    rule_based: dict, llm_inputs_snapshot: dict
) -> dict[str, Any]:
    """Wrap a rule-based result in the extended shape returned by ``_llm_detect_signals``."""
    skill_names = rule_based.get("detected_skills", [])
    n = len(skill_names)
    return {
        "detected_skills": skill_names,
        "skills_weights": {s: (1.0 / n if n else 0.0) for s in skill_names},
        "detected_global_skills": [],
        "global_skills_weights": {},
        "detected_themes": [],
        "detected_activities": rule_based.get("detected_activities", []),
        "dominant_emotions": rule_based.get("dominant_emotions", []),
        "energy_level": rule_based.get("energy_level", 5),
        "task_type": rule_based.get("task_type", "analytical"),
        "certainty": 0.0,
        "llm_inputs_snapshot": llm_inputs_snapshot,
    }


def _llm_detect_signals(
    *,
    canonical_text: str,
    skills: list,  # list[Skill]
    rule_based_result: dict,
    rag_hits: list[dict],
    ollama: Any,
    user_id: str,
    db: Session,
    qdrant: Any = None,
) -> dict[str, Any]:
    """Call Ollama to detect all signals; validate with up to 3 retries.

    Enriches the LLM context with:
    - User skill descriptions (from linked GlobalSkill entries)
    - Top-K globally discovered skills most relevant to the entry (GlobalSkill KB search)

    Returns a dict with all step-output keys including ``detected_global_skills``
    (list of source_skill_ids for skills the user doesn't have yet).
    """
    _MAX_ATTEMPTS = 3
    roster_by_lower: dict[str, str] = {s.name.lower(): s.name for s in skills}

    # -- Load descriptions for existing user skills --
    descriptions = _load_skill_descriptions(skills, db)

    # -- Search GlobalSkill KB for discovery candidates --
    global_candidates: list[GlobalSkill] = _search_global_skills(
        canonical_text, db, qdrant=qdrant
    )
    global_candidates_by_lower: dict[str, GlobalSkill] = {
        (gs.canonical_name or "").lower(): gs for gs in global_candidates
    }
    logger.debug(
        "[pipeline:signals] user=%s global_candidates=%s",
        user_id,
        [gs.canonical_name for gs in global_candidates],
    )

    # -- Build prompt sections (computed once; reused across retries) --
    roster_section = _build_roster_lines(skills, descriptions)
    global_section = _build_global_candidates_lines(global_candidates)
    formatted_hints = _format_hints(rule_based_result)
    formatted_rag = _format_rag(rag_hits)

    llm_inputs_snapshot: dict[str, Any] = {
        "skill_roster": [s.name for s in skills],
        "skill_descriptions_loaded": list(descriptions.keys()),
        "global_candidates": [gs.canonical_name for gs in global_candidates],
        "global_candidate_count": len(global_candidates),
        "theme_names": sorted(_CANONICAL_THEMES),
        "keyword_hints": formatted_hints,
        "rag_snippets": formatted_rag,
        "rag_hit_count": len(rag_hits or []),
    }

    user_skill_invalid_feedback = ""
    global_skill_invalid_feedback = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        prompt = _PROMPT_DETECT_SIGNALS.format(
            skill_roster=roster_section,
            global_skill_candidates=global_section,
            theme_names=", ".join(sorted(_CANONICAL_THEMES)),
            keyword_hints=formatted_hints,
            rag_context=formatted_rag,
            canonical_text=canonical_text,
        )
        correction_parts = []
        if user_skill_invalid_feedback:
            correction_parts.append(f"USER SKILLS CORRECTION:\n{user_skill_invalid_feedback}")
        if global_skill_invalid_feedback:
            correction_parts.append(f"DISCOVERED SKILLS CORRECTION:\n{global_skill_invalid_feedback}")
        if correction_parts:
            prompt += "\n\n# CORRECTION NOTE\n" + "\n\n".join(correction_parts)

        logger.debug(
            "[pipeline:signals] user=%s attempt=%d roster_lines=%d global_lines=%d",
            user_id,
            attempt,
            len(skills),
            len(global_candidates),
        )

        # --- LLM call ---
        try:
            raw_response = ollama.generate_json(prompt)["response"]
            parsed = json.loads(raw_response)
        except Exception as exc:
            logger.warning(
                "[pipeline:signals] user=%s LLM attempt=%d/%d call/parse failure: %s",
                user_id,
                attempt,
                _MAX_ATTEMPTS,
                exc,
            )
            if attempt == _MAX_ATTEMPTS:
                logger.warning(
                    "[pipeline:signals] user=%s all %d LLM attempts failed; "
                    "returning rule-based fallback",
                    user_id,
                    _MAX_ATTEMPTS,
                )
                return _rule_based_as_llm_output(rule_based_result, llm_inputs_snapshot)
            user_skill_invalid_feedback = ""
            global_skill_invalid_feedback = (
                "Your previous response was not valid JSON. "
                "Return ONLY a JSON object with no markdown."
            )
            continue

        # --- Parse user_skills (fuzzy match against existing roster) ---
        raw_user_skills = parsed.get("user_skills", [])
        if not isinstance(raw_user_skills, list):
            raw_user_skills = []

        valid_user_names: list[str] = []
        raw_user_weights: dict[str, float] = {}
        unrecognized_user: list[str] = []

        for item in raw_user_skills:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            try:
                weight = float(item.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            matched = _fuzzy_match_skill(name, roster_by_lower)
            if matched:
                valid_user_names.append(matched)
                raw_user_weights[matched] = weight
            else:
                unrecognized_user.append(name)

        # --- Parse discovered_skills (fuzzy match against GlobalSkill candidates) ---
        raw_discovered = parsed.get("discovered_skills", [])
        if not isinstance(raw_discovered, list):
            raw_discovered = []

        valid_global_ids: list[str] = []
        raw_global_weights: dict[str, float] = {}
        unrecognized_global: list[str] = []

        for item in raw_discovered:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            try:
                weight = float(item.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            matched_gs = _fuzzy_match_global(name, global_candidates_by_lower)
            if matched_gs and matched_gs.source_skill_id:
                valid_global_ids.append(str(matched_gs.source_skill_id))
                raw_global_weights[str(matched_gs.source_skill_id)] = weight
            else:
                unrecognized_global.append(name)

        # --- Validate themes (filter only — no retry) ---
        returned_themes = parsed.get("themes", [])
        if not isinstance(returned_themes, list):
            returned_themes = []
        valid_themes = [
            t for t in returned_themes if isinstance(t, str) and t in _CANONICAL_THEMES
        ]
        invalid_themes = [t for t in returned_themes if t not in _CANONICAL_THEMES]
        if invalid_themes:
            logger.warning(
                "[pipeline:signals] user=%s attempt=%d filtered invalid theme names: %s",
                user_id,
                attempt,
                invalid_themes,
            )

        # --- Other signals (clamp / validate, fall back to rule-based value) ---
        activities = parsed.get("activities", [])
        if not isinstance(activities, list):
            activities = []
        activities = [a for a in activities if isinstance(a, str)]

        emotions = parsed.get("emotions", [])
        if not isinstance(emotions, list):
            emotions = []
        emotions = [e for e in emotions if isinstance(e, str)]

        raw_energy = parsed.get("energy_level", rule_based_result.get("energy_level", 5))
        try:
            energy = max(1, min(10, int(raw_energy)))
        except (TypeError, ValueError):
            energy = int(rule_based_result.get("energy_level", 5))

        raw_task = parsed.get(
            "task_type", rule_based_result.get("task_type", "analytical")
        )
        task_type = (
            raw_task
            if raw_task in _VALID_TASK_TYPES
            else rule_based_result.get("task_type", "analytical")
        )

        raw_certainty = parsed.get("certainty", 0.5)
        try:
            certainty = max(0.0, min(1.0, float(raw_certainty)))
        except (TypeError, ValueError):
            certainty = 0.5

        # --- Handle unrecognized names → build retry feedback ---
        needs_retry = False
        user_skill_invalid_feedback = ""
        global_skill_invalid_feedback = ""

        if unrecognized_user:
            logger.warning(
                "[pipeline:signals] user=%s attempt=%d/%d "
                "unrecognized user skill names: %s",
                user_id,
                attempt,
                _MAX_ATTEMPTS,
                unrecognized_user,
            )
            if attempt < _MAX_ATTEMPTS:
                user_skill_invalid_feedback = (
                    f"The following names in 'user_skills' were not found in the roster: "
                    f"{unrecognized_user}.\n"
                    f"Valid roster:\n{roster_section}"
                )
                needs_retry = True

        if unrecognized_global:
            logger.warning(
                "[pipeline:signals] user=%s attempt=%d/%d "
                "unrecognized discovered skill names: %s",
                user_id,
                attempt,
                _MAX_ATTEMPTS,
                unrecognized_global,
            )
            if attempt < _MAX_ATTEMPTS:
                global_skill_invalid_feedback = (
                    f"The following names in 'discovered_skills' were not found in the "
                    f"knowledge base candidates: {unrecognized_global}.\n"
                    f"Valid candidates:\n{global_section}"
                )
                needs_retry = True

        if needs_retry:
            continue

        if unrecognized_user or unrecognized_global:
            logger.warning(
                "[pipeline:signals] user=%s max retries reached; "
                "keeping %d valid user skills, %d valid global skills; "
                "discarding user=%s global=%s",
                user_id,
                len(valid_user_names),
                len(valid_global_ids),
                unrecognized_user,
                unrecognized_global,
            )

        # --- Deduplicate and normalize weights ---
        deduped_user = list(dict.fromkeys(valid_user_names))
        deduped_user_weights = {s: raw_user_weights.get(s, 1.0) for s in deduped_user}
        normalized_user = _normalize_weights(deduped_user_weights) if deduped_user_weights else {}

        deduped_global = list(dict.fromkeys(valid_global_ids))
        deduped_global_weights = {
            sid: raw_global_weights.get(sid, 1.0) for sid in deduped_global
        }
        normalized_global = (
            _normalize_weights(deduped_global_weights) if deduped_global_weights else {}
        )

        logger.info(
            "[pipeline:signals] user=%s LLM attempt=%d "
            "user_skills=%s global_skills=%s themes=%s "
            "activities=%s emotions=%s energy=%s task=%s certainty=%.2f",
            user_id,
            attempt,
            deduped_user,
            deduped_global,
            valid_themes,
            activities,
            emotions,
            energy,
            task_type,
            certainty,
        )

        return {
            "detected_skills": sorted(set(deduped_user)),
            "skills_weights": normalized_user,
            "detected_global_skills": sorted(set(deduped_global)),
            "global_skills_weights": normalized_global,
            "detected_themes": sorted(set(valid_themes)),
            "detected_activities": activities,
            "dominant_emotions": emotions,
            "energy_level": energy,
            "task_type": task_type,
            "certainty": certainty,
            "llm_inputs_snapshot": llm_inputs_snapshot,
        }

    # Unreachable — the loop always returns or continues.
    return _rule_based_as_llm_output(rule_based_result, llm_inputs_snapshot)


# ---------------------------------------------------------------------------
# Public step function
# ---------------------------------------------------------------------------


def run(
    *,
    user_id: str,
    canonical_text: str,
    db: Session,
    ollama_health: dict[str, Any] | None = None,
    ollama: Any = None,
    rag_hits: list[dict[str, Any]] | None = None,
    qdrant: Any = None,
) -> dict[str, Any]:
    """Detect structured signals from *canonical_text*.

    The rule-based pre-pass always runs first and its results are fed as soft
    hints to the LLM when Ollama is available.  The LLM enriches every signal
    field and additionally:
    - detects themes (new)
    - detects per-skill importance weights (new)
    - discovers skills from the GlobalSkill KB the user doesn't yet track (new)

    Args:
        user_id:        Owning user UUID — used to scope the Skill query.
        canonical_text: Normalised entry text from the normalise step.
        db:             SQLAlchemy session (read-only within this step).
        ollama_health:  Health dict from step 04 (keys: connected, model_available).
        ollama:         OllamaClient instance.
        rag_hits:       RAG search hits from step 06 (list of dicts with a ``content`` key).
        qdrant:         Qdrant client (optional).  Used to embed GlobalSkill descriptions
                        for semantic pre-ranking of discovery candidates.

    Returns:
        Dict with keys:
            ``detected_skills``       — sorted list of matched user skill names.
            ``skills_weights``        — {name: float} normalised weights (sum=1).
            ``detected_global_skills``— sorted list of source_skill_ids for newly
                                        discovered skills (not in user's roster).
            ``global_skills_weights`` — {source_skill_id: float} normalised weights.
            ``detected_themes``       — sorted list of matched canonical theme names.
            ``detected_activities``   — list of activity descriptions.
            ``dominant_emotions``     — list of detected emotion strings.
            ``energy_level``          — int 1-10.
            ``self_compassion_score`` — int 1-10 (rule-based, always present).
            ``task_type``             — one of: analytical, creative, physical, social, intellectual.
            ``certainty``             — float 0-1; LLM confidence (0.0 when rule-based fallback).
            ``llm_inputs_snapshot``   — dict of rendered prompt fields for monitoring.
    """
    lowered = canonical_text.lower()
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_\-']*", lowered))

    # ---- Rule-based pass (always runs) ----
    skills: list[Skill] = db.query(Skill).filter(Skill.user_id == user_id).all()
    detected_skills: list[str] = []
    for skill in skills:
        tokens = set(skill.canonical_name.lower().split())
        if tokens and tokens.intersection(words):
            detected_skills.append(skill.name)

    detected_activities = [
        activity
        for activity, markers in _ACTIVITY_PATTERNS
        if any(marker in lowered for marker in markers)
    ]
    dominant_emotions = [e for e in _EMOTION_KEYWORDS if e in lowered]
    self_compassion_score = 3 if "hate myself" in lowered else 7
    unmapped_hints = sorted(
        hint
        for hint, keywords in _UNMAPPED_ACTIVITY_HINTS.items()
        if any(keyword in lowered for keyword in keywords)
    )

    rule_based_result: dict[str, Any] = {
        "detected_skills": sorted(set(detected_skills)),
        "detected_activities": detected_activities,
        "dominant_emotions": dominant_emotions,
        "energy_level": _estimate_energy(lowered),
        "self_compassion_score": self_compassion_score,
        "task_type": _classify_task_type(lowered, detected_activities),
    }

    # ---- LLM enrichment (conditional) ----
    llm_available = ollama is not None and bool(
        (ollama_health or {}).get("model_available")
    )
    logger.info(
        "[pipeline:signals] user=%s roster=%d llm_available=%s",
        user_id,
        len(skills),
        llm_available,
    )

    if not llm_available:
        n = len(rule_based_result["detected_skills"])
        result: dict[str, Any] = {
            **rule_based_result,
            "detected_themes": [],
            "skills_weights": {
                s: (1.0 / n if n else 0.0)
                for s in rule_based_result["detected_skills"]
            },
            "detected_global_skills": [],
            "global_skills_weights": {},
            "certainty": 0.0,
            "llm_inputs_snapshot": {},
        }
    else:
        llm_result = _llm_detect_signals(
            canonical_text=canonical_text,
            skills=skills,
            rule_based_result=rule_based_result,
            rag_hits=rag_hits or [],
            ollama=ollama,
            user_id=user_id,
            db=db,
            qdrant=qdrant,
        )
        # self_compassion_score is always rule-based.
        result = {**llm_result, "self_compassion_score": self_compassion_score}

    logger.info(
        "[pipeline:signals] user=%s "
        "detected_skills=%s global_skills=%s detected_themes=%s "
        "detected_activities=%s dominant_emotions=%s "
        "task_type=%s energy=%s certainty=%.2f unmapped_hints=%s",
        user_id,
        result["detected_skills"],
        result.get("detected_global_skills", []),
        result.get("detected_themes", []),
        result["detected_activities"],
        result["dominant_emotions"],
        result["task_type"],
        result["energy_level"],
        result.get("certainty", 0.0),
        unmapped_hints,
    )
    if unmapped_hints and not result["detected_skills"] and not result.get("detected_global_skills"):
        logger.warning(
            "[pipeline:signals] user=%s found activity hints without any skill matches "
            "hints=%s roster_preview=%s",
            user_id,
            unmapped_hints,
            [skill.canonical_name for skill in skills[:8]],
        )
    if unmapped_hints and not result["detected_activities"]:
        logger.warning(
            "[pipeline:signals] user=%s found raw activity hints that did not map into "
            "detected_activities hints=%s",
            user_id,
            unmapped_hints,
        )
    return result
