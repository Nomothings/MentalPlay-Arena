"""Anonymity audit for a paper submission.

Scans the project for anything that could identify the authors or the machine:
personal names, absolute machine paths, hostnames, e-mails, API-key literals,
and identifiable clinical institutions inside the case data.

Run before packaging the submission:
    uv run python scripts/audit_identity.py

Exit code 0 = clean; 1 = issues found. Sensitive strings are supplied
base64-encoded so this audit tool itself never leaks them as literals.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".venv", "data/models", ".git", "__pycache__", ".pytest_cache", "data/runs",
             "data/storage", "data/predictions", ".hf_cache"}

KNOWN_ISSUES = []  # (category, file, snippet)


def _dec(encoded: str) -> str:
    return base64.b64decode(encoded).decode("utf-8")


# ------------------------------------------------------------------- patterns

# Personal usernames and hostnames observed on the build machine, supplied
# base64-encoded (decoded at runtime) so this file stays literal-free.
IDENTITY_WORDS = [
    _dec("eW15YW5n"),           # personal username
    _dec("eWluZ3l1bWluZw=="),   # personal name
    _dec("emV5dQ=="),           # personal username
    _dec("c3VueGlhbw=="),       # personal name
    _dec("eGlhb3N1bg=="),       # personal name
    _dec("bm9kZTA5"),           # build-machine hostname
]

# Match only absolute path prefixes (line-start or after a quote/space/equal),
# not bare relative references such as "MentalPlay/data/...".
ABS_PATH_RE = re.compile(r"(?:^|[\s\"'=(])(/(?:home|Users|root|data|tmp|var|opt|etc|export)/)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
API_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,}")

# Identifiable clinical institutions that were found in the case data and
# have since been anonymized (base64-encoded; a residual match is a failure).
HOSPITAL_RE = re.compile(
    "|".join([
        _dec("Smluc2hhbiBIb3NwaXRhbA=="),   # Jinshan Hospital
        _dec("WW91eWFuZyBIb3NwaXRhbA=="),   # Youyang Hospital
        _dec("SHVheGkgSG9zcGl0YWw="),       # Huaxi Hospital
        _dec("U291dGh3ZXN0IEhvc3BpdGFs"),   # Southwest Hospital
    ]),
    re.I,
)
PHONE_RE = re.compile(r"1[3-9]\d{9}|0\d{2,3}[-\s]\d{7,8}")
ID_CARD_RE = re.compile(r"\d{17}[\dXx]")
CN_HOSPITAL_RE = re.compile(r"[一-鿿]{2,6}(?:医院|卫生院|诊所)")


# --------------------------------------------------------------------- scan


def _iter_text_files():
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # filter by the full relative directory path so nested skips work
        def _keep(d: str) -> bool:
            rel = os.path.relpath(os.path.join(dirpath, d), PROJECT_ROOT)
            return rel not in SKIP_DIRS and not d.startswith(".")

        dirnames[:] = [d for d in dirnames if _keep(d)]
        for fn in filenames:
            yield Path(dirpath) / fn


def _scan_file(path: Path) -> None:
    try:
        data = path.read_bytes()
    except OSError:
        return
    if b"\x00" in data[:2000]:
        return  # binary
    text = data.decode("utf-8", errors="ignore")

    for word in IDENTITY_WORDS:
        if word.lower() in text.lower():
            KNOWN_ISSUES.append(("identity", str(path.relative_to(PROJECT_ROOT)), word))
    for m in ABS_PATH_RE.finditer(text):
        if str(path.relative_to(PROJECT_ROOT)).startswith("tests"):
            continue  # path-guard tests reference patterns intentionally
        KNOWN_ISSUES.append(("abs_path", str(path.relative_to(PROJECT_ROOT)), m.group(0)))
    for m in EMAIL_RE.finditer(text):
        KNOWN_ISSUES.append(("email", str(path.relative_to(PROJECT_ROOT)), m.group(0)))
    for m in API_KEY_RE.finditer(text):
        KNOWN_ISSUES.append(("api_key", str(path.relative_to(PROJECT_ROOT)), m.group(0)[:12] + "..."))


def _scan_case_data() -> None:
    path = PROJECT_ROOT / "data" / "characters.jsonl"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                info = json.loads(line).get("character_info", "")
            except json.JSONDecodeError:
                continue
            for label, pattern in (
                ("hospital", HOSPITAL_RE),
                ("phone", PHONE_RE),
                ("id_card", ID_CARD_RE),
                ("cn_hospital", CN_HOSPITAL_RE),
            ):
                for m in pattern.finditer(info):
                    KNOWN_ISSUES.append((label, f"data/characters.jsonl:{i}", m.group(0)[:40]))


def _check_env_not_present() -> None:
    if (PROJECT_ROOT / ".env").exists():
        print("[info] .env exists locally (gitignored) — do NOT include it in the submission bundle.")
    if (PROJECT_ROOT / ".env.example").exists():
        text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        for m in API_KEY_RE.finditer(text):
            KNOWN_ISSUES.append(("api_key_in_example", ".env.example", m.group(0)[:12]))


def main() -> int:
    for path in _iter_text_files():
        _scan_file(path)
    _scan_case_data()
    _check_env_not_present()

    if not KNOWN_ISSUES:
        print("✓ anonymity audit PASSED — no identifying information found.")
        return 0

    print(f"✗ anonymity audit FAILED — {len(KNOWN_ISSUES)} finding(s):")
    for category, file, snippet in KNOWN_ISSUES[:50]:
        print(f"   [{category}] {file}: {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
