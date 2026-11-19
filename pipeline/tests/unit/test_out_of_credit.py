"""A run stops when the Claude API account is out of credit (2026-11-19)."""

import asyncio
from typing import Any

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.exitcodes import ExitCode
from thinkbible_pipeline.ledger import InMemoryLedger
from thinkbible_pipeline.llm.runner import OUT_OF_CREDIT, FakeRunner, OutOfCredit
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps, run


def test_the_run_stops_and_leaves_the_refused_section_as_it_was(publish_book: Any) -> None:
    runner = FakeRunner(responses={
        ("summaries", "2jn-1-1"): OutOfCredit(OUT_OF_CREDIT),
        ("summaries", "2jn-1-7"): {"summary": "The elder warns against deceivers."},
    })  # fmt: skip
    deps = Deps(
        store=publish_book.store,
        settings=load_settings(),
        pricing=load_pricing(),
        runner_factory=lambda: runner,
        approve_estimate=lambda _s: True,
        stages=registry(),
        library=publish_book.library,
        ledger=InMemoryLedger(),
    )
    result = asyncio.run(run(RunRequest(book="2JN", stages=["summaries", "generate"]), deps))
    [summaries] = result.stages  # the run stops: generate never starts
    assert summaries.stopped_by == "credit" and summaries.not_started >= 1
    assert result.exit_code == ExitCode.CAP_REACHED
    assert "summaries" not in publish_book.draft("2jn-1-1").stages  # no failure recorded
