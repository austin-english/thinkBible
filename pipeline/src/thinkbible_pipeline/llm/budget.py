"""Cost: price usage, estimate a stage, enforce the cap, confirm before spending (research R15)."""

from __future__ import annotations

import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from thinkbible_pipeline.config import Pricing, Settings
from thinkbible_pipeline.drafts.models import RunRecord
from thinkbible_pipeline.llm.runner import Usage

HISTORY_WINDOW = 20
# The Message Batches API's price: half of every token (T087).
BATCH_DISCOUNT = 0.5


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
    return total / 1_000_000 * (BATCH_DISCOUNT if usage.batch else 1.0)


def cost_per_section(stage: str, runs: Sequence[RunRecord], settings: Settings) -> float:
    """Median standard-price cost per section over the last 20 runs of ``stage`` (a batch run's
    cost counted at full price), else the settings default."""
    history = [
        r.spent_usd / r.sections.done / (BATCH_DISCOUNT if r.batch else 1.0)
        for r in runs
        if r.stage == stage and r.sections.done
    ]
    if history:
        return statistics.median(history[-HISTORY_WINDOW:])
    return settings.stage(stage).default_cost_usd


def estimate(
    stage: str,
    n_sections: int,
    runs: Sequence[RunRecord],
    settings: Settings,
    *,
    batch: bool = False,
) -> float:
    """``batch``: a batch run, where the stages marked ``batch`` cost half."""
    discount = BATCH_DISCOUNT if batch and settings.stage(stage).batch else 1.0
    return n_sections * cost_per_section(stage, runs, settings) * discount


@dataclass(frozen=True)
class StageEstimate:
    stage: str
    to_process: int
    skipped: int
    estimate_usd: float
    calls_model: bool
    live: int = 0  # live sections left alone (US6)
    free: int = 0  # sections to process with no model call (stored grades reused)


@dataclass(frozen=True)
class EstimateSummary:
    """The whole run's estimate, approved once before any model call (research R7, R15)."""

    stages: tuple[StageEstimate, ...]
    estimate_usd: float
    cap_usd: float | None

    @property
    def calls_model(self) -> bool:
        return any(s.calls_model and s.to_process > s.free for s in self.stages)


def confirm(
    summary: EstimateSummary,
    *,
    yes: bool,
    echo: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
) -> bool:
    """Print what the run will do and what it may cost, then ask unless ``yes``."""
    for s in summary.stages:
        line = f"{s.stage}: {s.to_process} sections to process, {s.skipped} skipped (already done)"
        if s.live:
            line += f", {s.live} skipped: live (use --refresh)"
        if s.free:
            line += f", {s.free} reusing stored grades (no cost)"
        if s.calls_model and s.to_process > s.free:
            line += f", about ${s.estimate_usd:.2f}"
        echo(line)
    cap = f"${summary.cap_usd:.2f}" if summary.cap_usd is not None else "none"
    echo(f"estimate ${summary.estimate_usd:.2f}, cap {cap}")
    if yes:
        return True
    return ask("Proceed? [y/N] ").strip().lower() in {"y", "yes"}
