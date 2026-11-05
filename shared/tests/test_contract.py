"""Contract tests: fixtures, JSON Schemas and models agree (constitution VII, research R16)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from thinkbible_core.models import ContractModel, PackIndex, StudyPack, VerseText
from thinkbible_core.rules import cross_field_violations
from thinkbible_core.schema import SchemaKind, schema_dir, validate

FIXTURES = schema_dir() / "fixtures"
KINDS: list[tuple[str, SchemaKind, type[ContractModel]]] = [
    ("study-pack", "study-pack", StudyPack),
    ("verses", "verses", VerseText),
    ("index", "index", PackIndex),
]


def kind_of(path: Path) -> tuple[SchemaKind, type[ContractModel]]:
    for prefix, kind, model in KINDS:
        if path.name.startswith(prefix):
            return kind, model
    raise AssertionError(f"fixture name must start with one of {[k[0] for k in KINDS]}: {path}")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))


def test_fixture_sets_are_present() -> None:
    prefixes = {kind_of(p)[0] for p in VALID}
    assert prefixes == {"study-pack", "verses", "index"}
    assert len(INVALID) >= 7


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixture_passes_schema_and_models(path: Path) -> None:
    doc = load(path)
    kind, model = kind_of(path)

    assert validate(doc, kind) == []

    obj = model.model_validate(doc)
    dumped = obj.to_doc()
    assert validate(dumped, kind) == [], "model output must satisfy the schema"
    assert dumped == doc, "round trip must be lossless"


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_fixture_fails_schema_and_models(path: Path) -> None:
    doc = load(path)
    kind, model = kind_of(path)

    assert validate(doc, kind), "schema should reject this fixture"
    with pytest.raises(ValidationError):
        model.model_validate(doc)


def test_valid_study_pack_has_no_cross_field_violations() -> None:
    pack = StudyPack.model_validate(load(FIXTURES / "valid" / "study-pack-mark-sample.json"))
    verses = VerseText.model_validate(load(FIXTURES / "valid" / "verses-bsb-sample.json"))
    assert cross_field_violations(pack, {"bsb": verses}) == []
