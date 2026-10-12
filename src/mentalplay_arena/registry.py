"""Scale registry and module loading.

The manifest.yaml at the project root is the single source of truth for the
scale inventory. This module loads it, resolves each scale to its data files
under data/scales/{Scale}/ and provides typed accessors.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import Settings, get_settings


@dataclass(frozen=True)
class ScaleDef:
    """A single scale entry resolved from the manifest."""

    name: str
    format: str  # LIST | KV
    module: str | None  # directory name under data/scales/, or None
    labels: list[str] = field(default_factory=list)
    list_threshold: float = 0.0
    dimension_thresholds: dict[str, float] = field(default_factory=dict)
    dimensions: dict[str, list[str]] = field(default_factory=dict)
    severity_thresholds: list[float] = field(default_factory=list)

    @property
    def is_list(self) -> bool:
        return self.format == "LIST"

    @property
    def is_kv(self) -> bool:
        return self.format == "KV"

    @property
    def has_module(self) -> bool:
        return bool(self.module)


class Registry:
    """Loads manifest.yaml and exposes the scale inventory."""

    def __init__(self, settings: Settings | None = None, manifest_path: Path | None = None):
        self.settings = settings or get_settings()
        if manifest_path is None:
            from .config import PROJECT_ROOT

            manifest_path = PROJECT_ROOT / "manifest.yaml"
        self.manifest_path = manifest_path
        self.data = self._load_manifest()
        self.scales: dict[str, ScaleDef] = {}
        for name, entry in self.data.get("scales", {}).items():
            self.scales[name] = self._parse_scale(name, entry)
        self.evaluation_scope = list(self.data.get("evaluation_scope", []))

    def _load_manifest(self) -> dict:
        with self.manifest_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _parse_scale(self, name: str, entry: dict) -> ScaleDef:
        return ScaleDef(
            name=name,
            format=str(entry.get("format", "KV")).upper(),
            module=entry.get("module") or None,
            labels=list(entry.get("labels", []) or []),
            list_threshold=float(entry.get("list_threshold", 0.0) or 0.0),
            dimension_thresholds={
                k: float(v) for k, v in (entry.get("dimension_thresholds", {}) or {}).items()
            },
            dimensions={
                k: list(v) for k, v in (entry.get("dimensions", {}) or {}).items()
            },
            severity_thresholds=[float(v) for v in (entry.get("severity_thresholds", []) or [])],
        )

    # ------------------------------------------------------------- accessors

    def scale(self, name: str) -> ScaleDef:
        if name not in self.scales:
            raise KeyError(f"Unknown scale: {name!r} (not declared in manifest.yaml)")
        return self.scales[name]

    def all_names(self) -> list[str]:
        return list(self.scales.keys())

    def module_names(self) -> list[str]:
        return [s.name for s in self.scales.values() if s.has_module]

    def scale_dir(self, scale: str) -> Path:
        """Absolute path to the module directory of a scale (raises if none)."""
        definition = self.scale(scale)
        if not definition.has_module:
            raise KeyError(f"Scale {scale!r} has no interview module (module: null in manifest)")
        return self.settings.resolve(self.settings.scales_dir) / definition.module

    # ------------------------------------------------------------- module data

    def load_config(self, scale: str) -> dict:
        path = self.scale_dir(scale) / "config.yaml"
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def load_inquiries(self, scale: str) -> list[dict]:
        path = self.scale_dir(scale) / "inquiries.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def load_rules(self, scale: str) -> list[dict]:
        path = self.scale_dir(scale) / "rules.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def load_scoring_module(self, scale: str):
        """Import and return the module's scoring.py (raises if unavailable)."""
        import importlib

        scale_dir = self.scale_dir(scale)
        module_name = f"arena_scale_{self._safe_module_name(scale)}"
        spec = importlib.util.spec_from_file_location(
            module_name, scale_dir / "scoring.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load scoring module for scale {scale!r}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _safe_module_name(scale: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in scale).lower()

    def questions_by_id(self, scale: str) -> dict[str, dict]:
        """Map question_id -> question record for fast lookup."""
        return {q["question_id"]: q for q in self.load_inquiries(scale)}
