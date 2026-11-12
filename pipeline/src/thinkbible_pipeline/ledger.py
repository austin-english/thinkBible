"""The spend ledger: one record per run with its cap and spend (research R8, R15).

Section workers add their cost after each section and start only while spend is under the cap.
Locally it lives in memory; in the cloud it's a DynamoDB item (``cloud/ledger.py``), shared by
every section Lambda of the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

RunStatus = Literal["running", "stopped-cap", "succeeded", "failed"]


@dataclass
class LedgerState:
    run_id: str
    book: str
    cap_usd: float | None
    spent_usd: float = 0.0
    status: RunStatus = "running"
    counts: dict[str, int] = field(default_factory=dict)
    execution_arn: str | None = None

    @property
    def under_cap(self) -> bool:
        return self.cap_usd is None or self.spent_usd < self.cap_usd


class SpendLedger(Protocol):
    def create(
        self, run_id: str, book: str, cap_usd: float | None, *, execution_arn: str | None = None
    ) -> None: ...

    def get(self, run_id: str) -> LedgerState | None: ...

    def can_start(self, run_id: str) -> bool:
        """True while the run is running and its spend is under the cap."""
        ...

    def add(self, run_id: str, cost_usd: float) -> None: ...

    def mark_stopped(self, run_id: str) -> None:
        """The cap was reached: no new sections start for the rest of the run."""
        ...

    def finish(self, run_id: str, status: RunStatus, counts: dict[str, int]) -> None: ...


class LedgerError(LookupError):
    pass


class InMemoryLedger:
    def __init__(self) -> None:
        self._runs: dict[str, LedgerState] = {}

    def create(
        self, run_id: str, book: str, cap_usd: float | None, *, execution_arn: str | None = None
    ) -> None:
        self._runs[run_id] = LedgerState(run_id, book, cap_usd, execution_arn=execution_arn)

    def get(self, run_id: str) -> LedgerState | None:
        return self._runs.get(run_id)

    def _state(self, run_id: str) -> LedgerState:
        state = self._runs.get(run_id)
        if state is None:
            raise LedgerError(f"no ledger entry for run {run_id}")
        return state

    def can_start(self, run_id: str) -> bool:
        state = self._state(run_id)
        return state.status == "running" and state.under_cap

    def add(self, run_id: str, cost_usd: float) -> None:
        self._state(run_id).spent_usd += cost_usd

    def mark_stopped(self, run_id: str) -> None:
        self._state(run_id).status = "stopped-cap"

    def finish(self, run_id: str, status: RunStatus, counts: dict[str, int]) -> None:
        state = self._state(run_id)
        state.status = status
        state.counts = dict(counts)
