"""Step modules for the 17-step AI processing pipeline.

Each module exposes one or more pure functions that implement a single
pipeline step. All dependencies (db session, clients, constants) are
injected as keyword-only arguments so every function can be tested in
complete isolation without touching the orchestrator.

Modules
-------
normalize    step 03    — canonicalise raw entry text
embedding    step 05    — generate / cache embedding vector
rag          step 06    — Qdrant nearest-neighbour search
signals      step 07    — detect skills, activities, emotions, energy, task type
structured   step 08    — persist AI-extracted fields to journal_entries_structured
variety      step 08a   — variety score + variety_multiplier_bp (Shannon entropy)
anomaly      step 08b   — troll multiplier precheck from historical signals
             step 14c   — persist AnomalyScore row
strategy     step 08c   — classify entry into balance strategies; update StrategyTracking
quests       steps 09-10 — match active quests; update progress / streak / completion
rewards      steps 11-13 — compute quest XP; persist skill + theme XpAward rows
progression  step 14    — increment skill.xp and theme.xp counters
insights     step 14b   — generate personalised insight via Ollama; persist Insight row
summary      step 15    — assemble the human-readable result summary dict
entry        step 16    — mark journal entry as completed + record duration
"""

from src.ai.steps import (
    anomaly,
    embedding,
    entry,
    insights,
    normalize,
    progression,
    quests,
    rag,
    rewards,
    signals,
    strategy,
    structured,
    summary,
    variety,
)

__all__ = [
    "normalize",
    "embedding",
    "rag",
    "signals",
    "structured",
    "variety",
    "anomaly",
    "strategy",
    "quests",
    "rewards",
    "progression",
    "insights",
    "summary",
    "entry",
]
