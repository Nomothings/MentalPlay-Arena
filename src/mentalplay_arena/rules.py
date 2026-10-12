"""Safe evaluation of scale rule expressions.

Replaces the original logic_parser (which compiled rule strings through
Python's eval()). This module parses the expression with the standard `ast`
module and walks the tree manually, permitting only comparisons, boolean
operators and simple constants — so arbitrary code can never execute.

Rule expression grammar (as authored in rules.json):
  "1_1 == A"
  "1_1==B and 1_2<=C"
  "2_1 != A or (2_2 >= 3)"
where question ids match `\\d+[_-]\\d+`, letters are single A-Z characters
compared as strings, and numbers are compared numerically.
"""

from __future__ import annotations

import ast
import re

QUESTION_ID_TOKEN_RE = re.compile(r"\b\d+[_-]\d+\b")
SINGLE_LETTER_RE = re.compile(r"^[A-Z]$")
MISSING_SENTINEL = "Z"  # "unanswered" value, same as the original


class UnsafeExpressionError(ValueError):
    """Raised when a rule expression uses unsupported or dangerous syntax."""


def _coerce(value: str) -> str | int:
    """Convert a stored answer value to a comparable Python value.

    - a single letter A-Z is kept as a string ('A', 'B', ...)
    - 'Z' (missing sentinel) is kept as the string 'Z'
    - anything parseable as an integer becomes an int (K-SADS numeric answers)
    - otherwise the raw string is used.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if re.match(r"^-?\d+$", s):
            return int(s)
        return s.upper() if len(s) == 1 else s
    return str(value)


class RuleEvaluator:
    """Evaluate a rule expression against a set of stored answers."""

    def __init__(self, answers: dict[str, str]):
        # normalize keys: answer dict may use 'N_M' question ids
        self.answers = {k: _coerce(v) for k, v in answers.items()}
        self._qid_map: dict[str, str] = {}  # placeholder name -> question id

    def _preprocess(self, expression: str) -> str:
        """Rewrite question ids ('1_1', '2-3') into safe Python identifiers.

        Python's lexer treats '1_1' as the number literal 11, so question ids
        must be converted to Name nodes before ast.parse sees them.
        """
        def repl(match: re.Match) -> str:
            qid = match.group(0)
            if qid not in self._qid_map.values():
                placeholder = f"__qid{len(self._qid_map)}__"
                self._qid_map[placeholder] = qid
            for placeholder, mapped in self._qid_map.items():
                if mapped == qid:
                    return placeholder
            raise AssertionError("unreachable")

        return QUESTION_ID_TOKEN_RE.sub(repl, expression)

    def evaluate(self, expression: str) -> bool:
        self._qid_map.clear()
        prepared = self._preprocess(expression)
        try:
            tree = ast.parse(prepared, mode="eval")
        except SyntaxError:
            return False
        try:
            return bool(self._eval(tree.body))
        except UnsafeExpressionError:
            return False

    # ------------------------------------------------------------------ nodes

    def _eval(self, node: ast.AST):
        if isinstance(node, ast.BoolOp):
            values = [self._eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise UnsafeExpressionError("unsupported bool op")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self._eval(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # K-SADS counting expressions: is_true(...) + is_true(...) == N
            return int(self._eval(node.left)) + int(self._eval(node.right))
        if isinstance(node, ast.Call):
            # The original grammar permits is_true(expr) -> int(bool(expr)).
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "is_true"
                and len(node.args) == 1
                and not node.keywords
            ):
                return int(bool(self._eval(node.args[0])))
            raise UnsafeExpressionError("only is_true() calls are allowed")
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator)
                if not self._compare(left, right, op):
                    return False
                left = right
            return True
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (str, int, float, bool)) and node.value is not None:
                return node.value
            raise UnsafeExpressionError("unsupported constant")
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        if isinstance(node, ast.Expression):
            return self._eval(node.body)
        raise UnsafeExpressionError(f"unsupported syntax: {type(node).__name__}")

    def _resolve_name(self, name: str) -> str | int:
        if name in self._qid_map:
            qid = self._qid_map[name]
            return self.answers.get(qid, MISSING_SENTINEL)
        if SINGLE_LETTER_RE.match(name):
            return name
        raise UnsafeExpressionError(f"unexpected identifier: {name!r}")

    @staticmethod
    def _compare(left, right, op) -> bool:
        """Compare two values, handling letter/number mixed comparisons safely.

        Strings compare as strings; ints compare numerically. When types mix
        (e.g. a stored int compared against a string), Python semantics apply
        and any TypeError degrades to False rather than crashing the run.
        """
        try:
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.LtE):
                return left <= right
            if isinstance(op, ast.Gt):
                return left > right
            if isinstance(op, ast.GtE):
                return left >= right
        except TypeError:
            return False
        raise UnsafeExpressionError(f"unsupported comparison: {type(op).__name__}")


def evaluate_expression(expression: str, answers: dict[str, str]) -> bool:
    """Module-level convenience wrapper."""
    return RuleEvaluator(answers).evaluate(expression)
