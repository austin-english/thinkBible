"""Text normalisation shared by the evidence check and the rule checks."""

from __future__ import annotations

import re
import unicodedata

# Curly quotes and dashes become plain ones (code points, to keep this file ASCII).
_QUOTES = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"}


def normalize(text: str) -> str:
    """Lowercase words only: punctuation, accents and spacing don't decide a match."""
    text = unicodedata.normalize("NFKD", text.translate(_QUOTES))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))
