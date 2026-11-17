"""Model calls behind one interface (research R6).

``BedrockRunner`` calls Claude in Amazon Bedrock through the Anthropic SDK (the ``bedrock-runtime``
endpoint by default, ``bedrock-mantle`` if settings say so) with structured output.
``FakeRunner`` replays recorded outputs for tests; tests never call models.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

import anthropic
from anthropic import (
    AsyncAnthropicBedrock,
    AsyncAnthropicBedrockMantle,
    BetaRefusalFallbackMiddleware,
)
from anthropic.types.beta import BetaTextBlockParam, BetaUsage
from pydantic import BaseModel, ValidationError

from thinkbible_pipeline.config import Settings

T = TypeVar("T", bound=BaseModel)

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
        five = one = 0
        if u.cache_creation is not None:
            five = u.cache_creation.ephemeral_5m_input_tokens
            one = u.cache_creation.ephemeral_1h_input_tokens
        else:
            five = u.cache_creation_input_tokens or 0
        return cls(
            model=model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_5m_tokens=five,
            cache_write_1h_tokens=one,
        )


class ModelError(Exception):
    """A model call failed for this section. The stage runner marks the section failed."""


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
        cfg = self._settings.stage(stage)
        blocks: list[BetaTextBlockParam] = [dict(b) for b in system]  # type: ignore[misc]
        if blocks:
            # Cache the stable prefix (shared context + stage prompt + guide). Per-section
            # content goes in the user turn, after the breakpoint.
            blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
        params: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": self._settings.max_tokens,
            "system": blocks,
            "messages": [{"role": "user", "content": user}],
        }
        # Per model (settings.toml): Claude 4.6 needs adaptive thinking turned on explicitly
        # (5.5 has it always on); Haiku 4.5 rejects an effort setting, so it gets neither.
        if cfg.thinking == "adaptive":
            params["thinking"] = {"type": "adaptive"}
        if cfg.effort is not None:
            params["output_config"] = {"effort": cfg.effort}
        assert_no_tools(params)
        return params

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
