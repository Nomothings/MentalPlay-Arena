"""Golden tests for the evaluation metrics (evaluation.py)."""

from __future__ import annotations

import pytest

from mentalplay_arena.config import get_settings
from mentalplay_arena.evaluation import (
    compute_kv_score,
    compute_list_score,
    evaluate_prediction,
    ordinal_map_for,
)
from mentalplay_arena.registry import Registry


@pytest.fixture(scope="module")
def registry():
    return Registry(get_settings())


class TestListScore:
    def test_perfect_match(self):
        s = compute_list_score(["A", "B"], ["A", "B"])
        assert s == {"f1_score": 1.0, "precision": 1.0, "recall": 1.0, "jaccard": 1.0}

    def test_partial_overlap(self):
        s = compute_list_score(["A", "B", "C"], ["A", "B", "D"])
        # tp=2, pred=3, gt=3, union=4
        assert s["precision"] == pytest.approx(2 / 3, abs=1e-3)
        assert s["recall"] == pytest.approx(2 / 3, abs=1e-3)
        assert s["f1_score"] == pytest.approx(0.6667, abs=1e-3)
        assert s["jaccard"] == pytest.approx(0.5, abs=1e-3)

    def test_no_overlap(self):
        s = compute_list_score(["A"], ["B"])
        assert s["f1_score"] == 0.0
        assert s["jaccard"] == 0.0

    def test_empty_pred_and_gt_is_perfect(self):
        s = compute_list_score([], [])
        assert s["f1_score"] == 1.0

    def test_empty_pred_only(self):
        s = compute_list_score([], ["A"])
        assert s["f1_score"] == 0.0


class TestKvScore:
    def test_iip32_ordinal(self, registry):
        definition = registry.scale("IIP-32")
        assert ordinal_map_for(definition) == {"weak": 0, "moderate": 1, "strong": 2}
        pred = {"Cold": "weak", "Domineering": "strong"}
        gt = {"Cold": "weak", "Domineering": "moderate", "Vindictive": "moderate"}
        s = compute_kv_score(pred, gt, definition)
        # Cold: 0 diff -> 1.0 ; Domineering: |2-1|/2=0.5 -> 0.5 ; Vindictive absent in pred -> skip
        assert s["ordinal_similarity"] == pytest.approx(0.75)
        assert s["dimension_scores"]["Cold"] == 1.0

    def test_dass42_ordinal(self, registry):
        definition = registry.scale("DASS-42")
        pred = {"Depression": "moderate", "Anxiety": "severe"}
        gt = {"Depression": "severe", "Anxiety": "severe", "Stress": "normal"}
        s = compute_kv_score(pred, gt, definition)
        # Depression: |2-3|/4=0.25 -> 0.75 ; Anxiety: 1.0 ; Stress skipped
        assert s["ordinal_similarity"] == pytest.approx(0.875)

    def test_empty_gt(self, registry):
        s = compute_kv_score({"A": "weak"}, {}, registry.scale("IIP-32"))
        assert s["ordinal_similarity"] == 0.0


class TestEvaluatePrediction:
    def test_single_scale(self, registry):
        prediction = {"id": "c1", "K-SADS": ["Schizophrenia", "Tic disorders"]}
        gt = {"id": "c1", "K-SADS": ["Schizophrenia", "Bipolar type I disorder"]}
        result = evaluate_prediction(prediction, gt, registry)
        assert result["K-SADS"] == pytest.approx(0.5)
        assert "total_score" not in result  # not all scope scales scored

    def test_total_score_when_all_scope_present(self, registry):
        # Build a prediction that covers every evaluation_scope scale.
        prediction = {"id": "c1"}
        gt = {"id": "c1"}
        for scale in registry.evaluation_scope:
            definition = registry.scale(scale)
            if definition.is_list:
                prediction[scale] = ["X"]
                gt[scale] = ["X"]
            else:
                dims = {k: list(v)[0] for k, v in list(definition.dimensions.items())[:1]}
                prediction[scale] = dims
                gt[scale] = dict(dims)
        result = evaluate_prediction(prediction, gt, registry)
        assert result["total_score"] == pytest.approx(1.0)
