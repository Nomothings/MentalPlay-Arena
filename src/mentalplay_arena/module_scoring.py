"""Unified scoring for scale modules.

Every module's data/scales/{Scale}/scoring.py ultimately feeds into this
module, which normalizes the divergent return shapes of the original modules
into a single ScoreResult. A rule-summation fallback covers scales whose
module is missing or whose scoring function errors at runtime, so one bad
module never kills a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import Settings, get_settings
from .registry import Registry
from .rules import RuleEvaluator


@dataclass
class ScoreResult:
    total: float
    severity: str
    dimensions: dict[str, Any] | None = field(default=None)


# Scales whose module consumes per-category score dicts (not raw answers).
KSADS_LIKE_KEYS = ("total_score", "module_scores")


def _is_ksads_like(result: Any) -> bool:
    """True when a module returned the K-SADS-style dict (score + module breakdown)."""
    return isinstance(result, dict) and all(k in result for k in KSADS_LIKE_KEYS)


def normalize_result(result: Any, scale: str) -> ScoreResult:
    """Convert any module return shape into a ScoreResult."""
    if isinstance(result, ScoreResult):
        return result

    if isinstance(result, tuple):
        if len(result) == 3:
            total, dimensions, severity = result
            return ScoreResult(total=float(total), severity=str(severity), dimensions=dimensions)
        if len(result) == 2:
            total, severity = result
            return ScoreResult(total=float(total), severity=str(severity))
        raise TypeError(f"{scale}: unsupported tuple return arity {len(result)}")

    if isinstance(result, dict) and _is_ksads_like(result):
        return ScoreResult(
            total=float(result.get("total_score", 0) or 0),
            severity=str(result.get("severity", "")),
            dimensions={"module_scores": result.get("module_scores")},
        )

    if isinstance(result, dict):
        return ScoreResult(
            total=float(result.get("total", 0) or 0),
            severity=str(result.get("severity", "")),
            dimensions=result.get("dimensions"),
        )

    if isinstance(result, (int, float)):
        return ScoreResult(total=float(result), severity="")

    raise TypeError(f"{scale}: cannot normalize result of type {type(result).__name__}")


def _call_module_function(module: Any, scale: str, answers: list[dict]) -> Any:
    """Call the module's scoring function, preferring the unified entry point."""
    if hasattr(module, "calculate_score"):
        return module.calculate_score(answers)
    # Modules that only expose their scale-specific function.
    specific = {
        "CDRS": "calculate_cdrs_score",
        "C-SSRS": "calculate_cssrs_score",
        "EDE-Q": "calculate_edeq_score",
        "SMQ": "calculate_smq_score",
        "Y-BOCS": "calculate_ybocs_score",
        "YMRS": "calculate_ymrs_score",
        "SNAP-IV-ODD": "calculate_snap_iv_odd_score",
        "BPRS": "calculate_bprs_score",
    }.get(scale)
    if specific and hasattr(module, specific):
        return getattr(module, specific)(answers)
    raise AttributeError(f"{scale}: no scoring entry point found in module")


def compute_scale_scores(
    scale: str,
    answers: list[dict],
    registry: Registry | None = None,
    settings: Settings | None = None,
) -> ScoreResult:
    """Compute scores for a module-backed scale from raw answers.

    answers: list of {"question_id": str, "answer": str} records.
    Falls back to rules.json summation when the module is missing or errors.
    """
    registry = registry or Registry(settings or get_settings())
    settings = settings or get_settings()

    try:
        module = registry.load_scoring_module(scale)
        result = _call_module_function(module, scale, answers)
        return normalize_result(result, scale)
    except Exception:
        pass  # fall through to the rule-summation fallback

    return _fallback_rules_summation(scale, answers, registry)


def compute_ksads_scores(
    category_scores: list[dict],
    registry: Registry | None = None,
    settings: Settings | None = None,
) -> ScoreResult:
    """Compute K-SADS scores from per-category score dicts.

    category_scores: list of {"category_id", "domain", "category_name", "score"}
    consumed by the module's calculate_ksads_score function.
    """
    registry = registry or Registry(settings or get_settings())
    module = registry.load_scoring_module("K-SADS")
    result = module.calculate_ksads_score(category_scores)
    return normalize_result(result, "K-SADS")


def _fallback_rules_summation(
    scale: str, answers: list[dict], registry: Registry
) -> ScoreResult:
    """Sum rule scores whose expression evaluates True (same semantics as the
    original scale_scoring._process_answers_with_rules)."""
    try:
        rules = registry.load_rules(scale)
    except Exception:
        return ScoreResult(total=0.0, severity="N/A")

    answer_map = {a.get("question_id"): a.get("answer") for a in answers}
    evaluator = RuleEvaluator(answer_map)
    total = 0.0
    for rule in rules:
        expression = rule.get("rule")
        if not expression:
            continue
        if evaluator.evaluate(str(expression)):
            total += float(rule.get("score", 0) or 0)

    definition = registry.scale(scale)
    severity = ""
    if definition.severity_thresholds:
        bands = definition.severity_thresholds
        level = sum(1 for t in bands if total >= t)
        names = ["none", "mild", "moderate", "severe", "extremely severe"]
        severity = names[min(level, len(names) - 1)]
    return ScoreResult(total=total, severity=severity)
