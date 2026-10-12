"""Guards against the hygiene requirements of the rebuild:

  - no hardcoded API-key literals in source code (all config via .env)
  - no personal names anywhere in the project (names are supplied base64-encoded
    so that this guard itself never leaks them as literals)
  - no absolute machine-specific paths in code (all paths relative)
"""

from __future__ import annotations

import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _decoded(encoded: str) -> str:
    return base64.b64decode(encoded).decode("utf-8")


# Forbidden personal names / path prefixes (base64-encoded, decoded at runtime).
FORBIDDEN_NAMES = [
    _decoded("eW15YW5n"),     # personal name
    _decoded("eGlhb3N1bg=="),  # personal name
    _decoded("c3VueGlhbw=="),  # personal name
    _decoded("L2hvbWUv"),     # home-dir prefix
]

CODE_DIRS = [
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "tests",
]

# Files that legitimately contain the user's API key (gitignored).
KEY_FILES = {PROJECT_ROOT / ".env"}


def _iter_code_files():
    for d in CODE_DIRS:
        if d.is_dir():
            for path in sorted(d.rglob("*.py")):
                if path == Path(__file__):
                    continue  # this guard itself names the forbidden strings
                yield path


def test_no_personal_names_in_code():
    hits = []
    for path in _iter_code_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in FORBIDDEN_NAMES:
            if name in text.lower():
                hits.append(f"{path}: {name}")
    assert not hits, f"Personal/absolute-path strings found: {hits}"


def test_no_api_key_literals_in_code():
    import re

    key_pattern = re.compile(r"sk-[A-Za-z0-9]{20,}")
    hits = []
    for path in _iter_code_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if key_pattern.search(text):
            hits.append(str(path))
    assert not hits, f"Hardcoded API keys in: {hits}"


def test_manifest_relative_and_clean():
    text = (PROJECT_ROOT / "manifest.yaml").read_text(encoding="utf-8")
    for name in FORBIDDEN_NAMES:
        assert name not in text.lower()


def test_gitignore_covers_env():
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi
