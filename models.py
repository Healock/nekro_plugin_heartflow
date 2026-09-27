"""Heartflow 的纯数据模型。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """一次 judge 的结构化结果。"""

    relevance: float = 0.0
    willingness: float = 0.0
    social: float = 0.0
    timing: float = 0.0
    continuity: float = 0.0
    overall_score: float = 0.0
    should_reply: bool = False
    reasoning: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "relevance": self.relevance,
            "willingness": self.willingness,
            "social": self.social,
            "timing": self.timing,
            "continuity": self.continuity,
            "overall_score": self.overall_score,
            "should_reply": self.should_reply,
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True, slots=True)
class RawMessage:
    """用于 judge 的轻量消息记录。"""

    sender_id: str
    sender_name: str
    content: str
    timestamp: float
    is_bot: bool = False
    is_tome: bool = False


@dataclass(slots=True)
class ChatState:
    """单个聊天频道的运行状态。"""

    energy: float = 1.0
    last_reply_time: float = 0.0
    last_trigger_time: float = 0.0
    last_energy_update_time: float = 0.0
    last_access_time: float = 0.0
    last_reset_date: str = ""
    total_messages: int = 0
    total_replies: int = 0
    total_triggers: int = 0
    pending_trigger_until: float = 0.0
    last_judge_result: JudgeResult | None = None
    raw_messages: Deque[RawMessage] = field(default_factory=deque)
