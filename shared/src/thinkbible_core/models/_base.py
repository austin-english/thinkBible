"""Shared base and constrained types for the content pack models.

The JSON Schemas in ``content/schema/`` are the contract. These models mirror them field for field
(camelCase aliases, no extra properties) and add the cross-field checks that fit on one object.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

SECTION_ID_PATTERN = r"^[0-9a-z]{3}-[0-9]{1,3}-[0-9]{1,3}$"
KEY_IDEA_ID_PATTERN = r"^[0-9a-z]{3}-[0-9]{1,3}-[0-9]{1,3}-k[0-9]{1,3}$"
QUESTION_ID_PATTERN = r"^[0-9a-z]{3}-[0-9]{1,3}-[0-9]{1,3}-q[0-9]{1,3}$"
PACK_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
TRANSLATION_ID_PATTERN = r"^[a-z][a-z0-9_]{1,15}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
BOOK_CODE_PATTERN = r"^[0-9A-Z]{3}$"

SectionId = Annotated[str, StringConstraints(pattern=SECTION_ID_PATTERN)]
KeyIdeaId = Annotated[str, StringConstraints(pattern=KEY_IDEA_ID_PATTERN)]
QuestionId = Annotated[str, StringConstraints(pattern=QUESTION_ID_PATTERN)]
PackVersion = Annotated[str, StringConstraints(pattern=PACK_VERSION_PATTERN)]
TranslationId = Annotated[str, StringConstraints(pattern=TRANSLATION_ID_PATTERN)]
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_PATTERN)]
BookCode = Annotated[str, StringConstraints(pattern=BOOK_CODE_PATTERN)]
Verse = Annotated[int, Field(ge=1, le=176)]

CommentatorId = Literal["matthew-henry", "jamieson-fausset-brown", "adam-clarke"]
Status = Literal["active", "retired"]


class ContractModel(BaseModel):
    """Base for every contract model: camelCase JSON, no unknown fields."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    def to_doc(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict in contract shape (camelCase, optional nulls omitted)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
