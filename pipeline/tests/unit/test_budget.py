import pytest

from thinkbible_pipeline.config import ConfigError, bare_model_id, load_pricing, load_settings
from thinkbible_pipeline.drafts.models import RunRecord, SectionCounts, TokenCounts
from thinkbible_pipeline.llm.budget import (
    Budget,
    EstimateSummary,
    confirm,
    cost_per_section,
    estimate,
    price,
)
from thinkbible_pipeline.llm.runner import Usage

SETTINGS = load_settings()
PRICING = load_pricing()


def _run(stage: str, done: int, spent: float) -> RunRecord:
    return RunRecord(
        run_id="r",
        book="mrk",
        stage=stage,
        started_at="2026-11-10T00:00:00+00:00",
        ended_at="2026-11-10T00:01:00+00:00",
        sections=SectionCounts(done=done),
        estimate_usd=0,
        cap_usd=None,
        spent_usd=spent,
        tokens=TokenCounts(),
        models=[],
        prompt_versions={},
    )


def test_settings_use_bedrock_mantle_ids() -> None:
    for name in ("summaries", "generate", "align", "review", "levels"):
        assert SETTINGS.stage(name).model.startswith("anthropic.claude-")
    assert SETTINGS.refusal_fallback_model == "anthropic.claude-opus-5-5"


def test_bare_model_id() -> None:
    assert bare_model_id("us.anthropic.claude-sonnet-5-5") == "claude-sonnet-5-5"
    assert bare_model_id("anthropic.claude-haiku-5-5") == "claude-haiku-5-5"
    assert bare_model_id("claude-opus-5-5") == "claude-opus-5-5"


def test_price_sonnet() -> None:
    u = Usage(
        model="anthropic.claude-sonnet-5-5",
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_tokens=1_000_000,
        cache_write_5m_tokens=1_000_000,
    )
    # 2 + 1 + 0.10 + 2.50
    assert price(u, PRICING) == pytest.approx(5.60)


def test_price_empty_usage_is_free_for_any_model() -> None:
    assert price(Usage(model="fake"), PRICING) == 0.0


def test_price_unknown_model_raises() -> None:
    with pytest.raises(ConfigError):
        price(Usage(model="anthropic.claude-mystery", input_tokens=1), PRICING)


def test_estimate_defaults_without_history() -> None:
    assert estimate("generate", 10, [], SETTINGS) == pytest.approx(0.6)


def test_estimate_uses_median_of_history() -> None:
    runs = [_run("generate", 10, 1.0), _run("generate", 10, 3.0), _run("generate", 5, 1.0)]
    runs.append(_run("review", 10, 100.0))  # other stages ignored
    runs.append(_run("generate", 0, 9.0))  # runs with nothing done ignored
    # per-section costs: 0.1, 0.3, 0.2 → median 0.2
    assert cost_per_section("generate", runs, SETTINGS) == pytest.approx(0.2)
    assert estimate("generate", 4, runs, SETTINGS) == pytest.approx(0.8)


def test_estimate_uses_last_20_runs() -> None:
    runs = [_run("generate", 1, 10.0)] * 5 + [_run("generate", 1, 1.0)] * 20
    assert cost_per_section("generate", runs, SETTINGS) == pytest.approx(1.0)


def test_budget_stops_new_sections_at_cap() -> None:
    b = Budget(1.0)
    assert b.can_start()
    b.add(0.6)
    assert b.can_start()
    b.add(0.4)
    assert not b.can_start()
    assert Budget(None).can_start()


def test_confirm_prints_and_asks() -> None:
    lines: list[str] = []
    summary = EstimateSummary("generate", 8, 2, 0.48, 0.96)
    assert confirm(summary, yes=False, echo=lines.append, ask=lambda _p: "y")
    assert not confirm(summary, yes=False, echo=lines.append, ask=lambda _p: "")
    assert confirm(summary, yes=True, echo=lines.append, ask=lambda _p: "n")
    assert "8 sections to process, 2 skipped" in lines[0]
    assert "$0.48" in lines[1] and "$0.96" in lines[1]
