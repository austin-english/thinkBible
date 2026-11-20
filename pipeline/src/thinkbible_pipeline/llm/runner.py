"""Model calls behind one interface (research R6).

``BedrockRunner`` calls Claude through the Anthropic SDK with structured output: in Amazon Bedrock
(the ``bedrock-runtime`` endpoint by default, ``bedrock-mantle`` if settings say so), or the Claude
API directly (endpoint ``anthropic``, e.g. the ``anthropic`` settings profile for the 5.5 models).
``FakeRunner`` replays recorded outputs for tests; tests never call models.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

import anthropic
from anthropic import (
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicBedrockMantle,
    BetaRefusalFallbackMiddleware,
)
from anthropic.types.beta import BetaTextBlockParam, BetaUsage
from pydantic import BaseModel, TypeAdapter, ValidationError

from thinkbible_pipeline.config import Settings

T = TypeVar("T", bound=BaseModel)

# The Claude API's server-side refusal fallback: a declined request is re-run on a fallback model
# chosen by the refusal category, inside the same call (Bedrock uses the SDK middleware instead).
SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Keys a request must never carry (constitution II: models get no tools or retrieval).
FORBIDDEN_REQUEST_KEYS = ("tools", "tool_choice", "mcp_servers", "container")


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    batch: bool = False  # answered by the Message Batches API: priced at half (T087)

    @property
    def cache_write_tokens(self) -> int:
        return self.cache_write_5m_tokens + self.cache_write_1h_tokens

    @property
    def is_empty(self) -> bool:
        return (
            not (self.input_tokens or self.output_tokens or self.cache_read_tokens)
            and not self.cache_write_tokens
        )

    @classmethod
    def from_api(cls, model: str, u: BetaUsage) -> Usage:
        return cls.from_dict(model, u.model_dump())

    @classmethod
    def from_dict(cls, model: str, u: Mapping[str, Any], *, batch: bool = False) -> Usage:
        """From a response's ``usage`` as JSON (a batch result is stored that way)."""
        five = one = 0
        cache = u.get("cache_creation")
        if cache:
            five = int(cache.get("ephemeral_5m_input_tokens") or 0)
            one = int(cache.get("ephemeral_1h_input_tokens") or 0)
        else:
            five = int(u.get("cache_creation_input_tokens") or 0)
        return cls(
            model=model,
            input_tokens=int(u.get("input_tokens") or 0),
            output_tokens=int(u.get("output_tokens") or 0),
            cache_read_tokens=int(u.get("cache_read_input_tokens") or 0),
            cache_write_5m_tokens=five,
            cache_write_1h_tokens=one,
            batch=batch,
        )


class ModelError(Exception):
    """A model call failed for this section. The stage runner marks the section failed."""


class OutOfCredit(ModelError):
    """The Claude API account is out of credit (2026-11-19). No retry or other section can
    succeed, so the run stops: sections already running finish, no new ones start, and the
    refused section is left as it was for the next run."""


OUT_OF_CREDIT = (
    "out of Claude API credit: add credit in the Claude Console (Plans & Billing), then run again"
)


class Throttled(ModelError):
    """Bedrock is throttling or overloaded (429/503/529) even after the SDK's own retries.

    Unlike other model errors it isn't recorded as a failed section: in the cloud the Lambda lets
    it escape so Step Functions retries the section with backoff (research R7).
    """


THROTTLE_STATUS = frozenset({429, 503, 529})


class Refused(ModelError):
    """Every model in the chain declined (``stop_reason == "refusal"``)."""

    def __init__(self, category: str | None, model: str) -> None:
        super().__init__(f"{model} declined the request (category: {category or 'unknown'})")
        self.category = category
        self.model = model


class InvalidOutput(ModelError):
    """Structured output still failed validation after the allowed retries."""


class ForbiddenRequest(AssertionError):
    pass


class ModelRunner(Protocol):
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
        """One structured call. ``stage`` picks the model and settings; ``call`` names the call
        when a stage makes more than one (``generate``: ``extract``, then ``questions``)."""
        ...


def assert_no_tools(params: Mapping[str, Any]) -> None:
    bad = [k for k in FORBIDDEN_REQUEST_KEYS if k in params]
    if bad:
        raise ForbiddenRequest(f"model requests must not include {bad} (constitution II)")


def anthropic_api_key(settings: Settings) -> str:
    """The Claude API key: ``ANTHROPIC_API_KEY`` if set, else the SSM SecureString named in
    settings (``api_key_parameter``), read with the caller's AWS credentials. Never logged."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if not settings.api_key_parameter:
        raise ModelError("the anthropic endpoint needs api_key_parameter in settings.toml")
    import boto3

    ssm = boto3.client("ssm", region_name=settings.region)
    try:
        value = ssm.get_parameter(Name=settings.api_key_parameter, WithDecryption=True)
    except Exception as e:  # report which parameter failed, never the value
        raise ModelError(
            f"couldn't read the API key from SSM parameter {settings.api_key_parameter!r}: "
            f"{type(e).__name__}"
        ) from e
    return str(value["Parameter"]["Value"])


class RateLimiter:
    """At most ``per_minute`` request starts in any 60 seconds (a sliding window)."""

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._starts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                while self._starts and now - self._starts[0] >= 60:
                    self._starts.popleft()
                if len(self._starts) < self.per_minute:
                    self._starts.append(now)
                    return
                await self._sleep(60 - (now - self._starts[0]) + 0.1)


def throttle_backoff(attempt: int) -> float:
    """Seconds to wait before retry ``attempt`` (0-based): 10, 20, 40, 60, 60…, with jitter."""
    base: float = min(60.0, 10.0 * float(2**attempt))
    return base * random.uniform(0.9, 1.1)


def build_request(
    settings: Settings,
    stage: str,
    system: Sequence[BetaTextBlockParam],
    user: str,
    *,
    batch: bool = False,
) -> dict[str, Any]:
    """A stage's request body, without the output format. A batch request carries no
    ``fallbacks`` (the Batches API refuses it): a refusal is re-run on the standard API."""
    cfg = settings.stage(stage)
    blocks: list[BetaTextBlockParam] = [dict(b) for b in system]  # type: ignore[misc]
    if blocks:
        # Cache the stable prefix (shared context + stage prompt + guide). Per-section
        # content goes in the user turn, after the breakpoint.
        blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    params: dict[str, Any] = {
        "model": cfg.model,
        "max_tokens": settings.max_tokens,
        "system": blocks,
        "messages": [{"role": "user", "content": user}],
    }
    # Per model (settings.toml): Claude 4.6 needs adaptive thinking turned on explicitly
    # (5.5 has it always on); Haiku 4.5 rejects an effort setting, so it gets neither.
    if cfg.thinking == "adaptive":
        params["thinking"] = {"type": "adaptive"}
    if cfg.effort is not None:
        params["output_config"] = {"effort": cfg.effort}
    if settings.endpoint == "anthropic" and not batch:
        params["betas"] = [SERVER_SIDE_FALLBACK_BETA]
        params["fallbacks"] = "default"
    assert_no_tools(params)
    return params


def output_format(output_model: type[BaseModel]) -> dict[str, Any]:
    """``output_config.format`` for ``output_model``, built the way the SDK's ``parse`` builds it
    (a batch request has no ``parse`` helper, so it carries the schema itself)."""
    schema = TypeAdapter(output_model).json_schema()
    return {"type": "json_schema", "schema": anthropic.transform_schema(schema)}


class BedrockRunner:
    """On-demand Bedrock calls with structured output, prompt caching and refusal fallback.

    Requests are paced per model to the account's requests-per-minute quota
    (``requests_per_minute`` in settings.toml), and a throttled request is retried with backoff
    (``throttle_retries``) before ``Throttled`` is raised. In the cloud each Lambda paces only
    itself; Step Functions retries what still comes back throttled.
    """

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._client = client or self._make_client(settings)
        self._sleep = sleep
        self._limiters: dict[str, RateLimiter | None] = {}

    def _limiter(self, stage: str) -> RateLimiter | None:
        cfg = self._settings.stage(stage)
        if cfg.model not in self._limiters:
            # Stages sharing a model share its quota: use the lowest any of them sets.
            rpms = [
                s.requests_per_minute
                for s in self._settings.stages.values()
                if s.model == cfg.model and s.requests_per_minute
            ]
            self._limiters[cfg.model] = RateLimiter(min(rpms), sleep=self._sleep) if rpms else None
        return self._limiters[cfg.model]

    @staticmethod
    def _make_client(settings: Settings) -> Any:
        if settings.endpoint == "anthropic":
            return AsyncAnthropic(api_key=anthropic_api_key(settings))
        # Bedrock has no server-side `fallbacks`: the SDK middleware retries a refused request on
        # the fallback model (research R6). It only handles `client.beta.messages` requests.
        # `betas=[]` keeps it from sending the fallback-credit beta header, which Bedrock may not
        # accept for every model; a retry simply pays full price.
        fallback = BetaRefusalFallbackMiddleware(
            [{"model": settings.refusal_fallback_model}], betas=[]
        )
        if settings.endpoint == "mantle":
            return AsyncAnthropicBedrockMantle(aws_region=settings.region, middleware=[fallback])
        # bedrock-runtime: AWS's recommended endpoint, and the one this account can use (R6).
        return AsyncAnthropicBedrock(aws_region=settings.region, middleware=[fallback])

    def build_request(
        self, stage: str, system: Sequence[BetaTextBlockParam], user: str
    ) -> dict[str, Any]:
        """The request body, without ``output_format``. Pure, so tests can inspect it."""
        return build_request(self._settings, stage, system, user)

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
        params = self.build_request(stage, system, user)
        what = f"{stage}.{call}" if call else stage
        last_error = "no attempt made"
        attempts = self._settings.invalid_output_retries + 1
        limiter = self._limiter(stage)
        attempt = throttled = 0
        while attempt < attempts:
            if limiter is not None:
                await limiter.wait()
            try:
                resp = await self._client.beta.messages.parse(**params, output_format=output_model)
            except (ValidationError, json.JSONDecodeError) as e:
                last_error = f"invalid structured output: {e}"
                attempt += 1
                continue
            except anthropic.APIStatusError as e:
                if e.status_code in THROTTLE_STATUS:
                    if throttled < self._settings.throttle_retries:
                        await self._sleep(throttle_backoff(throttled))
                        throttled += 1
                        continue
                    raise Throttled(
                        f"{section_id}: {e.status_code} after {throttled} retries: {e}"
                    ) from e
                if "credit balance is too low" in str(e):
                    raise OutOfCredit(OUT_OF_CREDIT) from e
                raise ModelError(f"{section_id}: {type(e).__name__}: {e}") from e
            except anthropic.APIError as e:
                raise ModelError(f"{section_id}: {type(e).__name__}: {e}") from e
            if resp.stop_reason == "refusal":
                category = resp.stop_details.category if resp.stop_details else None
                raise Refused(category, resp.model)
            if resp.stop_reason == "max_tokens":
                last_error = f"hit max_tokens ({self._settings.max_tokens})"
                attempt += 1
                continue
            parsed = resp.parsed_output
            if parsed is None:
                last_error = "no parsed output"
                attempt += 1
                continue
            return parsed, Usage.from_api(resp.model, resp.usage)
        raise InvalidOutput(f"{section_id} {what}: {last_error} after {attempts} attempts")


@dataclass
class FakeRunner:
    """Replays outputs from ``{fixtures}/{stage}/{section_id}.json`` or ``responses``.

    Keys are ``(stage, section_id)``, or ``("stage.call", section_id)`` for a named call (so
    ``("generate.extract", "mrk-1-1")`` and fixtures in ``generate.extract/``). A response that is
    an ``Exception`` is raised instead, to test failures; a ``list`` is replayed one item per call,
    to test regeneration. ``calls`` records every request so tests can count model calls, and
    ``prompts`` the user turn of each.
    """

    fixtures_dir: Path | None = None
    responses: dict[tuple[str, str], Any] = field(default_factory=dict)
    usage: Usage = field(default_factory=lambda: Usage(model="fake"))
    calls: list[tuple[str, str]] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

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
        name = f"{stage}.{call}" if call else stage
        self.calls.append((name, section_id))
        self.prompts.append(user)
        key = (name, section_id)
        if key in self.responses:
            value = self.responses[key]
            if isinstance(value, list):
                if not value:
                    raise ModelError(f"no more recorded outputs for {key}")
                value = value.pop(0)
        elif self.fixtures_dir is not None:
            path = self.fixtures_dir / name / f"{section_id}.json"
            if not path.is_file():
                raise ModelError(f"no recorded output at {path}")
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            raise ModelError(f"no recorded output for {key}")
        if isinstance(value, Exception):
            raise value
        return output_model.model_validate(value), self.usage
