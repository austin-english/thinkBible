"""A two-chapter fixture book through every implemented stage (T044, SC-005): no model calls.

The scripted runner answers from what it is actually given: it quotes the commentary in the
prompt (so the evidence check passes on real text) and aims questions at the idea IDs it was
shown, so sections, gathering, generation, the rules and the report all run for real.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.runner import Usage
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.versification import KJV_VERSES
from thinkbible_pipeline.stages import expand_all, registry
from thinkbible_pipeline.stages.base import Deps, estimate_run, run
from thinkbible_pipeline.storage import LocalBlobStore

CHAPTERS = (1, 2)
HEADINGS = {1: {1: "John Prepares the Way", 9: "The Baptism of Jesus", 16: "The First Disciples",
                29: "Jesus Heals Many", 40: "A Leper Cleansed"},
            2: {1: "A Paralytic Healed", 13: "Levi Called", 23: "Lord of the Sabbath"}}  # fmt: skip


def translation(code: str, word: str) -> dict[str, Any]:
    chapters = []
    for c in CHAPTERS:
        items: list[dict[str, Any]] = []
        for v in range(1, KJV_VERSES["MRK"][c - 1] + 1):
            if v in HEADINGS[c]:
                items.append({"type": "heading", "text": HEADINGS[c][v]})
            items.append({"type": "verse", "number": v, "text": f"{word} text of {c}:{v}."})
        chapters.append({"number": c, "items": items})
    return {"book": code, "chapters": chapters}


def commentary(name: str, every: int) -> dict[str, Any]:
    """Notes on every ``every``th verse, each with enough distinct words to quote."""
    chapters = []
    for c in CHAPTERS:
        items = [
            {"verse": v, "text": f"{name} observes that verse {c} {v} shows the grace of God "
                                 f"plainly to every reader who looks closely at chapter {c}."}
            for v in range(1, KJV_VERSES["MRK"][c - 1] + 1, every)
        ]  # fmt: skip
        chapters.append({"number": c, "items": items})
    return {"book": "MRK", "chapters": chapters}


_SECTION = re.compile(r"^Section (\S+): Mark (\d+):(\d+)-(\d+)", re.M)
_NOTE = re.compile(r'<commentary commentator="([a-z-]+)"[^>]*>\n\[[^\]]+\]\n(.+?)\n', re.S)
_IDEA = re.compile(r"^- (\S+-k\d+) \[verses (\d+)-(\d+)", re.M)
_GRADED = re.compile(r"^- (\S+) \[(?:key idea|question);", re.M)


@dataclass
class ScriptedRunner:
    """Writes valid outputs from each prompt: quotes the notes it is given, targets real IDs."""

    calls: list[tuple[str, str]] = field(default_factory=list)

    async def parse(self, stage: str, system: Any, user: str, output_model: type[BaseModel], *,
                    section_id: str, call: str | None = None) -> tuple[Any, Usage]:  # fmt: skip
        name = f"{stage}.{call}" if call else stage
        self.calls.append((name, section_id))
        m = _SECTION.search(user)
        assert m, user[:200]
        start, end = int(m.group(3)), int(m.group(4))
        if name == "review":  # every item is good, so the gate keeps them all
            value = {"items": [{"itemId": i, "score": 4, "reason": "Clear and faithful."}
                               for i in _GRADED.findall(user)]}  # fmt: skip
        elif name == "summaries":
            value: dict[str, Any] = {"summary": f"What happens in {section_id}."}
        elif name == "generate.extract":
            notes = {c: " ".join(text.split()[:8]) for c, text in _NOTE.findall(user)}
            value = {
                "keyIdeas": [
                    {"kind": "key", "title": f"Point {n}", "body": f"Why point {n} matters.",
                     "sources": [c], "verseStart": start, "verseEnd": end,
                     "evidence": [{"commentator": c, "quote": q}]}
                    for n, (c, q) in enumerate(notes.items(), 1)
                ],
                "context": "Mark wrote quickly for Roman believers.",
                "viewsDiffer": None,
                "noPrompt": not notes,
                "noPromptReason": None if notes else "No notes.",
            }  # fmt: skip
        else:
            ideas = [i[0] for i in _IDEA.findall(user)]
            value = {"questions": [
                {"text": "What do you make of this detail?", "type": "noticing",
                 "verseStart": start, "verseEnd": start, "targets": [ideas[0]]},
                {"text": "Why might the whole passage be told this way?", "type": "meaning",
                 "verseStart": start, "verseEnd": end, "targets": ideas[:2]},
                {"text": "How does this connect with the rest of Scripture?", "type": "application",
                 "verseStart": start, "verseEnd": end, "targets": ideas[-1:]},
            ]}  # fmt: skip
        model = load_settings().stage(stage).model  # priced like the real call
        return output_model.model_validate(value), Usage(model=model, input_tokens=1000,
                                                         output_tokens=200)  # fmt: skip


def make(tmp_path: Path, make_library: Any) -> tuple[Deps, ScriptedRunner]:
    library = make_library({
        ("bsb", "MRK"): translation("MRK", "BSB"),
        ("kjv", "MRK"): translation("MRK", "KJV"),
        ("matthew-henry", "MRK"): commentary("Henry", 8),
        ("jamieson-fausset-brown", "MRK"): commentary("Jamieson", 3),
        ("adam-clarke", "MRK"): commentary("Clarke", 2),
    })  # fmt: skip
    runner = ScriptedRunner()
    deps = Deps(
        store=DraftStore("mrk", LocalBlobStore(tmp_path / "drafts")),
        settings=load_settings(),
        pricing=load_pricing(),
        runner_factory=lambda: runner,  # type: ignore[arg-type,return-value]
        approve_estimate=lambda _s: True,
        stages=registry(),
        library=library,
    )
    return deps, runner


def test_fixture_book_end_to_end(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Independent of the repo's real calibration file: this book's grader is uncalibrated.
    from thinkbible_pipeline.gate.calibration import CalibrationSet

    monkeypatch.setattr("thinkbible_pipeline.stages.report.load_calibration",
                        lambda _path: CalibrationSet())  # fmt: skip
    deps, runner = make(tmp_path, make_library)
    request = RunRequest(book="mark", stages=expand_all("all"))  # type: ignore[arg-type]
    result = asyncio.run(run(request, deps))
    assert result.exit_code == ExitCode.OK, result.stages

    root = tmp_path / "drafts" / "mrk"
    ids = deps.store.section_ids()
    assert ids[0] == "mrk-1-1" and all(i.startswith(("mrk-1-", "mrk-2-")) for i in ids)
    for name in ("book.json", "sections.json", "scorecard.json", "review.html"):
        assert (root / name).is_file(), name
    assert sorted(p.name for p in (root / "sections").iterdir()) == sorted(f"{i}.json" for i in ids)
    assert {p.name.split("-", 2)[-1] for p in (root / "runs").iterdir()} == {
        "intro.json", "summaries.json", "generate.json", "check.json", "review.json"
    }  # fmt: skip

    for sid in ids:
        section = deps.store.read_draft_or_new(sid).section
        ideas = section["keyIdeas"]
        assert ideas and all(i["sources"] for i in ideas)  # every idea names a commentator
        questions = section["questions"]
        assert 1 <= len(questions) <= min(3, len(ideas))  # one per idea at most, never more than 3

    card = json.loads((root / "scorecard.json").read_text())
    assert card["sections"] == len(ids) and card["failedSections"] == []
    assert card["notGenerated"] == []
    for sid in ids:  # every section passed the schema and cross-field checks
        assert [c.ok for c in deps.store.read_draft_or_new(sid).checks] == [True]
    assert json.loads((root / "book.json").read_text())["status"] == "gated"
    assert "Mark <span>scorecard</span>" in (root / "review.html").read_text()
    # summary, extract, questions, grade, answer, judge per section
    assert len(runner.calls) == 4 * len(ids)  # summaries, extract, questions, review
    assert card["ideaPassRate"] == 1.0 and card["questionPassRate"] == 1.0
    assert card["graded"] is True and not card["promotable"]  # no calibration yet
    assert any("calibrat" in b for b in card["blockers"])


def test_a_second_run_reports_nothing_to_do(tmp_path: Path, make_library: Any) -> None:
    deps, runner = make(tmp_path, make_library)
    request = RunRequest(book="mark", stages=expand_all("all"))  # type: ignore[arg-type]
    asyncio.run(run(request, deps))
    calls = len(runner.calls)
    _plans, summary = estimate_run(request, deps)
    assert summary.estimate_usd == 0.0
    assert all(s.to_process == 0 for s in summary.stages)
    again = asyncio.run(run(request, deps))
    assert len(runner.calls) == calls and again.spent_usd == 0.0
