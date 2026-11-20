"""Retire a key idea or question, optionally with a replacement (T081, FR-024).

Live wording never changes. To fix or improve a live item, it is retired (it stays in the pack,
marked ``retired``) and, with a replacement, a new item takes its place with a new ID that records
the ID it ``replaces``. Retiring a key idea also retires the active questions that target only
that idea. ``retiredIn`` is set when the book is next published.

The replacement's wording comes from the owner (``--text`` for a question; ``--title`` and
``--body`` for a key idea); anything not given is copied. A replaced question has no KJV variant
until ``run --refresh`` aligns the section again.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from thinkbible_core.ids import parse_item_id
from thinkbible_pipeline.drafts.ids import next_id
from thinkbible_pipeline.drafts.store import DraftStore


class RetireError(Exception):
    pass


@dataclass
class RetireResult:
    retired: list[str] = field(default_factory=list)  # the item, and questions retired with it
    replacement: str | None = None


def retire(
    store: DraftStore,
    item_id: str,
    *,
    replace: bool = False,
    text: str | None = None,
    title: str | None = None,
    body: str | None = None,
) -> RetireResult:
    try:
        parts = parse_item_id(item_id)
    except ValueError as e:
        raise RetireError(str(e)) from e
    draft = store.read_draft(parts.section)
    if draft is None:
        raise RetireError(f"no draft for section {parts.section}")
    kind = "keyIdeas" if parts.kind == "k" else "questions"
    items: list[dict[str, Any]] = draft.section.get(kind, [])
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        raise RetireError(f"{item_id} is not in {parts.section}'s published content")
    if item.get("status", "active") == "retired":
        raise RetireError(f"{item_id} is already retired")
    if parts.kind == "q" and (title or body):
        raise RetireError("a question takes --text, not --title or --body")
    if parts.kind == "k" and text:
        raise RetireError("a key idea takes --title and --body, not --text")
    result = RetireResult(retired=[item_id])
    item["status"] = "retired"
    if parts.kind == "k":
        retired_ideas = {i["id"] for i in items if i.get("status") == "retired"}
        for q in draft.section.get("questions", []):
            if q.get("status", "active") == "active" and set(q["targets"]) <= retired_ideas:
                q["status"] = "retired"
                result.retired.append(q["id"])
    if replace:
        new = copy.deepcopy(item)
        for stale in ("addedIn", "retiredIn", "textByTranslation", "replaces"):
            new.pop(stale, None)
        new.update({"id": next_id(draft, parts.section, parts.kind), "status": "active",
                    "replaces": item_id})  # fmt: skip
        if text is not None:
            new["text"] = text
        if title is not None:
            new["title"] = title
        if body is not None:
            new["body"] = body
        if parts.kind == "k" and item_id in draft.evidence:
            draft.evidence[new["id"]] = draft.evidence[item_id]
        items.append(new)
        result.replacement = new["id"]
    store.write_draft(parts.section, draft)
    return result
