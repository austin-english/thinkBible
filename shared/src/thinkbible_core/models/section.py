"""Section, KeyIdea, Question and notes (content/schema/section.schema.json)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)

from thinkbible_core.models._base import (
    CommentatorId,
    ContractModel,
    KeyIdeaId,
    PackVersion,
    QuestionId,
    SectionId,
    Status,
    TranslationId,
    Verse,
)

QuestionText = Annotated[str, StringConstraints(min_length=10, max_length=160, pattern=r"\?$")]


class _VersionedItem(ContractModel):
    """Fields shared by key ideas and questions: status and version lifecycle."""

    status: Status
    added_in: PackVersion
    retired_in: PackVersion | None = None

    @model_validator(mode="after")
    def _retired_needs_version(self) -> _VersionedItem:
        if self.status == "retired" and self.retired_in is None:
            raise ValueError("retiredIn is required when status is retired")
        if self.status == "active" and self.retired_in is not None:
            raise ValueError("retiredIn must be absent while status is active")
        return self


class KeyIdea(_VersionedItem):
    id: KeyIdeaId
    title: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    sources: Annotated[list[CommentatorId], Field(min_length=1, max_length=3)]
    agreed: bool
    verse_start: Verse
    verse_end: Verse
    replaces: KeyIdeaId | None = None

    @model_validator(mode="after")
    def _check(self) -> KeyIdea:
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("sources must be unique")
        if self.agreed != (len(self.sources) >= 2):
            raise ValueError("agreed must be true exactly when sources has 2 or more entries")
        if self.verse_start > self.verse_end:
            raise ValueError("verseStart must be <= verseEnd")
        return self


class Question(_VersionedItem):
    id: QuestionId
    level: Annotated[int, Field(ge=1, le=3)]
    type: Literal["noticing", "meaning", "application", "seasonal"]
    verse_start: Verse
    verse_end: Verse
    text: QuestionText
    text_by_translation: dict[TranslationId, QuestionText] | None = None
    targets: Annotated[list[KeyIdeaId], Field(min_length=1)]
    is_alternate: bool
    replaces: QuestionId | None = None
    series: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,40}$")] | None = None

    @model_validator(mode="after")
    def _check(self) -> Question:
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("targets must be unique")
        if self.verse_start > self.verse_end:
            raise ValueError("verseStart must be <= verseEnd")
        return self


class ManuscriptNote(ContractModel):
    chapter: Annotated[int, Field(ge=1)]
    verse_start: Verse
    verse_end: Verse
    text: Annotated[str, StringConstraints(min_length=1, max_length=280)]


class VerseNote(ContractModel):
    """Reserved for V2. The MVP pipeline does not generate these."""

    chapter: Annotated[int, Field(ge=1)]
    verse: Verse
    anchor: Annotated[str, StringConstraints(max_length=40)] | None = None
    text: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Section(ContractModel):
    id: SectionId
    ref: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    chapter: Annotated[int, Field(ge=1, le=150)]
    verse_start: Verse
    verse_end: Verse
    title: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    no_prompt: bool
    context: Annotated[str, StringConstraints(min_length=1, max_length=280)]
    # Required by the schema but nullable: always serialised, even when None.
    views_differ: Annotated[str, StringConstraints(max_length=400)] | None
    manuscript_notes: list[ManuscriptNote]
    verse_notes: list[VerseNote] | None = None
    key_ideas: list[KeyIdea]
    questions: list[Question]

    @model_validator(mode="after")
    def _check(self) -> Section:
        if self.verse_start > self.verse_end:
            raise ValueError("verseStart must be <= verseEnd")
        return self

    @model_serializer(mode="wrap")
    def _keep_views_differ(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            key = "viewsDiffer" if info.by_alias else "views_differ"
            data.setdefault(key, None)
        return data
