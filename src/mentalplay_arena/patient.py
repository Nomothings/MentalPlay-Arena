"""The simulated patient agent.

Loads a character profile from the database, wraps it in an English role-play
system prompt, and answers clinician/interviewer utterances through the unified
LLM client with a pluggable memory strategy.
"""

from __future__ import annotations

from .config import Settings, get_settings
from .llm import get_llm
from .memory import BaseMemory, create_memory


class PatientAgent:
    def __init__(
        self,
        character_id: str,
        character_info: str | None = None,
        llm=None,
        memory: BaseMemory | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.character_id = character_id
        self.llm = llm if llm is not None else get_llm(self.settings)
        self.memory = memory or create_memory(self.settings.memory_method, self.settings.memory_window_size)
        self.character_info = character_info or ""
        self._system_prompt: str | None = None

    def set_character_info(self, character_info: str) -> None:
        self.character_info = character_info
        self._system_prompt = None  # invalidate cached prompt

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            template_path = self.settings.resolve(self.settings.prompts_dir) / "templates" / "patient_system.txt"
            template = template_path.read_text(encoding="utf-8")
            self._system_prompt = template.replace("{character_info}", self.character_info)
        return self._system_prompt

    def chat(self, utterance: str) -> str:
        """Answer the interviewer's utterance as the patient."""
        history = self.memory.get_messages()
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        messages.append({"role": "user", "content": utterance})

        response = self.llm.chat_messages(messages)
        self.memory.add_message("user", utterance)
        self.memory.add_message("assistant", response)
        return response

    def get_history(self) -> list[dict]:
        return self.memory.get_history()
