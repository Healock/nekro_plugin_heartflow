"""Heartflow 的历史消息读取适配层。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import RawMessage


async def load_recent_messages(chat_key: str, limit: int, *, logger: Any = None) -> list[RawMessage]:
    """从 Nekro 的聊天消息表读取有限历史。

    `DBChatMessage` 是当前 Nekro 工作区已经使用的数据库模型。导入放在函数内，
    避免插件导入阶段访问数据库，也让数据库尚未初始化时可以安全降级。
    """

    if not chat_key or limit <= 0:
        return []
    try:
        from nekro_agent.models.db_chat_message import DBChatMessage

        rows = await DBChatMessage.filter(chat_key=chat_key).order_by("-send_timestamp", "-id").limit(limit).all()
        return [
            RawMessage(
                sender_id=str(row.sender_id),
                sender_name=str(row.sender_nickname or row.sender_name or row.sender_id),
                content=str(row.content_text or "").strip(),
                timestamp=float(row.send_timestamp or 0),
                is_bot=str(row.sender_id) == "-1",
                is_tome=bool(row.is_tome),
            )
            for row in reversed(rows)
            if str(row.content_text or "").strip()
        ]
    except Exception as exc:
        if logger is not None:
            logger.warning(f"读取聊天历史失败，已使用当前消息降级：{type(exc).__name__}")
        return []


def merge_current_message(history: Iterable[RawMessage], current: RawMessage, limit: int) -> list[RawMessage]:
    """将尚未入库的当前消息加入有限窗口。"""

    if limit <= 0:
        return []
    return [*list(history), current][-limit:]


def find_last_bot_reply(history: Iterable[RawMessage]) -> str:
    """返回最近一条机器人文本。"""

    for message in reversed(list(history)):
        if message.is_bot and message.content:
            return message.content
    return ""


def render_history(history: Iterable[RawMessage], *, max_chars: int = 4000) -> list[str]:
    """将历史转换为 judge 可读的有界文本。"""

    lines: list[str] = []
    used = 0
    for message in history:
        role = "机器人" if message.is_bot else "群成员"
        line = f"【{role}】{message.sender_name}：{message.content[:500]}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return lines
