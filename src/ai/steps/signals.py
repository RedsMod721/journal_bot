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

import concurrent.futures
import difflib
import json
import logging
import re
import threading
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
_GLOBAL_SKILL_OVERLAP_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "did",
        "do",
        "for",
        "from",
        "had",
        "has",
        "have",
        "i",
        "in",
        "is",
        "it",
        "my",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "today",
        "was",
        "with",
    }
)

_PROMPT_DETECT_SKILLS = """\
# JOURNAL ENTRY

{canonical_text}

# Mission

You are a world class personal-journal analysis specialist with 20 years of \
experience identifying skills from unstructured journal entries. Your task is to \
analyse the provided journal entry and detect which skills the user practised. \
Use a precise, factual, neutral tone.

# INSTRUCTIONS AND STEPS

1. Read the journal entry carefully.
2. For each skill in the USER SKILL ROSTER, decide whether the entry provides \
clear evidence the user practised or engaged with that skill. Assign a weight \
(importance) 0.0-1.0 — weights do not need to sum to 1.
3. For each skill in DISCOVERABLE SKILLS FROM KNOWLEDGE BASE, decide whether the \
entry clearly demonstrates engagement with that skill. If so, add it to \
"discovered_skills". These are skills the user does not yet track.
4. Use the keyword detection hints as soft guidance — do not be limited by them.
5. Use the prior context snippets as additional evidence where relevant.
6. Rate your overall certainty in the detection from 0.0 to 1.0.

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
- If no skills are detected, return empty arrays.
- Use "discovered_skills" for new KB skills; use "user_skills" for existing roster skills.
- CRITICAL: Only include a skill in "user_skills" if it was DIRECTLY and explicitly \
practiced in this specific entry. Do NOT infer skills by analogy or association.
- CRITICAL — Physical skills (Physical Health, Cardio Endurance, Strength Training, \
Running, or any exercise/fitness skill): ONLY include if the entry explicitly describes \
a physical activity such as gym, running, pushups, cycling, swimming, hiking, sports, \
or physical labour. Time duration alone (e.g. "4h of coding", "3h studying", "socialised \
for 4h") does NOT qualify. Socialising, meetings, reading, coding, studying, and \
philosophy NEVER qualify for physical skills, regardless of duration.
- CRITICAL — Meditation: ONLY include if the entry explicitly uses words like \
"meditated", "meditation", "mindfulness", "breathing exercise", or similar. Focused \
work, coding, writing, or attending meetings does NOT count as Meditation.
- CRITICAL — Leisure, Restorative Leisure, Work Recovery, Unwinding: ONLY include \
if the user explicitly describes resting, relaxing, or unwinding (e.g. "I relaxed", \
"took a break", "watched TV to unwind"). Coding, professional work, studying, and \
meetings NEVER qualify as leisure or restorative activities.
- An empty "user_skills" array is correct and expected when the entry does not \
explicitly mention practicing any skill from your roster.
- When "discovered_skills" contains a precise match for the entry's main activity, \
prefer it and leave "user_skills" empty if roster skills are not explicitly practiced.\


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

Example 3 — time duration does NOT trigger physical skills:
Journal entry: "I socialised with colleagues for 4h"
Roster: [Physical Health, Mental Wellbeing, Cardio Endurance]
KB candidates include: [Restorative Leisure, Sleep, Physical Health]
Correct output:
  "user_skills": [{{"name": "Mental Wellbeing", "weight": 0.8}}]
  "discovered_skills": []   ← "4h" duration does NOT make this physical; no exercise mentioned

Example 4 — coding is NOT meditation or leisure:
Journal entry: "I practiced python for 2h"
Roster: [Meditation, Physical Health, Restorative Leisure, Programming]
KB candidates include: [Python, Restorative Leisure, Meditation]
Correct output:
  "user_skills": [{{"name": "Programming", "weight": 1.0}}]
  "discovered_skills": []   ← no meditation, no physical activity, no explicit leisure

# USER SKILL ROSTER
# (skills you already track — include in "user_skills" if genuinely involved)

{skill_roster}

# DISCOVERABLE SKILLS FROM KNOWLEDGE BASE
# (skills you do NOT yet track — include in "discovered_skills" if the entry \
clearly demonstrates engagement)

{global_skill_candidates}

# KEYWORD DETECTION HINTS (rule-based pre-pass, use as soft guidance)

{keyword_hints}

# PRIOR CONTEXT SNIPPETS (from knowledge base)

{rag_context}

# JOURNAL ENTRY

{canonical_text}
"""

_PROMPT_DETECT_CONTEXT = """\
# JOURNAL ENTRY

{canonical_text}

# Mission

You are a world class personal-journal analysis specialist with 20 years of \
experience identifying activities, emotions, energy signals, and task types from \
unstructured journal entries. Your task is to analyse the provided journal entry \
and extract these contextual signals. Use a precise, factual, neutral tone.

# INSTRUCTIONS AND STEPS

1. Read the journal entry carefully.
2. List every activity the user performed or mentions performing.
3. List every emotion explicitly or implicitly expressed.
4. Estimate energy level (1 = completely drained, 10 = full energy).
5. Classify the dominant task type.
6. Use the keyword detection hints as soft guidance — do not be limited by them.
7. Use the prior context snippets as additional evidence where relevant.
8. Rate your overall certainty in the detection from 0.0 to 1.0.

# FORMAT OF ELEMENTS

Return a JSON object with this exact structure:
{{
  "activities": ["<activity description>", ...],
  "emotions": ["<emotion>", ...],
  "energy_level": <integer 1-10>,
  "task_type": "<one of: analytical, creative, physical, social, intellectual>",
  "certainty": <float 0.0-1.0>
}}

# RULES

- Return ONLY valid JSON. No markdown, no explanation.
- If no activities/emotions are detected, return empty arrays.
- "task_type" must be exactly one of: analytical, creative, physical, social, intellectual.
- "energy_level" must be an integer between 1 and 10.

# USER SKILL ROSTER
# (for context — helps understand the user's domain and likely activities)

{skill_roster}

# DISCOVERABLE SKILLS FROM KNOWLEDGE BASE
# (for context only)

{global_skill_candidates}

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


def _normalize_lookup_label(value: str) -> str:
    """Normalize a skill label for case-insensitive exact lookup."""
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace("_", " "))


def _overlap_tokens(value: str) -> set[str]:
    """Tokenize *value* while excluding high-noise stopwords."""
    return {
        token
        for token in re.findall(r"\w+", (value or "").lower())
        if len(token) > 2 and token not in _GLOBAL_SKILL_OVERLAP_STOPWORDS
    }


# ---------------------------------------------------------------------------
# Module-level cache for GlobalSkill embeddings
# Populated lazily on first use; persists for the process lifetime.
# GlobalSkill KB is static (not user-editable), so no invalidation needed.
# ---------------------------------------------------------------------------
_global_skill_embed_cache: dict[str, list[float]] = {}  # gs.id (str) → vector
_global_skill_embed_lock = threading.Lock()


def _ensure_global_skill_embeddings(
    all_skills: list, qdrant: Any
) -> None:
    """Encode and cache embeddings for any GlobalSkills not yet in the cache.

    Uses batch encoding when available (``encode_batch``), otherwise falls back
    to individual ``encode_text`` calls.  The cache is populated once per process
    and reused on all subsequent calls, making per-entry latency negligible.
    """
    uncached = [gs for gs in all_skills if str(gs.id) not in _global_skill_embed_cache]
    if not uncached:
        return
    logger.info(
        "[pipeline:signals] Building GlobalSkill embedding cache for %d skills …",
        len(uncached),
    )
    texts = [
        f"{gs.canonical_name or ''} {gs.description or ''}".strip()
        for gs in uncached
    ]
    try:
        if hasattr(qdrant, "encode_batch"):
            vectors = qdrant.encode_batch(texts)
        else:
            vectors = [qdrant.encode_text(t) for t in texts]
        for gs, vec in zip(uncached, vectors):
            _global_skill_embed_cache[str(gs.id)] = vec
        logger.info(
            "[pipeline:signals] GlobalSkill embedding cache ready (%d total)",
            len(_global_skill_embed_cache),
        )
    except Exception as exc:
        logger.warning(
            "[pipeline:signals] GlobalSkill embedding cache build failed: %s", exc
        )


def _search_global_skills(
    canonical_text: str,
    db: Session,
    top_k: int = _GLOBAL_SKILL_SEARCH_TOP_K,
    qdrant: Any = None,
) -> list:
    """Find the most relevant GlobalSkill entries for *canonical_text*.

    When the qdrant client (with ``encode_text``) is available, uses semantic
    embedding similarity ranked across **all** global skills — no keyword
    pre-filtering gate.  This correctly surfaces skills whose descriptions are
    semantically related to the entry even when there is zero literal token
    overlap (e.g. "mushrooms and roots in the forest" → Foraging).

    The per-skill embeddings are computed once and stored in a module-level
    cache, so the cost is only paid on first call per process.

    Falls back to keyword/token-overlap ranking when embeddings are unavailable.
    """
    all_skills: list[GlobalSkill] = (
        db.query(GlobalSkill).filter(GlobalSkill.description.isnot(None)).all()
    )
    if not all_skills:
        return []

    # Primary path: full semantic embedding ranking across all global skills
    if qdrant is not None and hasattr(qdrant, "encode_text"):
        try:
            with _global_skill_embed_lock:
                _ensure_global_skill_embeddings(all_skills, qdrant)
            entry_vec = qdrant.encode_text(canonical_text)
            embed_scored: list[tuple[GlobalSkill, float]] = []
            for gs in all_skills:
                gs_vec = _global_skill_embed_cache.get(str(gs.id))
                if gs_vec:
                    score = _cosine(entry_vec, gs_vec)
                    embed_scored.append((gs, score))
            embed_scored.sort(key=lambda x: -x[1])
            result = [gs for gs, _ in embed_scored[:top_k]]
            logger.debug(
                "[pipeline:signals] GlobalSkill embedding ranked top-%d: %s",
                top_k,
                [gs.canonical_name for gs in result],
            )
            return result
        except Exception as exc:
            logger.warning(
                "[pipeline:signals] GlobalSkill embedding ranking failed, "
                "falling back to keyword overlap: %s",
                exc,
            )

    # Fallback: keyword/token overlap
    entry_tokens = _overlap_tokens(canonical_text)
    scored: list[tuple[GlobalSkill, int]] = []
    for gs in all_skills:
        text = f"{gs.canonical_name or ''} {gs.description or ''}".lower()
        gs_tokens = _overlap_tokens(text)
        overlap = len(entry_tokens & gs_tokens)
        scored.append((gs, overlap))

    scored.sort(key=lambda x: -x[1])
    candidates = [gs for gs, sc in scored[:_GLOBAL_SKILL_CANDIDATE_POOL] if sc > 0]
    if not candidates:
        # Short entry with no keyword overlap — still surface top-k
        candidates = [gs for gs, _ in scored[:top_k]]

    return candidates[:top_k]


_PHYSICAL_CATEGORIES: frozenset[str] = frozenset({"Physical", "physical"})

# Global skill names whose presence in the candidate list is misleading for
# non-physical entries (e.g. "Sleep" surfacing for reading entries).
_PHYSICAL_NOISE_NAMES: frozenset[str] = frozenset(
    {
        "sleep",
        "sleep consistency",
        "sleep quality",
        "restorative sleep",
        "napping",
        "rest",
    }
)


def _filter_global_candidates_for_non_physical(
    candidates: list,
    detected_activities: list[str],
) -> list:
    """Remove Physical-category and sleep/rest global skill candidates when the
    entry contains no physical activities.

    This prevents the LLM from being primed to match the user's physical skills
    (e.g. Physical Health, Cardio Endurance) when it sees sleep/fitness candidates
    in the knowledge-base window for purely cognitive or social entries.
    """
    has_physical_activity = bool(
        set(detected_activities) & _PHYSICAL_ACTIVITY_KEYS
    )
    if has_physical_activity:
        return candidates

    # Also allow physical candidates when the entry itself contains clear physical
    # tokens (handles entries like "I built a cabin" where activity key is "build").
    # The caller already ran rule_based_result; we just check the activity list.
    filtered = []
    for gs in candidates:
        category = (gs.category or "").strip()
        name_lower = (gs.canonical_name or "").lower()
        if category in _PHYSICAL_CATEGORIES and name_lower in _PHYSICAL_NOISE_NAMES:
            continue
        filtered.append(gs)
    return filtered


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
    snippets: list[str] = []
    for hit in rag_hits or []:
        if not isinstance(hit, dict):
            continue
        content = hit.get("content")
        if not content and isinstance(hit.get("payload"), dict):
            content = hit["payload"].get("content")
        if content:
            snippets.append(str(content))
        if len(snippets) >= 3:
            break
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



def _llm_call_skills(
    *,
    base_prompt: str,
    roster_by_lower: dict[str, str],
    global_candidates_by_lower: dict[str, Any],
    global_all_by_normalized_name: dict[str, Any],
    roster_section: str,
    global_section: str,
    rule_based_result: dict,
    user_id: str,
    ollama: Any,
) -> dict[str, Any]:
    """Call Ollama to detect skills only; validate with up to 3 retries.

    Returns a dict with keys: detected_skills, skills_weights,
    detected_global_skills, global_skills_weights, certainty,
    llm_prompt, llm_raw_output, llm_failure_reason.
    """
    _MAX_ATTEMPTS = 3
    user_skill_invalid_feedback = ""
    global_skill_invalid_feedback = ""
    best_attempt_result: dict[str, Any] | None = None
    best_attempt_score: tuple[int, int, float] = (-1, -1, -1.0)

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        prompt = base_prompt
        correction_parts = []
        if user_skill_invalid_feedback:
            correction_parts.append(f"USER SKILLS CORRECTION:\n{user_skill_invalid_feedback}")
        if global_skill_invalid_feedback:
            correction_parts.append(f"DISCOVERED SKILLS CORRECTION:\n{global_skill_invalid_feedback}")
        if correction_parts:
            prompt += "\n\n# CORRECTION NOTE\n" + "\n\n".join(correction_parts)

        logger.debug(
            "[pipeline:signals:skills] user=%s attempt=%d",
            user_id,
            attempt,
        )

        raw_response = ""
        try:
            # Skills detection is a classification task — lower temperature reduces
            # non-determinism without losing recall.
            raw_response = ollama.generate_json(prompt, temperature=0.15)["response"]
            parsed = json.loads(raw_response)
        except Exception as exc:
            logger.warning(
                "[pipeline:signals:skills] user=%s attempt=%d/%d call/parse failure: %s",
                user_id,
                attempt,
                _MAX_ATTEMPTS,
                exc,
            )
            if attempt == _MAX_ATTEMPTS:
                if best_attempt_result is not None:
                    logger.warning(
                        "[pipeline:signals:skills] user=%s returning best partial result "
                        "after final call/parse failure",
                        user_id,
                    )
                    return best_attempt_result
                skill_names = rule_based_result.get("detected_skills", [])
                n = len(skill_names)
                return {
                    "detected_skills": skill_names,
                    "skills_weights": {s: (1.0 / n if n else 0.0) for s in skill_names},
                    "detected_global_skills": [],
                    "global_skills_weights": {},
                    "certainty": 0.0,
                    "llm_prompt": prompt,
                    "llm_raw_output": raw_response,
                    "llm_failure_reason": str(exc),
                }
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
            if matched_gs is None:
                matched_gs = global_all_by_normalized_name.get(
                    _normalize_lookup_label(name)
                )
            if matched_gs and matched_gs.source_skill_id:
                valid_global_ids.append(str(matched_gs.source_skill_id))
                raw_global_weights[str(matched_gs.source_skill_id)] = weight
            else:
                unrecognized_global.append(name)

        raw_certainty = parsed.get("certainty", 0.5)
        try:
            certainty = max(0.0, min(1.0, float(raw_certainty)))
        except (TypeError, ValueError):
            certainty = 0.5

        # --- Deduplicate and normalize weights ---
        deduped_user = list(dict.fromkeys(valid_user_names))
        deduped_user_weights = {s: raw_user_weights.get(s, 1.0) for s in deduped_user}
        normalized_user = (
            _normalize_weights(deduped_user_weights) if deduped_user_weights else {}
        )

        deduped_global = list(dict.fromkeys(valid_global_ids))
        deduped_global_weights = {
            sid: raw_global_weights.get(sid, 1.0) for sid in deduped_global
        }
        normalized_global = (
            _normalize_weights(deduped_global_weights) if deduped_global_weights else {}
        )

        current_result = {
            "detected_skills": sorted(set(deduped_user)),
            "skills_weights": normalized_user,
            "detected_global_skills": sorted(set(deduped_global)),
            "global_skills_weights": normalized_global,
            "certainty": certainty,
            "llm_prompt": prompt,
            "llm_raw_output": raw_response,
            "llm_failure_reason": "",
        }
        current_score = (
            len(deduped_user) + len(deduped_global),
            len(deduped_global),
            certainty,
        )
        if current_score > best_attempt_score:
            best_attempt_result = current_result
            best_attempt_score = current_score

        # --- Handle unrecognized names → build retry feedback ---
        needs_retry = False
        user_skill_invalid_feedback = ""
        global_skill_invalid_feedback = ""

        if unrecognized_user:
            logger.warning(
                "[pipeline:signals:skills] user=%s attempt=%d/%d "
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
                "[pipeline:signals:skills] user=%s attempt=%d/%d "
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
            if best_attempt_result is not None and best_attempt_score > current_score:
                logger.warning(
                    "[pipeline:signals:skills] user=%s max retries reached; returning best "
                    "prior partial result instead of worse final attempt",
                    user_id,
                )
                return best_attempt_result
            logger.warning(
                "[pipeline:signals:skills] user=%s max retries reached; "
                "keeping %d valid user skills, %d valid global skills; "
                "discarding user=%s global=%s",
                user_id,
                len(valid_user_names),
                len(valid_global_ids),
                unrecognized_user,
                unrecognized_global,
            )

        logger.info(
            "[pipeline:signals:skills] user=%s attempt=%d "
            "user_skills=%s global_skills=%s certainty=%.2f",
            user_id,
            attempt,
            deduped_user,
            deduped_global,
            certainty,
        )
        return current_result

    # Unreachable — the loop always returns or continues.
    skill_names = rule_based_result.get("detected_skills", [])
    n = len(skill_names)
    return {
        "detected_skills": skill_names,
        "skills_weights": {s: (1.0 / n if n else 0.0) for s in skill_names},
        "detected_global_skills": [],
        "global_skills_weights": {},
        "certainty": 0.0,
        "llm_prompt": base_prompt,
        "llm_raw_output": "",
        "llm_failure_reason": "max retries exceeded",
    }


def _llm_call_context(
    *,
    base_prompt: str,
    rule_based_result: dict,
    user_id: str,
    ollama: Any,
) -> dict[str, Any]:
    """Call Ollama to detect context signals only; validate with up to 3 retries.

    Returns a dict with keys: detected_activities, dominant_emotions,
    energy_level, task_type, certainty, llm_prompt, llm_raw_output, llm_failure_reason.
    """
    _MAX_ATTEMPTS = 3
    parse_error_feedback = ""
    best_attempt_result: dict[str, Any] | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        prompt = base_prompt
        if parse_error_feedback:
            prompt += f"\n\n# CORRECTION NOTE\n{parse_error_feedback}"

        logger.debug(
            "[pipeline:signals:context] user=%s attempt=%d",
            user_id,
            attempt,
        )

        raw_response = ""
        try:
            raw_response = ollama.generate_json(prompt, temperature=0.35)["response"]
            parsed = json.loads(raw_response)
        except Exception as exc:
            logger.warning(
                "[pipeline:signals:context] user=%s attempt=%d/%d call/parse failure: %s",
                user_id,
                attempt,
                _MAX_ATTEMPTS,
                exc,
            )
            if attempt == _MAX_ATTEMPTS:
                if best_attempt_result is not None:
                    return best_attempt_result
                return {
                    "detected_activities": rule_based_result.get("detected_activities", []),
                    "dominant_emotions": rule_based_result.get("dominant_emotions", []),
                    "energy_level": rule_based_result.get("energy_level", 5),
                    "task_type": rule_based_result.get("task_type", "analytical"),
                    "certainty": 0.0,
                    "llm_prompt": prompt,
                    "llm_raw_output": raw_response,
                    "llm_failure_reason": str(exc),
                }
            parse_error_feedback = (
                "Your previous response was not valid JSON. "
                "Return ONLY a JSON object with no markdown."
            )
            continue

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

        current_result = {
            "detected_activities": activities,
            "dominant_emotions": emotions,
            "energy_level": energy,
            "task_type": task_type,
            "certainty": certainty,
            "llm_prompt": prompt,
            "llm_raw_output": raw_response,
            "llm_failure_reason": "",
        }
        best_attempt_result = current_result

        logger.info(
            "[pipeline:signals:context] user=%s attempt=%d "
            "activities=%s emotions=%s energy=%s task=%s certainty=%.2f",
            user_id,
            attempt,
            activities,
            emotions,
            energy,
            task_type,
            certainty,
        )
        return current_result

    # Unreachable — the loop always returns or continues.
    return {
        "detected_activities": rule_based_result.get("detected_activities", []),
        "dominant_emotions": rule_based_result.get("dominant_emotions", []),
        "energy_level": rule_based_result.get("energy_level", 5),
        "task_type": rule_based_result.get("task_type", "analytical"),
        "certainty": 0.0,
        "llm_prompt": base_prompt,
        "llm_raw_output": "",
        "llm_failure_reason": "max retries exceeded",
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
    """Call Ollama to detect all signals via two parallel focused LLM calls.

    Runs two calls in parallel:
    - Skills call: detects user_skills + discovered_skills
    - Context call: detects activities, emotions, energy_level, task_type

    Themes are not LLM-extracted; detected_themes is always [].

    All DB reads happen before threads are spawned (SQLAlchemy sessions are not
    thread-safe). Both prompts receive identical context sections for consistency.
    """
    roster_by_lower: dict[str, str] = {s.name.lower(): s.name for s in skills}

    # -- Load descriptions for existing user skills (DB read — before threads) --
    descriptions = _load_skill_descriptions(skills, db)

    # -- Search GlobalSkill KB for discovery candidates (DB read — before threads) --
    global_candidates: list[GlobalSkill] = _search_global_skills(
        canonical_text, db, qdrant=qdrant
    )
    global_candidates = _filter_global_candidates_for_non_physical(
        global_candidates, rule_based_result["detected_activities"]
    )
    global_candidates_by_lower: dict[str, GlobalSkill] = {
        (gs.canonical_name or "").lower(): gs for gs in global_candidates
    }
    all_globals_for_exact_lookup: list[GlobalSkill] = (
        db.query(GlobalSkill)
        .filter(
            GlobalSkill.canonical_name.isnot(None),
            GlobalSkill.source_skill_id.isnot(None),
        )
        .all()
    )
    global_all_by_normalized_name: dict[str, GlobalSkill] = {
        _normalize_lookup_label(str(gs.canonical_name)): gs
        for gs in all_globals_for_exact_lookup
        if gs.canonical_name
    }
    logger.debug(
        "[pipeline:signals] user=%s global_candidates=%s",
        user_id,
        [gs.canonical_name for gs in global_candidates],
    )

    # -- Build shared prompt sections (computed once; identical for both prompts) --
    roster_section = _build_roster_lines(skills, descriptions)
    global_section = _build_global_candidates_lines(global_candidates)
    formatted_hints = _format_hints(rule_based_result)
    formatted_rag = _format_rag(rag_hits)

    llm_inputs_snapshot: dict[str, Any] = {
        "skill_roster": [s.name for s in skills],
        "skill_descriptions_loaded": list(descriptions.keys()),
        "global_candidates": [gs.canonical_name for gs in global_candidates],
        "global_candidate_count": len(global_candidates),
        "keyword_hints": formatted_hints,
        "rag_snippets": formatted_rag,
        "rag_hit_count": len(rag_hits or []),
    }

    # -- Build both prompts (identical context, different extraction focus) --
    shared_sections = dict(
        skill_roster=roster_section,
        global_skill_candidates=global_section,
        keyword_hints=formatted_hints,
        rag_context=formatted_rag,
        canonical_text=canonical_text,
    )
    skills_prompt = _PROMPT_DETECT_SKILLS.format(**shared_sections)
    context_prompt = _PROMPT_DETECT_CONTEXT.format(**shared_sections)

    # -- Run both LLM calls in parallel (threads do HTTP I/O only, no DB access) --
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        skills_future = executor.submit(
            _llm_call_skills,
            base_prompt=skills_prompt,
            roster_by_lower=roster_by_lower,
            global_candidates_by_lower=global_candidates_by_lower,
            global_all_by_normalized_name=global_all_by_normalized_name,
            roster_section=roster_section,
            global_section=global_section,
            rule_based_result=rule_based_result,
            user_id=user_id,
            ollama=ollama,
        )
        context_future = executor.submit(
            _llm_call_context,
            base_prompt=context_prompt,
            rule_based_result=rule_based_result,
            user_id=user_id,
            ollama=ollama,
        )
        skills_result = skills_future.result()
        context_result = context_future.result()

    # -- Merge results --
    combined_certainty = (skills_result["certainty"] + context_result["certainty"]) / 2.0
    failure_reason = (
        skills_result["llm_failure_reason"] or context_result["llm_failure_reason"]
    )

    logger.info(
        "[pipeline:signals] user=%s LLM "
        "user_skills=%s global_skills=%s "
        "activities=%s emotions=%s energy=%s task=%s certainty=%.2f",
        user_id,
        skills_result["detected_skills"],
        skills_result["detected_global_skills"],
        context_result["detected_activities"],
        context_result["dominant_emotions"],
        context_result["energy_level"],
        context_result["task_type"],
        combined_certainty,
    )

    return {
        "detected_skills": skills_result["detected_skills"],
        "skills_weights": skills_result["skills_weights"],
        "detected_global_skills": skills_result["detected_global_skills"],
        "global_skills_weights": skills_result["global_skills_weights"],
        "detected_themes": [],
        "detected_activities": context_result["detected_activities"],
        "dominant_emotions": context_result["dominant_emotions"],
        "energy_level": context_result["energy_level"],
        "task_type": context_result["task_type"],
        "certainty": combined_certainty,
        "llm_inputs_snapshot": llm_inputs_snapshot,
        "llm_prompt": skills_result["llm_prompt"],
        "llm_raw_output": skills_result["llm_raw_output"],
        "llm_failure_reason": failure_reason,
    }


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
                ``llm_prompt``            — full prompt sent to the LLM for the returned attempt.
                ``llm_raw_output``        — raw JSON string returned by the LLM for the returned attempt.
                ``llm_failure_reason``    — parse/call failure reason when the step falls back.
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
