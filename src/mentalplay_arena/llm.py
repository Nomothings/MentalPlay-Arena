"""Unified LLM client for MentalPlay-Arena.

A single OpenAI-compatible client with three backends selected via .env:
  - api   : primary cloud endpoint (with optional backup fallback)
  - local : vllm-served local model (OpenAI-compatible)
  - mock  : deterministic MockLLM for offline tests / --mock runs

All interviewer/patient code goes through get_llm() — never construct
OpenAI clients elsewhere.
"""

from __future__ import annotations

import ast
import re
import time
import warnings
from string import ascii_uppercase
from typing import Iterable, Sequence

from openai import OpenAI

from .config import Settings, get_settings


def _load_template(name: str, settings: Settings) -> str:
    """Load a prompt template from data/prompts/templates/{name}.txt."""
    path = settings.resolve(settings.prompts_dir) / "templates" / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


class LLMClient:
    """OpenAI-compatible chat client with primary/backup/local backends."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._clients: list[tuple[OpenAI, str]] = []  # (client, model)
        self._init_clients()

    def _init_clients(self) -> None:
        s = self.settings
        if s.llm_active_backend == "local":
            if not s.llm_local_base_url:
                raise RuntimeError("LLM_ACTIVE_BACKEND=local requires LLM_LOCAL_BASE_URL")
            self._clients = [(OpenAI(base_url=s.llm_local_base_url, api_key="local"), s.llm_local_model)]
            return
        # api backend
        if s.llm_api_key and s.llm_api_base_url and s.llm_api_model:
            self._clients.append((OpenAI(api_key=s.llm_api_key, base_url=s.llm_api_base_url), s.llm_api_model))
        if s.llm_backup_key and s.llm_backup_base_url and s.llm_backup_model:
            self._clients.append((OpenAI(api_key=s.llm_backup_key, base_url=s.llm_backup_base_url), s.llm_backup_model))
        if not self._clients:
            raise RuntimeError(
                "No LLM credentials configured. Set LLM_ACTIVE_BACKEND=mock for offline "
                "runs, or fill LLM_API_KEY/LLM_API_BASE_URL/LLM_API_MODEL in .env."
            )

    # ------------------------------------------------------------ basic chat

    def chat(self, prompt: str, system: str | None = None) -> str:
        """Single-shot chat; falls back through clients then raises on total failure."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat_messages(messages)

    def chat_messages(self, messages: list[dict]) -> str:
        """Chat with a full message list (roles: system/user/assistant)."""
        last_error: Exception | None = None
        for attempt in range(max(1, self.settings.llm_max_retries)):
            for client, model in self._clients:
                try:
                    completion = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=self.settings.llm_temperature,
                        max_tokens=self.settings.llm_max_tokens,
                        timeout=self.settings.llm_timeout,
                    )
                    content = completion.choices[0].message.content
                    if content:
                        return content.strip()
                except Exception as exc:  # noqa: BLE001 - provider errors vary
                    last_error = exc
                    warnings.warn(f"LLM call failed ({model}): {exc}")
            time.sleep(self.settings.llm_retry_delay * (attempt + 1))
        raise RuntimeError(f"All LLM attempts failed: {last_error}")

    def chat_batch(self, prompts: Sequence[str], concurrency: int | None = None) -> list[str]:
        """Batch chat preserving input order (sequential; simple and reliable)."""
        return [self.chat(p) for p in prompts]

    # --------------------------------------------------- interview-specific

    def map_answer_to_options(self, answer: str, answer_space: Iterable[str]) -> str:
        """Map a patient's free-text answer to an option letter (A-Z).

        Semantics preserved from the original implementation: first valid
        letter found in the LLM reply wins; any failure defaults to 'A'.
        """
        options = list(answer_space)
        letter_options = list(zip(ascii_uppercase, options))
        valid_letters = set(ascii_uppercase[: len(options)])
        prompt = _load_template("answer_mapping", self.settings).format(
            answer=answer,
            options=" ".join(f"{letter}: {opt}" for letter, opt in letter_options),
        )
        try:
            result = self.chat(prompt).upper()
            for c in ascii_uppercase:
                if c in result:
                    if c in valid_letters:
                        return c
                    warnings.warn(
                        f"Mapped answer '{c}' out of valid range {valid_letters}; defaulting to 'A'."
                    )
                    return "A"
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"Answer mapping failed: {exc}; defaulting to 'A'.")
        return "A"

    def refine_question(self, question_text: str, context: list[dict]) -> str:
        """Rephrase a question naturally for the interview (falls back to raw text)."""
        if not self.settings.llm_refine_questions:
            return question_text
        context_str = self._format_context(context)
        prompt = _load_template("refine_question", self.settings).format(
            context=context_str, question=question_text
        )
        try:
            refined = self.chat(prompt)
            return refined if refined else question_text
        except Exception:
            return question_text

    def generate_empathic_response(self, user_answer: str, context: list[dict]) -> str:
        """Short empathic follow-up (falls back to a neutral sentence)."""
        if not self.settings.llm_empathic_responses:
            return ""
        context_str = self._format_context(context)
        prompt = _load_template("empathic_response", self.settings).format(
            context=context_str, user_answer=user_answer
        )
        try:
            response = self.chat(prompt)
            return response if response else "I understand."
        except Exception:
            return "I understand."

    @staticmethod
    def _format_context(context: list[dict]) -> str:
        if not context:
            return "No previous context"
        return "\n".join(f"{turn['role']}: {turn['content']}" for turn in context[-5:])

def parse_structured_json(text: str) -> dict | None:
    """Best-effort parse of an LLM JSON reply (with markdown fences stripped)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        return ast.literal_eval(cleaned)
    except (ValueError, SyntaxError):
        pass
    try:
        import json

        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class MockLLM:
    """Deterministic stand-in for offline tests and `--mock` runs.

    Scripted answer letters can be provided per question; otherwise every
    answer maps to 'A' (matching the original default semantics).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        scripted_letters: dict[str, str] | None = None,
        scripted_responses: list[str] | None = None,
    ):
        self.settings = settings or get_settings()
        self.scripted_letters = scripted_letters or {}
        self._scripted_responses = list(scripted_responses or [])
        self.chat_calls: list[str] = []

    def chat(self, prompt: str, system: str | None = None) -> str:
        self.chat_calls.append(prompt)
        if self._scripted_responses:
            return self._scripted_responses.pop(0)
        # Default patient-like reply when unscripted: a neutral, in-character answer.
        return "I have been feeling quite low recently."

    def chat_messages(self, messages: list[dict]) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        self.chat_calls.append(last_user)
        if self._scripted_responses:
            return self._scripted_responses.pop(0)
        return "I have been feeling quite low recently."

    def chat_batch(self, prompts: Sequence[str], concurrency: int | None = None) -> list[str]:
        return [self.chat(p) for p in prompts]

    def map_answer_to_options(self, answer: str, answer_space: Iterable[str]) -> str:
        options = list(answer_space)
        if answer in self.scripted_letters:
            return self.scripted_letters[answer]
        return "A"

    def refine_question(self, question_text: str, context: list[dict]) -> str:
        return question_text

    def generate_empathic_response(self, user_answer: str, context: list[dict]) -> str:
        return "I understand."

class LLM:
    """Small facade so interviewer/patient code can use either backend uniformly."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        if self.settings.llm_active_backend == "mock":
            self._impl = MockLLM(settings=self.settings)
        else:
            self._impl = LLMClient(self.settings)

    def __getattr__(self, name: str):
        return getattr(self._impl, name)


def get_llm(settings: Settings | None = None) -> LLM:
    """Factory used by all package code."""
    return LLM(settings)
