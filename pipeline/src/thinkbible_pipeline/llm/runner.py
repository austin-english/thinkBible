"""Model calls behind one interface (research R6).

``BedrockRunner`` calls Claude in Amazon Bedrock through the Anthropic SDK's Mantle client with
structured output. ``FakeRunner`` replays recorded outputs for tests; tests never call models.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

import anthropic
from anthropic import AsyncAnthropicBedrockMantle, BetaRefusalFallbackMiddleware
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
    ) -> tuple[T, Usage]: ...


def assert_no_tools(params: Mapping[str, Any]) -> None:
    bad = [k for k in FORBIDDEN_REQUEST_KEYS if k in params]
    if bad:
        raise ForbiddenRequest(f"model requests must not include {bad} (constitution II)")


class BedrockRunner:
    """On-demand Bedrock calls with structured output, prompt caching and refusal fallback."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        # Bedrock has no server-side `fallbacks`: the SDK middleware retries a refused request on
        # the fallback model (research R6). It only handles `client.beta.messages` requests.
        self._client = client or AsyncAnthropicBedrockMantle(
            aws_region=settings.region,
            middleware=[
                BetaRefusalFallbackMiddleware([{"model": settings.refusal_fallback_model}])
            ],
        )

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
            # Thinking is adaptive and always on for these models; effort sets its depth.
            "output_config": {"effort": cfg.effort},
        }
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
    ) -> tuple[T, Usage]:
        params = self.build_request(stage, system, user)
        last_error = "no attempt made"
        attempts = self._settings.invalid_output_retries + 1
        for _ in range(attempts):
            try:
                resp = await self._client.beta.messages.parse(**params, output_format=output_model)
            except (ValidationError, json.JSONDecodeError) as e:
                last_error = f"invalid structured output: {e}"
                continue
            except anthropic.APIError as e:
                raise ModelError(f"{section_id}: {type(e).__name__}: {e}") from e
            if resp.stop_reason == "refusal":
                category = resp.stop_details.category if resp.stop_details else None
                raise Refused(category, resp.model)
            if resp.stop_reason == "max_tokens":
                last_error = f"hit max_tokens ({self._settings.max_tokens})"
                continue
            parsed = resp.parsed_output
            if parsed is None:
                last_error = "no parsed output"
                continue
            return parsed, Usage.from_api(resp.model, resp.usage)
        raise InvalidOutput(f"{section_id} {stage}: {last_error} after {attempts} attempts")


@dataclass
class FakeRunner:
    """Replays outputs from ``{fixtures}/{stage}/{section_id}.json`` or ``responses``.

    A response that is an ``Exception`` is raised instead, to test failures. ``calls`` records every
    request so tests can assert how many model calls were made.
    """

    fixtures_dir: Path | None = None
    responses: dict[tuple[str, str], Any] = field(default_factory=dict)
    usage: Usage = field(default_factory=lambda: Usage(model="fake"))
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def parse(
        self,
        stage: str,
        system: Sequence[BetaTextBlockParam],
        user: str,
        output_model: type[T],
        *,
        section_id: str,
    ) -> tuple[T, Usage]:
        self.calls.append((stage, section_id))
        key = (stage, section_id)
        if key in self.responses:
            value = self.responses[key]
        elif self.fixtures_dir is not None:
            path = self.fixtures_dir / stage / f"{section_id}.json"
            if not path.is_file():
                raise ModelError(f"no recorded output at {path}")
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            raise ModelError(f"no recorded output for {key}")
        if isinstance(value, Exception):
            raise value
        return output_model.model_validate(value), self.usage
