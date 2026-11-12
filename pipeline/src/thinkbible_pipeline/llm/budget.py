"""Cost: price usage, estimate a stage, enforce the cap, confirm before spending (research R15)."""

from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from thinkbible_pipeline.config import Pricing, Settings
from thinkbible_pipeline.drafts.models import RunRecord
from thinkbible_pipeline.llm.runner import Usage

HISTORY_WINDOW = 20


def price(usage: Usage, pricing: Pricing) -> float:
    """USD for one response. Usage with no tokens costs nothing, whatever the model."""
    if usage.is_empty:
        return 0.0
    p = pricing.for_model(usage.model)
    total = (
        usage.input_tokens * p.input
        + usage.output_tokens * p.output
        + usage.cache_read_tokens * p.cache_read
        + usage.cache_write_5m_tokens * p.cache_write_5m
        + usage.cache_write_1h_tokens * p.cache_write_1h
    )
    return total / 1_000_000


def cost_per_section(stage: str, runs: Sequence[RunRecord], settings: Settings) -> float:
    """Median cost per section over the last 20 runs of ``stage``, else the settings default."""
    history = [r.spent_usd / r.sections.done for r in runs if r.stage == stage and r.sections.done]
    if history:
        return statistics.median(history[-HISTORY_WINDOW:])
    return settings.stage(stage).default_cost_usd


def estimate(stage: str, n_sections: int, runs: Sequence[RunRecord], settings: Settings) -> float:
    return n_sections * cost_per_section(stage, runs, settings)


class Budget:
    """Tracks spend against a cap. Once spend reaches the cap, no new section may start."""

    def __init__(self, cap_usd: float | None) -> None:
        self.cap_usd = cap_usd
        self.spent_usd = 0.0

    def add(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd

    def can_start(self) -> bool:
        return self.cap_usd is None or self.spent_usd < self.cap_usd

    @property
    def exceeded(self) -> bool:
        return not self.can_start()


@dataclass(frozen=True)
class EstimateSummary:
    stage: str
    to_process: int
    skipped: int
    estimate_usd: float
    cap_usd: float


def confirm(
    summary: EstimateSummary,
    *,
    yes: bool,
    echo: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
) -> bool:
    """Print what a stage will do and what it may cost, then ask unless ``yes``."""
    echo(
        f"{summary.stage}: {summary.to_process} sections to process, "
        f"{summary.skipped} skipped (already done)"
    )
    echo(f"  estimate ${summary.estimate_usd:.2f}, cap ${summary.cap_usd:.2f}")
    if yes:
        return True
    return ask("Proceed? [y/N] ").strip().lower() in {"y", "yes"}
