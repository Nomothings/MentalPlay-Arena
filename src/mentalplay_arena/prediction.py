"""Best-effort shaping of a run's per-scale result into the evaluation format.

Evaluation expects:
  - LIST scales : list of labels
  - KV scales   : dict {dimension: level}

Where a module provides a dimension breakdown these are derived from it;
otherwise an empty value is returned (the scale simply scores no prediction).
"""

from __future__ import annotations

from .registry import Registry


def _as_score(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def shape_prediction(scale: str, run_scale_result: dict, registry: Registry) -> dict:
    """Convert one scale's run result into {scale: list | dict} for evaluation."""
    definition = registry.scale(scale)
    dimensions = run_scale_result.get("dimensions")

    if definition.is_list:
        module_scores = None
        if isinstance(dimensions, dict):
            module_scores = dimensions.get("module_scores")
        if isinstance(module_scores, list) and module_scores:
            threshold = definition.list_threshold
            labels = [
                m.get("domain") for m in module_scores
                if _as_score(m.get("score")) >= threshold and m.get("domain")
            ]
            return {scale: labels}
        return {scale: []}

    if definition.is_kv:
        if isinstance(dimensions, dict) and dimensions and all(
            isinstance(v, str) for v in dimensions.values()
        ):
            return {scale: dimensions}
        return {scale: {}}

    return {scale: {}}
