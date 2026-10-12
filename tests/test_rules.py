"""Tests for the safe rule-expression evaluator (rules.py)."""

from __future__ import annotations

import pytest

from mentalplay_arena.rules import RuleEvaluator, evaluate_expression


class TestRuleEvaluator:
    def test_simple_equality(self):
        assert evaluate_expression("1_1 == A", {"1_1": "A"}) is True
        assert evaluate_expression("1_1 == A", {"1_1": "B"}) is False

    def test_compact_spaced_and(self):
        # GAD-7 style spaced form
        assert evaluate_expression("1_1 == A and 1_2 == B", {"1_1": "A", "1_2": "B"}) is True
        assert evaluate_expression("1_1 == A and 1_2 == B", {"1_1": "A", "1_2": "A"}) is False

    def test_ksads_compact_operators(self):
        # K-SADS style: no spaces, comparison operators
        assert evaluate_expression("1_1==B and 1_2<=C", {"1_1": "B", "1_2": "C"}) is True
        assert evaluate_expression("1_1==B and 1_2<=C", {"1_1": "B", "1_2": "D"}) is False
        assert evaluate_expression("1_3>A", {"1_3": "B"}) is True
        assert evaluate_expression("1_3>A", {"1_3": "A"}) is False

    def test_numeric_comparison(self):
        assert evaluate_expression("2_1 >= 3", {"2_1": "3"}) is True
        assert evaluate_expression("2_1 >= 3", {"2_1": "2"}) is False

    def test_or_operator(self):
        assert evaluate_expression("1_1 == A or 1_1 == B", {"1_1": "B"}) is True

    def test_not_operator(self):
        assert evaluate_expression("not 1_1 == A", {"1_1": "B"}) is True

    def test_parenthesized_expression(self):
        assert evaluate_expression("(1_1 == A or 1_1 == B) and 1_2 == C",
                                   {"1_1": "B", "1_2": "C"}) is True
        assert evaluate_expression("(1_1 == A or 1_1 == B) and 1_2 == C",
                                   {"1_1": "B", "1_2": "A"}) is False

    def test_missing_answer_uses_sentinel(self):
        # 'Z' is the unanswered sentinel; "1_1 == Z" should be True when absent
        assert evaluate_expression("1_1 == Z", {}) is True
        assert evaluate_expression("1_1 == A", {}) is False

    def test_mixed_letter_number_compare_degrades_false(self):
        # stored numeric answer vs a letter constant -> TypeError -> False
        assert evaluate_expression("1_1 <= A", {"1_1": "3"}) is False

    def test_underscore_question_id(self):
        assert evaluate_expression("3_1 == C", {"3_1": "C"}) is True


class TestRuleSecurity:
    def test_import_attempt_rejected(self):
        assert evaluate_expression("__import__('os')", {}) is False

    def test_attribute_access_rejected(self):
        assert evaluate_expression("1_1 == A or 1_1.__class__", {"1_1": "A"}) is False

    def test_arbitrary_identifiers_rejected(self):
        # Unknown identifiers are rejected and degrade to False (never executed).
        assert evaluate_expression("x == A", {}) is False

    def test_bad_syntax_returns_false(self):
        assert evaluate_expression("1_1 == ", {"1_1": "A"}) is False
