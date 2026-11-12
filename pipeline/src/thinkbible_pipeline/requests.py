"""Request objects shared by the CLI and a future cloud trigger (contracts/cli.md).

The CLI parses flags into these; API Gateway or Step Functions will send the same JSON
(camelCase: ``capUsd``, ``autoApprove``).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from thinkbible_core.ids import BookInfo, UnknownBookError, resolve_book

# `all` runs sections through report and stops at "ready for review" (contracts/cli.md).
STAGE_ORDER: tuple[str, ...] = (
    "sections",
    "summaries",
    "generate",
    "align",
    "check",
    "review",
    "levels",
    "report",
)
MODEL_STAGES = frozenset({"summaries", "generate", "align", "review", "levels"})

Env = Literal["dev", "prod"]


class _Request(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    book: str

    @field_validator("book")
    @classmethod
    def _known_book(cls, v: str) -> str:
        try:
            resolve_book(v)
        except UnknownBookError as e:
            raise ValueError(str(e)) from e
        return v

    @property
    def book_info(self) -> BookInfo:
        return resolve_book(self.book)


class RunRequest(_Request):
    stages: Annotated[list[str], Field(min_length=1)]
    sections: list[str] | None = None
    fresh: bool = False
    refresh: bool = False
    cap_usd: Annotated[float, Field(gt=0)] | None = None  # None = 2x the estimate
    auto_approve: bool = False
    env: Env = "dev"

    @field_validator("stages", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        return [s.strip() for s in v.split(",") if s.strip()] if isinstance(v, str) else v

    @field_validator("sections", mode="before")
    @classmethod
    def _split_sections(cls, v: object) -> object:
        return [s.strip() for s in v.split(",") if s.strip()] if isinstance(v, str) else v

    @field_validator("stages")
    @classmethod
    def _expand(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for s in v:
            names = STAGE_ORDER if s == "all" else (s,)
            for name in names:
                if name not in STAGE_ORDER:
                    raise ValueError(f"unknown stage {name!r}; expected one of {STAGE_ORDER}")
                if name not in out:
                    out.append(name)
        # Always run in pipeline order, whatever order they were given in.
        return sorted(out, key=STAGE_ORDER.index)


class PublishRequest(_Request):
    """Publish the book's drafts to dev (R14). A passing run does this automatically."""

    dry_run: bool = False


class PromoteRequest(_Request):
    """Copy the book's current dev version to production (R14, FR-021)."""
