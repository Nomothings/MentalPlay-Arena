"""Evaluation metrics.

Pure, offline scoring of a prediction against expert ground truth:
  - LIST scales : F1 (primary), precision, recall, Jaccard
  - KV scales   : ordinal similarity (mean of 1 - |rank_pred-rank_gt| / d_max)

Scale type and the ordinal level ordering come from the manifest, so no scale
name is hardcoded in the metric code.
"""

from __future__ import annotations

from .registry import Registry, ScaleDef


def compute_list_score(pred_list: list, gt_list: list) -> dict[str, float]:
    """F1 / precision / recall / Jaccard for list scales (matches the original)."""
    pred_set = set(pred_list)
    gt_set = set(gt_list)

    if not gt_set and not pred_set:
        return {"f1_score": 1.0, "precision": 1.0, "recall": 1.0, "jaccard": 1.0}
    if not gt_set or not pred_set:
        return {"f1_score": 0.0, "precision": 0.0, "recall": 0.0, "jaccard": 0.0}

    tp = len(pred_set & gt_set)
    precision = tp / len(pred_set)
    recall = tp / len(gt_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    union = pred_set | gt_set
    jaccard = len(pred_set & gt_set) / len(union) if union else 0.0

    return {
        "f1_score": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "jaccard": round(jaccard, 4),
    }


def ordinal_map_for(definition: ScaleDef) -> dict[str, int]:
    """Build a global level->rank map from the manifest dimensions.

    Levels are ordered by first appearance across the scale's dimensions, so
    'weak < moderate < strong' and 'normal < mild < moderate < severe <
    extremely severe' come out in the correct clinical order.
    """
    ordering: list[str] = []
    for levels in definition.dimensions.values():
        for level in levels:
            if level not in ordering:
                ordering.append(level)
    return {level: rank for rank, level in enumerate(ordering)}


def compute_kv_score(pred_dict: dict, gt_dict: dict, definition: ScaleDef) -> dict:
    """Ordinal similarity across dimensions present in both prediction and GT."""
    ordinal_map = ordinal_map_for(definition)
    d_max = max(1, len(ordinal_map) - 1)

    dimension_scores: dict[str, float] = {}
    total = 0.0
    valid = 0
    for dim, gt_level in gt_dict.items():
        pred_level = pred_dict.get(dim)
        if pred_level is None:
            continue
        gt_rank = ordinal_map.get(gt_level)
        pred_rank = ordinal_map.get(pred_level)
        if gt_rank is None or pred_rank is None:
            continue
        similarity = 1 - (abs(pred_rank - gt_rank) / d_max)
        dimension_scores[dim] = round(similarity, 4)
        total += similarity
        valid += 1

    mean = total / valid if valid else 0.0
    return {"ordinal_similarity": round(mean, 4), "dimension_scores": dimension_scores}


def compute_scale_score(pred, gt, definition: ScaleDef) -> dict | None:
    """Compute a metric for one scale, or None when data is not comparable."""
    if pred is None or gt is None:
        return None
    if definition.is_list:
        if not isinstance(pred, list) or not isinstance(gt, list):
            return None
        return compute_list_score(pred, gt)
    if definition.is_kv:
        if not isinstance(pred, dict) or not isinstance(gt, dict):
            return None
        return compute_kv_score(pred, gt, definition)
    return None


def evaluate_prediction(
    prediction: dict,
    ground_truth: dict,
    registry: Registry,
    detailed: bool = True,
) -> dict:
    """Score one character's prediction against its ground truth.

    Returns {id, <scale>: primary_score..., total_score, details}.
    total_score is the mean over scales in the manifest's evaluation_scope that
    were scored; it is included only when every scope scale was scored.
    """
    char_id = prediction.get("id", ground_truth.get("id", "unknown"))
    result: dict = {"id": char_id}
    details: dict[str, dict] = {}
    scale_scores: dict[str, float] = {}

    for scale_name in registry.all_names():
        definition = registry.scale(scale_name)
        pred_data = prediction.get(scale_name)
        gt_data = ground_truth.get(scale_name)
        score_result = compute_scale_score(pred_data, gt_data, definition)
        if score_result is None:
            continue
        primary = score_result.get("f1_score", score_result.get("ordinal_similarity", 0.0))
        scale_scores[scale_name] = round(primary, 4)
        details[scale_name] = score_result

    scope = registry.evaluation_scope
    scored_scope = [s for s in scope if s in scale_scores]
    if scored_scope == scope:
        result["total_score"] = round(sum(scale_scores[s] for s in scope) / len(scope), 4)
    result.update(scale_scores)
    if detailed:
        result["details"] = details
    return result
