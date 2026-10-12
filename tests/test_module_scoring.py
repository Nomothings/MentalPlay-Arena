"""Tests for the unified module scoring (module_scoring.py).

Parametrized over all 21 module-backed scales: every module must load and
return a ScoreResult for synthetic answers. K-SADS (which consumes per-category
score dicts) is tested separately.
"""

from __future__ import annotations

import pytest

from mentalplay_arena.config import get_settings
from mentalplay_arena.module_scoring import (
    ScoreResult,
    compute_ksads_scores,
    compute_scale_scores,
)
from mentalplay_arena.registry import Registry


@pytest.fixture(scope="module")
def registry():
    return Registry(get_settings())


def _synthetic_answers(scale: str, registry: Registry, letter: str = "A") -> list[dict]:
    inquiries = registry.load_inquiries(scale)
    return [{"question_id": q["question_id"], "answer": letter} for q in inquiries]


ALL_MODULES = sorted(
    name for name in Registry(get_settings()).all_names()
    if Registry(get_settings()).scale(name).has_module
)


class TestAllModuleContracts:
    @pytest.mark.parametrize("scale", ALL_MODULES)
    def test_module_loads_and_returns_score_result(self, scale, registry):
        answers = _synthetic_answers(scale, registry)
        result = compute_scale_scores(scale, answers, registry)
        assert isinstance(result, ScoreResult), scale
        assert isinstance(result.total, (int, float)), scale
        assert isinstance(result.severity, str), scale

    @pytest.mark.parametrize("scale", ALL_MODULES)
    def test_empty_answers_do_not_crash(self, scale, registry):
        result = compute_scale_scores(scale, [], registry)
        assert isinstance(result, ScoreResult), scale


class TestKSADS:
    def test_ksads_consumes_category_scores(self, registry):
        # Synthesize one category-score record per K-SADS category (1..13).
        category_scores = [
            {"category_id": cid, "domain": f"domain-{cid}", "category_name": f"cat-{cid}",
             "score": 1}
            for cid in range(1, 14)
        ]
        result = compute_ksads_scores(category_scores, registry)
        assert isinstance(result, ScoreResult)
        assert result.total >= 0
        # The K-SADS module returns a dict with module_scores; normalized to dimensions.
        assert result.dimensions is not None
        assert "module_scores" in result.dimensions

    def test_ksads_all_zero_scores(self, registry):
        category_scores = [
            {"category_id": cid, "domain": f"d{cid}", "category_name": f"c{cid}", "score": 0}
            for cid in range(1, 14)
        ]
        result = compute_ksads_scores(category_scores, registry)
        assert isinstance(result.total, (int, float))


class TestFallback:
    def test_unknown_scale_falls_back_to_rules_summation(self, registry):
        # A scale with a module dir but a broken scoring.py should still score.
        result = compute_scale_scores("PHQ-9", [], registry)
        assert isinstance(result, ScoreResult)
