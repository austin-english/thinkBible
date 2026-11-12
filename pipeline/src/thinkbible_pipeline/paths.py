"""Repository paths used by the pipeline (content, config, prompts, drafts)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

REPO_ROOT_ENV = "THINKBIBLE_REPO_ROOT"


@dataclass(frozen=True)
class RepoPaths:
    """All paths are derived from the repo root, so tests can point this at a temp directory."""

    root: Path

    @property
    def content(self) -> Path:
        return self.root / "content"

    @property
    def schema(self) -> Path:
        return self.content / "schema"

    @property
    def sources(self) -> Path:
        """Local cache of the frozen source snapshot (gitignored except the manifest)."""
        return self.content / "sources"

    @property
    def manifest(self) -> Path:
        return self.sources / "manifest.json"

    @property
    def drafts_root(self) -> Path:
        return self.content / "drafts"

    def drafts(self, book_slug: str) -> Path:
        """``content/drafts/{book}``, e.g. ``content/drafts/mrk``."""
        return self.drafts_root / book_slug

    @property
    def pipeline(self) -> Path:
        return self.root / "pipeline"

    @property
    def config(self) -> Path:
        return self.pipeline / "config"

    @property
    def prompts(self) -> Path:
        return self.pipeline / "prompts"


def find_repo_root(start: Path | None = None) -> Path:
    """``$THINKBIBLE_REPO_ROOT``, else the nearest parent with ``content/`` and ``pipeline/``."""
    override = os.environ.get(REPO_ROOT_ENV)
    if override:
        return Path(override)
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "content").is_dir() and (parent / "pipeline").is_dir():
            return parent
    raise FileNotFoundError(f"repo root not found above {here}; set {REPO_ROOT_ENV}")


@cache
def repo_paths() -> RepoPaths:
    return RepoPaths(find_repo_root())
