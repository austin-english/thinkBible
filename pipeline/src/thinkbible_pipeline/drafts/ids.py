"""Permanent IDs for key ideas and questions (research R13): ``mrk-1-1-k3``, ``mrk-1-1-q4``.

The number comes from the section's counter in its draft, which only ever increases, so an ID is
never reused, even for an item the gate dropped before it was ever published.
"""

from __future__ import annotations

from typing import Literal

from thinkbible_pipeline.drafts.models import SectionDraft


def next_id(draft: SectionDraft, section_id: str, kind: Literal["k", "q"]) -> str:
    """Give out the next ``k`` (key idea) or ``q`` (question) ID of ``section_id``."""
    value = getattr(draft.ids, kind) + 1
    setattr(draft.ids, kind, value)
    return f"{section_id}-{kind}{value}"
