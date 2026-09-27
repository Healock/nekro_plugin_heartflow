"""Heartflow 生命周期回调。"""

from __future__ import annotations

from nekro_agent.api.schemas import AgentCtx

from . import plugin
from .runtime import runtime


@plugin.mount_on_channel_reset()
async def reset_channel(ctx: AgentCtx) -> None:
    """重置当前频道的心流内存状态。"""

    runtime.reset_chat(ctx.chat_key)


@plugin.mount_cleanup_method()
async def cleanup_plugin() -> None:
    """清理心流状态、锁和人格缓存。"""

    runtime.clear()
