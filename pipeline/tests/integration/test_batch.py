"""Batch runs (T087) on the fixture book, with a fake Batches API: no model calls.

The fake answers each batch request the way the scripted runner answers a standard call, so a
batch run must produce exactly the content of a standard run, at half the price of the batch
stages, in rounds.
"""

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.llm.batch import (
    Answer,
    AwaitingBatch,
    BatchReplayRunner,
    BatchStore,
    FakeBatchClient,
    PendingCall,
)
from thinkbible_pipeline.llm.runner import FakeRunner, ModelError, OutOfCredit
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import expand_all
from thinkbible_pipeline.stages.base import Deps, run

_spec = importlib.util.spec_from_file_location(
    "fixture_book", Path(__file__).with_name("test_generate_fixture_book.py")
)
assert _spec and _spec.loader
_fixture_book = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture_book)
make = _fixture_book.make


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


def scripted_batch(runner: Any, **kwargs: Any) -> FakeBatchClient:
    """Answer each batch request as the scripted runner answers the same call."""

    async def respond(call: PendingCall) -> dict[str, Any]:
        stage, _, name = call.what.partition(".")
        user = call.params["messages"][0]["content"]
        out, _usage = await runner.parse(stage, [], user, _Loose, section_id=call.section_id,
                                         call=name or None)  # fmt: skip
        return dict(out.model_dump())

    return FakeBatchClient(respond=respond, **kwargs)


def sections(deps: Deps) -> dict[str, Any]:
    return {sid: deps.store.read_draft_or_new(sid).section for sid in deps.store.section_ids()}


def batch_deps(tmp_path: Path, make_library: Any, **client: Any) -> tuple[Deps, Any, Any]:
    deps, runner = make(tmp_path, make_library)
    fake = scripted_batch(runner, **client)
    deps.batch_client_factory = lambda: fake
    return deps, runner, fake


def all_stages(**kw: Any) -> RunRequest:
    return RunRequest(book="mark", stages=expand_all("all"), **kw)  # type: ignore[arg-type]


def test_a_batch_run_writes_what_a_standard_run_writes_at_half_the_price(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    standard, _ = make(tmp_path / "standard", make_library)
    plain = asyncio.run(run(all_stages(), standard))
    deps, _runner, fake = batch_deps(tmp_path / "batch", make_library, polls=2)
    result = asyncio.run(run(all_stages(batch=True), deps))
    assert result.exit_code == ExitCode.OK, result.stages
    assert sections(deps) == sections(standard)

    # generate: key ideas, then questions (two rounds); review: one round. The rest are standard.
    whats = [sorted({c.what for c in calls}) for calls in fake.batches.values()]
    assert whats == [["generate.extract"], ["generate.questions"], ["review"]]
    n = len(deps.store.section_ids())
    assert all(len(calls) == n for calls in fake.batches.values())

    by_stage = {s.stage: s for s in result.stages}
    plain_by_stage = {s.stage: s for s in plain.stages}
    for stage in ("generate", "review"):
        assert by_stage[stage].done == n
        assert by_stage[stage].spent_usd == pytest.approx(plain_by_stage[stage].spent_usd / 2)
    assert by_stage["summaries"].spent_usd == pytest.approx(plain_by_stage["summaries"].spent_usd)
    records = {r.stage: r for r in deps.store.read_runs()}
    assert records["generate"].batch and not records["summaries"].batch


async def _no_sleep(_seconds: float) -> None:
    return None


def test_a_second_batch_run_has_nothing_to_do(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    deps, _runner, fake = batch_deps(tmp_path, make_library)
    asyncio.run(run(all_stages(batch=True), deps))
    batches = len(fake.batches)
    deps2, _r, fake2 = batch_deps(tmp_path, make_library)
    asyncio.run(run(all_stages(batch=True), deps2))
    assert len(fake.batches) == batches and fake2.batches == {}


def test_out_of_credit_at_submit_stops_the_run(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    deps, _runner, fake = batch_deps(tmp_path, make_library)

    async def broke(_calls: Any) -> str:
        raise OutOfCredit("out of Claude API credit")

    fake.submit = broke  # type: ignore[method-assign]
    result = asyncio.run(run(all_stages(batch=True), deps))
    generate = next(s for s in result.stages if s.stage == "generate")
    assert generate.done == 0 and generate.not_started == len(deps.store.section_ids())
    assert result.stopped_by == "credit" and result.exit_code == ExitCode.CAP_REACHED
    assert all("generate" not in deps.store.read_draft_or_new(s).stages
               for s in deps.store.section_ids())  # fmt: skip


# --- the replay runner on its own ---


class Out(BaseModel):
    summary: str


def replay(tmp_path: Path, standard: Any = None) -> tuple[BatchReplayRunner, BatchStore]:
    from thinkbible_pipeline.config import load_settings
    from thinkbible_pipeline.drafts.store import DraftStore
    from thinkbible_pipeline.storage import LocalBlobStore

    store = BatchStore(DraftStore("mrk", LocalBlobStore(tmp_path)), "run1")
    return BatchReplayRunner(load_settings(), standard or FakeRunner(), store), store


def ask(runner: BatchReplayRunner, stage: str = "generate") -> Any:
    return asyncio.run(runner.parse(stage, [{"type": "text", "text": "S"}], "U", Out,
                                    section_id="mrk-1-1", call="extract"))  # fmt: skip


def pending(runner: BatchReplayRunner) -> PendingCall:
    with pytest.raises(AwaitingBatch) as e:
        ask(runner)
    return e.value.call


def test_a_call_waits_then_is_answered_from_the_store_at_batch_price(tmp_path: Path) -> None:
    runner, store = replay(tmp_path)
    call = pending(runner)
    assert call.what == "generate.extract" and "fallbacks" not in call.params
    assert call.params["output_config"]["format"]["type"] == "json_schema"
    store.save_answers([Answer(custom_id=call.custom_id, type="succeeded", model="m",
                               stop_reason="end_turn", text='{"summary": "ok"}',
                               usage={"input_tokens": 10})])  # fmt: skip
    out, usage = ask(runner)
    assert out.summary == "ok" and usage.batch and usage.input_tokens == 10


def test_invalid_output_is_retried_as_a_new_request(tmp_path: Path) -> None:
    runner, store = replay(tmp_path)
    first = pending(runner)
    store.save_answers([Answer(custom_id=first.custom_id, type="succeeded", model="m",
                               stop_reason="end_turn", text="not json")])  # fmt: skip
    second = pending(runner)
    assert second.custom_id != first.custom_id and second.params == first.params


def test_a_refusal_or_expiry_reruns_once_on_the_standard_api(tmp_path: Path) -> None:
    standard = FakeRunner(responses={("generate.extract", "mrk-1-1"): {"summary": "standard"}})
    runner, store = replay(tmp_path, standard)
    call = pending(runner)
    store.save_answers([Answer(custom_id=call.custom_id, type="succeeded", model="m",
                               stop_reason="refusal")])  # fmt: skip
    out, usage = ask(runner)
    assert out.summary == "standard" and not usage.batch
    assert standard.calls == [("generate.extract", "mrk-1-1")]
    store.save_answers([Answer(custom_id=call.custom_id, type="expired")])
    assert ask(runner)[0].summary == "standard"


def test_a_rejected_request_fails_the_section(tmp_path: Path) -> None:
    runner, store = replay(tmp_path)
    call = pending(runner)
    store.save_answers([Answer(custom_id=call.custom_id, type="errored",
                               error_type="invalid_request", error="bad schema")])  # fmt: skip
    with pytest.raises(ModelError, match="bad schema"):
        ask(runner)


def test_stages_not_marked_batch_call_the_standard_api(tmp_path: Path) -> None:
    standard = FakeRunner(responses={("summaries.extract", "mrk-1-1"): {"summary": "now"}})
    runner, _store = replay(tmp_path, standard)
    assert ask(runner, "summaries")[0].summary == "now"


def test_pending_requests_are_json(tmp_path: Path) -> None:
    runner, store = replay(tmp_path)
    call = pending(runner)
    store.write_pending("generate", call)
    assert store.read_pending("generate", "mrk-1-1") == call
    json.dumps(call.params)  # what the Batches API receives


# --- replays must be deterministic (2026-11-20: intro rewrote itself every round) ---


class Text(BaseModel):
    summary: str


class TwoCalls:
    """Like intro and generate: a first call whose answer feeds the second."""

    def __init__(self, name: str, first: str, second: str, salt: Any = None) -> None:
        self.name, self.first, self.second, self.salt = name, first, second, salt
        self.always_run = False

    def prompt_version(self, deps: Deps) -> str:
        return "v1"

    def model(self, deps: Deps) -> str | None:
        return deps.settings.stage(self.second).model

    def costs_nothing(self, *_a: Any) -> bool:
        return False

    def applies_to(self, *_a: Any) -> bool:
        return True

    def inputs(self, section_id: str, draft: Any, deps: Deps) -> Any:
        return {"s": section_id}

    async def execute(self, section_id: str, inputs: Any, draft: Any, deps: Deps) -> Any:
        from thinkbible_pipeline.stages.base import SectionResult

        a, u1 = await deps.runner.parse(self.first, [], f"write {section_id}", Text,
                                        section_id=section_id, call="write")  # fmt: skip
        extra = self.salt() if self.salt else ""
        b, u2 = await deps.runner.parse(self.second, [], f"grade {a.summary}{extra}", Text,
                                        section_id=section_id, call="grade")  # fmt: skip
        draft.summary = b.summary
        return SectionResult(usages=[u1, u2])


def two_call_deps(
    tmp_path: Path, make_library: Any, stage: Any
) -> tuple[Deps, FakeRunner, FakeBatchClient]:
    from thinkbible_pipeline.stages import registry

    deps, _scripted = make(tmp_path, make_library)
    asyncio.run(run(RunRequest(book="mark", stages=["sections"]), deps))
    counter = iter(range(1000))

    class Fresh(FakeRunner):
        async def parse(self, stage: str, *a: Any, **kw: Any) -> Any:  # a new draw every call
            self.calls.append((stage, kw["section_id"]))
            return Text(summary=f"draft {next(counter)}"), self.usage

    standard = Fresh()
    fake = FakeBatchClient(respond=lambda call: {"summary": "graded"})
    deps.runner_factory = lambda: standard
    deps.batch_client_factory = lambda: fake
    deps.stages = {**registry(), stage.name: stage}
    deps.__dict__.pop("runner", None)
    return deps, standard, fake


def test_a_refusal_fallback_is_made_once_and_replayed(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first call is refused in the batch and re-run on the standard API, which answers
    # differently every time. Its answer feeds the second call, so unless the fallback is
    # remembered, every replay asks a new second question and the stage never settles.
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    stage = TwoCalls("review", first="review", second="review")
    deps, standard, fake = two_call_deps(tmp_path, make_library, stage)
    fake.respond = lambda call: (
        Answer(custom_id="", type="succeeded", stop_reason="refusal")
        if call.what == "review.write"
        else {"summary": "graded"}
    )
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"], batch=True), deps))
    n = len(deps.store.section_ids())
    assert result.stages[0].done == n, result.stages
    assert [sorted({c.what for c in v}) for v in fake.batches.values()] == [
        ["review.write"], ["review.grade"]
    ]  # fmt: skip
    assert len(fake.batches["msgbatch_2"]) == n  # each section's grade asks about its own draft
    assert len(standard.calls) == n  # each fallback made once, then remembered


def test_a_stage_not_marked_batch_makes_only_standard_calls(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    stage = TwoCalls("intro", first="intro", second="review")  # intro grades with review's model
    deps, standard, fake = two_call_deps(tmp_path, make_library, stage)
    result = asyncio.run(run(RunRequest(book="mark", stages=["intro"], batch=True), deps))
    assert result.stages[0].done == len(deps.store.section_ids())
    assert fake.batches == {} and len(standard.calls) == 2 * len(deps.store.section_ids())


def test_a_stage_that_never_settles_fails_after_the_round_limit(
    tmp_path: Path, make_library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uuid

    from thinkbible_pipeline.llm.batch import MAX_ROUNDS

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    stage = TwoCalls(
        "review", first="summaries", second="review", salt=lambda: uuid.uuid4().hex
    )  # a request that differs on every replay
    deps, _standard, fake = two_call_deps(tmp_path, make_library, stage)
    result = asyncio.run(run(RunRequest(book="mark", stages=["review"], batch=True), deps))
    review = result.stages[0]
    assert review.failed == len(deps.store.section_ids()) and review.done == 0
    assert len(fake.batches) == MAX_ROUNDS
    assert all("batch rounds" in e for e in review.failures.values())


def test_a_failed_section_still_counts_what_it_spent(tmp_path: Path, make_library: Any) -> None:
    from thinkbible_pipeline.llm.runner import Usage
    from thinkbible_pipeline.stages import registry

    deps, _scripted = make(tmp_path, make_library)
    asyncio.run(run(RunRequest(book="mark", stages=["sections"]), deps))
    ids = deps.store.section_ids()
    paid = Usage(model="claude-haiku-5-5", output_tokens=100_000)
    runner = FakeRunner(usage=paid, responses={
        **{("summaries.write", s): {"summary": "draft"} for s in ids},
        **{("summaries.grade", s): ModelError("boom") for s in ids},
    })  # fmt: skip
    deps.runner_factory = lambda: runner
    deps.stages = {**registry(), "summaries": TwoCalls("summaries", "summaries", "summaries")}
    deps.__dict__.pop("runner", None)
    result = asyncio.run(run(RunRequest(book="mark", stages=["summaries"], cap_usd=100), deps))
    stage = result.stages[0]
    assert stage.failed == len(ids) and stage.done == 0
    assert stage.spent_usd > 0  # the first call of each section was paid for
    record = deps.store.read_draft_or_new(ids[0]).stages["summaries"]
    assert record.status == "failed" and record.cost_usd > 0

    # And that spend counts toward the cap: with the default (twice the tiny estimate), the run
    # stops after the first failed section instead of spending on the rest unseen.
    deps2, _ = make(tmp_path / "again", make_library)
    asyncio.run(run(RunRequest(book="mark", stages=["sections"]), deps2))
    deps2.runner_factory = lambda: runner
    deps2.stages = deps.stages
    capped = asyncio.run(run(RunRequest(book="mark", stages=["summaries"]), deps2)).stages[0]
    assert capped.stopped_by == "cap" and capped.failed == 1
