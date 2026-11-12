"""Stage implementations, registered by name. Stages are added by the US1-US6 tasks."""

from __future__ import annotations

from thinkbible_pipeline.stages.base import BookStage, SectionStage


def registry() -> dict[str, SectionStage | BookStage]:
    return {}
