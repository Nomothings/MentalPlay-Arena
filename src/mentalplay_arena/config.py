"""Central configuration for MentalPlay-Arena.

All settings are loaded from the single .env file at the project root.
Every module in the package must obtain settings through get_settings()
rather than reading environment variables or files directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


# Project root = MentalPlay-Arena/ (parent of the src/ directory).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    """Runtime settings derived from the .env file (all relative paths resolved)."""

    # Backend selection
    llm_active_backend: str = "api"  # api | local | mock

    # Primary cloud API
    llm_api_base_url: str = ""
    llm_api_key: str = ""
    llm_api_model: str = ""

    # Backup cloud API
    llm_backup_base_url: str = ""
    llm_backup_key: str = ""
    llm_backup_model: str = ""

    # Local model (vllm, OpenAI-compatible)
    llm_local_base_url: str = "http://127.0.0.1:8001/v1"
    llm_local_model: str = ""

    # Common LLM parameters
    llm_timeout: float = 60.0
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.7
    llm_batch_size: int = 10
    llm_max_retries: int = 5
    llm_retry_delay: float = 2.0

    # Interview behavior
    llm_refine_questions: bool = True
    llm_empathic_responses: bool = True
    max_turns_per_scale: int = 200

    # Patient memory
    memory_method: str = "none"  # none | window
    memory_window_size: int = 5

    # Storage paths (relative to project root)
    database_path: Path = Path("data/storage/arena.db")
    runs_dir: Path = Path("data/runs")
    predictions_dir: Path = Path("data/predictions")
    characters_path: Path = Path("data/characters.jsonl")
    ground_truth_path: Path = Path("data/ground_truth/results.jsonl")
    scales_dir: Path = Path("data/scales")
    prompts_dir: Path = Path("data/prompts")

    # Translation
    google_translate_api_key: str = ""
    translation_source_lang: str = "zh-CN"
    translation_target_lang: str = "en"

    # Model downloads
    hf_endpoint: str = "https://hf-mirror.com"

    # Extra / unknown keys preserved for forward compatibility.
    extras: dict = field(default_factory=dict)

    def resolve(self, path: Path) -> Path:
        """Resolve a possibly-relative path against the project root."""
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _env_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env_path: Path | None = None) -> Settings:
    """Load settings from the .env file (project root by default).

    In tests an explicit env_path can point at a temporary .env.
    """
    target = env_path or (PROJECT_ROOT / ".env")
    load_dotenv(dotenv_path=target, override=False)

    env = os.environ
    extras = {k: v for k, v in env.items() if k.startswith("LLM_") or k.startswith("MEMORY_")}

    def path_of(key: str) -> Path:
        return Path(env.get(key, "") or key)

    return Settings(
        llm_active_backend=env.get("LLM_ACTIVE_BACKEND", "api").strip().lower(),
        llm_api_base_url=env.get("LLM_API_BASE_URL", "").strip(),
        llm_api_key=env.get("LLM_API_KEY", "").strip(),
        llm_api_model=env.get("LLM_API_MODEL", "").strip(),
        llm_backup_base_url=env.get("LLM_BACKUP_BASE_URL", "").strip(),
        llm_backup_key=env.get("LLM_BACKUP_KEY", "").strip(),
        llm_backup_model=env.get("LLM_BACKUP_MODEL", "").strip(),
        llm_local_base_url=env.get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:8001/v1").strip(),
        llm_local_model=env.get("LLM_LOCAL_MODEL", "").strip(),
        llm_timeout=float(env.get("LLM_TIMEOUT", "60") or 60),
        llm_max_tokens=int(env.get("LLM_MAX_TOKENS", "2048") or 2048),
        llm_temperature=float(env.get("LLM_TEMPERATURE", "0.7") or 0.7),
        llm_batch_size=int(env.get("LLM_BATCH_SIZE", "10") or 10),
        llm_max_retries=int(env.get("LLM_MAX_RETRIES", "5") or 5),
        llm_retry_delay=float(env.get("LLM_RETRY_DELAY", "2") or 2),
        llm_refine_questions=_env_bool(env.get("LLM_REFINE_QUESTIONS", ""), True),
        llm_empathic_responses=_env_bool(env.get("LLM_EMPATHIC_RESPONSES", ""), True),
        max_turns_per_scale=int(env.get("MAX_TURNS_PER_SCALE", "200") or 200),
        memory_method=env.get("MEMORY_METHOD", "none").strip().lower(),
        memory_window_size=int(env.get("MEMORY_WINDOW_SIZE", "5") or 5),
        database_path=path_of("DATABASE_PATH"),
        runs_dir=path_of("RUNS_DIR"),
        predictions_dir=path_of("PREDICTIONS_DIR"),
        characters_path=path_of("CHARACTERS_PATH"),
        ground_truth_path=path_of("GROUND_TRUTH_PATH"),
        google_translate_api_key=env.get("GOOGLE_TRANSLATE_API_KEY", "").strip(),
        translation_source_lang=env.get("TRANSLATION_SOURCE_LANG", "zh-CN").strip(),
        translation_target_lang=env.get("TRANSLATION_TARGET_LANG", "en").strip(),
        hf_endpoint=env.get("HF_ENDPOINT", "https://hf-mirror.com").strip(),
        extras=extras,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings accessor. All package code should use this."""
    return load_settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests between runs)."""
    get_settings.cache_clear()
