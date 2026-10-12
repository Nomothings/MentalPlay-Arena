"""Conversation memory strategies for the simulated patient.

Only two strategies are kept (the original had five):
  - NoMemory     : scale mode default; the patient sees only its system prompt
                   and the current question each turn.
  - WindowMemory : interview mode; keeps the last k conversation turns so the
                   patient stays consistent across scales.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMemory(ABC):
    """Common interface for all memory strategies."""

    @abstractmethod
    def add_message(self, role: str, content: str) -> None: ...

    @abstractmethod
    def get_messages(self) -> list[dict]:
        """Conversation turns to include in the next prompt (oldest first)."""

    @abstractmethod
    def get_history(self) -> list[dict]:
        """Full recorded history (independent of what fits in context)."""

    def clear(self) -> None:
        self.add_message = self._noop  # pragma: no cover - placeholder

    @staticmethod
    def _noop(role: str, content: str) -> None:  # pragma: no cover
        pass


class NoMemory(BaseMemory):
    """Keeps no conversation; only the system prompt is sent each turn."""

    def __init__(self) -> None:
        self._history: list[dict] = []

    def add_message(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        return []

    def get_history(self) -> list[dict]:
        return list(self._history)


class WindowMemory(BaseMemory):
    """Keeps the last k turns (each turn = one patient reply)."""

    def __init__(self, window_size: int = 5) -> None:
        self.window_size = max(1, window_size)
        self._history: list[dict] = []

    def add_message(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        # include the last (2 * window_size) messages so interviewer questions
        # and patient answers stay paired within the window.
        return self._history[-(2 * self.window_size) :]

    def get_history(self) -> list[dict]:
        return list(self._history)


def create_memory(method: str, window_size: int = 5) -> BaseMemory:
    method = (method or "none").strip().lower()
    if method == "window":
        return WindowMemory(window_size)
    return NoMemory()
