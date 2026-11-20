"""Canonical JSON for committed files, and the camelCase base model for pipeline data."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class JsonModel(BaseModel):
    """camelCase JSON, snake_case Python, no unknown fields."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def canonical_json(value: Any) -> str:
    """Sorted keys, 2-space indent, trailing newline: small, stable git diffs."""
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def compact_canonical(value: Any) -> str:
    """Sorted keys, no whitespace: for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write canonical JSON atomically (temp file + rename), creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(canonical_json(value))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)
