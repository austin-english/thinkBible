"""Composition root: build the real dependencies for a request (local runs).

A cloud trigger builds its own ``Deps`` (different approval callback) and calls the same
``stages.base.run``.
"""

from __future__ import annotations

from collections.abc import Callable

from thinkbible_pipeline.config import load_pricing, load_settings
from thinkbible_pipeline.drafts.store import DraftStore
from thinkbible_pipeline.llm.budget import EstimateSummary, confirm
from thinkbible_pipeline.llm.runner import BedrockRunner, ModelRunner
from thinkbible_pipeline.paths import RepoPaths, repo_paths
from thinkbible_pipeline.requests import RunRequest
from thinkbible_pipeline.sources.snapshot import SourceError, verify
from thinkbible_pipeline.stages import registry
from thinkbible_pipeline.stages.base import Deps


def source_preflight(book_code: str, paths: RepoPaths) -> Callable[[], None]:
    def check() -> None:
        problems = verify(paths=paths, books={book_code})
        if problems:
            raise SourceError("\n".join(f"{p.source}/{p.book}: {p.message}" for p in problems))

    return check


def local_deps(
    request: RunRequest,
    *,
    echo: Callable[[str], None] = print,
    ask: Callable[[str], str] = input,
    paths: RepoPaths | None = None,
) -> Deps:
    paths = paths or repo_paths()
    settings = load_settings(paths.config)

    def approve(summary: EstimateSummary) -> bool:
        return confirm(summary, yes=request.auto_approve, echo=echo, ask=ask)

    def runner() -> ModelRunner:
        return BedrockRunner(settings)

    return Deps(
        store=DraftStore(request.book_info.slug, paths),
        settings=settings,
        pricing=load_pricing(paths.config),
        runner_factory=runner,
        approve_estimate=approve,
        stages=registry(),
        preflight=source_preflight(request.book_info.code, paths),
        echo=echo,
    )
