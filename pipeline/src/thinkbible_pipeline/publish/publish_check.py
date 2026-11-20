"""The live publish check (T071, data-model "Publish check", FR-024): live content only grows.

Run on ``promote`` against the live channel's current pack. The draft channel may be republished
from scratch and skips it. Each problem is one line; any problem refuses the promotion (exit 5):
- a section is missing, or its chapter or verse range changed;
- a key idea or question is missing (retire it instead);
- the wording of a published item changed: a key idea's title or body, a question's text or its
  per-translation wording;
- an ID now names a different item: another verse range, or another kind (key or background) or
  question type;
- a retired item is active again;
- a ``replaces`` names an item that isn't retired.
"""

from __future__ import annotations

from thinkbible_core.models.pack import StudyPack
from thinkbible_core.models.section import KeyIdea, Question
from thinkbible_pipeline.publish.build import section_items

Item = KeyIdea | Question


def _items(pack: StudyPack) -> dict[str, Item]:
    return {i.id: i for s in pack.sections for i in section_items(s)}


def _wording(item: Item) -> tuple[object, ...]:
    if isinstance(item, KeyIdea):
        return (item.title, item.body)
    return (item.text, item.text_by_translation)


def _identity(item: Item) -> tuple[object, ...]:
    kind = item.kind if isinstance(item, KeyIdea) else item.type
    return (type(item).__name__, kind, item.verse_start, item.verse_end)


def publish_check(previous: StudyPack, new: StudyPack) -> list[str]:
    """Why ``new`` can't replace ``previous`` on the live channel; empty when it can."""
    problems: list[str] = []
    sections = {s.id: s for s in new.sections}
    for old in previous.sections:
        now = sections.get(old.id)
        if now is None:
            problems.append(f"section {old.id} is missing")
        elif (now.chapter, now.verse_start, now.verse_end) != (
            old.chapter,
            old.verse_start,
            old.verse_end,
        ):
            problems.append(
                f"section {old.id} moved from {old.chapter}:{old.verse_start}-{old.verse_end} to "
                f"{now.chapter}:{now.verse_start}-{now.verse_end}"
            )
    before, after = _items(previous), _items(new)
    for item_id, old_item in before.items():
        new_item = after.get(item_id)
        if new_item is None:
            problems.append(f"{item_id} is missing (retire it instead)")
            continue
        if _identity(new_item) != _identity(old_item):
            problems.append(f"{item_id} now names a different item (an ID is never reused)")
        elif _wording(new_item) != _wording(old_item):
            problems.append(f"{item_id}: its published wording changed (retire and replace it)")
        if old_item.status == "retired" and new_item.status == "active":
            problems.append(f"{item_id} was retired and is active again")
    for item_id, item in after.items():
        if item.replaces is not None:
            target = after.get(item.replaces)
            if target is None or target.status != "retired":
                problems.append(f"{item_id} replaces {item.replaces}, which isn't retired")
    return problems
