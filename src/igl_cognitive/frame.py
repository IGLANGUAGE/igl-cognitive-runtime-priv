"""CognitiveFrame — единая согласованная конфигурация способа осмысления.

CE.1-r3 contract. Deterministic. No LLM, no memory, no network.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any


# --- Реестр допустимых фреймов (CE.1-r3) ---

VALID_FRAMES: frozenset[tuple[str, str, str]] = frozenset({
    ("conversation", "none", "conceptual_exploration"),
    ("hypothesis", "philosophy", "conceptual_exploration"),
    ("hypothesis", "mathematics", "formal_derivation"),
    ("verification", "mathematics", "formal_verification"),
    ("verification", "empirics", "formal_verification"),
    ("task", "engineering", "practical_execution"),
    ("memory", "none", "recall"),
})

VALID_REGISTERS: frozenset[str] = frozenset({
    "conversation", "hypothesis", "verification", "task", "memory",
})

VALID_COORDINATE_SYSTEMS: frozenset[str] = frozenset({
    "none", "mathematics", "philosophy", "empirics", "engineering",
})

VALID_STRATEGIES: frozenset[str] = frozenset({
    "conceptual_exploration", "formal_verification",
    "formal_derivation", "practical_execution", "recall",
})

VALID_TIERS: frozenset[str] = frozenset({"small", "medium", "strong"})


@dataclass(frozen=True)
class CognitiveFrame:
    """Единая согласованная конфигурация.

    revision — часть состояния истории, но НЕ часть конфигурации.
    Сравнение конфигураций выполняется через frame_config().
    """
    register: str
    coordinate_system: str
    strategy: str
    model_tier: str
    revision: int = 0


def is_valid_frame(frame: CognitiveFrame) -> bool:
    """Фрейм валиден, если тройка в VALID_FRAMES и tier допустим."""
    triple = (frame.register, frame.coordinate_system, frame.strategy)
    if triple not in VALID_FRAMES:
        return False
    if frame.model_tier not in VALID_TIERS:
        return False
    if not isinstance(frame.revision, int) or frame.revision < 0:
        return False
    return True


def frame_config(frame: CognitiveFrame) -> dict[str, str]:
    """Конфигурация без revision — для сравнения двух фреймов."""
    return {
        "register": frame.register,
        "coordinate_system": frame.coordinate_system,
        "strategy": frame.strategy,
        "model_tier": frame.model_tier,
    }


def frames_same_config(a: CognitiveFrame, b: CognitiveFrame) -> bool:
    """Равны ли конфигурации (revision исключён)."""
    return frame_config(a) == frame_config(b)


# --- Каноническая сериализация ---

def _canonical_json(obj: Any) -> str:
    """Каноническая сериализация: сортировка ключей, без пробелов."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def frame_to_dict(frame: CognitiveFrame) -> dict[str, Any]:
    """Полный фрейм в dict (revision включён)."""
    return asdict(frame)


def frame_from_dict(d: dict[str, Any]) -> CognitiveFrame:
    """Восстановление фрейма из dict."""
    return CognitiveFrame(
        register=d["register"],
        coordinate_system=d["coordinate_system"],
        strategy=d["strategy"],
        model_tier=d["model_tier"],
        revision=d.get("revision", 0),
    )


def frame_hash(frame: CognitiveFrame) -> str:
    """Канонический хеш фрейма (revision ВКЛЮЧЁН — для state_hash)."""
    return hashlib.sha256(
        _canonical_json(frame_to_dict(frame)).encode("utf-8")
    ).hexdigest()


def frame_config_hash(frame: CognitiveFrame) -> str:
    """Канонический хеш конфигурации (revision ИСКЛЮЧЁН)."""
    return hashlib.sha256(
        _canonical_json(frame_config(frame)).encode("utf-8")
    ).hexdigest()


def frame_registry_hash() -> str:
    """Канонический хеш VALID_FRAMES + допустимые tier."""
    payload = {
        "valid_frames": sorted(list(VALID_FRAMES)),
        "valid_tiers": sorted(list(VALID_TIERS)),
    }
    return hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()