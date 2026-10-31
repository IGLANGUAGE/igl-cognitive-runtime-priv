"""Rule — HARD/SOFT правило выбора CognitiveFrame (CE.1-r3).

HARD ограничивает множество допустимых фреймов (ALLOWED).
SOFT ранжирует допустимые фреймы по целочисленному весу.

condition — идентификатор реализованного предиката, а не строка для LLM.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .frame import VALID_TIERS


VALID_PRIORITIES: frozenset[str] = frozenset({"HARD", "SOFT"})


@dataclass(frozen=True)
class Rule:
    """Одно правило.

    HARD:
      - frame задаёт точные register/coordinate_system/strategy,
      - min_model_tier задаёт нижнюю границу tier (не точное значение),
      - weight не используется (должен быть None).

    SOFT:
      - frame задаёт частичный фрейм, которому должен удовлетворять кандидат,
      - weight — positive int, вклад в ранжирование,
      - min_model_tier не используется (должен быть None).
    """
    id: str
    priority: str
    condition: str
    frame: dict[str, str] = field(default_factory=dict)
    scope: str = ""
    weight: int | None = None
    min_model_tier: str | None = None


def is_valid_rule(rule: Rule) -> bool:
    """Валидация правила по контракту CE.1-r3."""
    if not rule.id or not isinstance(rule.id, str):
        return False
    if rule.priority not in VALID_PRIORITIES:
        return False
    if not rule.condition or not isinstance(rule.condition, str):
        return False

    if rule.priority == "HARD":
        if rule.weight is not None:
            return False
        if rule.min_model_tier is not None and rule.min_model_tier not in VALID_TIERS:
            return False
    else:  # SOFT
        if rule.min_model_tier is not None:
            return False
        if rule.weight is None:
            return False
        if not isinstance(rule.weight, int) or isinstance(rule.weight, bool):
            return False
        if rule.weight <= 0:
            return False

    # Поля frame, если заданы, должны быть из допустимых множеств
    for key, value in rule.frame.items():
        if key not in {"register", "coordinate_system", "strategy"}:
            return False
        if not isinstance(value, str):
            return False

    return True


# --- Каноническая сериализация ---

def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rule_to_dict(rule: Rule) -> dict[str, Any]:
    d = {
        "id": rule.id,
        "priority": rule.priority,
        "condition": rule.condition,
        "frame": dict(rule.frame),
        "scope": rule.scope,
        "weight": rule.weight,
        "min_model_tier": rule.min_model_tier,
    }
    return d


def rule_from_dict(d: dict[str, Any]) -> Rule:
    return Rule(
        id=d["id"],
        priority=d["priority"],
        condition=d["condition"],
        frame=dict(d.get("frame", {})),
        scope=d.get("scope", ""),
        weight=d.get("weight"),
        min_model_tier=d.get("min_model_tier"),
    )


def rule_hash(rule: Rule) -> str:
    return hashlib.sha256(
        _canonical_json(rule_to_dict(rule)).encode("utf-8")
    ).hexdigest()


def ruleset_hash(rules: list[Rule]) -> str:
    """Канонический хеш набора правил.

    Порядок в списке не влияет: правила сортируются по id (T15).
    """
    normalized = sorted(
        (rule_to_dict(r) for r in rules),
        key=lambda d: (d["id"], d["priority"]),
    )
    return hashlib.sha256(
        _canonical_json(normalized).encode("utf-8")
    ).hexdigest()