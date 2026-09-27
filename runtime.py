"""Heartflow 的运行时状态容器。"""

from __future__ import annotations

import asyncio
import weakref
from collections import OrderedDict
from typing import Iterable

from .logic import refresh_state
from .models import ChatState, RawMessage
from .settings import HeartflowSettings


class HeartflowRuntime:
    """保存内存状态、会话锁和人格缓存。"""

    def __init__(self) -> None:
        self.states: dict[str, ChatState] = {}
        self.locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self.persona_cache: OrderedDict[str, str] = OrderedDict()

    def lock_for(self, chat_key: str) -> asyncio.Lock:
        lock = self.locks.get(chat_key)
        if lock is None:
            lock = asyncio.Lock()
            self.locks[chat_key] = lock
        return lock

    def get_state(self, chat_key: str, settings: HeartflowSettings, now: float) -> ChatState:
        if chat_key not in self.states:
            self._evict(settings.max_tracked_chats)
            self.states[chat_key] = ChatState()
        state = self.states[chat_key]
        if state.raw_messages.maxlen != settings.raw_buffer_size:
            state.raw_messages = type(state.raw_messages)(state.raw_messages, maxlen=settings.raw_buffer_size)
        refresh_state(state, now, settings.energy_recovery_rate)
        return state

    def record_message(self, chat_key: str, message: RawMessage, settings: HeartflowSettings) -> None:
        state = self.states.get(chat_key)
        if state is None:
            state = ChatState()
            self.states[chat_key] = state
        if state.raw_messages.maxlen != settings.raw_buffer_size:
            state.raw_messages = type(state.raw_messages)(state.raw_messages, maxlen=settings.raw_buffer_size)
        state.raw_messages.append(message)
        state.total_messages += 1

    def recent_messages(self, chat_key: str, limit: int) -> list[RawMessage]:
        state = self.states.get(chat_key)
        if state is None or limit <= 0:
            return []
        return list(state.raw_messages)[-limit:]

    def get_persona(self, cache_key: str) -> str | None:
        value = self.persona_cache.get(cache_key)
        if value is not None:
            self.persona_cache.move_to_end(cache_key)
        return value

    def set_persona(self, cache_key: str, value: str, max_entries: int) -> None:
        self.persona_cache[cache_key] = value
        self.persona_cache.move_to_end(cache_key)
        while len(self.persona_cache) > max_entries:
            self.persona_cache.popitem(last=False)

    def reset_chat(self, chat_key: str) -> None:
        self.states.pop(chat_key, None)

    def clear_persona_cache(self) -> int:
        count = len(self.persona_cache)
        self.persona_cache.clear()
        return count

    def clear(self) -> None:
        self.states.clear()
        self.locks.clear()
        self.persona_cache.clear()

    def _evict(self, max_entries: int) -> None:
        while len(self.states) >= max_entries:
            candidates: Iterable[tuple[str, ChatState]] = sorted(
                self.states.items(), key=lambda item: item[1].last_access_time
            )
            for chat_key, _state in candidates:
                lock = self.locks.get(chat_key)
                if lock is not None and lock.locked():
                    continue
                self.states.pop(chat_key, None)
                break
            else:
                return


runtime = HeartflowRuntime()
