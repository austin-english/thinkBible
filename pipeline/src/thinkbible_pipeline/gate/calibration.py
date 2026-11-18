"""Grader calibration (R16, FR-020, constitution v1.2.0): does the grader agree with the owner?

``pipeline/evals/calibration.json`` (committed) holds items from the drafts with the owner's
pass/fail grade, each a copy of the item as it was labelled so a later regeneration doesn't change
what was graded, and one result per grader run: the grader prompt version and model, and the
share of items where the grader's pass/fail (above ``review_flag_threshold``) matches the owner's.

A book may be promoted only when the latest result for the *current* grader prompt and model has
at least ``gate.min_agreement`` on at least ``gate.min_calibration_items`` items.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from thinkbible_pipeline.drafts.models import SectionDraft
from thinkbible_pipeline.jsonio import JsonModel, read_json, write_json


class CalibrationItem(JsonModel):
    item_id: str
    kind: Literal["keyIdea", "question"]
    section_id: str
    item: dict[str, Any]  # the item as labelled
    owner_grade: Literal["pass", "fail"]
    note: str | None = None
    # For a question: the key ideas it aims at, as they were when labelled. The grader sees them,
    # so the item can still be graded after its section is regenerated with new ideas.
    target_ideas: list[dict[str, Any]] = Field(default_factory=list)


def target_ideas(item: dict[str, Any], draft: SectionDraft) -> list[dict[str, Any]]:
    """The key ideas a question aims at, from the draft's kept and dropped ideas."""
    ideas = {i["id"]: i for i in draft.section.get("keyIdeas", [])}
    ideas.update(
        {d.item_id: {"id": d.item_id, **d.item} for d in draft.dropped if "-k" in d.item_id}
    )
    return [ideas[t] for t in item.get("targets", []) if t in ideas]


class CalibrationResult(JsonModel):
    grader_prompt_version: str
    grader_model: str
    agreement: float
    items: int
    run_at: str
    disagreements: list[str] = Field(default_factory=list)  # item IDs where the grader differed


class CalibrationSet(JsonModel):
    items: list[CalibrationItem] = Field(default_factory=list)
    results: list[CalibrationResult] = Field(default_factory=list)

    def result_for(self, prompt_version: str, model: str) -> CalibrationResult | None:
        """The latest result for this grader prompt version and model, if any."""
        matching = [
            r for r in self.results
            if r.grader_prompt_version == prompt_version and r.grader_model == model
        ]  # fmt: skip
        return max(matching, key=lambda r: r.run_at) if matching else None


def load_calibration(path: Path) -> CalibrationSet:
    return CalibrationSet.model_validate(read_json(path)) if path.is_file() else CalibrationSet()


def save_calibration(path: Path, calibration: CalibrationSet) -> None:
    write_json(path, calibration.to_doc())


def agreement(owner: dict[str, bool], grader: dict[str, bool]) -> tuple[float, list[str]]:
    """Share of items both graded where pass/fail matches, and the IDs where it doesn't."""
    both = [i for i in owner if i in grader]
    if not both:
        return 0.0, []
    differ = [i for i in both if owner[i] != grader[i]]
    return round(1 - len(differ) / len(both), 4), differ


def candidates(
    drafts: dict[str, SectionDraft], labelled: set[str], seed: int = 7
) -> list[tuple[str, Literal["keyIdea", "question"], dict[str, Any]]]:
    """Items to label, mixing kept and dropped ones so the set has both good and weak items.

    Returns (section id, kind, item), alternating key ideas and questions, in a stable order.
    """
    pool: dict[str, list[tuple[str, Literal["keyIdea", "question"], dict[str, Any]]]] = {
        "keyIdea": [],
        "question": [],
    }
    for sid, draft in sorted(drafts.items()):
        for idea in draft.section.get("keyIdeas", []):
            pool["keyIdea"].append((sid, "keyIdea", idea))
        for q in draft.section.get("questions", []):
            pool["question"].append((sid, "question", q))
        for d in draft.dropped:
            if d.stage in ("check", "review") and d.item.get(
                "text" if "-q" in d.item_id else "title"
            ):
                kind: Literal["keyIdea", "question"] = (
                    "question" if "-q" in d.item_id else "keyIdea"
                )
                pool[kind].append((sid, kind, {"id": d.item_id, **d.item}))
    rng = random.Random(seed)
    for items in pool.values():
        rng.shuffle(items)
    out = []
    for pair in zip(pool["keyIdea"], pool["question"], strict=False):
        out += list(pair)
    longer = pool["keyIdea"] if len(pool["keyIdea"]) > len(pool["question"]) else pool["question"]
    out += longer[min(len(pool["keyIdea"]), len(pool["question"])) :]
    return [c for c in out if c[2]["id"] not in labelled]


# --- the two commands: label (owner) and run (grader) ---


def _show(
    sid: str, kind: str, item: dict[str, Any], draft: SectionDraft, passage: str
) -> list[str]:
    from thinkbible_pipeline.report.render import NAMES, readable

    ch = int(sid.split("-")[1])
    lines = [f"\n=== {sid} · {kind} {item['id']}", passage, ""]
    if kind == "keyIdea":
        lines += [f"Key idea: {readable(item['title'], ch)}", f"  {readable(item['body'], ch)}"]
        lines.append("  Sources: " + ", ".join(NAMES.get(s, s) for s in item.get("sources", [])))
        for e in draft.evidence.get(item["id"], []):
            lines.append(f"  Evidence ({NAMES.get(e.commentator, e.commentator)}): “{e.quote}”")
    else:
        titles = {i["id"]: i["title"] for i in draft.section.get("keyIdeas", [])}
        lines.append(f"Question: {readable(item['text'], ch)}")
        lines.append("  Aims at: " + "; ".join(titles.get(t, t) for t in item.get("targets", [])))
    return lines


def label_items(
    calibration: CalibrationSet,
    drafts: dict[str, SectionDraft],
    passages: dict[str, str],
    *,
    target: int,
    save: Callable[[CalibrationSet], None],
    echo: Callable[[str], None],
    ask: Callable[[str], str],
) -> int:
    """Show unlabelled items one at a time and record the owner's pass/fail until ``target``.

    ``passages`` maps section ID to its BSB text. Saves after every grade. Returns how many were
    labelled in this session.
    """
    done = 0
    labelled = {i.item_id for i in calibration.items}
    for sid, kind, item in candidates(drafts, labelled):
        if len(calibration.items) >= target:
            break
        for line in _show(sid, kind, item, drafts[sid], passages.get(sid, "")):
            echo(line)
        answer = (
            ask(
                f"[{len(calibration.items)}/{target}] Should this ship? [p]ass / [f]ail / [s]kip / "
                "[q]uit: "
            )
            .strip()
            .lower()
        )
        if answer.startswith("q"):
            break
        if not answer.startswith(("p", "f")):
            continue
        note = ask("Why? (optional): ").strip() or None if answer.startswith("f") else None
        calibration.items.append(
            CalibrationItem(
                item_id=item["id"],
                kind=kind,
                section_id=sid,
                item=dict(item),
                owner_grade="pass" if answer.startswith("p") else "fail",
                note=note,
                target_ideas=target_ideas(item, drafts[sid]) if kind == "question" else [],
            )
        )
        save(calibration)
        done += 1
    return done


GradeFn = Callable[[str, list[dict[str, Any]]], Awaitable[dict[str, int]]]


async def run_calibration(
    calibration: CalibrationSet,
    grade: GradeFn,
    *,
    threshold: int,
    prompt_version: str,
    model: str,
    now: str,
) -> CalibrationResult:
    """Grade every labelled item with the grader (one call per section) and record agreement.

    ``grade(section_id, items)`` returns {item id: score 1-5}; an item passes above ``threshold``.
    """
    by_section: dict[str, list[dict[str, Any]]] = {}
    for c in calibration.items:
        by_section.setdefault(c.section_id, []).append(c.item)
    scores: dict[str, int] = {}
    for sid, items in sorted(by_section.items()):
        scores.update(await grade(sid, items))
    owner = {c.item_id: c.owner_grade == "pass" for c in calibration.items}
    grader = {i: s > threshold for i, s in scores.items()}
    share, differ = agreement(owner, grader)
    result = CalibrationResult(
        grader_prompt_version=prompt_version,
        grader_model=model,
        agreement=share,
        items=len([i for i in owner if i in grader]),
        run_at=now,
        disagreements=differ,
    )
    calibration.results.append(result)
    return result
