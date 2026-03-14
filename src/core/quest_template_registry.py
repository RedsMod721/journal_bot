"""Quest template registry loader for the Week 7 matcher artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


def _normalize_confidence_value(value: Any) -> float:
    raw = float(value)
    if 0.0 <= raw <= 1.0:
        return raw
    if 1.0 < raw <= 100.0:
        return raw / 100.0
    raise ValueError(f"confidence must be in [0,1] or [0,100], got {value!r}")


@dataclass(frozen=True)
class QuestTemplateDefinition:
    template_key: str
    skill_semantic_key: str
    quest_kind: str
    min_confidence: float
    max_active: int
    cooldown_days: int
    target_min: int
    target_max: int
    target_select_rule: str
    delta_rule: dict[str, Any]
    signals_required: tuple[str, ...]
    predicate: dict[str, Any]
    score_weights_bp: dict[str, int]


class QuestTemplateRegistry:
    """Immutable, validated quest template catalog."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.file_hash: str
        self.templates: tuple[QuestTemplateDefinition, ...]
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Quest template artifact not found: {self.path}")

        raw_bytes = self.path.read_bytes()
        self.file_hash = hashlib.sha256(raw_bytes).hexdigest()
        payload = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Quest template artifact must be a JSON object")
        if payload.get("schema_version") != 1:
            raise ValueError("Quest template artifact schema_version must be 1")

        raw_templates = payload.get("templates")
        if not isinstance(raw_templates, list):
            raise ValueError("Quest template artifact missing templates list")

        parsed: list[QuestTemplateDefinition] = []
        for idx, row in enumerate(raw_templates, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Quest template row {idx} must be an object")

            template_key = str(row.get("template_key") or "").strip()
            skill_semantic_key = str(row.get("skill_semantic_key") or "").strip()
            quest_kind = str(row.get("quest_kind") or "").strip()
            if not template_key or not skill_semantic_key:
                raise ValueError(
                    f"Quest template row {idx} requires template_key and skill_semantic_key"
                )
            if quest_kind not in {"cumulative", "recursive"}:
                raise ValueError(
                    f"Quest template {template_key!r} has unsupported quest_kind {quest_kind!r}"
                )

            target_range = row.get("target_range") or {}
            if not isinstance(target_range, dict):
                raise ValueError(
                    f"Quest template {template_key!r} target_range must be an object"
                )
            target_min = int(target_range.get("min", 1))
            target_max = int(target_range.get("max", target_min))
            if target_min < 1 or target_max < target_min:
                raise ValueError(
                    f"Quest template {template_key!r} has invalid target_range"
                )

            score_weights = row.get("score_weights_bp") or {}
            if not isinstance(score_weights, dict):
                raise ValueError(
                    f"Quest template {template_key!r} score_weights_bp must be an object"
                )

            parsed.append(
                QuestTemplateDefinition(
                    template_key=template_key,
                    skill_semantic_key=skill_semantic_key,
                    quest_kind=quest_kind,
                    min_confidence=_normalize_confidence_value(
                        row.get("min_confidence", 0.0)
                    ),
                    max_active=max(1, int(row.get("max_active", 1))),
                    cooldown_days=max(0, int(row.get("cooldown_days", 0))),
                    target_min=target_min,
                    target_max=target_max,
                    target_select_rule=str(row.get("target_select_rule") or "min"),
                    delta_rule=dict(row.get("delta_rule") or {"type": "fixed", "delta": 1}),
                    signals_required=tuple(
                        str(item)
                        for item in (row.get("signals_required") or [])
                        if str(item).strip()
                    ),
                    predicate=dict(row.get("predicate") or {}),
                    score_weights_bp={
                        str(key): int(value) for key, value in score_weights.items()
                    },
                )
            )

        self.templates = tuple(sorted(parsed, key=lambda item: item.template_key))

    def get_file_hash(self) -> str:
        return self.file_hash


@lru_cache(maxsize=8)
def load_quest_template_registry(path: str) -> QuestTemplateRegistry:
    return QuestTemplateRegistry(path)
