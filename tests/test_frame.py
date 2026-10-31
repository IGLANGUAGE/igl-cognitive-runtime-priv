"""Tests for CognitiveFrame (CE.1-r3)."""

import pytest

from igl_cognitive.frame import (
    CognitiveFrame,
    VALID_FRAMES,
    VALID_TIERS,
    is_valid_frame,
    frame_config,
    frames_same_config,
    frame_to_dict,
    frame_from_dict,
    frame_hash,
    frame_config_hash,
    frame_registry_hash,
)


def make_frame(**overrides) -> CognitiveFrame:
    base = dict(
        register="verification",
        coordinate_system="mathematics",
        strategy="formal_verification",
        model_tier="strong",
        revision=0,
    )
    base.update(overrides)
    return CognitiveFrame(**base)


# --- VALID_FRAMES ---

def test_valid_frames_has_seven_triples():
    assert len(VALID_FRAMES) == 7


def test_valid_frames_contains_canonical_verification():
    assert ("verification", "mathematics", "formal_verification") in VALID_FRAMES


# --- is_valid_frame ---

def test_valid_frame_accepted():
    assert is_valid_frame(make_frame()) is True


@pytest.mark.parametrize("triple", [
    ("verification", "philosophy", "formal_verification"),  # нет в реестре
    ("conversation", "mathematics", "recall"),              # нет в реестре
    ("task", "engineering", "recall"),                      # нет в реестре
])
def test_invalid_triple_rejected(triple):
    f = CognitiveFrame(*triple, model_tier="medium", revision=0)
    assert is_valid_frame(f) is False


def test_invalid_tier_rejected():
    f = make_frame(model_tier="huge")
    assert is_valid_frame(f) is False


def test_negative_revision_rejected():
    f = make_frame(revision=-1)
    assert is_valid_frame(f) is False


# --- config vs revision ---

def test_frame_config_excludes_revision():
    f = make_frame(revision=5)
    cfg = frame_config(f)
    assert "revision" not in cfg
    assert cfg["register"] == "verification"


def test_frames_same_config_ignores_revision():
    a = make_frame(revision=0)
    b = make_frame(revision=7)
    assert frames_same_config(a, b) is True


def test_frames_different_config_detected():
    a = make_frame()
    b = make_frame(model_tier="medium")
    assert frames_same_config(a, b) is False


# --- serialization round-trip ---

def test_frame_dict_roundtrip():
    f = make_frame(revision=3)
    d = frame_to_dict(f)
    back = frame_from_dict(d)
    assert back == f


# --- hashes ---

def test_frame_hash_includes_revision():
    a = make_frame(revision=0)
    b = make_frame(revision=1)
    assert frame_hash(a) != frame_hash(b)


def test_frame_config_hash_excludes_revision():
    a = make_frame(revision=0)
    b = make_frame(revision=99)
    assert frame_config_hash(a) == frame_config_hash(b)


def test_frame_hash_is_canonical():
    a = make_frame(revision=2)
    b = make_frame(revision=2)
    assert frame_hash(a) == frame_hash(b)


def test_frame_registry_hash_stable():
    h1 = frame_registry_hash()
    h2 = frame_registry_hash()
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex
    