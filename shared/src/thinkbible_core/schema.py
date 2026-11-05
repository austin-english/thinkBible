"""Validate documents against the content pack JSON Schemas in ``content/schema/``."""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SchemaKind = Literal["section", "study-pack", "verses", "index"]
SCHEMA_FILES: dict[SchemaKind, str] = {
    "section": "section.schema.json",
    "study-pack": "study-pack.schema.json",
    "verses": "verses.schema.json",
    "index": "index.schema.json",
}
SCHEMA_DIR_ENV = "THINKBIBLE_SCHEMA_DIR"


def schema_dir() -> Path:
    """``$THINKBIBLE_SCHEMA_DIR`` if set, else ``content/schema`` found above this package."""
    override = os.environ.get(SCHEMA_DIR_ENV)
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "content" / "schema"
        if (candidate / SCHEMA_FILES["section"]).is_file():
            return candidate
    raise FileNotFoundError(
        f"content/schema not found above {__file__}; set {SCHEMA_DIR_ENV} to its location"
    )


@cache
def _load(directory: str) -> tuple[dict[SchemaKind, dict[str, Any]], Registry[Any]]:
    root = Path(directory)
    schemas: dict[SchemaKind, dict[str, Any]] = {
        kind: json.loads((root / name).read_text(encoding="utf-8"))
        for kind, name in SCHEMA_FILES.items()
    }
    registry: Registry[Any] = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def validator(kind: SchemaKind, directory: Path | None = None) -> Draft202012Validator:
    schemas, registry = _load(str(directory or schema_dir()))
    return Draft202012Validator(
        schemas[kind],
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def validate(doc: Any, kind: SchemaKind, directory: Path | None = None) -> list[str]:
    """Return schema errors for ``doc`` as readable messages (empty list = valid)."""
    errors = sorted(validator(kind, directory).iter_errors(doc), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
