"""Stage implementations, registered by name. Stages are added by the US1-US6 tasks."""

from __future__ import annotations

from thinkbible_pipeline.requests import STAGE_ORDER
from thinkbible_pipeline.stages.base import BookStage, SectionStage
from thinkbible_pipeline.stages.checks import CheckStage
from thinkbible_pipeline.stages.generate import GenerateStage
from thinkbible_pipeline.stages.report import ReportStage
from thinkbible_pipeline.stages.sections import SectionsStage
from thinkbible_pipeline.stages.summaries import SummariesStage


def registry() -> dict[str, SectionStage | BookStage]:
    stages: list[SectionStage | BookStage] = [
        SectionsStage(),
        SummariesStage(),
        GenerateStage(),
        CheckStage(),
        ReportStage(),
    ]
    return {s.name: s for s in stages}


def expand_all(stage_arg: str) -> str:
    """``all`` (alone or in a list) means every stage that is implemented, in pipeline order.

    Stages planned for later user stories (review, levels, align) are left out until they
    exist; naming one of them explicitly still fails with "not implemented yet".
    """
    names = [s.strip() for s in stage_arg.split(",") if s.strip()]
    if "all" not in names:
        return stage_arg
    implemented = registry()
    expanded = [n for n in STAGE_ORDER if n in implemented]
    expanded += [n for n in names if n != "all" and n not in expanded]
    return ",".join(expanded)
