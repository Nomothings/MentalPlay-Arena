"""The scale interviewer engine.

Drives a multi-turn clinical interview over one scale's questions, mirroring the
original Quizzer loop:
  - each patient answer is LLM-mapped to an option letter
  - the question's `action` field decides the next step:
      * none/'none'       -> advance to the next question in file order, or finish
      * 'judge'           -> evaluate category rules; first match wins (rules in
                             file order, highest rule_id first per original)
      * explicit qid      -> jump to that question
  - K-SADS special condition: when judging category 13, if any configured
    special category has a matched score of 3, jump to special_jump_question.
  - hard turn guard MAX_TURNS_PER_SCALE prevents infinite loops.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import Settings, get_settings
from .llm import get_llm
from .registry import Registry
from .rules import RuleEvaluator

FINISH = object()  # sentinel: interview ended


@dataclass
class Turn:
    question_id: str
    question_text: str
    answer_space: list[str]
    raw_answer: str
    mapped_answer: str
    action: str | None
    category_id: int | None


class Interviewer:
    def __init__(
        self,
        scale: str,
        llm=None,
        registry: Registry | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.scale = scale
        self.llm = llm if llm is not None else get_llm(self.settings)
        self.registry = registry or Registry(self.settings)
        self.definition = self.registry.scale(scale)

        self.questions: list[dict] = self.registry.load_inquiries(scale)
        self.by_id: dict[str, dict] = {q["question_id"]: q for q in self.questions}
        self.rules: list[dict] = self.registry.load_rules(scale)
        self.rules_by_category: dict[int, list[dict]] = defaultdict(list)
        for rule in self.rules:
            self.rules_by_category[rule.get("category_id")].append(rule)

        config = self.registry.load_config(scale)
        scoring_cfg = config.get("scoring", {}) or {}
        self.special_categories = [int(c) for c in (scoring_cfg.get("special_categories") or [])]
        self.special_jump_question = scoring_cfg.get("special_jump_question")

        self.turns: list[Turn] = []
        self.category_scores: dict[int, float] = {}
        self.conversation: list[dict] = []
        self._visit_counts: dict[str, int] = {}
        self.finished = False
        self.error: str | None = None

    # ------------------------------------------------------------------ start

    def start(self) -> dict:
        """Return the first question dict."""
        first = self.questions[0]
        return self._prepare_question(first)

    def _prepare_question(self, q: dict) -> dict:
        text = self.llm.refine_question(q["question_text"], self.conversation)
        return {
            "question_id": q["question_id"],
            "question_text": text,
            "answer_space": q["answer_space"],
            "category_id": q.get("category_id"),
        }

    # ------------------------------------------------------------------ submit

    def submit_answer(self, question_id: str, raw_answer: str) -> dict:
        """Process an answer; returns a 'continue'/'finished'/'error' dict."""
        if self.finished:
            return {"status": "finished", "message": "Interview already finished"}

        current = self.by_id.get(question_id)
        if not current:
            self.error = f"Unknown question: {question_id}"
            return {"status": "error", "message": self.error}

        mapped = self.llm.map_answer_to_options(raw_answer, current["answer_space"])
        action = (current.get("action") or "").strip() or None

        # Loop guard: a healthy interview never revisits the same question many times.
        self._visit_counts[question_id] = self._visit_counts.get(question_id, 0) + 1
        if self._visit_counts[question_id] > 5:
            self.finished = True
            self.error = f"Loop detected: question {question_id} visited {self._visit_counts[question_id]} times"
            return {"status": "finished", "message": self.error}

        self.turns.append(Turn(
            question_id=question_id,
            question_text=current["question_text"],
            answer_space=list(current["answer_space"]),
            raw_answer=raw_answer,
            mapped_answer=mapped,
            action=action,
            category_id=current.get("category_id"),
        ))
        self.conversation.append({"role": "user", "content": raw_answer})
        empathic = self.llm.generate_empathic_response(raw_answer, self.conversation)
        if empathic:
            self.conversation.append({"role": "assistant", "content": empathic})

        if len(self.turns) >= self.settings.max_turns_per_scale:
            self.finished = True
            self.error = f"Turn limit reached ({self.settings.max_turns_per_scale})"
            return {"status": "finished", "message": self.error}

        if action is None or action.lower() == "none":
            return self._advance(question_id)
        if action.lower() == "judge":
            return self._judge(current, question_id)
        return self._jump(action, question_id)

    # -------------------------------------------------------------- dispatch

    def _advance(self, question_id: str) -> dict:
        nxt = self._next_in_order(question_id)
        if nxt:
            return {"status": "continue", "question": self._prepare_question(nxt)}
        return self._finish()

    def _jump(self, target: str, question_id: str) -> dict:
        nxt = self.by_id.get(target)
        if nxt:
            return {"status": "continue", "question": self._prepare_question(nxt)}
        self.error = f"Action points to unknown question: {target}"
        return {"status": "error", "message": self.error}

    def _judge(self, current: dict, question_id: str) -> dict:
        category_id = current.get("category_id")
        answer_map = {t.question_id: t.mapped_answer for t in self.turns}

        special_condition = False
        if category_id is not None and self.special_categories and int(category_id) == 13:
            special_condition = any(
                self.category_scores.get(c) == 3.0 for c in self.special_categories
            )

        for rule in reversed(self.rules_by_category.get(category_id, [])):  # desc rule_id
            try:
                if not RuleEvaluator(answer_map).evaluate(str(rule.get("rule", ""))):
                    continue
            except Exception:
                continue

            self.category_scores[category_id] = float(rule.get("score", 0) or 0)  # replace

            next_qid = rule.get("action")
            if special_condition and self.special_jump_question:
                next_qid = self.special_jump_question
            if next_qid is None or str(next_qid).strip().lower() in ("", "none"):
                return self._finish()
            return self._jump(str(next_qid), question_id)

        # no rule matched -> continue to next question in order
        return self._advance(question_id)

    def _next_in_order(self, question_id: str) -> dict | None:
        for i, q in enumerate(self.questions):
            if q["question_id"] == question_id:
                if i + 1 < len(self.questions):
                    return self.questions[i + 1]
                return None
        return None

    # --------------------------------------------------------------- results

    def _finish(self) -> dict:
        self.finished = True
        return {"status": "finished", "message": "Interview completed"}

    def get_answers(self) -> list[dict]:
        """Answers in the format expected by the scoring modules."""
        return [{"question_id": t.question_id, "answer": t.mapped_answer} for t in self.turns]

    def get_category_scores(self) -> list[dict]:
        """Per-category score records (consumed by K-SADS scoring)."""
        out = []
        for q in self.questions:
            cid = q.get("category_id")
            if cid is None:
                continue
            if any(item["category_id"] == cid for item in out):
                continue
            out.append({
                "category_id": cid,
                "domain": q.get("domain", ""),
                "category_name": q.get("category", ""),
                "score": int(self.category_scores.get(cid, 0)),
            })
        return out
