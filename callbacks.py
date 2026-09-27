"""消息回调和运行时提示注入。"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from nekro_agent.api.message import ChatMessage
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.api.signal import MsgSignal
from nekro_agent.schemas.chat_message import ChatType

from . import config, plugin
from .history import find_last_bot_reply, load_recent_messages, merge_current_message, render_history
from .judge import JudgeEngine
from .judge_client import JudgeClient
from .logic import (
    can_process_message,
    commit_trigger_assumption,
    mark_passive,
    render_active_prompt,
    reserve_trigger,
)
from .models import RawMessage
from .runtime import runtime
from .settings import HeartflowSettings, load_settings


def _is_group_message(message: ChatMessage) -> bool:
    value = getattr(message.chat_type, "value", message.chat_type)
    return str(value) == ChatType.GROUP.value


def _is_command_message(message: ChatMessage) -> bool:
    """兼容部分适配器在扩展字段中保留的命令标记。"""

    ext_data = message.ext_data if isinstance(message.ext_data, dict) else {}
    return bool(ext_data.get("is_command") or ext_data.get("command_name"))


async def _current_persona(ctx: AgentCtx, settings: HeartflowSettings) -> str:
    try:
        preset = await ctx.current_preset()
        content = str(getattr(preset, "content", "") or "").strip()
    except Exception as exc:
        plugin.logger.warning(f"读取当前人格失败，judge 将不使用人格文本：{type(exc).__name__}")
        return ""
    if not content:
        return ""
    content = content[:6000]
    cache_key = hashlib.sha256(content.encode("utf-8")).hexdigest()
    cached = runtime.get_persona(cache_key)
    if cached is not None:
        return cached
    runtime.set_persona(cache_key, content, settings.max_persona_cache)
    return content


async def _build_payload(ctx: AgentCtx, message: ChatMessage, settings: HeartflowSettings, now: float) -> dict[str, Any]:
    current = RawMessage(
        sender_id=str(message.sender_id),
        sender_name=str(message.sender_nickname or message.sender_name or message.sender_id),
        content=(message.content_text or "").strip(),
        timestamp=float(message.send_timestamp or now),
        is_bot=str(message.sender_id) == "-1",
        is_tome=bool(message.is_tome),
    )
    history = await load_recent_messages(message.chat_key, settings.judge_context_count, logger=plugin.logger)
    if not history:
        history = runtime.recent_messages(message.chat_key, settings.judge_context_count)
    window = merge_current_message(history, current, settings.judge_context_count)
    state = runtime.states[message.chat_key]
    persona = await _current_persona(ctx, settings)
    previous_messages = window[:-1]
    last_reply = find_last_bot_reply(previous_messages)
    minutes_since_reply = None
    if state.last_reply_time:
        minutes_since_reply = max(0.0, now - state.last_reply_time) / 60.0
    return {
        "chat_key": message.chat_key,
        "persona": persona,
        "energy": round(state.energy, 4),
        "minutes_since_last_reply": minutes_since_reply,
        "last_bot_reply": last_reply,
        "recent_messages": render_history(window),
        "current_message": {
            "sender_id": current.sender_id,
            "sender_name": current.sender_name,
            "content": current.content,
            "timestamp": current.timestamp,
        },
    }


def _allowed(message: ChatMessage, settings: HeartflowSettings) -> bool:
    if not settings.enable_heartflow or not _is_group_message(message):
        return False
    if settings.whitelist_enabled and (
        not settings.chat_whitelist or message.chat_key not in settings.chat_whitelist
    ):
        return False
    if _is_command_message(message):
        return False
    if str(message.sender_id) == "-1" or not (message.content_text or "").strip():
        return False
    return True


@plugin.mount_on_user_message()
async def on_user_message(ctx: AgentCtx, message: ChatMessage) -> MsgSignal | None:
    """判断普通群消息是否应该触发一次正常 Agent 请求。"""

    settings = load_settings(config)
    if not _allowed(message, settings):
        return None

    chat_key = message.chat_key
    now = time.time()
    async with runtime.lock_for(chat_key):
        state = runtime.get_state(chat_key, settings, now)
        raw_message = RawMessage(
            sender_id=str(message.sender_id),
            sender_name=str(message.sender_nickname or message.sender_name or message.sender_id),
            content=(message.content_text or "").strip(),
            timestamp=float(message.send_timestamp or now),
            is_tome=bool(message.is_tome),
        )
        runtime.record_message(chat_key, raw_message, settings)
        if bool(message.is_tome):
            return None
        if not can_process_message(state, now, settings.min_reply_interval_seconds):
            plugin.logger.debug(f"心流处于冷却中：{chat_key}")
            return None

        try:
            payload = await _build_payload(ctx, message, settings, now)
            client = JudgeClient(
                settings.judge_api_base_url,
                settings.judge_api_key,
                settings.judge_model,
                settings.judge_api_path,
            )
            if not client.is_configured:
                if settings.judge_provider_name:
                    plugin.logger.warning(
                        "检测到旧的 judge_provider_name，但 Nekro 版本需要配置独立 judge_api_base_url、judge_api_key 和 judge_model。"
                    )
                return None
            result = await JudgeEngine(client, plugin.logger).decide(
                payload,
                weights=settings.weights,
                threshold=settings.reply_threshold,
                timeout_seconds=settings.judge_timeout_seconds,
                max_retries=settings.judge_max_retries,
                include_reasoning=settings.judge_include_reasoning,
            )
            state.last_judge_result = result
            if result is None:
                mark_passive(state, settings.energy_recovery_rate)
                return None
            if not result.should_reply:
                mark_passive(state, settings.energy_recovery_rate)
                return None

            pending_seconds = max(60.0, settings.judge_timeout_seconds * 2)
            reserve_trigger(state, now, pending_seconds=pending_seconds)
            # Nekro 公共 API 没有 Agent 完成回调，0.1.0 按触发预留近似提交精力和统计。
            commit_trigger_assumption(
                state,
                now,
                settings.energy_decay_rate,
                pending_seconds=pending_seconds,
            )
            plugin.logger.info(f"心流触发主动参与：{chat_key}，评分 {result.overall_score:.2f}")
            return MsgSignal.FORCE_TRIGGER
        except Exception as exc:
            plugin.logger.exception(f"心流处理消息异常，已安全降级：{type(exc).__name__}")
            mark_passive(state, settings.energy_recovery_rate)
            return None


@plugin.mount_prompt_inject_method(
    "heartflow_active_context",
    "提示当前回复是否由心流主动触发。",
)
async def inject_active_context(ctx: AgentCtx) -> str:
    """为主动触发的正常 Agent 提供短运行时提示。"""

    try:
        settings = load_settings(config)
        if not settings.enable_heartflow:
            return ""
        state = runtime.states.get(ctx.chat_key)
        if state is None:
            return ""
        return render_active_prompt(state, time.time())
    except Exception as exc:
        plugin.logger.warning(f"心流提示注入失败：{type(exc).__name__}")
        return ""
