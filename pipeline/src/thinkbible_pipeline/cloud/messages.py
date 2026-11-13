"""JSON payloads passed between the Step Functions states (camelCase on the wire)."""

from __future__ import annotations

from pydantic import Field

from thinkbible_pipeline.jsonio import JsonModel
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.stages.base import SectionOutcome, StagePlan, StageResult


class RunInput(JsonModel):
    """The execution input the CLI sends with ``StartExecution``."""

    run_id: str
    request: RunRequest
    cap_usd: float | None = None


class StageInput(RunInput):
    """One item of the Stages map: the run plus the stage to plan."""

    stage: str


class PlanOutput(StageInput):
    """``plan_stage`` output: what the Sections map runs, and what ``finish_stage`` records."""

    started_at: str
    plan: StagePlan
    section_ids: list[str] = Field(default_factory=list)
    stopped: bool = False  # the cap stopped an earlier stage; nothing runs


class SectionInput(RunInput):
    stage: str
    section_id: str


class FinishStageInput(PlanOutput):
    outcomes: list[SectionOutcome] = Field(default_factory=list)


class FinishRunInput(RunInput):
    stage_results: list[StageResult] = Field(default_factory=list)


class RunOutput(JsonModel):
    run_id: str
    book: str
    status: str
    exit_code: int
    spent_usd: float
    stages: list[StageResult]
    # True when the run included `report` and no section failed: publish to the draft channel (R14).
    publishable: bool
