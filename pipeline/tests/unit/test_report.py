"""The scorecard and review page (T055) and what ``--stage all`` runs (T056)."""

from datetime import UTC, datetime
from typing import Any

import pytest

from thinkbible_pipeline.drafts.models import (
    DroppedItem,
    RunRecord,
    SectionCounts,
    SectionDraft,
    SectionMapEntry,
    StageRecord,
    TokenCounts,
)
from thinkbible_pipeline.report.render import readable, render_review
from thinkbible_pipeline.report.scorecard import build_scorecard
from thinkbible_pipeline.stages import expand_all

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)


def entry(sid: str, start: int, end: int) -> SectionMapEntry:
    return SectionMapEntry(
        id=sid, chapter=1, verse_start=start, verse_end=end, title=sid, title_source="bsb-heading"
    )


def stage(status: str = "done", cost: float = 0.1) -> StageRecord:
    return StageRecord.model_validate(
        {"promptVersion": "v3", "model": "m", "inputHash": "h", "completedAt": "t",
         "costUsd": cost, "status": status}
    )  # fmt: skip


def idea(sid: str, n: int) -> dict[str, Any]:
    return {
        "id": f"{sid}-k{n}",
        "title": "T",
        "body": "B.",
        "sources": ["matthew-henry"],
        "agreed": False,
        "verseStart": 1,
        "verseEnd": 1,
    }


def question(sid: str, n: int) -> dict[str, Any]:
    return {
        "id": f"{sid}-q{n}",
        "type": "noticing",
        "verseStart": 1,
        "verseEnd": 1,
        "text": "Why might this matter?",
        "targets": [f"{sid}-k0"],
    }


def draft(ideas: int, questions: int, drops: list[str], **kw: Any) -> SectionDraft:
    sid = kw.pop("sid", "mrk-1-1")
    return SectionDraft(
        section={
            "keyIdeas": [idea(sid, n) for n in range(ideas)],
            "questions": [question(sid, n) for n in range(questions)],
            "noPrompt": kw.pop("no_prompt", False),
            "context": "Mark wrote for Roman readers.",
            "viewsDiffer": None,
        },
        dropped=[
            DroppedItem(item_id=d, stage="generate", reason="evidence: not found") for d in drops
        ],
        stages={"generate": stage(kw.pop("status", "done"))},
        **kw,
    )


def run(run_id: str, started: str, spent: float) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        book="mrk",
        stage="generate",
        started_at=started,
        ended_at=started,
        sections=SectionCounts(),
        estimate_usd=0,
        spent_usd=spent,
        tokens=TokenCounts(),
        models=["sonnet"],
        prompt_versions={"generate": "v3"},
    )


def test_scorecard_counts_kept_dropped_failed_and_missing() -> None:
    sections = [entry("mrk-1-1", 1, 8), entry("mrk-1-9", 9, 11), entry("mrk-1-12", 12, 15),
                entry("mrk-1-16", 16, 20)]  # fmt: skip
    drafts = {
        "mrk-1-1": draft(3, 4, ["mrk-1-1-k4", "mrk-1-1-q9"]),
        "mrk-1-9": draft(1, 0, [], sid="mrk-1-9", no_prompt=True, no_prompt_reason="Only names."),
        "mrk-1-12": draft(2, 2, [], sid="mrk-1-12", failed="no question on the whole passage",
                          status="failed"),
    }  # fmt: skip
    runs = [run("old", "2026-11-16T10:00", 1.0), run("new", "2026-11-17T10:00", 0.25)]
    card = build_scorecard("MRK", sections, drafts, runs, NOW)
    assert card.run_id == "new" and card.cost_usd == 0.25  # the latest run only
    assert (card.kept_ideas, card.kept_questions) == (6, 6)
    assert card.ideas.total == 0 and card.idea_pass_rate is None  # nothing graded yet
    assert card.dropped_by_stage == {"generate": 2}
    assert [f.section_id for f in card.failed_sections] == ["mrk-1-12"]
    assert card.failed_sections[0].reason == "no question on the whole passage"
    assert [n.section_id for n in card.no_prompt] == ["mrk-1-9"] and card.not_generated == [
        "mrk-1-16"
    ]
    assert not card.graded and not card.promotable
    assert "1 sections not generated" in card.blockers and "1 sections failed" in card.blockers


def test_review_page_shows_sections_ideas_and_problems(make_library: Any) -> None:
    lib = make_library({
        ("bsb", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": [
            {"type": "verse", "number": v, "text": f"BSB verse {v}."} for v in range(1, 21)]}]},
        ("kjv", "MRK"): {"book": "MRK", "chapters": [{"number": 1, "items": [
            {"type": "verse", "number": v, "text": f"KJV verse {v}."} for v in range(1, 21)]}]},
    })  # fmt: skip
    sections = [entry("mrk-1-1", 1, 8), entry("mrk-1-16", 16, 20)]
    drafts = {"mrk-1-1": draft(2, 2, ["mrk-1-1-k3"])}
    card = build_scorecard("MRK", sections, drafts, [], NOW)
    html = render_review(card, sections, drafts, lib)
    assert "Mark <span>scorecard</span>" in html and "Not promotable yet" in html
    assert 'id="mrk-1-1"' in html and 'data-problem="yes"' in html  # an evidence drop
    assert "BSB verse 3." in html and "KJV verse 3." in html
    assert "Not generated yet" in html  # mrk-1-16
    assert "evidence: not found" in html


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In {{ref:1:7}}, John speaks.", "In (verse 7), John speaks."),
        ("Look at {{ref:1:7-8}}.", "Look at (verses 7-8)."),
        ("Compare {{ref:2:3}}.", "Compare (2:3)."),
        # Already in parentheses: no second pair (Mark 1:38 showed "( (verse 38))").
        ("he says 'I came forth' ({{ref:1:38}}).", "he says 'I came forth' (verse 38)."),
    ],
)
def test_placeholders_read_as_the_app_shows_them(text: str, expected: str) -> None:
    assert readable(text, 1) == expected


def test_all_means_every_implemented_stage_in_order() -> None:
    every = "sections,intro,summaries,generate,align,check,review,report"
    assert expand_all("all") == every
    assert expand_all("generate") == "generate"
    assert expand_all("generate,all") == every
