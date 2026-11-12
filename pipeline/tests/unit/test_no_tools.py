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
    assert params["output_config"] == {"effort": cfg.effort}
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
