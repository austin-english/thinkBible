"""Lambda handlers for the ``thinkbible-pipeline`` state machine (research R7).

Each handler parses its payload, builds the cloud ``Deps`` (S3 drafts and sources, the DynamoDB
ledger, the Bedrock runner) and calls one shared step from ``stages/base.py``.

    StartRun → Stages (map, one at a time) [PlanStage → Sections (map) [RunSection]
             → SubmitBatch → (a batch run with sections waiting: Wait → CheckBatch, until the
               batch has ended → Sections again) → FinishStage] → FinishRun
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from thinkbible_pipeline.cloud.ledger import DynamoLedger
from thinkbible_pipeline.cloud.messages import (
    FinishRunInput,
    FinishStageInput,
    PlanOutput,
    RunInput,
    RunOutput,
    SectionInput,
    StageInput,
)
from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.llm.batch import AnthropicBatchClient, collect_round
from thinkbible_pipeline.llm.runner import BedrockRunner, ModelRunner, Throttled
from thinkbible_pipeline.paths import repo_paths
from thinkbible_pipeline.publish.channel import PackChannel, pack_channels
from thinkbible_pipeline.publish.draft import publish_after_run
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.snapshot import (
    SourceError,
    SourceLibrary,
    SourceStore,
    load_manifest,
    verify,
)
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import (
    BookStage,
    Deps,
    StagePlan,
    StageResult,
    exit_code_for,
    finish_stage,
    plan_stage,
    run_counts,
    run_one_section,
    split_waiting,
    submit_batch_or_stop,
)
from thinkbible_pipeline.storage import S3BlobStore

Event = dict[str, Any]


class SourceChecksumError(Exception):
    """Matched by name in the state machine's Catch → the "SourceChecksum" Fail state."""


@dataclass(frozen=True)
class CloudEnv:
    """Set by Terraform on every pipeline Lambda (research R19)."""

    drafts_bucket: str
    sources_bucket: str
    ledger_table: str
    code_version: str

    @classmethod
    def from_environ(cls) -> CloudEnv:
        return cls(
            drafts_bucket=os.environ["DRAFTS_BUCKET"],
            sources_bucket=os.environ["SOURCES_BUCKET"],
            ledger_table=os.environ["LEDGER_TABLE"],
            code_version=_bundle_code_version(),
        )


def _bundle_code_version() -> str:
    info = repo_paths().root / "BUILD_INFO.json"
    if info.is_file():
        return str(json.loads(info.read_text(encoding="utf-8")).get("gitHead", "unknown"))
    return os.environ.get("CODE_VERSION", "unknown")


def cloud_deps(request: RunRequest, env: CloudEnv) -> Deps:
    paths = repo_paths()
    settings = load_settings(paths.config)
    sources = SourceStore.s3(env.sources_bucket)
    book = request.book_info

    def preflight() -> None:
        problems = verify(store=sources, manifest=load_manifest(paths), books={book.code})
        if problems:
            raise SourceError("\n".join(f"{p.source}/{p.book}: {p.message}" for p in problems))

    def runner() -> ModelRunner:
        return BedrockRunner(settings)

    return Deps(
        store=DraftStore(book.slug, S3BlobStore(env.drafts_bucket, "drafts/")),
        settings=settings,
        pricing=load_pricing(paths.config),
        runner_factory=runner,
        # The CLI showed the estimate and got approval before starting the execution.
        approve_estimate=lambda _summary: True,
        stages=registry(),
        ledger=DynamoLedger(env.ledger_table),
        preflight=preflight,
        echo=print,
        code_version=env.code_version,
        library=SourceLibrary(sources, load_manifest(paths)),
        batch_client_factory=lambda: AnthropicBatchClient(settings),
    )


def env_channels() -> tuple[PackChannel, PackChannel] | None:
    """The packs bucket's channels from the Lambda environment (set by Terraform, US3)."""
    return pack_channels(os.environ.get("PACKS_BUCKET", ""), os.environ.get("DISTRIBUTION_ID", ""))


# Tests replace this to inject moto-backed channels.
CHANNELS_FACTORY: Callable[[], tuple[PackChannel, PackChannel] | None] = env_channels

# Tests replace this to inject moto-backed stores and a FakeRunner.
DEPS_FACTORY: Callable[[RunRequest], Deps] = lambda request: cloud_deps(  # noqa: E731
    request, CloudEnv.from_environ()
)


def _dump(model: Any) -> Event:
    # Keep nulls: the state machine's JSONPath selectors (e.g. "$.capUsd") need every key present.
    return dict(model.model_dump(mode="json", by_alias=True))


# --- handlers ---


def start_run(event: Event, _context: object = None) -> Event:
    """Verify the sources the book needs, then create the run's ledger item."""
    inp = RunInput.model_validate(event)
    deps = DEPS_FACTORY(inp.request)
    try:
        deps.preflight()
    except SourceError as e:
        raise SourceChecksumError(str(e)) from e
    deps.ledger.create(inp.run_id, deps.store.book, inp.cap_usd)
    return _dump(inp)


def plan_stage_handler(event: Event, _context: object = None) -> Event:
    """Plan one stage. Book-level stages (sections, report) run here and return no sections."""
    inp = StageInput.model_validate(event)
    deps = DEPS_FACTORY(inp.request)
    started = deps.clock()
    state = deps.ledger.get(inp.run_id)
    if state is not None and state.status == "stopped-cap":
        out = PlanOutput(
            **inp.model_dump(),
            started_at=started.isoformat(),
            plan=StagePlan(stage=inp.stage),
            stopped=True,
        )
        return _dump(out)
    stage = deps.stage(inp.stage)
    if isinstance(stage, BookStage):
        asyncio.run(stage.run_book(inp.request, deps))
    plan = plan_stage(stage, inp.request, deps)
    out = PlanOutput(
        **inp.model_dump(),
        started_at=started.isoformat(),
        plan=plan,
        section_ids=plan.section_ids,
    )
    return _dump(out)


def run_section(event: Event, _context: object = None) -> Event:
    """Run one stage for one section. Throttling escapes so Step Functions retries it."""
    inp = SectionInput.model_validate(event)
    deps = DEPS_FACTORY(inp.request)
    if inp.request.batch:
        deps.start_batch(inp.run_id)
    stage = deps.stage(inp.stage)
    if isinstance(stage, BookStage):
        raise TypeError(f"{inp.stage} is a book-level stage; it has no sections")
    outcome = asyncio.run(
        run_one_section(stage, inp.section_id, run_id=inp.run_id, deps=deps, reraise=(Throttled,))
    )
    return _dump(outcome)


def submit_batch(event: Event, _context: object = None) -> Event:
    """After a Sections map: settle its outcomes, and in a batch run send the waiting sections'
    requests as one batch. ``batchId`` is null when no section waits (on to FinishStage)."""
    inp = FinishStageInput.model_validate(event)
    settled, waiting = split_waiting(inp.round_outcomes)
    out = inp.model_copy(
        update={"outcomes": inp.outcomes + settled, "round_outcomes": [], "section_ids": [],
                "batch_id": None, "batch_ready": False}
    )  # fmt: skip
    if waiting:
        deps = DEPS_FACTORY(inp.request)
        deps.start_batch(inp.run_id)
        batch_id, ended = asyncio.run(
            submit_batch_or_stop(
                inp.stage, waiting, run_id=inp.run_id, deps=deps, rounds=inp.rounds
            )
        )
        out.outcomes = out.outcomes + ended
        if batch_id is not None:
            gone = {o.section_id for o in ended}
            out.batch_id = batch_id
            out.section_ids = [s for s in waiting if s not in gone]
            out.rounds = inp.rounds + 1
    return _dump(out)


def check_batch(event: Event, _context: object = None) -> Event:
    """Has the batch ended? If so, save its answers; the waiting sections then run again."""
    inp = FinishStageInput.model_validate(event)
    if inp.batch_id is None:
        raise ValueError("CheckBatch needs a batchId")
    deps = DEPS_FACTORY(inp.request)
    ctx = deps.start_batch(inp.run_id)
    ready = asyncio.run(collect_round(inp.batch_id, deps.store, ctx))
    return _dump(inp.model_copy(update={"batch_ready": ready}))


def finish_stage_handler(event: Event, _context: object = None) -> Event:
    """Write the stage's run record; mark the run stopped if the cap stopped any section."""
    inp = FinishStageInput.model_validate(event)
    if inp.plan.book_level and not inp.stopped:
        return _dump(StageResult(stage=inp.stage, done=1))
    deps = DEPS_FACTORY(inp.request)
    if inp.request.batch:
        deps.start_batch(inp.run_id)  # so the run record says the stage ran at batch prices
    if inp.stopped:
        state = deps.ledger.get(inp.run_id)
        reason = state.stop_reason if state and state.stop_reason else "cap"
        return _dump(StageResult(stage=inp.stage, stopped_by=reason))
    result = finish_stage(
        inp.plan,
        inp.outcomes,
        run_id=inp.run_id,
        started=datetime.fromisoformat(inp.started_at),
        deps=deps,
        cap_usd=inp.cap_usd,
    )
    return _dump(result)


def finish_run(event: Event, _context: object = None) -> Event:
    """Final status and counts. The execution's output is what `run --wait` reports."""
    inp = FinishRunInput.model_validate(event)
    deps = DEPS_FACTORY(inp.request)
    stages = inp.stage_results
    stopped = any(s.stopped_by for s in stages)
    deps.ledger.finish(inp.run_id, "stopped-cap" if stopped else "succeeded", run_counts(stages))
    out = RunOutput(
        run_id=inp.run_id,
        book=deps.store.book,
        status="stopped-cap" if stopped else "succeeded",
        exit_code=int(exit_code_for(stages)),
        spent_usd=round(sum(s.spent_usd for s in stages), 6),
        stages=stages,
        publishable="report" in inp.request.stages and not any(s.failed for s in stages),
    )
    if out.publishable and not stopped and not inp.request.publish:
        out.publish = "publish: skipped (--no-publish)"
    elif out.publishable and not stopped:
        out.publish = publish_after_run(
            deps.store, deps.library, CHANNELS_FACTORY(), deps.clock(), deps.echo
        )
    return _dump(out)
