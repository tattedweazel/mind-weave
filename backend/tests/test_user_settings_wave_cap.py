"""Tests for parallel wave cap settings and batch helper."""

from collections import deque

import pytest

from app.domain.user_settings import (
    MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT,
    resolve_auto_play_tts_on_node_end,
    resolve_max_concurrent_lm_studio_calls,
    resolve_tts_playback_when,
)
from app.domain.workflow_executor.helpers import pop_wave_batch


def test_resolve_auto_play_tts_on_node_end_defaults_true():
    assert resolve_auto_play_tts_on_node_end(None) is True
    assert resolve_auto_play_tts_on_node_end({}) is True
    assert resolve_auto_play_tts_on_node_end({"auto_play_tts_on_node_end": None}) is True


def test_resolve_auto_play_tts_on_node_end_boolean():
    assert resolve_auto_play_tts_on_node_end({"auto_play_tts_on_node_end": False}) is False
    assert resolve_auto_play_tts_on_node_end({"auto_play_tts_on_node_end": True}) is True


def test_resolve_auto_play_tts_on_node_end_invalid_types_fall_back_true():
    assert resolve_auto_play_tts_on_node_end({"auto_play_tts_on_node_end": "no"}) is True
    assert resolve_auto_play_tts_on_node_end({"auto_play_tts_on_node_end": 0}) is True


def test_resolve_tts_playback_when_prefers_string():
    assert resolve_tts_playback_when({"tts_playback_when": "after_workflow"}) == "after_workflow"
    assert resolve_tts_playback_when({"tts_playback_when": "manual"}) == "manual"
    assert resolve_tts_playback_when({"tts_playback_when": "inline"}) == "inline"


def test_resolve_tts_playback_when_invalid_string_falls_back_to_legacy_bool():
    assert resolve_tts_playback_when({"tts_playback_when": "nope", "auto_play_tts_on_node_end": False}) == "manual"
    assert resolve_tts_playback_when({"tts_playback_when": "nope", "auto_play_tts_on_node_end": True}) == "inline"


def test_resolve_auto_play_false_for_after_workflow():
    assert resolve_auto_play_tts_on_node_end({"tts_playback_when": "after_workflow"}) is False
    assert resolve_auto_play_tts_on_node_end({"tts_playback_when": "manual"}) is False


def test_resolve_max_concurrent_lm_studio_calls_default():
    assert resolve_max_concurrent_lm_studio_calls(None) == MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT
    assert resolve_max_concurrent_lm_studio_calls({}) == MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": None}) == MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT


def test_resolve_max_concurrent_lm_studio_calls_clamps():
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": 5}) == 5
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": 1}) == 1
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": 32}) == 32
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": 0}) == 1
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": 99}) == 32


def test_resolve_max_concurrent_lm_studio_calls_invalid_types_fall_back():
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": True}) == MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT
    assert resolve_max_concurrent_lm_studio_calls({"max_concurrent_lm_studio_calls": "3"}) == MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT


@pytest.mark.parametrize(
    "cap,expected_lens",
    [
        (3, [3, 3, 2]),
        (10, [8]),
    ],
)
def test_pop_wave_batch_splits_waves(cap: int, expected_lens: list[int]):
    order_index = {f"n{i}": i for i in range(8)}
    ready: deque[str] = deque(f"n{i}" for i in range(8))
    batches: list[list[str]] = []
    while ready:
        batches.append(pop_wave_batch(ready, order_index, cap))
    assert [len(b) for b in batches] == expected_lens
    assert sum(len(b) for b in batches) == 8


def test_pop_wave_batch_orders_by_order_index():
    ready: deque[str] = deque(["c", "a", "b"])
    order_index = {"a": 0, "b": 1, "c": 2}
    b = pop_wave_batch(ready, order_index, 3)
    assert b == ["a", "b", "c"]
    assert list(ready) == []


def test_pop_wave_batch_empty():
    assert pop_wave_batch(deque(), {}, 3) == []
