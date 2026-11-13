"""`verify` exit codes: 2 on a missing manifest or a changed file, 0 when everything matches."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from thinkbible_pipeline.cli import app
from thinkbible_pipeline.jsonio import canonical_json, sha256_hex, write_json
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources import snapshot
from thinkbible_pipeline.sources.models import BookFile, SourceEntry, SourceManifest


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RepoPaths:
    paths = RepoPaths(tmp_path)
    monkeypatch.setattr(snapshot, "repo_paths", lambda: paths)
    return paths


def write_snapshot(paths: RepoPaths) -> Path:
    data = canonical_json({"book": "MRK", "chapters": []}).encode()
    path = paths.sources / "bsb" / "MRK.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    bf = BookFile(
        file="bsb/MRK.json",
        s3_key="snapshots/d/bsb/MRK.json",
        sha256=sha256_hex(data),
        bytes=len(data),
        retrieved_at="d",
        snapshot_id="d",
    )
    entry = SourceEntry(
        kind="translation", api_id="BSB", name="BSB", license="PD", books={"MRK": bf}
    )
    write_json(
        paths.manifest,
        SourceManifest(bucket="b", api_version="V1", sources={"bsb": entry}).to_doc(),
    )
    return path


def test_verify_without_manifest(repo: RepoPaths) -> None:
    result = CliRunner().invoke(app, ["verify"])
    assert result.exit_code == 2 and "run `import`" in result.output


def test_verify_ok_then_tampered(repo: RepoPaths) -> None:
    path = write_snapshot(repo)
    ok = CliRunner().invoke(app, ["verify"])
    assert (
        ok.exit_code == 0 and "all 1 files in" in ok.output and "match manifest.json" in ok.output
    )
    path.write_bytes(path.read_bytes().replace(b"MRK", b"MRX"))
    bad = CliRunner().invoke(app, ["verify"])
    assert bad.exit_code == 2 and "bsb/MRK" in bad.output


def test_import_needs_books_or_all() -> None:
    result = CliRunner().invoke(app, ["import"])
    assert result.exit_code == 1 and "--all" in result.output
