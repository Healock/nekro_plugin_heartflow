"""Heartflow 的纯逻辑函数。

此模块不依赖 Nekro，便于用单元测试覆盖状态转换、judge 解析和存储序列化。
"""

from __future__ import annotations

import datetime as _datetime
import json
import math
import re
from typing import Any, Mapping

from .models import ChatState, JudgeResult, RawMessage

DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 0.25,
    "willingness": 0.20,
    "social": 0.20,
    "timing": 0.15,
    "continuity": 0.20,
}


def clamp_number(value: object, default: float, minimum: float, maximum: float, *, integer: bool = False) -> float | int:
    """将配置值转换为有限的有界数字。"""

    if isinstance(value, bool):
        number = default
    else:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            number = default
    if not math.isfinite(number):
        number = default
    number = max(minimum, min(maximum, number))
    return int(number) if integer else number


def normalize_weights(values: Mapping[str, object]) -> dict[str, float]:
    """清洗并归一化五项 judge 权重。"""

    weights = {
        name: float(clamp_number(values.get(name), default, 0.0, 1.0))
        for name, default in DEFAULT_WEIGHTS.items()
    }
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    return {name: value / total for name, value in weights.items()}


def extract_json(text: str) -> object:
    """从模型输出中提取 JSON。"""

    source = (text or "").strip()
    if not source:
        raise ValueError("模型返回为空")
    try:
        return json.loads(source)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", source, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    object_match = re.search(r"\{.*\}", source, flags=re.DOTALL)
    if object_match:
        try:
            return json.loads(object_match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回的对象不是有效 JSON") from exc
    raise ValueError("模型返回中没有 JSON 对象")


def _score(payload: Mapping[str, Any], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool):
        raise ValueError(f"评分字段 {name} 不能是布尔值")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"评分字段 {name} 不是数字") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 10.0:
        raise ValueError(f"评分字段 {name} 超出 0 到 10 范围")
    return score


def validate_judge_payload(
    payload: object,
    weights: Mapping[str, float],
    threshold: float,
    *,
    include_reasoning: bool,
) -> JudgeResult:
    """校验 judge JSON 并计算总体分数。"""

    if not isinstance(payload, Mapping):
        raise ValueError("judge JSON 顶层必须是对象")
    scores = {name: _score(payload, name) for name in DEFAULT_WEIGHTS}
    overall = sum(scores[name] * float(weights[name]) for name in DEFAULT_WEIGHTS) / 10.0
    reasoning = str(payload.get("reasoning", "")).strip() if include_reasoning else ""
    return JudgeResult(
        **scores,
        overall_score=overall,
        should_reply=overall >= threshold,
        reasoning=reasoning[:300],
    )


def refresh_state(state: ChatState, now: float, recovery_rate: float, *, today: str | None = None) -> None:
    """应用日期重置和每五分钟一次的自然精力恢复。"""

    current_date = today or _datetime.date.fromtimestamp(now).isoformat()
    if state.last_reset_date != current_date:
        state.last_reset_date = current_date
        state.energy = min(1.0, state.energy + 0.2)
    if state.last_energy_update_time > 0:
        elapsed_minutes = max(0.0, now - state.last_energy_update_time) / 60.0
        state.energy = min(1.0, state.energy + (elapsed_minutes / 5.0) * recovery_rate)
    state.last_energy_update_time = now
    state.last_access_time = now


def can_process_message(state: ChatState, now: float, minimum_interval: float) -> bool:
    """判断频道是否已通过冷却时间。"""

    if minimum_interval <= 0:
        return True
    last_activity = max(state.last_reply_time, state.last_trigger_time)
    return not last_activity or now - last_activity >= minimum_interval


def mark_passive(state: ChatState, recovery_rate: float) -> None:
    """应用一次未回复后的精力恢复。"""

    state.energy = min(1.0, state.energy + recovery_rate)


def reserve_trigger(state: ChatState, now: float, *, pending_seconds: float) -> None:
    """记录一次主动触发预留。"""

    state.last_trigger_time = now
    state.pending_trigger_until = now + max(0.0, pending_seconds)
    state.total_triggers += 1


def commit_reply(state: ChatState, now: float, decay_rate: float) -> None:
    """在确认主模型有输出后提交主动回复状态。"""

    state.last_reply_time = now
    state.last_trigger_time = now
    state.pending_trigger_until = 0.0
    state.total_replies += 1
    state.energy = max(0.1, state.energy - decay_rate)


def commit_trigger_assumption(state: ChatState, now: float, decay_rate: float, *, pending_seconds: float) -> None:
    """在没有 Agent 响应回调时，按触发预留近似提交状态。"""

    state.last_reply_time = now
    state.pending_trigger_until = now + max(0.0, pending_seconds)
    state.total_replies += 1
    state.energy = max(0.1, state.energy - decay_rate)


def rollback_trigger(state: ChatState, reservation: float) -> None:
    """仅回滚仍属于当前请求的触发预留。"""

    if state.last_trigger_time == reservation:
        state.last_trigger_time = 0.0
        state.pending_trigger_until = 0.0


def render_active_prompt(state: ChatState, now: float) -> str:
    """生成短的主动参与提示；没有有效预留时返回空字符串。"""

    if state.pending_trigger_until <= now:
        return ""
    return "本轮由心流主动触发，请自然加入当前话题，不要解释触发机制。"


def serialize_state(state: ChatState) -> str:
    """将有限状态序列化为可放入 plugin.store 的 JSON 字符串。"""

    payload = {
        "energy": state.energy,
        "last_reply_time": state.last_reply_time,
        "last_trigger_time": state.last_trigger_time,
        "last_energy_update_time": state.last_energy_update_time,
        "last_access_time": state.last_access_time,
        "last_reset_date": state.last_reset_date,
        "total_messages": state.total_messages,
        "total_replies": state.total_replies,
        "total_triggers": state.total_triggers,
        "pending_trigger_until": state.pending_trigger_until,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def deserialize_state(value: str | None) -> ChatState:
    """安全读取 plugin.store 中的状态，异常数据回退到初始状态。"""

    if not value:
        return ChatState()
    try:
        payload = json.loads(value)
        if not isinstance(payload, Mapping):
            raise ValueError("状态 JSON 顶层不是对象")
        state = ChatState()
        for field_name in (
            "energy",
            "last_reply_time",
            "last_trigger_time",
            "last_energy_update_time",
            "last_access_time",
            "last_reset_date",
            "total_messages",
            "total_replies",
            "total_triggers",
            "pending_trigger_until",
        ):
            if field_name in payload:
                setattr(state, field_name, payload[field_name])
        state.energy = float(max(0.0, min(1.0, state.energy)))
        for field_name in (
            "last_reply_time",
            "last_trigger_time",
            "last_energy_update_time",
            "last_access_time",
            "pending_trigger_until",
        ):
            setattr(state, field_name, float(getattr(state, field_name)))
        for field_name in ("total_messages", "total_replies", "total_triggers"):
            setattr(state, field_name, max(0, int(getattr(state, field_name))))
        state.last_reset_date = str(state.last_reset_date)
        return state
    except (TypeError, ValueError, json.JSONDecodeError):
        return ChatState()


def raw_message_to_prompt(message: RawMessage) -> str:
    role = "机器人" if message.is_bot else "群成员"
    return f"【{role}】{message.sender_name}：{message.content[:500]}"
