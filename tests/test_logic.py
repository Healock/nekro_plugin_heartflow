from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "nekro_plugin_heartflow"
if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(PACKAGE_ROOT)]  # type: ignore[attr-defined]
    sys.modules[PACKAGE_NAME] = package

from nekro_plugin_heartflow.history import merge_current_message, render_history  # noqa: E402
from nekro_plugin_heartflow.judge import JudgeEngine  # noqa: E402
from nekro_plugin_heartflow.logic import (  # noqa: E402
    can_process_message,
    commit_trigger_assumption,
    deserialize_state,
    extract_json,
    normalize_weights,
    refresh_state,
    render_active_prompt,
    serialize_state,
    validate_judge_payload,
)
from nekro_plugin_heartflow.models import ChatState, RawMessage  # noqa: E402
from nekro_plugin_heartflow.settings import load_settings  # noqa: E402


def test_weights_and_json_validation() -> None:
    weights = normalize_weights({"relevance": 0, "willingness": 0, "social": 0, "timing": 0, "continuity": 0})
    assert weights == {
        "relevance": 0.25,
        "willingness": 0.2,
        "social": 0.2,
        "timing": 0.15,
        "continuity": 0.2,
    }

    payload = extract_json("```json\n{\"relevance\": 8, \"willingness\": 7, \"social\": 6, \"timing\": 5, \"continuity\": 4}\n```")
    result = validate_judge_payload(payload, weights, 0.5, include_reasoning=False)
    assert result.should_reply is True
    assert result.reasoning == ""


def test_state_transition_and_message_window() -> None:
    state = ChatState(energy=0.5, last_energy_update_time=100, last_reset_date="2026-01-01")
    refresh_state(state, 700, 0.02, today="2026-01-01")
    assert state.energy == pytest.approx(0.54)
    assert can_process_message(state, 700, 30) is True
    state.last_trigger_time = 690
    assert can_process_message(state, 700, 30) is False

    messages = [RawMessage("1", "甲", "旧消息", 1)]
    current = RawMessage("2", "乙", "当前消息", 2)
    window = merge_current_message(messages, current, 2)
    assert [message.content for message in window] == ["旧消息", "当前消息"]
    assert render_history(window) == ["【群成员】甲：旧消息", "【群成员】乙：当前消息"]


def test_prompt_expiry_and_store_serialization() -> None:
    state = ChatState(pending_trigger_until=20)
    assert render_active_prompt(state, 19)
    assert render_active_prompt(state, 20) == ""

    commit_trigger_assumption(state, 10, 0.1, pending_seconds=30)
    assert state.total_replies == 1
    assert state.energy == pytest.approx(0.9)

    state.energy = 0.35
    state.total_messages = 3
    state.total_replies = 1
    serialized = serialize_state(state)
    restored = deserialize_state(serialized)
    assert restored.energy == pytest.approx(0.35)
    assert restored.total_messages == 3
    assert restored.total_replies == 1
    assert deserialize_state("not-json").energy == 1.0


def test_settings_keep_astrbot_defaults_and_clamp_values() -> None:
    settings = load_settings(SimpleNamespace())
    assert settings.reply_threshold == 0.6
    assert settings.context_messages_count == 5
    assert settings.judge_context_count == 10
    assert settings.max_tracked_chats == 1000
    assert settings.weights["relevance"] == pytest.approx(0.25)

    custom = load_settings(
        SimpleNamespace(
            reply_threshold=3,
            judge_relevance=0,
            judge_willingness=0,
            judge_social=0,
            judge_timing=0,
            judge_continuity=0,
        )
    )
    assert custom.reply_threshold == 1.0
    assert custom.weights["relevance"] == pytest.approx(0.25)


class _FakeJudge:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, _system_prompt: str, _user_prompt: str, _timeout: float) -> str:
        self.calls += 1
        if self.calls == 1:
            return "不是 JSON"
        return '{"relevance": 9, "willingness": 8, "social": 7, "timing": 6, "continuity": 8}'


@pytest.mark.asyncio
async def test_judge_retries_invalid_output_and_returns_result() -> None:
    fake = _FakeJudge()
    result = await JudgeEngine(fake).decide(
        {"current_message": {"content": "测试"}},
        weights={
            "relevance": 0.25,
            "willingness": 0.2,
            "social": 0.2,
            "timing": 0.15,
            "continuity": 0.2,
        },
        threshold=0.6,
        timeout_seconds=2,
        max_retries=1,
        include_reasoning=True,
    )
    assert fake.calls == 2
    assert result is not None
    assert result.should_reply is True
