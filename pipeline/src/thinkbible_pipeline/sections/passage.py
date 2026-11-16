"""A section's verses as plain text for a prompt: one numbered verse per line.

A psalm title comes first when the section starts at verse 1. Editorial headings are left out
(the section title is given separately), and verses a translation omits are simply absent, so the
model sees each translation as it is.
"""

from __future__ import annotations

from thinkbible_pipeline.drafts.models import SectionMapEntry
from thinkbible_pipeline.sources.models import SubtitleItem, VerseItem
from thinkbible_pipeline.sources.snapshot import SourceLibrary


def passage_text(
    library: SourceLibrary, translation: str, book: str, section: SectionMapEntry
) -> str:
    chapter = next(
        (c for c in library.translation(translation, book).chapters if c.number == section.chapter),
        None,
    )
    if chapter is None:
        return ""
    lines: list[str] = []
    for item in chapter.items:
        if isinstance(item, SubtitleItem) and section.verse_start == 1:
            lines.append(f"[title] {item.text}")
        elif (
            isinstance(item, VerseItem) and section.verse_start <= item.number <= section.verse_end
        ):
            lines.append(f"{item.number} {item.text}")
    return "\n".join(lines)
