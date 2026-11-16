"""The ``sections`` stage (T045): writes the map once, freezes it once live, feeds the estimate."""

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.models import BookState, SectionDraft
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.llm.runner import FakeRunner
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.versification import KJV_VERSES
from thinkbible_pipeline.stages.base import Deps, SectionResult, SectionStage, estimate_run, run
from thinkbible_pipeline.stages.sections import SectionsStage
from thinkbible_pipeline.storage import LocalBlobStore


def bsb_mark() -> dict[str, Any]:
    chapters = []
    for number, last in enumerate(KJV_VERSES["MRK"], 1):
        items: list[dict[str, Any]] = [{"type": "heading", "text": f"Chapter {number}"}]
        items += [{"type": "verse", "number": v, "text": "x"} for v in range(1, last + 1)]
        chapters.append({"number": number, "items": items})
    return {"book": "MRK", "chapters": chapters}


class Out(BaseModel):
    summary: str


class ModelStage(SectionStage):
    """Stands in for a model stage after `sections`, to check the run's estimate."""

    name = "summaries"

    def prompt_version(self, deps: Deps) -> str:
        return "v1"

    def model(self, deps: Deps) -> str:
        return deps.settings.stage("summaries").model

    def inputs(self, section_id: str, draft: SectionDraft, deps: Deps) -> Any:
        return section_id

    async def execute(
        self, section_id: str, inputs: Any, draft: SectionDraft, deps: Deps
    ) -> SectionResult:
        return SectionResult()


def make_deps(tmp_path: Path, make_library: Any, echo: list[str]) -> Deps:
    return Deps(
        store=DraftStore("mrk", LocalBlobStore(tmp_path / "drafts")),
        settings=load_settings(),
        pricing=load_pricing(),
        runner_factory=lambda: FakeRunner(responses={}),
        approve_estimate=lambda _s: True,
        stages={"sections": SectionsStage(), "summaries": ModelStage()},
        echo=echo.append,
        library=make_library({("bsb", "MRK"): bsb_mark()}),
    )


def test_writes_the_map_then_leaves_it_alone(tmp_path: Path, make_library: Any) -> None:
    echo: list[str] = []
    deps = make_deps(tmp_path, make_library, echo)
    request = RunRequest(book="mark", stages=["sections"])
    asyncio.run(run(request, deps))
    ids = deps.store.section_ids()
    assert ids[0] == "mrk-1-1" and len(ids) > 16
    state = deps.store.read_book()
    assert state is not None and state.status == "sectioned" and state.book.id == "MRK"
    assert echo[-1].startswith(f"sections: wrote {len(ids)} sections")
    asyncio.run(run(request, deps))
    assert echo[-1] == f"sections: unchanged ({len(ids)} sections)"


def test_a_live_book_keeps_its_sections(tmp_path: Path, make_library: Any) -> None:
    echo: list[str] = []
    deps = make_deps(tmp_path, make_library, echo)
    deps.store.write_section_map([])
    deps.store.write_book(
        BookState.model_validate(
            {"book": {"id": "MRK", "name": "Mark"}, "status": "promoted", "lastPromoted": "1.0.0"}
        )
    )
    asyncio.run(run(RunRequest(book="mark", stages=["sections"]), deps))
    assert deps.store.section_ids() == []
    assert "frozen" in echo[-1]


def test_a_run_that_starts_with_sections_is_estimated_for_them(
    tmp_path: Path, make_library: Any
) -> None:
    deps = make_deps(tmp_path, make_library, [])
    assert deps.store.section_ids() == []  # nothing on disk yet
    plans, summary = estimate_run(RunRequest(book="mark", stages=["sections", "summaries"]), deps)
    model_plan = next(p for p in plans if p.stage == "summaries")
    expected = len(
        SectionsStage().planned_section_ids(RunRequest(book="mark", stages=["sections"]), deps)
    )
    assert len(model_plan.items) == expected > 16
    assert summary.estimate_usd > 0
