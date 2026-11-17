"""Model requests never carry tools (constitution II); the runner handles refusals and retries."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from anthropic.types.beta import BetaUsage
from pydantic import BaseModel

from thinkbible_pipeline.config import load_settings
from thinkbible_pipeline.llm.runner import (
    FORBIDDEN_REQUEST_KEYS,
    BedrockRunner,
    ForbiddenRequest,
    InvalidOutput,
    Refused,
    assert_no_tools,
)
from thinkbible_pipeline.requests import MODEL_STAGES

SETTINGS = load_settings()
SYSTEM: list[Any] = [{"type": "text", "text": "context"}, {"type": "text", "text": "stage"}]


class Out(BaseModel):
    summary: str


def _resp(parsed: Out | None = None, stop: str = "end_turn", category: str | None = None) -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        stop_details=SimpleNamespace(category=category) if stop == "refusal" else None,
        parsed_output=parsed,
        model="anthropic.claude-haiku-5-5",
        usage=BetaUsage.model_construct(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=50,
            cache_creation_input_tokens=0,
            cache_creation=None,
        ),
    )


class FakeClient:
    """Stands in for AsyncAnthropicBedrockMantle: records kwargs, replays scripted responses."""

    def __init__(self, *responses: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.mark.parametrize("stage", sorted(MODEL_STAGES))
def test_request_for_every_stage_has_no_tools(stage: str) -> None:
    params = BedrockRunner(SETTINGS, client=FakeClient()).build_request(stage, SYSTEM, "passage")
    for key in FORBIDDEN_REQUEST_KEYS:
        assert key not in params
    cfg = SETTINGS.stage(stage)
    assert params["model"] == cfg.model
    # Thinking and effort are sent only when the stage's model takes them (settings.toml).
    if cfg.effort is None:
        assert "output_config" not in params
    else:
        assert params["output_config"] == {"effort": cfg.effort}
    if cfg.thinking == "adaptive":
        assert params["thinking"] == {"type": "adaptive"}
    else:
        assert "thinking" not in params
    # The stable prefix is cached; the per-section text is the user turn.
    assert params["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in params["system"][0]
    assert params["messages"] == [{"role": "user", "content": "passage"}]


def test_sent_request_has_no_tools_and_uses_structured_output() -> None:
    client = FakeClient(_resp(Out(summary="ok")))
    out, usage = asyncio.run(
        BedrockRunner(SETTINGS, client=client).parse(
            "summaries", SYSTEM, "passage", Out, section_id="mrk-1-1"
        )
    )
    assert out.summary == "ok"
    sent = client.calls[0]
    assert not set(FORBIDDEN_REQUEST_KEYS) & set(sent)
    assert sent["output_format"] is Out
    assert usage.input_tokens == 100 and usage.cache_read_tokens == 50


def test_assert_no_tools_rejects_tools() -> None:
    with pytest.raises(ForbiddenRequest):
        assert_no_tools({"model": "x", "tools": []})


def test_refusal_raises_with_category() -> None:
    client = FakeClient(_resp(stop="refusal", category="general_harms"))
    with pytest.raises(Refused) as e:
        asyncio.run(
            BedrockRunner(SETTINGS, client=client).parse(
                "generate", SYSTEM, "x", Out, section_id="mrk-1-1"
            )
        )
    assert e.value.category == "general_harms"


def test_invalid_output_retried_then_succeeds() -> None:
    client = FakeClient(_resp(None), _resp(stop="max_tokens"), _resp(Out(summary="third")))
    out, _ = asyncio.run(
        BedrockRunner(SETTINGS, client=client).parse(
            "summaries", SYSTEM, "x", Out, section_id="mrk-1-1"
        )
    )
    assert out.summary == "third"
    assert len(client.calls) == 3


def test_invalid_output_gives_up_after_retries() -> None:
    client = FakeClient(*[_resp(None)] * (SETTINGS.invalid_output_retries + 1))
    with pytest.raises(InvalidOutput):
        asyncio.run(
            BedrockRunner(SETTINGS, client=client).parse(
                "summaries", SYSTEM, "x", Out, section_id="mrk-1-1"
            )
        )
    assert len(client.calls) == SETTINGS.invalid_output_retries + 1


def test_client_follows_the_endpoint_setting() -> None:
    import dataclasses

    from anthropic import AsyncAnthropicBedrock, AsyncAnthropicBedrockMantle

    runtime = BedrockRunner(SETTINGS)
    assert type(runtime._client) is AsyncAnthropicBedrock
    mantle = BedrockRunner(dataclasses.replace(SETTINGS, endpoint="mantle"))
    assert type(mantle._client) is AsyncAnthropicBedrockMantle


def _throttle() -> Exception:
    """A Bedrock 429, as the SDK raises it (its response only needs these attributes here)."""
    import anthropic

    response = SimpleNamespace(status_code=429, headers={}, request=None)
    return anthropic.RateLimitError("Too many requests", response=response, body=None)  # type: ignore[arg-type]


def test_throttled_requests_are_retried_with_backoff() -> None:
    client = FakeClient(_throttle(), _throttle(), _resp(Out(summary="after waiting")))
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    out, _ = asyncio.run(
        BedrockRunner(SETTINGS, client=client, sleep=sleep).parse(
            "summaries", SYSTEM, "x", Out, section_id="mrk-1-1"
        )
    )
    assert out.summary == "after waiting" and len(client.calls) == 3
    throttle_waits = [w for w in waits if w >= 9]
    assert 9 <= throttle_waits[0] <= 11 and 18 <= throttle_waits[1] <= 22  # 10s, then 20s


def test_throttling_beyond_the_retries_raises_throttled() -> None:
    from thinkbible_pipeline.llm.runner import Throttled

    retries = SETTINGS.throttle_retries
    client = FakeClient(*[_throttle() for _ in range(retries + 1)])

    async def sleep(_seconds: float) -> None:
        return None

    with pytest.raises(Throttled, match=f"after {retries} retries"):
        asyncio.run(
            BedrockRunner(SETTINGS, client=client, sleep=sleep).parse(
                "summaries", SYSTEM, "x", Out, section_id="mrk-1-1"
            )
        )
    assert len(client.calls) == retries + 1


def test_rate_limiter_keeps_starts_within_the_quota() -> None:
    from thinkbible_pipeline.llm.runner import RateLimiter

    now = [0.0]
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(3, clock=lambda: now[0], sleep=sleep)

    async def five_requests() -> list[float]:
        starts = []
        for _ in range(5):
            await limiter.wait()
            starts.append(now[0])
            now[0] += 1  # each request takes a second to send
        return starts

    starts = asyncio.run(five_requests())
    assert starts[:3] == [0.0, 1.0, 2.0]
    assert starts[3] >= 60.0 and starts[4] >= 61.0  # the 4th waits for the 1st to age out


def test_stages_sharing_a_model_share_its_quota() -> None:
    runner = BedrockRunner(SETTINGS, client=FakeClient())
    haiku = [s for s, c in SETTINGS.stages.items() if c.model == SETTINGS.stage("summaries").model]
    assert len(haiku) > 1
    assert all(runner._limiter(s) is runner._limiter(haiku[0]) for s in haiku)
    assert runner._limiter("review").per_minute == 5  # type: ignore[union-attr]
