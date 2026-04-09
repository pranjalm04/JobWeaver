from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LMSession:
    """In-memory chat history for one logical LM invocation (e.g. one chunk or one job URL)."""

    session_id: str
    _messages: list[dict[str, str]] = field(default_factory=list)

    def reset(self) -> None:
        self._messages.clear()

    def add_system(self, content: str) -> None:
        self._messages.append({"role": "system", "content": content})

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self._messages.append({"role": "assistant", "content": content})

    def messages_for_completion(self) -> list[dict[str, str]]:
        return list(self._messages)
