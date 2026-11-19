"""Comparing eval arms (T083, FR-029): the gate's measures of what readers get, and a side-by-side
page of every sample section's questions under each arm.

The measures, per arm (a candidate run more than once is averaged):
- **first questions graded 4-5** and **full sets** of questions: the promotion gate's measures;
- **big-picture first questions**: how often a section leads with a question the grader marked
  big-picture;
- **mean grade of kept questions** and the **key idea pass rate**;
- the share of all candidate questions passing, and the rubric lines broken (information).

A candidate is adopted only if it does at least as well as the current arm on each of the first
five (FR-029). On a small sample one question moves a rate by several points, so the control
candidate (no changes) shows how far two runs of the same prompts differ.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from thinkbible_core.rules import max_questions
from thinkbible_pipeline.drafts.models import SectionDraft
from thinkbible_pipeline.evals.run import Arm
from thinkbible_pipeline.report.render import TEMPLATES

_BREAKS = re.compile(r"\(breaks: ([^)]*)\)")
STRONG = 4
# The measures a candidate must match or beat (FR-029), with their labels.
DECIDING = {
    "strong_first": "First questions graded 4-5",
    "full_sets": "Sections with a full set of questions",
    "big_first": "Big-picture first questions",
    "mean_kept": "Mean grade of kept questions",
    "idea_pass": "Key ideas passing",
}


@dataclass
class Measures:
    sections: int = 0
    strong_first: float = 0.0
    full_sets: float = 0.0
    big_first: float = 0.0
    mean_kept: float = 0.0
    idea_pass: float = 0.0
    candidate_pass: float = 0.0
    failed: int = 0
    cost_usd: float = 0.0
    broken: Counter[str] = field(default_factory=Counter)


def _active(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in items if i.get("status", "active") == "active"]


def measure(arm: Arm, threshold: int) -> Measures:
    m = Measures(failed=len(arm.failures), cost_usd=arm.cost_usd)
    firsts = full = big = 0
    kept_grades: list[int] = []
    ideas = ideas_ok = cands = cands_ok = 0
    for draft in arm.drafts.values():
        if draft.failed or draft.section.get("noPrompt"):
            continue
        m.sections += 1
        questions = _active(draft.section.get("questions", []))
        keys = [i for i in _active(draft.section.get("keyIdeas", [])) if i.get("kind") == "key"]
        grade = draft.grades.get
        if questions:
            first = grade(str(questions[0]["id"]))
            firsts += bool(first and first.score >= STRONG)
            big += bool(first and first.focus == "big-picture")
            if len(questions) >= max_questions(len(keys)):
                full += 1
        kept_grades += [g.score for q in questions if (g := grade(str(q["id"])))]
        for item_id, g in draft.grades.items():
            kind = item_id.rsplit("-", 1)[-1][:1]
            if kind == "k":
                ideas += 1
                ideas_ok += g.score > threshold
            elif kind == "q":
                cands += 1
                cands_ok += g.score > threshold
            m.broken.update(r.strip() for b in _BREAKS.findall(g.notes or "") for r in b.split(","))
    if m.sections:
        m.strong_first, m.full_sets, m.big_first = (
            firsts / m.sections, full / m.sections, big / m.sections
        )  # fmt: skip
    m.mean_kept = mean(kept_grades) if kept_grades else 0.0
    m.idea_pass = ideas_ok / ideas if ideas else 0.0
    m.candidate_pass = cands_ok / cands if cands else 0.0
    return m


def averaged(runs: list[Measures]) -> Measures:
    out = Measures(sections=round(mean(r.sections for r in runs)))
    for name in ("strong_first", "full_sets", "big_first", "mean_kept", "idea_pass",
                 "candidate_pass"):  # fmt: skip
        setattr(out, name, mean(getattr(r, name) for r in runs))
    out.failed = sum(r.failed for r in runs)
    out.cost_usd = sum(r.cost_usd for r in runs)
    for r in runs:
        out.broken.update(r.broken)
    return out


@dataclass
class Verdict:
    rows: list[tuple[str, float, float, bool]]  # label, current, candidate, at least as well

    @property
    def adopt(self) -> bool:
        return all(ok for *_, ok in self.rows)


def compare(current: Measures, candidate: Measures) -> Verdict:
    rows = [
        (label, getattr(current, key), getattr(candidate, key),
         getattr(candidate, key) >= getattr(current, key) - 1e-9)
        for key, label in DECIDING.items()
    ]  # fmt: skip
    return Verdict(rows)


def _section_view(draft: SectionDraft | None) -> dict[str, Any]:
    if draft is None:
        return {"missing": True}
    ideas = {i["id"]: i["title"] for i in draft.section.get("keyIdeas", [])}
    questions = []
    for q in _active(draft.section.get("questions", [])):
        g = draft.grades.get(q["id"])
        questions.append({
            "text": q["text"], "grade": g.score if g else None,
            "focus": g.focus if g else None,
            "central": draft.central_idea in q.get("targets", []),
        })  # fmt: skip
    return {"missing": False, "failed": draft.failed,
            "central": ideas.get(draft.central_idea or ""), "questions": questions}  # fmt: skip


def render(
    sample: str, candidate: str, sections: list[str], arms: list[Arm], current: Measures,
    cand_m: Measures, verdict: Verdict,
) -> str:  # fmt: skip
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["j2"]))
    views = [
        {"label": arm.label, "views": {sid: _section_view(arm.drafts.get(sid)) for sid in sections}}
        for arm in arms
    ]
    return env.get_template("eval.html.j2").render(
        sample=sample, candidate=candidate, sections=sections, arms=views, current=current,
        cand_m=cand_m, verdict=verdict,
    )  # fmt: skip
