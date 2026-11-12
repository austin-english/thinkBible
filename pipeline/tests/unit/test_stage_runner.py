"""The stage runner: skip on same hash, --fresh, isolated failures, cap, declined estimate."""

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import SectionDraft, SectionMapEntry
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.budget import EstimateSummary
from thinkbible_pipeline.llm.runner import FakeRunner, ModelError, Usage
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.snapshot import ChecksumMismatch
from thinkbible_pipeline.stages.base import Deps, RunResult, SectionResult, SectionStage, run
from thinkbible_pipeline.storage import LocalBlobStore

SETTINGS = load_settings()
IDS = ["mrk-1-1", "mrk-1-9", "mrk-1-12"]


class Summary(BaseModel):
    summary: str


class SummaryStage(SectionStage):
    """A minimal model stage: one call per section, result stored in the draft."""

    name = "summaries"

    def __init__(self) -> None:
        self.passages: dict[str, str] = dict.fromkeys(IDS, "text")

    def prompt_version(self, deps: Deps) -> str:
        return "v1"

    def model(self, deps: Deps) -> str | None:
        return deps.settings.stage(self.name).model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {"passage": self.passages[section_id]}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        out, usage = await deps.runner.parse(
            self.name, [], inputs["passage"], Summary, section_id=section_id
        )
        draft.summary = out.summary
        return SectionResult(usages=[usage])


def _store(tmp_path: Path) -> DraftStore:
    store = DraftStore("mrk", LocalBlobStore(tmp_path / "drafts"))
    store.write_section_map(
        [
            SectionMapEntry(
                id=sid, chapter=1, verse_start=v, verse_end=v, title="t", title_source="split"
            )
            for sid, v in zip(IDS, (1, 9, 12), strict=True)
        ]
    )
    return store


class Harness:
    def __init__(self, tmp_path: Path, **settings: Any) -> None:
        self.store = _store(tmp_path)
        self.stage = SummaryStage()
        self.runner = FakeRunner(responses={("summaries", s): {"summary": s} for s in IDS})
        self.estimates: list[EstimateSummary] = []
        self.approve = True
        self.settings = dataclasses.replace(SETTINGS, **settings)
        self.preflight_error: Exception | None = None
        self.extra_stages: dict[str, SectionStage] = {}

    def _approve(self, summary: EstimateSummary) -> bool:
        self.estimates.append(summary)
        return self.approve

    def _preflight(self) -> None:
        if self.preflight_error:
            raise self.preflight_error

    def run(self, **request: Any) -> RunResult:
        deps = Deps(
            store=self.store,
            settings=self.settings,
            pricing=load_pricing(),
            runner_factory=lambda: self.runner,
            approve_estimate=self._approve,
            stages={"summaries": self.stage, **self.extra_stages},
            preflight=self._preflight,
        )
        req = RunRequest(book="mark", stages=request.pop("stages", ["summaries"]), **request)
        return asyncio.run(run(req, deps))


def test_runs_every_section_then_skips_on_same_hash(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    first = h.run()
    assert first.exit_code == ExitCode.OK
    assert (first.stages[0].done, first.stages[0].skipped) == (3, 0)
    assert len(h.runner.calls) == 3
    draft = h.store.read_draft("mrk-1-9")
    assert draft is not None and draft.summary == "mrk-1-9"
    assert draft.stages["summaries"].status == "done"

    second = h.run()
    assert (second.stages[0].done, second.stages[0].skipped) == (0, 3)
    assert len(h.runner.calls) == 3  # SC-005: an unchanged re-run makes zero model calls
    assert len(h.estimates) == 1  # nothing to process, so nothing to approve
    assert [r.stage for r in h.store.read_runs()] == ["summaries", "summaries"]


def test_changed_inputs_rerun_only_that_section(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.run()
    h.stage.passages["mrk-1-12"] = "edited"
    result = h.run()
    assert (result.stages[0].done, result.stages[0].skipped) == (1, 2)
    assert h.runner.calls[-1] == ("summaries", "mrk-1-12")


def test_fresh_reruns_everything(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.run()
    result = h.run(fresh=True)
    assert result.stages[0].done == 3
    assert len(h.runner.calls) == 6


def test_sections_filter(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    result = h.run(sections=["mrk-1-9"])
    assert result.stages[0].done == 1
    assert h.runner.calls == [("summaries", "mrk-1-9")]
    bad = h.run(sections=["mrk-9-9"])
    assert bad.exit_code == ExitCode.USAGE


def test_one_failure_does_not_stop_others(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.runner.responses[("summaries", "mrk-1-9")] = ModelError("boom")
    result = h.run()
    assert result.exit_code == ExitCode.SECTIONS_FAILED
    s = result.stages[0]
    assert (s.done, s.failed) == (2, 1)
    failed = h.store.read_draft("mrk-1-9")
    assert failed is not None
    assert failed.stages["summaries"].status == "failed"
    assert "boom" in (failed.stages["summaries"].error or "")
    # A failed section is retried on the next run; done ones are skipped.
    h.runner.responses[("summaries", "mrk-1-9")] = {"summary": "fixed"}
    again = h.run()
    assert (again.stages[0].done, again.stages[0].skipped) == (1, 2)


def test_cap_stops_new_sections(tmp_path: Path) -> None:
    h = Harness(tmp_path, concurrency=1)
    # Each call costs 1M Haiku output tokens = $0.50.
    h.runner.usage = Usage(model="anthropic.claude-haiku-5-5", output_tokens=1_000_000)
    result = h.run(cap_usd=0.6)
    s = result.stages[0]
    assert result.exit_code == ExitCode.CAP_REACHED
    assert s.stopped_by == "cap"
    assert (s.done, s.not_started) == (2, 1)  # the second section started under the cap
    assert s.spent_usd == pytest.approx(1.0)
    assert h.store.read_runs()[-1].stopped_by == "cap"


def test_default_cap_is_twice_the_estimate(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.run()
    est = h.estimates[0]
    assert [(s.stage, s.to_process) for s in est.stages] == [("summaries", 3)]
    assert est.estimate_usd == pytest.approx(3 * SETTINGS.stage("summaries").default_cost_usd)
    assert est.cap_usd == pytest.approx(2 * est.estimate_usd)


class AlignStage(SummaryStage):
    """A second model stage whose inputs depend on the first stage's output."""

    name = "align"

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return {"summary": draft.summary}

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        _out, usage = await deps.runner.parse(
            self.name, [], str(inputs["summary"]), Summary, section_id=section_id
        )
        return SectionResult(usages=[usage])


def test_estimate_counts_sections_an_earlier_stage_will_change(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    align = AlignStage()
    h.extra_stages["align"] = align
    for s in IDS:
        h.runner.responses[("align", s)] = {"summary": s}
    h.run(stages=["summaries", "align"])
    # Change one passage: summaries re-runs it, so align must count it too, before it runs.
    h.stage.passages["mrk-1-12"] = "edited"
    h.runner.responses[("summaries", "mrk-1-12")] = {"summary": "new summary"}
    result = h.run(stages=["summaries", "align"])
    est = h.estimates[-1]
    assert [(s.stage, s.to_process, s.skipped) for s in est.stages] == [
        ("summaries", 1, 2),
        ("align", 1, 2),
    ]
    assert [(s.stage, s.done, s.skipped) for s in result.stages] == [
        ("summaries", 1, 2),
        ("align", 1, 2),
    ]


def test_declined_estimate_makes_zero_calls(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.approve = False
    result = h.run()
    assert result.stopped_by == "declined"
    assert result.exit_code == ExitCode.OK
    assert h.runner.calls == []
    assert h.store.read_runs() == []


def test_source_mismatch_exits_2_before_any_work(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.preflight_error = ChecksumMismatch(tmp_path / "bsb/MRK.json", "a" * 64, "b" * 64)
    result = h.run()
    assert result.exit_code == ExitCode.SOURCE_CHECKSUM
    assert h.runner.calls == []


def test_unimplemented_stage_is_a_usage_error(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    result = h.run(stages=["generate"])
    assert result.exit_code == ExitCode.USAGE
    assert "not implemented" in (result.error or "")


def test_drafts_are_canonical_json(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.run()
    text = (tmp_path / "drafts" / "mrk" / "sections" / "mrk-1-1.json").read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert '\n  "stages": {' in text  # 2-space indent, sorted keys
    keys = [line.split('"')[1] for line in text.splitlines() if line.startswith('  "')]
    assert keys == sorted(keys)
