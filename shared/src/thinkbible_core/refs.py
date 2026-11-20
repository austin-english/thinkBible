"""Verse-reference placeholders in pack text (research R13).

Study text never quotes a translation's verse numbering directly. It writes ``{{ref:C:V}}`` or
``{{ref:C:V-V}}``, and the app renders it for the reader's translation ("verse 7" in the current
chapter, "1:7" otherwise). Every placeholder must resolve in every published translation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

PLACEHOLDER_RE = re.compile(r"\{\{ref:(?P<chapter>\d+):(?P<start>\d+)(?:-(?P<end>\d+))?\}\}")
_ANY_BRACES_RE = re.compile(r"\{\{.*?\}\}")


@dataclass(frozen=True)
class Ref:
    chapter: int
    start: int
    end: int

    @property
    def verses(self) -> list[tuple[int, int]]:
        return [(self.chapter, v) for v in range(self.start, self.end + 1)]

    def __str__(self) -> str:
        tail = f"-{self.end}" if self.end != self.start else ""
        return f"{{{{ref:{self.chapter}:{self.start}{tail}}}}}"


def find_refs(text: str) -> list[Ref]:
    """All well-formed placeholders in ``text``, in order."""
    refs = []
    for m in PLACEHOLDER_RE.finditer(text):
        start = int(m["start"])
        end = int(m["end"]) if m["end"] else start
        refs.append(Ref(int(m["chapter"]), start, end))
    return refs


def malformed(text: str) -> list[str]:
    """``{{…}}`` fragments that are not valid placeholders, plus ranges that run backwards."""
    bad = [frag for frag in _ANY_BRACES_RE.findall(text) if not PLACEHOLDER_RE.fullmatch(frag)]
    bad += [str(r) for r in find_refs(text) if r.end < r.start]
    return bad


def unresolved(
    text: str, verse_sets: Mapping[str, Iterable[tuple[int, int]]]
) -> list[tuple[str, Ref]]:
    """Placeholders whose verses are missing from a translation, as (translation_id, ref)."""
    sets = {tr: set(vs) for tr, vs in verse_sets.items()}
    missing: list[tuple[str, Ref]] = []
    for ref in find_refs(text):
        for tr, present in sets.items():
            if any(v not in present for v in ref.verses):
                missing.append((tr, ref))
    return missing
