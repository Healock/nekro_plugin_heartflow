"""Heartflow 管理命令。"""

from __future__ import annotations

import time

from nekro_agent.api.plugin import CmdCtl, CommandExecutionContext, CommandPermission, CommandResponse

from . import config, plugin
from .runtime import runtime
from .settings import load_settings


def _minutes_since(timestamp: float, now: float) -> str:
    if not timestamp:
        return "暂无"
    return f"{max(0.0, now - timestamp) / 60.0:.1f} 分钟前"


@plugin.mount_command(
    name="heartflow",
    description="查看当前频道的心流状态。",
    aliases=["心流"],
    permission=CommandPermission.SUPER_USER,
    category="心流",
)
async def heartflow_status(context: CommandExecutionContext) -> CommandResponse:
    """查看当前频道的心流状态。"""

    settings = load_settings(config)
    state = runtime.states.get(context.chat_key)
    now = time.time()
    if state is None:
        return CmdCtl.success(
            f"频道：{context.chat_key}\n插件状态：{'已启用' if settings.enable_heartflow else '已禁用'}\n当前尚无心流状态。"
        )
    reply_rate = state.total_replies / max(1, state.total_messages) * 100
    return CmdCtl.success(
        "\n".join(
            [
                "心流状态报告",
                f"频道：{context.chat_key}",
                f"插件状态：{'已启用' if settings.enable_heartflow else '已禁用'}",
                f"精力：{state.energy:.2f}/1.00",
                f"上次回复：{_minutes_since(state.last_reply_time, now)}",
                f"消息数：{state.total_messages}",
                f"回复数（按触发估算）：{state.total_replies}",
                f"触发数：{state.total_triggers}",
                f"回复率：{reply_rate:.1f}%",
                f"回复阈值：{settings.reply_threshold:.2f}",
                f"判断模型：{settings.judge_model or '未配置'}",
                f"重试次数：{settings.judge_max_retries}",
                f"白名单：{'启用' if settings.whitelist_enabled else '关闭'}",
                f"人格缓存：{len(runtime.persona_cache)}",
            ]
        )
    )


@plugin.mount_command(
    name="heartflow_reset",
    description="重置当前频道的心流状态。",
    permission=CommandPermission.SUPER_USER,
    category="心流",
)
async def heartflow_reset(context: CommandExecutionContext) -> CommandResponse:
    """重置当前频道的心流状态。"""

    async with runtime.lock_for(context.chat_key):
        runtime.reset_chat(context.chat_key)
    return CmdCtl.success("当前频道的心流状态已重置。")


@plugin.mount_command(
    name="heartflow_cache",
    description="查看心流人格缓存。",
    permission=CommandPermission.SUPER_USER,
    category="心流",
)
async def heartflow_cache_status(_context: CommandExecutionContext) -> CommandResponse:
    """查看人格缓存数量。"""

    if not runtime.persona_cache:
        return CmdCtl.success("当前没有人格缓存。")
    return CmdCtl.success(f"当前人格缓存数量：{len(runtime.persona_cache)}。")


@plugin.mount_command(
    name="heartflow_cache_clear",
    description="清除心流人格缓存。",
    permission=CommandPermission.SUPER_USER,
    category="心流",
)
async def heartflow_cache_clear(_context: CommandExecutionContext) -> CommandResponse:
    """清除人格缓存。"""

    count = runtime.clear_persona_cache()
    return CmdCtl.success(f"已清除 {count} 个心流人格缓存。")
