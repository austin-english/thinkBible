"""The stage runner: ``run(request, deps) -> RunResult`` (research R7, R8, R15).

It never reads stdin or argv. Approval of the estimate comes through ``deps.approve_estimate``:
locally the ``Proceed? [y/N]`` prompt, in the cloud a Step Functions wait-for-approval step.
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from typing import Any

from thinkbible_pipeline.config import Pricing, Settings
from thinkbible_pipeline.drafts.models import (
    RunRecord,
    SectionCounts,
    SectionDraft,
    StageRecord,
    TokenCounts,
)
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.jsonio import compact_canonical, sha256_hex
from thinkbible_pipeline.llm.budget import Budget, EstimateSummary, estimate, price
from thinkbible_pipeline.llm.runner import ModelRunner, Usage
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.snapshot import SourceError


@dataclass
class SectionResult:
    """What one section's work used. The runner prices it and records the stage."""

    usages: list[Usage] = field(default_factory=list)


class SectionStage(ABC):
    """A stage that runs once per section, keyed by input hash so re-runs are free (SC-005)."""

    name: str
    # Read-only stages without model calls (check, report) always run.
    always_run: bool = False

    @abstractmethod
    def prompt_version(self, deps: Deps) -> str: ...

    @abstractmethod
    def model(self, deps: Deps) -> str | None:
        """The model ID this stage calls, or None for stages without model calls."""

    @abstractmethod
    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        """Everything the output depends on, as JSON-ready data. Hashed to decide skips."""

    @abstractmethod
    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        """Do the work and update ``draft`` in place. Raise to mark only this section failed."""


class BookStage(ABC):
    """A stage that works on the whole book at once (``sections``, ``report``)."""

    name: str

    @abstractmethod
    async def run_book(self, request: RunRequest, deps: Deps) -> None: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Deps:
    store: DraftStore
    settings: Settings
    pricing: Pricing
    runner_factory: Callable[[], ModelRunner]
    approve_estimate: Callable[[EstimateSummary], bool]
    stages: Mapping[str, SectionStage | BookStage]
    # Verifies source checksums before any work (FR-002). Raises SourceError on a mismatch.
    preflight: Callable[[], None] = lambda: None
    clock: Callable[[], datetime] = _utcnow
    echo: Callable[[str], None] = lambda _msg: None

    @cached_property
    def runner(self) -> ModelRunner:
        """Created on first use, so stages without model calls never need AWS credentials."""
        return self.runner_factory()


@dataclass
class StageResult:
    stage: str
    done: int = 0
    skipped: int = 0
    failed: int = 0
    not_started: int = 0
    spent_usd: float = 0.0
    estimate_usd: float = 0.0
    cap_usd: float | None = None
    declined: bool = False
    stopped_by: str | None = None
    failures: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    stages: list[StageResult] = field(default_factory=list)
    error: str | None = None
    error_code: ExitCode | None = None

    @property
    def spent_usd(self) -> float:
        return sum(s.spent_usd for s in self.stages)

    @property
    def stopped_by(self) -> str | None:
        for s in self.stages:
            if s.stopped_by:
                return s.stopped_by
            if s.declined:
                return "declined"
        return None

    @property
    def exit_code(self) -> ExitCode:
        if self.error_code is not None:
            return self.error_code
        if any(s.stopped_by == "cap" for s in self.stages):
            return ExitCode.CAP_REACHED
        if any(s.failed for s in self.stages):
            return ExitCode.SECTIONS_FAILED
        return ExitCode.OK


def input_hash(inputs: Any, prompt_version: str, model: str | None) -> str:
    """sha256 of the canonical JSON of (inputs, prompt version, model ID) (research R8)."""
    return sha256_hex(
        compact_canonical({"inputs": inputs, "promptVersion": prompt_version, "model": model})
    )


async def run(request: RunRequest, deps: Deps) -> RunResult:
    result = RunResult()
    try:
        deps.preflight()
    except SourceError as e:
        return RunResult(error=str(e), error_code=ExitCode.SOURCE_CHECKSUM)

    for name in request.stages:
        stage = deps.stages.get(name)
        if stage is None:
            result.error = f"stage {name!r} is not implemented yet"
            result.error_code = ExitCode.USAGE
            return result
        if isinstance(stage, BookStage):
            await stage.run_book(request, deps)
            result.stages.append(StageResult(stage=name, done=1))
            continue
        try:
            sr = await run_section_stage(stage, request, deps)
        except UnknownSections as e:
            result.error = str(e)
            result.error_code = ExitCode.USAGE
            return result
        result.stages.append(sr)
        if sr.declined or sr.stopped_by == "cap":
            break
    return result


class UnknownSections(ValueError):
    pass


async def run_section_stage(stage: SectionStage, request: RunRequest, deps: Deps) -> StageResult:
    store = deps.store
    all_ids = store.section_ids()
    if request.sections:
        unknown = sorted(set(request.sections) - set(all_ids))
        if unknown:
            raise UnknownSections(f"sections not in sections.json: {', '.join(unknown)}")
        ids = [i for i in all_ids if i in set(request.sections)]
    else:
        ids = all_ids

    pv = stage.prompt_version(deps)
    model = stage.model(deps)
    out = StageResult(stage=stage.name)
    started = deps.clock()

    # Decide what to run. A section is skipped when its last successful run used the same
    # prompt version and inputs (unless --fresh).
    todo: list[tuple[str, Any, str, SectionDraft]] = []
    for sid in ids:
        draft = store.read_draft_or_new(sid)
        inputs = stage.inputs(sid, draft, deps)
        h = input_hash(inputs, pv, model)
        rec = draft.stages.get(stage.name)
        same = (
            rec is not None
            and rec.status == "done"
            and rec.prompt_version == pv
            and rec.input_hash == h
        )
        if same and not request.fresh and not stage.always_run:
            out.skipped += 1
        else:
            todo.append((sid, inputs, h, draft))

    budget = Budget(None)
    if model is not None and todo:
        out.estimate_usd = estimate(stage.name, len(todo), store.read_runs(), deps.settings)
        cap = request.cap_usd if request.cap_usd is not None else 2 * out.estimate_usd
        out.cap_usd = cap if cap > 0 else None
        summary = EstimateSummary(
            stage=stage.name,
            to_process=len(todo),
            skipped=out.skipped,
            estimate_usd=out.estimate_usd,
            cap_usd=out.cap_usd or 0.0,
        )
        if not deps.approve_estimate(summary):
            out.declined = True
            return out
        budget = Budget(out.cap_usd)

    tokens = TokenCounts()
    models_used: set[str] = {model} if model else set()
    sem = asyncio.Semaphore(max(1, deps.settings.concurrency))

    async def work(sid: str, inputs: Any, h: str, draft: SectionDraft) -> None:
        async with sem:
            if not budget.can_start():
                out.not_started += 1
                return
            try:
                res = await stage.execute(sid, inputs, draft, deps)
            except Exception as e:  # one failure marks only this section (research R8)
                fresh = store.read_draft_or_new(sid)
                fresh.stages[stage.name] = StageRecord(
                    prompt_version=pv,
                    model=model,
                    input_hash=h,
                    completed_at=deps.clock().isoformat(),
                    cost_usd=0.0,
                    status="failed",
                    error=f"{type(e).__name__}: {e}",
                )
                store.write_draft(sid, fresh)
                out.failed += 1
                out.failures[sid] = str(e)
                deps.echo(f"  {sid}: failed: {e}")
                return
            cost = sum(price(u, deps.pricing) for u in res.usages)
            budget.add(cost)
            out.spent_usd += cost
            for u in res.usages:
                tokens.input += u.input_tokens
                tokens.output += u.output_tokens
                tokens.cache_read += u.cache_read_tokens
                tokens.cache_write += u.cache_write_tokens
                if not u.is_empty:
                    models_used.add(u.model)
            draft.stages[stage.name] = StageRecord(
                prompt_version=pv,
                model=model,
                input_hash=h,
                completed_at=deps.clock().isoformat(),
                cost_usd=round(cost, 6),
                status="done",
            )
            store.write_draft(sid, draft)
            out.done += 1

    await asyncio.gather(*(work(*t) for t in todo))

    if out.not_started:
        out.stopped_by = "cap"
    store.append_run(
        RunRecord(
            run_id=f"{started:%Y%m%dT%H%M%SZ}-{stage.name}-{uuid.uuid4().hex[:6]}",
            book=store.book,
            stage=stage.name,
            started_at=started.isoformat(),
            ended_at=deps.clock().isoformat(),
            sections=SectionCounts(done=out.done, skipped=out.skipped, failed=out.failed),
            estimate_usd=round(out.estimate_usd, 6),
            cap_usd=out.cap_usd,
            spent_usd=round(out.spent_usd, 6),
            tokens=tokens,
            models=sorted(models_used),
            prompt_versions={stage.name: pv},
            stopped_by="cap" if out.stopped_by == "cap" else None,
        )
    )
    return out
