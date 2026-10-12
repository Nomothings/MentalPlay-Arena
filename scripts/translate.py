"""Batch translation of Chinese assets into English.

Pipeline:
  1. translate the 12 MentalInfusion prompt files  -> data/prompts/{name}.txt
  2. translate SAPAS inquiries.json question_text  -> in-place in data/scales/SAPAS/

Backends (selected via .env TRANSLATION_BACKEND):
  - llm   (default): the project's unified LLM client (.env LLM_* config)
  - google_api     : Google Cloud Translation v2 REST API (needs GOOGLE_TRANSLATE_API_KEY)
  - free           : deep-translator GoogleTranslator (public endpoint; rate-limited)

Design guarantees:
  - the LLM prompt states the task is machine translation and forbids anything
    but the translation itself
  - placeholders (<INPUT>, <ANSWER_SPACE>, <QUESTION_TEXT>, {var} tokens) are
    protected with sentinels and restored after translation; post-translation
    validation re-checks that no placeholder was lost
  - idempotent: sha256 state file data/prompts/.translations.json; unchanged
    sources are skipped; only failed/absent entries are retried
  - output validation: no CJK characters may remain in any target, and every
    placeholder present in the source must still be present in the target
  - failed chunks are logged to data/prompts/translate_errors.log and the
    script exits non-zero if any chunk failed
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------- setup

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from mentalplay_arena.config import get_settings  # noqa: E402

ORIGINAL_PROMPTS_DIR = PROJECT_ROOT / ".." / "MentalPlay" / "MentalInfusion" / "prompts"
PROMPT_TARGETS = [
    "DASS-42", "DERS", "ERQ", "IIP", "IRI", "MBTI", "PDQ", "PID",
    "SCL-90", "SUICIDE", "WHODAS", "polishment",
]
SAPAS_INQUIRIES = PROJECT_ROOT / "data" / "scales" / "SAPAS" / "inquiries.json"
STATE_FILE = PROJECT_ROOT / "data" / "prompts" / ".translations.json"
ERROR_LOG = PROJECT_ROOT / "data" / "prompts" / "translate_errors.log"

# Placeholders that must survive translation verbatim.
PLACEHOLDER_PATTERNS = [
    re.compile(r"<INPUT>"),
    re.compile(r"<ANSWER_SPACE>"),
    re.compile(r"<QUESTION_TEXT>"),
    re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}"),
]
CJK_RE = re.compile(r"[一-鿿]")
CHUNK_MAX_CHARS = 2500  # keep each chunk's translation under the token budget


# ------------------------------------------------------------------ utilities

def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def protect_placeholders(text: str) -> tuple[str, list[str]]:
    """Replace known placeholders with sentinels; return (protected, originals)."""
    originals: list[str] = []
    counter = 0
    for pattern in PLACEHOLDER_PATTERNS:
        text, n = pattern.subn(lambda m: _sentinel(counter, originals, m.group(0), text), text)
        counter += n  # placeholder may appear multiple times
    return text, originals


def _sentinel(index: int, originals: list[str], original: str, _text: str) -> str:
    # one sentinel per unique original value
    if original in originals:
        return f"__PH{originals.index(original)}__"
    originals.append(original)
    return f"__PH{len(originals) - 1}__"


def restore_placeholders(text: str, originals: list[str]) -> str:
    for i, original in enumerate(originals):
        text = text.replace(f"__PH{i}__", original)
    return text


def split_chunks(text: str) -> list[str]:
    """Split into <= CHUNK_MAX_CHARS chunks on paragraph boundaries."""
    paragraphs = re.split(r"(\n\s*\n)", text)
    chunks: list[str] = []
    current = ""
    for part in paragraphs:
        if len(current) + len(part) > CHUNK_MAX_CHARS and current:
            chunks.append(current)
            current = part
        else:
            current += part
    if current.strip():
        chunks.append(current)
    return chunks


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


PLACEHOLDER_TOKEN_RE = re.compile(r"(<[A-Za-z_][A-Za-z0-9_]*>|\{[A-Za-z_][A-Za-z0-9_]*\})")


def lost_placeholders(source: str, target: str) -> list[str]:
    """Return placeholders present in source but missing in target."""
    source_tokens = set(PLACEHOLDER_TOKEN_RE.findall(source))
    target_tokens = set(PLACEHOLDER_TOKEN_RE.findall(target))
    return sorted(source_tokens - target_tokens)


def strip_code_fence(text: str) -> str:
    """Remove a single surrounding markdown fence if the model added one."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def validate_translation(source: str, target: str) -> list[str]:
    """Check a translation: no CJK may remain and no placeholder may be lost.

    Returns a list of human-readable problems (empty when valid).
    """
    problems: list[str] = []
    if has_cjk(target):
        problems.append("CJK characters remain in the translation")
    missing = lost_placeholders(source, target)
    if missing:
        problems.append(f"placeholders lost: {missing}")
    return problems


CJK_PUNCT_MAP = {
    "【": "[", "】": "]", "（": "(", "）": ")", "，": ",", "。": ".",
    "；": ";", "：": ":", "！": "!", "？": "?", "、": ", ", "—": "—",
    "·": "·", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...",
    "　": " ", "／": "/", "－": "-", "～": "~",
}


def normalize_cjk_punct(text: str) -> str:
    """Replace leftover CJK punctuation with English equivalents.

    Translation models sometimes keep Chinese bracket/colon glyphs even after
    translating the words; this normalizes them so the output is truly English.
    """
    return "".join(CJK_PUNCT_MAP.get(ch, ch) for ch in text)


# ---------------------------------------------------------------- backends

class TranslateBackend:
    def translate(self, chunks: list[str]) -> list[str]:
        raise NotImplementedError


class GoogleApiBackend(TranslateBackend):
    """Google Cloud Translation v2 REST API (batched)."""

    def __init__(self, api_key: str, source: str, target: str):
        self.api_key = api_key
        self.source = source
        self.target = target

    def translate(self, chunks: list[str]) -> list[str]:
        import requests

        results: list[str] = []
        for i in range(0, len(chunks), 20):  # v2 allows up to 128 qs; keep 20 for safety
            batch = chunks[i : i + 20]
            resp = requests.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": self.api_key},
                json={"q": batch, "source": self.source, "target": self.target, "format": "text"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()["data"]["translations"]
            results.extend(item["translatedText"] for item in data)
            if i + 20 < len(chunks):
                time.sleep(0.2)
        return results


class FreeEndpointBackend(TranslateBackend):
    """deep-translator public Google endpoint (rate-limited)."""

    def __init__(self, source: str, target: str):
        from deep_translator import GoogleTranslator

        self.translator = GoogleTranslator(source=source, target=target)

    def translate(self, chunks: list[str]) -> list[str]:
        results: list[str] = []
        for chunk in chunks:
            for attempt in range(4):
                try:
                    results.append(self.translator.translate(chunk))
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 3:
                        raise
                    time.sleep(2 * (attempt + 1))
            time.sleep(1.0)
        return results


LLM_TRANSLATION_PROMPT = """# Task: Machine Translation (Chinese -> English)

You are a professional medical translator. Translate the Chinese text delimited
by <SOURCE>...</SOURCE> into English. This text is a clinical psychology
data-collection prompt used to instruct an LLM.

## Translation Rules
1. Translate ALL Chinese text into natural, fluent English.
2. Preserve every placeholder token EXACTLY as-is: <INPUT>, <ANSWER_SPACE>,
   <QUESTION_TEXT>, {{context}}, {{question}}, {{user_answer}}, and any other
   <...> or {{...}} token you encounter. Never translate, alter or drop them.
3. Preserve the markdown structure: headings (##, ###, ####), bullet lists,
   numbering, bold/emphasis markers, tables and code blocks.
4. Keep scale names and English medical terms as-is (do not translate
   already-English words).
5. Do not add, remove, reorder or summarize any content.

## Output
Output ONLY the English translation of the source text. No preamble, no
explanations, no code fences.

<SOURCE>
{text}
</SOURCE>
"""


class LLMBackend(TranslateBackend):
    """Translation through the project's unified LLM client (.env LLM_*)."""

    def __init__(self):
        from dataclasses import replace

        from mentalplay_arena.config import get_settings
        from mentalplay_arena.llm import get_llm

        # Translation needs a larger token budget and a more patient timeout
        # than short chat calls (a 2.5k-char Chinese chunk can yield ~6.5k
        # chars of English, which exceeds the default 2048-token cap).
        settings = replace(
            get_settings(), llm_max_tokens=4096, llm_timeout=300
        )
        self.llm = get_llm(settings)

    def translate(self, chunks: list[str]) -> list[str]:
        results: list[str] = []
        for chunk in chunks:
            translated = self._translate_chunk(chunk)
            results.append(translated)
        return results

    def _translate_chunk(self, chunk: str) -> str:
        """Translate one chunk, retrying once if CJK survives or placeholders break."""
        for attempt in range(2):
            raw = self.llm.chat(LLM_TRANSLATION_PROMPT.format(text=chunk))
            cleaned = normalize_cjk_punct(strip_code_fence(raw))
            if not has_cjk(cleaned) and not lost_placeholders(chunk, cleaned):
                return cleaned
            if attempt == 1:
                raise RuntimeError(
                    "LLM translation failed validation after retry "
                    "(CJK remaining or placeholders lost)"
                )
        return chunk  # unreachable; kept for type checker


def build_backend() -> TranslateBackend:
    settings = get_settings()
    mode = settings.extras.get("TRANSLATION_BACKEND", "llm").strip().lower()
    if mode == "google_api" and settings.google_translate_api_key:
        return GoogleApiBackend(
            settings.google_translate_api_key,
            settings.translation_source_lang,
            settings.translation_target_lang,
        )
    if mode == "free":
        return FreeEndpointBackend(
            settings.translation_source_lang, settings.translation_target_lang
        )
    return LLMBackend()


# ---------------------------------------------------------------- translation

def translate_text(text: str, backend: TranslateBackend) -> str:
    """Translate free text while protecting placeholders."""
    protected, originals = protect_placeholders(text)
    if not has_cjk(protected):
        return text  # nothing to translate (and placeholders preserved)
    chunks = split_chunks(protected)
    translated_chunks = backend.translate(chunks)
    joined = "".join(translated_chunks)
    return restore_placeholders(joined, originals)


def translate_file(src: Path, dst: Path) -> bool:
    """Translate one prompt file. Returns True on success, False on failure."""
    state = load_state()
    text = src.read_text(encoding="utf-8")
    digest = sha256_of(text)
    key = os.path.relpath(src.resolve(), PROJECT_ROOT)

    # Idempotency: skip only when the source is unchanged AND an English target
    # already exists (the source itself is Chinese, so it is not the check).
    if (
        state.get(key, {}).get("sha256") == digest
        and dst.exists()
        and not has_cjk(dst.read_text(encoding="utf-8"))
    ):
        return True

    backend = build_backend()
    translated = ""
    last_error: Exception | None = None
    for attempt in range(3):  # file-level retry: a transient API failure may clear up
        try:
            translated = translate_text(text, backend)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2 * (attempt + 1))
    if not translated:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {src.name}: {last_error}\n")
        return False

    problems = validate_translation(text, translated)
    if problems:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {src.name}: {problems}\n")
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(translated, encoding="utf-8")
    state[key] = {"sha256": digest, "target": str(dst), "translated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_state(state)
    return True


def translate_sapas_inquiries() -> bool:
    """Translate question_text fields of SAPAS inquiries.json in place."""
    state = load_state()
    data = json.loads(SAPAS_INQUIRIES.read_text(encoding="utf-8"))
    digest = sha256_of(SAPAS_INQUIRIES.read_text(encoding="utf-8"))
    key = f"json:{os.path.relpath(SAPAS_INQUIRIES.resolve(), PROJECT_ROOT)}"

    if state.get(key, {}).get("sha256") == digest:
        return True

    backend = build_backend()
    changed = False
    try:
        for item in data:
            qt = item.get("question_text", "")
            if has_cjk(qt):
                translated = translate_text(qt, backend)
                if validate_translation(qt, translated):
                    raise ValueError(f"SAPAS q{item.get('question_id')}: translation failed validation")
                item["question_text"] = translated
                changed = True
            for opt in item.get("answer_space", []):
                if has_cjk(opt):
                    translated = translate_text(opt, backend)
                    if validate_translation(opt, translated):
                        raise ValueError(f"SAPAS q{item.get('question_id')}: option translation failed validation")
                    idx = item["answer_space"].index(opt)
                    item["answer_space"][idx] = translated
                    changed = True
    except Exception as exc:  # noqa: BLE001
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SAPAS inquiries: {exc}\n")
        return False

    if changed:
        SAPAS_INQUIRIES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    state[key] = {"sha256": digest, "translated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_state(state)
    return True


def main() -> int:
    settings = get_settings()
    prompts_src = Path(settings.extras.get("PROMPTS_SRC", str(ORIGINAL_PROMPTS_DIR)))
    prompts_dst = settings.resolve(settings.prompts_dir)

    failures: list[str] = []

    for name in PROMPT_TARGETS:
        src = Path(prompts_src) / f"{name}.txt"
        dst = prompts_dst / f"{name}.txt"
        if not src.exists():
            continue
        ok = translate_file(src, dst)
        print(f"{'OK  ' if ok else 'FAIL'} {name}.txt")
        if not ok:
            failures.append(f"{name}.txt")

    ok = translate_sapas_inquiries()
    print(f"{'OK  ' if ok else 'FAIL'} SAPAS/inquiries.json")
    if not ok:
        failures.append("SAPAS/inquiries.json")

    if failures:
        print(f"\n{len(failures)} translation failures logged to {ERROR_LOG}")
        return 1
    print("\nAll translations complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
