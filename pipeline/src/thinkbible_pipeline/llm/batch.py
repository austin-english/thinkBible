"""Claude Message Batches for cloud runs (T087): every token at half price, results usually
within the hour (at most 24 hours).

**Replay in rounds.** The stages don't change. In a batch run, ``BatchReplayRunner`` stands in
for the runner:

1. Each section of a stage runs from the start. Every model call of a batch stage looks up its
   answer in the run's answer store (``{book}/batches/{runId}/answers/``), keyed by the exact
   request and the attempt number. A call with no answer yet raises ``AwaitingBatch``: the
   section stops there, its draft is **not** written, and the request is saved as pending.
2. ``submit_round`` sends every waiting section's pending request as one batch.
3. ``collect_round`` polls it (the state machine waits between polls; no Lambda stays open)
   and saves the answers once it has ended.
4. The waiting sections run again from the start. Replays are deterministic (same draft, same
   sources, same prompts, same answers), so each now gets past that call and either finishes,
   writing its draft as usual, or stops at its next call. When none waits, the stage is done.

A stage with two calls in a row (``generate``: key ideas, then questions) takes two rounds; an
invalid answer is retried as one more round. Stages not marked ``batch`` in settings.toml call
the standard API as usual.

**Every call is remembered.** Replaying is only deterministic if every call before the waiting
one gives the same answer again, and a fresh model call doesn't (``intro`` once rewrote its
introduction on every replay, so its graded text, and the grading request, changed each round:
2026-11-20). So in a batch run the standard calls are stored too, keyed by their request and how
many times the section has made that request so far, and a replay reuses them: nothing is paid
twice. Batching follows the stage that is running (``replay_scope``): a stage not marked
``batch`` makes only standard calls, whichever model settings it borrows. A stage still waiting
after ``MAX_ROUNDS`` fails its waiting sections rather than looping.

**What a batch can't do**: carry ``fallbacks``. A refused request, and one the batch failed for
a temporary reason (a server error, expired, canceled), is re-run once on the standard API, which
falls back server-side. A request the batch rejected as invalid fails the section.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar, cast

import anthropic
from anthropic.types import TextBlock
from anthropic.types.beta import BetaTextBlockParam
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages import MessageBatchErroredResult, MessageBatchSucceededResult
from anthropic.types.messages.batch_create_params import Request
from pydantic import BaseModel, Field, ValidationError

from thinkbible_pipeline.config import Settings
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.jsonio import JsonModel, compact_canonical, sha256_hex
from thinkbible_pipeline.llm.runner import (
    OUT_OF_CREDIT,
    THROTTLE_STATUS,
    InvalidOutput,
    ModelError,
    ModelRunner,
    OutOfCredit,
    Throttled,
    Usage,
    anthropic_api_key,
    build_request,
    output_format,
)

T = TypeVar("T", bound=BaseModel)

# Seconds between polls: in the cloud the state machine's Wait state (Terraform
# `batch_poll_seconds`), locally `run --local --batch`.
LOCAL_POLL_SECONDS = 60.0
# A stage needs 1-3 rounds (generate: key ideas, questions, a retry). More means no progress.
MAX_ROUNDS = 8


class PendingCall(JsonModel):
    """A request a section is waiting on."""

    custom_id: str
    section_id: str
    what: str  # "generate.extract", "review", … (for logs and the fake client)
    params: dict[str, Any]


class Answer(JsonModel):
    """One batch result, as stored."""

    custom_id: str
    type: Literal["succeeded", "errored", "canceled", "expired"]
    model: str | None = None
    stop_reason: str | None = None
    text: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None  # "errored": invalid_request, api_error, overloaded_error, …
    error: str | None = None


class AwaitingBatch(Exception):  # a pause, not an error
    """The section needs an answer the batch hasn't given yet: it stops here, unwritten."""

    def __init__(self, call: PendingCall) -> None:
        super().__init__(f"{call.section_id}: waiting for {call.what}")
        self.call = call


def custom_id(params: dict[str, Any], attempt: int, occurrence: int = 0) -> str:
    """The request's key: the same request, attempt and occurrence (the how-many-th time this
    section's run of the stage makes this request) always get the same ID. At most 64
    characters: letters, digits, ``_`` and ``-``."""
    key = {"params": params, "attempt": attempt, "occurrence": occurrence}
    return "r" + sha256_hex(compact_canonical(key))[:63]


@dataclass
class _Replay:
    stage: str
    seen: dict[str, int] = field(default_factory=dict)

    def occurrence(self, params: dict[str, Any]) -> int:
        base = sha256_hex(compact_canonical(params))
        n = self.seen.get(base, 0)
        self.seen[base] = n + 1
        return n


_REPLAY: ContextVar[_Replay | None] = ContextVar("thinkbible_replay", default=None)


@contextmanager
def replay_scope(stage: str) -> Iterator[None]:
    """One run of ``stage`` for one section: which stage is running (so its calls are batched
    or not) and how many times each request has been made so far."""
    token = _REPLAY.set(_Replay(stage))
    try:
        yield
    finally:
        _REPLAY.reset(token)


def _usage_json(u: Usage) -> dict[str, Any]:
    return {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": u.cache_read_tokens,
        "cache_creation": {
            "ephemeral_5m_input_tokens": u.cache_write_5m_tokens,
            "ephemeral_1h_input_tokens": u.cache_write_1h_tokens,
        },
    }


class BatchStore:
    """A run's pending requests and answers, next to the drafts: ``{book}/batches/{runId}/``."""

    def __init__(self, store: DraftStore, run_id: str) -> None:
        self._store = store
        self._prefix = f"batches/{run_id}"

    def answer(self, cid: str) -> Answer | None:
        text = self._store.read_text(f"{self._prefix}/answers/{cid}.json")
        return Answer.model_validate_json(text) if text is not None else None

    def save_answers(self, answers: Sequence[Answer]) -> None:
        for a in answers:
            self._store.write_text(
                f"{self._prefix}/answers/{a.custom_id}.json",
                json.dumps(a.to_doc()),
                "application/json",
            )

    def write_pending(self, stage: str, call: PendingCall) -> None:
        self._store.write_text(
            f"{self._prefix}/pending/{stage}/{call.section_id}.json",
            json.dumps(call.to_doc()),
            "application/json",
        )

    def read_pending(self, stage: str, section_id: str) -> PendingCall | None:
        text = self._store.read_text(f"{self._prefix}/pending/{stage}/{section_id}.json")
        return PendingCall.model_validate_json(text) if text is not None else None


class BatchReplayRunner:
    """The runner in a batch run: answers from the store, or a pause (see the module docstring).
    Calls of stages not marked ``batch`` go to ``standard``."""

    def __init__(self, settings: Settings, standard: ModelRunner, store: BatchStore) -> None:
        self._settings = settings
        self._standard = standard
        self._store = store

    async def parse(
        self,
        stage: str,
        system: Sequence[BetaTextBlockParam],
        user: str,
        output_model: type[T],
        *,
        section_id: str,
        call: str | None = None,
    ) -> tuple[T, Usage]:
        scope = _REPLAY.get()
        running = scope.stage if scope is not None else stage
        if not (running in self._settings.stages and self._settings.stages[running].batch):
            return await self._remembered(stage, system, user, output_model, section_id, call)
        what = f"{stage}.{call}" if call else stage
        params = build_request(self._settings, stage, system, user, batch=True)
        params["output_config"] = {
            **params.get("output_config", {}),
            "format": output_format(output_model),
        }
        occurrence = scope.occurrence(params) if scope is not None else 0
        attempts = self._settings.invalid_output_retries + 1
        last_error = "no attempt made"
        for attempt in range(attempts):
            cid = custom_id(params, attempt, occurrence)
            answer = self._store.answer(cid)
            if answer is None:
                raise AwaitingBatch(
                    PendingCall(custom_id=cid, section_id=section_id, what=what, params=params)
                )
            if answer.type == "errored" and answer.error_type == "invalid_request":
                raise ModelError(f"{section_id} {what}: the batch rejected the request: "
                                 f"{answer.error}")  # fmt: skip
            if answer.type != "succeeded" or answer.stop_reason == "refusal":
                # No `fallbacks` in a batch: once more on the standard API, which falls back.
                return await self._remembered(stage, system, user, output_model, section_id, call)
            if answer.stop_reason == "max_tokens":
                last_error = f"hit max_tokens ({self._settings.max_tokens})"
                continue
            try:
                parsed = output_model.model_validate_json(answer.text or "")
            except ValidationError as e:
                last_error = f"invalid structured output: {e}"
                continue
            return parsed, Usage.from_dict(answer.model or params["model"], answer.usage,
                                           batch=True)  # fmt: skip
        raise InvalidOutput(f"{section_id} {what}: {last_error} after {attempts} attempts")

    async def _remembered(
        self,
        stage: str,
        system: Sequence[BetaTextBlockParam],
        user: str,
        output_model: type[T],
        section_id: str,
        call: str | None,
    ) -> tuple[T, Usage]:
        """A standard call, made once per run: a replay gets the stored answer back."""
        params = build_request(self._settings, stage, system, user)
        key = {"standard": params, "output": output_model.__name__}
        scope = _REPLAY.get()
        cid = custom_id(key, 0, scope.occurrence(key) if scope is not None else 0)
        stored = self._store.answer(cid)
        if stored is not None and stored.text is not None:
            usage = Usage.from_dict(stored.model or params["model"], stored.usage)
            return output_model.model_validate_json(stored.text), usage
        out, usage = await self._standard.parse(
            stage, system, user, output_model, section_id=section_id, call=call
        )
        self._store.save_answers([Answer(
            custom_id=cid, type="succeeded", model=usage.model, stop_reason="end_turn",
            text=out.model_dump_json(by_alias=True), usage=_usage_json(usage),
        )])  # fmt: skip
        return out, usage


# --- the Batches API ---


class BatchClient(Protocol):
    async def submit(self, calls: Sequence[PendingCall]) -> str:
        """Send the requests as one batch; returns its ID."""
        ...

    async def ended(self, batch_id: str) -> bool:
        """Whether the batch has finished processing (every request answered or expired)."""
        ...

    async def results(self, batch_id: str) -> list[Answer]: ...


def _api_error(e: anthropic.APIStatusError, what: str) -> ModelError:
    if "credit balance is too low" in str(e):
        return OutOfCredit(OUT_OF_CREDIT)
    if e.status_code in THROTTLE_STATUS:
        return Throttled(f"{what}: {e.status_code}: {e}")
    return ModelError(f"{what}: {type(e).__name__}: {e}")


class AnthropicBatchClient:
    """The Claude API's Message Batches (``client.messages.batches``)."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=anthropic_api_key(settings))

    async def submit(self, calls: Sequence[PendingCall]) -> str:
        requests = [
            Request(custom_id=c.custom_id, params=cast(MessageCreateParamsNonStreaming, c.params))
            for c in calls
        ]
        try:
            batch = await self._client.messages.batches.create(requests=requests)
        except anthropic.APIStatusError as e:
            raise _api_error(e, "submitting a batch") from e
        return str(batch.id)

    async def ended(self, batch_id: str) -> bool:
        try:
            batch = await self._client.messages.batches.retrieve(batch_id)
        except anthropic.APIStatusError as e:
            raise _api_error(e, f"checking batch {batch_id}") from e
        return bool(batch.processing_status == "ended")

    async def results(self, batch_id: str) -> list[Answer]:
        out: list[Answer] = []
        async for item in await self._client.messages.batches.results(batch_id):
            result = item.result
            if isinstance(result, MessageBatchSucceededResult):
                msg = result.message
                text = next((b.text for b in msg.content if isinstance(b, TextBlock)), None)
                out.append(Answer(
                    custom_id=item.custom_id, type="succeeded", model=msg.model,
                    stop_reason=msg.stop_reason, text=text,
                    usage=msg.usage.model_dump(mode="json"),
                ))  # fmt: skip
            elif isinstance(result, MessageBatchErroredResult):
                err = result.error.error
                out.append(Answer(custom_id=item.custom_id, type="errored",
                                  error_type=err.type, error=err.message))  # fmt: skip
            else:
                out.append(Answer(custom_id=item.custom_id, type=result.type))
        return out


@dataclass
class FakeBatchClient:
    """For tests: answers each request with ``respond(call)``, which returns the output as a dict
    (a succeeded answer), an ``Answer`` (to test refusals and errors) or raises. A batch ends after
    ``polls`` checks."""

    respond: Callable[[PendingCall], Any]  # a dict or Answer, or an awaitable of one
    polls: int = 0
    usage: dict[str, Any] = field(default_factory=lambda: {"input_tokens": 1000,
                                                          "output_tokens": 200})  # fmt: skip
    batches: dict[str, list[PendingCall]] = field(default_factory=dict)
    _checks: dict[str, int] = field(default_factory=dict)

    async def submit(self, calls: Sequence[PendingCall]) -> str:
        batch_id = f"msgbatch_{len(self.batches) + 1}"
        self.batches[batch_id] = list(calls)
        return batch_id

    async def ended(self, batch_id: str) -> bool:
        self._checks[batch_id] = self._checks.get(batch_id, 0) + 1
        return self._checks[batch_id] > self.polls

    async def results(self, batch_id: str) -> list[Answer]:
        out: list[Answer] = []
        for call in self.batches[batch_id]:
            value = self.respond(call)
            if inspect.isawaitable(value):
                value = await value
            if isinstance(value, Answer):
                out.append(value.model_copy(update={"custom_id": call.custom_id}))
                continue
            out.append(Answer(custom_id=call.custom_id, type="succeeded",
                              model=call.params["model"], stop_reason="end_turn",
                              text=json.dumps(value), usage=self.usage))  # fmt: skip
        return out


# --- one round ---


@dataclass
class BatchContext:
    """Set on ``Deps`` for a batch run: the run's ID (it keys the stored answers) and the client."""

    run_id: str
    client_factory: Callable[[], BatchClient]
    poll_seconds: float = LOCAL_POLL_SECONDS
    _client: BatchClient | None = None

    @property
    def client(self) -> BatchClient:
        if self._client is None:
            self._client = self.client_factory()
        return self._client


async def submit_round(
    stage: str, waiting: Sequence[str], store: DraftStore, ctx: BatchContext
) -> tuple[str | None, list[str]]:
    """Send the waiting sections' requests as one batch. Returns its ID and the sections that
    had no pending request (they can't continue; the caller marks them failed)."""
    batches = BatchStore(store, ctx.run_id)
    calls: dict[str, PendingCall] = {}
    missing: list[str] = []
    for sid in waiting:
        call = batches.read_pending(stage, sid)
        if call is None:
            missing.append(sid)
        else:
            calls.setdefault(call.custom_id, call)  # identical requests share one answer
    if not calls:
        return None, missing
    return await ctx.client.submit(list(calls.values())), missing


async def collect_round(batch_id: str, store: DraftStore, ctx: BatchContext) -> bool:
    """If the batch has ended, save its answers and return True."""
    if not await ctx.client.ended(batch_id):
        return False
    BatchStore(store, ctx.run_id).save_answers(await ctx.client.results(batch_id))
    return True
