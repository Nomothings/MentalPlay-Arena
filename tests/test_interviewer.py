"""Tests for the interviewer engine (interviewer.py) using a mock LLM."""

from __future__ import annotations

import pytest

from mentalplay_arena.config import get_settings
from mentalplay_arena.interviewer import Interviewer
from mentalplay_arena.registry import Registry


@pytest.fixture(scope="module")
def registry():
    return Registry(get_settings())


def _run_interview(scale: str, registry: Registry, mock_llm) -> Interviewer:
    interviewer = Interviewer(scale, llm=mock_llm, registry=registry, settings=get_settings())
    question = interviewer.start()
    guard = 0
    while True:
        guard += 1
        assert guard < 500, f"{scale} did not terminate"
        outcome = interviewer.submit_answer(question["question_id"], "some answer")
        if outcome["status"] != "continue":
            return interviewer
        question = outcome["question"]


class TestSequentialScales:
    @pytest.mark.parametrize("scale", ["GAD-7", "PHQ-9", "Y-BOCS"])
    def test_runs_to_finish(self, scale, registry, mock_llm):
        interviewer = _run_interview(scale, registry, mock_llm)
        assert interviewer.finished is True, scale
        assert len(interviewer.turns) >= 2, scale

    def test_turns_recorded_with_mapped_answers(self, registry, mock_llm):
        interviewer = _run_interview("GAD-7", registry, mock_llm)
        assert all(t.mapped_answer in {"A", "B", "C", "D"} for t in interviewer.turns)
        assert all(t.raw_answer for t in interviewer.turns)


class TestKSADS:
    def test_runs_to_finish(self, registry, mock_llm):
        interviewer = _run_interview("K-SADS", registry, mock_llm)
        assert interviewer.finished is True
        assert len(interviewer.turns) > 5
        assert interviewer.get_category_scores()

    def test_category_scores_populated(self, registry, mock_llm):
        interviewer = _run_interview("K-SADS", registry, mock_llm)
        scores = interviewer.get_category_scores()
        # K-SADS has 13 categories; at least some should carry a score.
        assert any(item["score"] > 0 for item in scores)


class TestCSSRS:
    def test_judge_scale_finishes(self, registry, mock_llm):
        interviewer = _run_interview("C-SSRS", registry, mock_llm)
        assert interviewer.finished is True
