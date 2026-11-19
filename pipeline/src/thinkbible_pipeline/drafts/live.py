"""Live content is frozen (US6, FR-024, FR-024a).

``promote`` records each section's live items on its draft (``SectionDraft.live``). From then on:
- ``generate``, ``summaries`` and ``align`` skip the section unless ``--refresh``
  (``stages/base.plan_stage``);
- ``check`` fails the section if a live item's wording changed (``frozen_violations``), and
  otherwise only reports;
- ``review`` grades it for the scorecard but never drops, re-picks or removes anything live.

A live item changes only through ``retire`` (``drafts/retire.py``): it becomes ``retired``, and a
replacement with a new ID records the ID it ``replaces``.
"""

from __future__ import annotations

from typing import Any

from thinkbible_pipeline.drafts.models import LiveRecord, SectionDraft

# The fields of a published item that may never change (FR-024), by kind of item.
FROZEN_FIELDS = {"keyIdeas": ("title", "body"), "questions": ("text", "textByTranslation")}
# Stages that would rewrite a section's content: they skip a live section unless --refresh.
GUARDED_STAGES = frozenset({"generate", "summaries", "align"})
FROZEN_MESSAGE = "published text is frozen: retire and replace (FR-024)"


def is_live(draft: SectionDraft) -> bool:
    return draft.live is not None and bool(draft.live.items)


def live_ids(draft: SectionDraft) -> set[str]:
    return set(draft.live.items) if draft.live is not None else set()


def snapshot(section: dict[str, Any], version: str) -> LiveRecord:
    """The live record of a published section (its doc from the promoted study pack)."""
    items: dict[str, dict[str, Any]] = {}
    for kind, fields in FROZEN_FIELDS.items():
        for item in section.get(kind, []):
            items[item["id"]] = {f: item.get(f) for f in (*fields, "status")}
    return LiveRecord(version=version, items=items)


def frozen_violations(draft: SectionDraft) -> list[str]:
    """Each live item that is missing, reworded, or retired and active again."""
    if draft.live is None:
        return []
    current: dict[str, dict[str, Any]] = {}
    kinds: dict[str, str] = {}
    for kind in FROZEN_FIELDS:
        for item in draft.section.get(kind, []):
            current[item["id"]], kinds[item["id"]] = item, kind
    out = []
    for item_id, published in draft.live.items.items():
        now = current.get(item_id)
        if now is None:
            out.append(f"{item_id} is missing: {FROZEN_MESSAGE}")
            continue
        if any(now.get(f) != published.get(f) for f in FROZEN_FIELDS[kinds[item_id]]):
            out.append(f"{item_id}: {FROZEN_MESSAGE}")
        if published.get("status") == "retired" and now.get("status", "active") == "active":
            out.append(f"{item_id} was retired and is active again: {FROZEN_MESSAGE}")
    return out
