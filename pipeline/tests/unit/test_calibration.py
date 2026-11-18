"""Grader calibration (T095, R16): agreement, which result is current, and labelling."""

import asyncio
from pathlib import Path
from typing import Any

from thinkbible_pipeline.drafts.models import DroppedItem, Evidence, SectionDraft
from thinkbible_pipeline.gate.calibration import (
    CalibrationItem,
    CalibrationResult,
    CalibrationSet,
    agreement,
    label_items,
    load_calibration,
    run_calibration,
    save_calibration,
)


def result(version: str, model: str, run_at: str, share: float = 0.9) -> CalibrationResult:
    return CalibrationResult(grader_prompt_version=version, grader_model=model, agreement=share,
                             items=30, run_at=run_at)  # fmt: skip


def test_agreement_is_the_share_of_pass_fail_matches() -> None:
    owner = {"a": True, "b": False, "c": True, "d": False}
    grader = {"a": True, "b": True, "c": True, "d": False, "e": False}  # e wasn't labelled
    assert agreement(owner, grader) == (0.75, ["b"])
    assert agreement({}, grader) == (0.0, [])


def test_only_a_result_for_the_current_grader_prompt_and_model_counts() -> None:
    cal = CalibrationSet(results=[
        result("review@v1", "opus-4-6", "2026-11-17T10:00", 0.80),
        result("review@v1", "opus-4-6", "2026-11-18T10:00", 0.90),
        result("review@v2", "opus-4-6", "2026-11-19T10:00", 0.95),
    ])  # fmt: skip
    latest = cal.result_for("review@v1", "opus-4-6")
    assert latest is not None and latest.agreement == 0.90  # the latest for that version
    assert cal.result_for("review@v1", "opus-5-5") is None  # a new model needs a new run
    assert cal.result_for("review@v3", "opus-4-6") is None
    # The same model on another endpoint keeps its calibration.
    api = CalibrationSet(results=[result("review@v9", "claude-opus-5-5", "2026-11-18T10:00")])
    assert api.result_for("review@v9", "us.anthropic.claude-opus-5-5") is not None


def draft() -> SectionDraft:
    return SectionDraft(
        section={
            "keyIdeas": [{"id": "mrk-1-1-k1", "title": "John prepares the way", "body": "Why.",
                          "sources": ["matthew-henry"], "verseStart": 1, "verseEnd": 8}],
            "questions": [{"id": "mrk-1-1-q1", "text": "Why might John come first?",
                           "targets": ["mrk-1-1-k1"], "verseStart": 2, "verseEnd": 3}],
        },
        evidence={"mrk-1-1-k1": [Evidence(commentator="matthew-henry", quote="he prepared")]},
        dropped=[DroppedItem(item_id="mrk-1-1-q2", stage="review", reason="graded 2",
                             item={"text": "What does verse 6 say?",
                                   "targets": ["mrk-1-1-k1"]})],
    )  # fmt: skip


def test_labelling_records_grades_and_keeps_a_copy(tmp_path: Path) -> None:
    path = tmp_path / "calibration.json"
    cal = CalibrationSet()
    drafts = {"mrk-1-1": draft()}
    answers = iter(["p", "f", "Reads like a quiz.", "s"])
    shown: list[str] = []
    n = label_items(cal, drafts, {"mrk-1-1": "1 The beginning…"}, target=30,
                    save=lambda c: save_calibration(path, c), echo=shown.append,
                    ask=lambda _prompt: next(answers))  # fmt: skip
    assert n == 2 and len(cal.items) == 2
    # Ideas and questions alternate: the idea first (pass), then a question (fail, with a note).
    assert [(c.kind, c.owner_grade, c.note) for c in cal.items] == [
        ("keyIdea", "pass", None), ("question", "fail", "Reads like a quiz.")
    ]  # fmt: skip
    assert "1 The beginning…" in shown  # the passage is shown with each item
    # A question keeps the ideas it aims at, so it still grades after the section is regenerated.
    question = next(c for c in cal.items if c.kind == "question")
    assert [i["title"] for i in question.target_ideas] == ["John prepares the way"]
    # The copy is what was labelled, whatever happens to the draft later.
    drafts["mrk-1-1"].section["keyIdeas"][0]["title"] = "Changed by a regeneration"
    saved = load_calibration(path)
    assert [c.item.get("title") for c in saved.items if c.kind == "keyIdea"] == [
        "John prepares the way"
    ]
    # Labelled items aren't offered again.
    again = label_items(saved, drafts, {}, target=30, save=lambda c: None, echo=lambda _l: None,
                        ask=lambda _p: "q")  # fmt: skip
    assert again == 0


def test_labelling_stops_at_the_target() -> None:
    cal = CalibrationSet(items=[
        CalibrationItem(item_id=f"x-{n}", kind="question", section_id="mrk-1-1",
                        item={"id": f"x-{n}"}, owner_grade="pass") for n in range(30)
    ])  # fmt: skip
    asked: list[str] = []
    n = label_items(cal, {"mrk-1-1": draft()}, {}, target=30, save=lambda c: None,
                    echo=lambda _l: None, ask=lambda p: asked.append(p) or "p")  # fmt: skip
    assert n == 0 and asked == []


def test_only_held_out_items_are_measured() -> None:
    cal = CalibrationSet(items=[
        CalibrationItem(item_id="mrk-1-1-q1", kind="question", section_id="mrk-1-1",
                        item={"id": "mrk-1-1-q1"}, owner_grade="pass", role="example"),
        CalibrationItem(item_id="mrk-1-1-q2", kind="question", section_id="mrk-1-1",
                        item={"id": "mrk-1-1-q2"}, owner_grade="fail"),
    ])  # fmt: skip
    seen: list[str] = []

    async def grade(sid: str, items: list[dict[str, Any]]) -> dict[str, int]:
        seen.extend(i["id"] for i in items)
        return {i["id"]: 2 for i in items}

    res = asyncio.run(run_calibration(cal, grade, threshold=2, prompt_version="review@v7",
                                      model="opus", now="2026-11-18T12:00"))  # fmt: skip
    assert seen == ["mrk-1-1-q2"]  # the example is in the grader's prompt, so it isn't measured
    assert res.items == 1 and res.agreement == 1.0 and res.scores == {"mrk-1-1-q2": 2}


def test_a_calibration_run_grades_by_section_and_records_agreement() -> None:
    cal = CalibrationSet(items=[
        CalibrationItem(item_id="mrk-1-1-k1", kind="keyIdea", section_id="mrk-1-1",
                        item={"id": "mrk-1-1-k1"}, owner_grade="pass"),
        CalibrationItem(item_id="mrk-1-1-q2", kind="question", section_id="mrk-1-1",
                        item={"id": "mrk-1-1-q2"}, owner_grade="fail"),
        CalibrationItem(item_id="mrk-1-9-q1", kind="question", section_id="mrk-1-9",
                        item={"id": "mrk-1-9-q1"}, owner_grade="pass"),
    ])  # fmt: skip
    calls: list[tuple[str, int]] = []

    async def grade(sid: str, items: list[dict[str, Any]]) -> dict[str, int]:
        calls.append((sid, len(items)))
        return {"mrk-1-1-k1": 5, "mrk-1-1-q2": 4, "mrk-1-9-q1": 3}

    res = asyncio.run(run_calibration(cal, grade, threshold=2, prompt_version="review@v1",
                                      model="opus", now="2026-11-17T12:00"))  # fmt: skip
    assert calls == [("mrk-1-1", 2), ("mrk-1-9", 1)]  # one grader call per section
    assert res.agreement == round(2 / 3, 4) and res.disagreements == ["mrk-1-1-q2"]
    assert cal.results == [res] and res.items == 3
