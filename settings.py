"""插件配置的运行时清洗。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .logic import clamp_number, normalize_weights


@dataclass(frozen=True, slots=True)
class HeartflowSettings:
    enable_heartflow: bool
    judge_provider_name: str
    judge_api_base_url: str
    judge_api_key: str
    judge_model: str
    judge_api_path: str
    reply_threshold: float
    energy_decay_rate: float
    energy_recovery_rate: float
    context_messages_count: int
    judge_context_count: int
    min_reply_interval_seconds: int
    judge_timeout_seconds: float
    max_tracked_chats: int
    max_persona_cache: int
    whitelist_enabled: bool
    chat_whitelist: frozenset[str]
    judge_include_reasoning: bool
    judge_max_retries: int
    weights: dict[str, float]
    raw_buffer_size: int


def _get(config: Any, name: str, default: Any) -> Any:
    return getattr(config, name, default)


def load_settings(config: Any) -> HeartflowSettings:
    context_count = int(clamp_number(_get(config, "context_messages_count", 5), 5, 1, 100, integer=True))
    judge_context_count = int(
        clamp_number(_get(config, "judge_context_count", 10), 10, 1, 100, integer=True)
    )
    raw_whitelist = _get(config, "chat_whitelist", [])
    whitelist = frozenset(str(item) for item in raw_whitelist) if isinstance(raw_whitelist, list) else frozenset()
    weight_values = {
        name: _get(config, f"judge_{name}", default)
        for name, default in {
            "relevance": 0.25,
            "willingness": 0.20,
            "social": 0.20,
            "timing": 0.15,
            "continuity": 0.20,
        }.items()
    }
    api_path = str(_get(config, "judge_api_path", "/chat/completions") or "/chat/completions").strip()
    if not api_path.startswith("/"):
        api_path = f"/{api_path}"
    return HeartflowSettings(
        enable_heartflow=bool(_get(config, "enable_heartflow", False)),
        judge_provider_name=str(_get(config, "judge_provider_name", "") or ""),
        judge_api_base_url=str(_get(config, "judge_api_base_url", "") or "").strip(),
        judge_api_key=str(_get(config, "judge_api_key", "") or ""),
        judge_model=str(_get(config, "judge_model", "") or "").strip(),
        judge_api_path=api_path,
        reply_threshold=float(clamp_number(_get(config, "reply_threshold", 0.6), 0.6, 0.0, 1.0)),
        energy_decay_rate=float(clamp_number(_get(config, "energy_decay_rate", 0.1), 0.1, 0.0, 1.0)),
        energy_recovery_rate=float(clamp_number(_get(config, "energy_recovery_rate", 0.02), 0.02, 0.0, 1.0)),
        context_messages_count=context_count,
        judge_context_count=judge_context_count,
        min_reply_interval_seconds=int(
            clamp_number(_get(config, "min_reply_interval_seconds", 0), 0, 0, 86400, integer=True)
        ),
        judge_timeout_seconds=float(
            clamp_number(_get(config, "judge_timeout_seconds", 30), 30, 5, 120)
        ),
        max_tracked_chats=int(
            clamp_number(_get(config, "max_tracked_chats", 1000), 1000, 1, 10000, integer=True)
        ),
        max_persona_cache=int(
            clamp_number(_get(config, "max_persona_cache", 100), 100, 1, 1000, integer=True)
        ),
        whitelist_enabled=bool(_get(config, "whitelist_enabled", False)),
        chat_whitelist=whitelist,
        judge_include_reasoning=bool(_get(config, "judge_include_reasoning", True)),
        judge_max_retries=int(
            clamp_number(_get(config, "judge_max_retries", 3), 3, 0, 5, integer=True)
        ),
        weights=normalize_weights(weight_values),
        raw_buffer_size=max(context_count, judge_context_count) * 4,
    )
