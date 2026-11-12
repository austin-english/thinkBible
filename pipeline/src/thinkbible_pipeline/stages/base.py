"""The stage runner, split into steps the cloud and local paths share (research R7, R8, R15).

- ``estimate_run``: what the whole run will process and cost, for the one approval.
- ``plan_stage``: which sections of one stage need running (hash and skip).
- ``run_one_section``: run one stage for one section (cap check, execute, save, add cost).
- ``finish_stage``: write the stage's run record and stop the run at the cap.

In the cloud each step is a Lambda under Step Functions (``cloud/handlers.py``). ``run()`` is the
local mode (``run --local`` and tests): the same steps with asyncio. Nothing here reads stdin or
argv; approval comes through ``deps.approve_estimate``.
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from typing import Any, Literal

from pydantic import Field

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
from thinkbible_pipeline.jsonio import JsonModel, compact_canonical, sha256_hex
from thinkbible_pipeline.ledger import InMemoryLedger, RunStatus, SpendLedger
from thinkbible_pipeline.llm.budget import EstimateSummary, StageEstimate, estimate, price
from thinkbible_pipeline.llm.runner import ModelRunner, Usage
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.snapshot import SourceError

# --- stage interfaces ---


@dataclass
class SectionResult:
    """What one section's work used. The runner prices it and records the stage."""

    usages: list[Usage] = field(default_factory=list)


class SectionStage(ABC):
    """A stage that runs once per section, keyed by input hash so re-runs are free (SC-005)."""

    name: str
    # Stages without model calls that must see every section each time (report-like) set this.
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


Stage = SectionStage | BookStage

# --- dependencies ---


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Deps:
    store: DraftStore
    settings: Settings
    pricing: Pricing
    runner_factory: Callable[[], ModelRunner]
    approve_estimate: Callable[[EstimateSummary], bool]
    stages: Mapping[str, Stage]
    ledger: SpendLedger = field(default_factory=InMemoryLedger)
    # Verifies source checksums before any work (FR-002). Raises SourceError on a mismatch.
    preflight: Callable[[], None] = lambda: None
    clock: Callable[[], datetime] = _utcnow
    echo: Callable[[str], None] = lambda _msg: None
    code_version: str = "unknown"

    @cached_property
    def runner(self) -> ModelRunner:
        """Created on first use, so stages without model calls never need AWS credentials."""
        return self.runner_factory()

    def stage(self, name: str) -> Stage:
        stage = self.stages.get(name)
        if stage is None:
            raise UnknownStage(f"stage {name!r} is not implemented yet")
        return stage


class UnknownStage(LookupError):
    pass


class UnknownSections(ValueError):
    pass


# --- step results (JSON models, so they travel through Step Functions payloads) ---


class PlanItem(JsonModel):
    section_id: str
    input_hash: str


class StagePlan(JsonModel):
    stage: str
    book_level: bool = False
    prompt_version: str = ""
    model: str | None = None
    items: list[PlanItem] = Field(default_factory=list)
    skipped: int = 0
    estimate_usd: float = 0.0

    @property
    def section_ids(self) -> list[str]:
        return [i.section_id for i in self.items]


class SectionOutcome(JsonModel):
    section_id: str
    status: Literal["done", "failed", "not_started"]
    cost_usd: float = 0.0
    tokens: TokenCounts = Field(default_factory=TokenCounts)
    models: list[str] = Field(default_factory=list)
    error: str | None = None


class StageResult(JsonModel):
    stage: str
    done: int = 0
    skipped: int = 0
    failed: int = 0
    not_started: int = 0
    spent_usd: float = 0.0
    estimate_usd: float = 0.0
    stopped_by: Literal["cap"] | None = None
    failures: dict[str, str] = Field(default_factory=dict)


@dataclass
class RunResult:
    stages: list[StageResult] = field(default_factory=list)
    declined: bool = False
    error: str | None = None
    error_code: ExitCode | None = None

    @property
    def spent_usd(self) -> float:
        return sum(s.spent_usd for s in self.stages)

    @property
    def stopped_by(self) -> str | None:
        if self.declined:
            return "declined"
        return "cap" if any(s.stopped_by == "cap" for s in self.stages) else None

    @property
    def exit_code(self) -> ExitCode:
        if self.error_code is not None:
            return self.error_code
        if any(s.stopped_by == "cap" for s in self.stages):
            return ExitCode.CAP_REACHED
        if any(s.failed for s in self.stages):
            return ExitCode.SECTIONS_FAILED
        return ExitCode.OK


def exit_code_for(stages: list[StageResult]) -> ExitCode:
    return RunResult(stages=stages).exit_code


def new_run_id(now: datetime) -> str:
    return f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def input_hash(inputs: Any, prompt_version: str, model: str | None) -> str:
    """sha256 of the canonical JSON of (inputs, prompt version, model ID) (research R8)."""
    return sha256_hex(
        compact_canonical({"inputs": inputs, "promptVersion": prompt_version, "model": model})
    )


# --- steps ---


def _section_ids(request: RunRequest, deps: Deps) -> list[str]:
    all_ids = deps.store.section_ids()
    if not request.sections:
        return all_ids
    unknown = sorted(set(request.sections) - set(all_ids))
    if unknown:
        raise UnknownSections(f"sections not in sections.json: {', '.join(unknown)}")
    wanted = set(request.sections)
    return [i for i in all_ids if i in wanted]


def plan_stage(
    stage: Stage,
    request: RunRequest,
    deps: Deps,
    *,
    assume_changed: frozenset[str] = frozenset(),
) -> StagePlan:
    """Which sections of ``stage`` need running. Read-only, so the CLI can use it to estimate.

    ``assume_changed`` lists sections an earlier stage of the same run will rewrite: when
    estimating a multi-stage run, those count as "to process" for later stages too.
    """
    if isinstance(stage, BookStage):
        return StagePlan(stage=stage.name, book_level=True)
    pv = stage.prompt_version(deps)
    model = stage.model(deps)
    plan = StagePlan(stage=stage.name, prompt_version=pv, model=model)
    for sid in _section_ids(request, deps):
        draft = deps.store.read_draft_or_new(sid)
        h = input_hash(stage.inputs(sid, draft, deps), pv, model)
        rec = draft.stages.get(stage.name)
        unchanged = (
            rec is not None
            and rec.status == "done"
            and rec.prompt_version == pv
            and rec.input_hash == h
            and sid not in assume_changed
        )
        if unchanged and not request.fresh and not stage.always_run:
            plan.skipped += 1
        else:
            plan.items.append(PlanItem(section_id=sid, input_hash=h))
    if model is not None and plan.items:
        plan.estimate_usd = estimate(
            stage.name, len(plan.items), deps.store.read_runs(), deps.settings
        )
    return plan


def estimate_run(request: RunRequest, deps: Deps) -> tuple[list[StagePlan], EstimateSummary]:
    """Plan every stage of the run (read-only) and total the estimate (contracts/cli.md)."""
    plans: list[StagePlan] = []
    changed: set[str] = set()
    for name in request.stages:
        plan = plan_stage(deps.stage(name), request, deps, assume_changed=frozenset(changed))
        plans.append(plan)
        if plan.model is not None:
            changed.update(plan.section_ids)
    total = sum(p.estimate_usd for p in plans)
    cap = request.cap_usd if request.cap_usd is not None else 2 * total
    summary = EstimateSummary(
        stages=tuple(
            StageEstimate(
                stage=p.stage,
                to_process=len(p.items),
                skipped=p.skipped,
                estimate_usd=p.estimate_usd,
                calls_model=p.model is not None,
            )
            for p in plans
            if not p.book_level
        ),
        estimate_usd=total,
        cap_usd=cap if cap > 0 else None,
    )
    return plans, summary


async def run_one_section(
    stage: SectionStage,
    section_id: str,
    *,
    run_id: str,
    deps: Deps,
    reraise: tuple[type[BaseException], ...] = (),
) -> SectionOutcome:
    """Run ``stage`` for one section and save the result. Failures are recorded, not raised,
    except the exception types in ``reraise`` (the cloud lets throttling escape for a retry)."""
    if not deps.ledger.can_start(run_id):
        return SectionOutcome(section_id=section_id, status="not_started")
    pv = stage.prompt_version(deps)
    model = stage.model(deps)
    store = deps.store
    draft = store.read_draft_or_new(section_id)
    inputs = stage.inputs(section_id, draft, deps)
    h = input_hash(inputs, pv, model)
    try:
        res = await stage.execute(section_id, inputs, draft, deps)
    except reraise:
        raise
    except Exception as e:  # one failure marks only this section (research R8)
        fresh = store.read_draft_or_new(section_id)
        fresh.stages[stage.name] = StageRecord(
            prompt_version=pv,
            model=model,
            input_hash=h,
            completed_at=deps.clock().isoformat(),
            cost_usd=0.0,
            status="failed",
            error=f"{type(e).__name__}: {e}",
        )
        store.write_draft(section_id, fresh)
        deps.echo(f"  {section_id}: failed: {e}")
        return SectionOutcome(section_id=section_id, status="failed", error=str(e))

    cost = sum(price(u, deps.pricing) for u in res.usages)
    tokens = TokenCounts()
    models: set[str] = set()
    for u in res.usages:
        tokens.input += u.input_tokens
        tokens.output += u.output_tokens
        tokens.cache_read += u.cache_read_tokens
        tokens.cache_write += u.cache_write_tokens
        if not u.is_empty:
            models.add(u.model)
    draft.stages[stage.name] = StageRecord(
        prompt_version=pv,
        model=model,
        input_hash=h,
        completed_at=deps.clock().isoformat(),
        cost_usd=round(cost, 6),
        status="done",
    )
    store.write_draft(section_id, draft)
    deps.ledger.add(run_id, cost)
    return SectionOutcome(
        section_id=section_id,
        status="done",
        cost_usd=round(cost, 6),
        tokens=tokens,
        models=sorted(models),
    )


def finish_stage(
    plan: StagePlan,
    outcomes: list[SectionOutcome],
    *,
    run_id: str,
    started: datetime,
    deps: Deps,
    cap_usd: float | None = None,
) -> StageResult:
    """Write the stage's run record and stop the run if the cap stopped any section."""
    result = StageResult(stage=plan.stage, skipped=plan.skipped, estimate_usd=plan.estimate_usd)
    tokens = TokenCounts()
    models: set[str] = {plan.model} if plan.model else set()
    for o in outcomes:
        if o.status == "done":
            result.done += 1
        elif o.status == "failed":
            result.failed += 1
            result.failures[o.section_id] = o.error or ""
        else:
            result.not_started += 1
        result.spent_usd += o.cost_usd
        tokens.input += o.tokens.input
        tokens.output += o.tokens.output
        tokens.cache_read += o.tokens.cache_read
        tokens.cache_write += o.tokens.cache_write
        models.update(o.models)
    if result.not_started:
        result.stopped_by = "cap"
        deps.ledger.mark_stopped(run_id)
    deps.store.write_run(
        RunRecord(
            run_id=run_id,
            book=deps.store.book,
            stage=plan.stage,
            started_at=started.isoformat(),
            ended_at=deps.clock().isoformat(),
            sections=SectionCounts(done=result.done, skipped=result.skipped, failed=result.failed),
            estimate_usd=round(plan.estimate_usd, 6),
            cap_usd=cap_usd,
            spent_usd=round(result.spent_usd, 6),
            tokens=tokens,
            models=sorted(models),
            prompt_versions={plan.stage: plan.prompt_version} if plan.prompt_version else {},
            code_version=deps.code_version,
            stopped_by="cap" if result.stopped_by == "cap" else None,
        )
    )
    return result


def run_counts(stages: list[StageResult]) -> dict[str, int]:
    return {
        "done": sum(s.done for s in stages),
        "skipped": sum(s.skipped for s in stages),
        "failed": sum(s.failed for s in stages),
        "notStarted": sum(s.not_started for s in stages),
    }


# --- local mode ---


async def run(request: RunRequest, deps: Deps, *, run_id: str | None = None) -> RunResult:
    """Run every requested stage in-process (``run --local`` and tests)."""
    try:
        deps.preflight()
    except SourceError as e:
        return RunResult(error=str(e), error_code=ExitCode.SOURCE_CHECKSUM)
    try:
        _plans, summary = estimate_run(request, deps)
    except (UnknownStage, UnknownSections) as e:
        return RunResult(error=str(e), error_code=ExitCode.USAGE)
    if summary.calls_model and not deps.approve_estimate(summary):
        return RunResult(declined=True)

    run_id = run_id or new_run_id(deps.clock())
    deps.ledger.create(run_id, deps.store.book, summary.cap_usd)
    result = RunResult()
    sem = asyncio.Semaphore(max(1, deps.settings.concurrency))

    async def one(stage: SectionStage, sid: str) -> SectionOutcome:
        async with sem:
            return await run_one_section(stage, sid, run_id=run_id, deps=deps)

    for name in request.stages:
        stage = deps.stage(name)
        started = deps.clock()
        if isinstance(stage, BookStage):
            await stage.run_book(request, deps)
            result.stages.append(StageResult(stage=name, done=1))
            continue
        plan = plan_stage(stage, request, deps)
        outcomes = list(await asyncio.gather(*(one(stage, sid) for sid in plan.section_ids)))
        sr = finish_stage(
            plan, outcomes, run_id=run_id, started=started, deps=deps, cap_usd=summary.cap_usd
        )
        result.stages.append(sr)
        if sr.stopped_by == "cap":
            break

    status: RunStatus = "stopped-cap" if result.stopped_by == "cap" else "succeeded"
    deps.ledger.finish(run_id, status, run_counts(result.stages))
    return result
