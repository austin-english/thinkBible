"""Stage implementations, registered by name. Stages are added by the US1-US6 tasks."""

from __future__ import annotations

from thinkbible_pipeline.stages.base import BookStage, SectionStage
from thinkbible_pipeline.stages.generate import GenerateStage
from thinkbible_pipeline.stages.sections import SectionsStage
from thinkbible_pipeline.stages.summaries import SummariesStage


def registry() -> dict[str, SectionStage | BookStage]:
    stages: list[SectionStage | BookStage] = [SectionsStage(), SummariesStage(), GenerateStage()]
    return {s.name: s for s in stages}
