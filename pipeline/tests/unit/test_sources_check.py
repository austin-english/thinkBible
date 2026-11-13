"""`sources check` (T034b): versification, order and coverage problems in the cached snapshot."""

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from thinkbible_pipeline.cli import app
from thinkbible_pipeline.jsonio import canonical_json, sha256_hex, write_json
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources import snapshot
from thinkbible_pipeline.sources.check import check_sources
from thinkbible_pipeline.sources.models import BookFile, SourceEntry, SourceManifest
from thinkbible_pipeline.sources.snapshot import SourceStore
from thinkbible_pipeline.sources.versification import KJV_VERSES


def put(paths: RepoPaths, entry: SourceEntry, source: str, book: str, doc: dict[str, Any]) -> None:
    data = canonical_json(doc).encode()
    path = paths.sources / source / f"{book}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    entry.books[book] = BookFile(
        file=f"{source}/{book}.json",
        s3_key=f"snapshots/d/{source}/{book}.json",
        sha256=sha256_hex(data),
        bytes=len(data),
        retrieved_at="d",
        snapshot_id="d",
    )


def full_translation(book: str) -> dict[str, Any]:
    return {
        "book": book,
        "chapters": [
            {
                "number": c,
                "items": [{"type": "verse", "number": v, "text": "Text."} for v in range(1, n + 1)],
            }
            for c, n in enumerate(KJV_VERSES[book], 1)
        ],
    }


def snapshot_with(paths: RepoPaths, mark_commentary: dict[str, Any]) -> SourceManifest:
    tr = SourceEntry(
        kind="translation", api_id="BSB", name="BSB", license="PD", origin="helloao:BSB"
    )
    for code in KJV_VERSES:
        doc = full_translation(code)
        if code == "MRK":  # omit 7:16, as the BSB does
            doc["chapters"][6]["items"] = [
                i for i in doc["chapters"][6]["items"] if i["number"] != 16
            ]
        put(paths, tr, "bsb", code, doc)
    co = SourceEntry(
        kind="commentary", api_id="JFB", name="JFB", license="PD", origin="crosswire:JFB@3.0"
    )
    put(paths, co, "jamieson-fausset-brown", "MRK", mark_commentary)
    manifest = SourceManifest(
        bucket="b", api_version="V1", sources={"bsb": tr, "jamieson-fausset-brown": co}
    )
    write_json(paths.manifest, manifest.to_doc())
    return manifest


GOOD_MARK = {
    "book": "MRK",
    "chapters": [
        {
            "number": c,
            "introduction": {"text": f"Chapter {c}", "refs": ["MAT 12:9-21"]},
            "items": [],
        }
        for c in range(1, 17)
    ]
    + [],
}


def test_clean_snapshot_passes_with_summary(tmp_path: Path) -> None:
    paths = RepoPaths(tmp_path)
    doc = {**GOOD_MARK, "chapters": [dict(c) for c in GOOD_MARK["chapters"]]}
    doc["chapters"][3]["items"] = [
        {"verse": 1, "verseEnd": 20, "text": "On the sower", "refs": []},
        {"verse": 21, "text": "On the lamp", "refs": ["LUK 8:16"]},
    ]
    manifest = snapshot_with(paths, doc)
    report = check_sources(store=SourceStore.local(paths), manifest=manifest)
    assert report.ok
    bsb, jfb = report.sources
    assert bsb.summary.startswith("31,101 verses") and "MRK 7:16" in bsb.summary
    assert (
        "2 notes covering 3% of verses" in jfb.summary and "17 references" in jfb.summary
    )  # 16 chapter intros + 1
    assert len(jfb.warnings) == 65  # the other books aren't in this test snapshot


def test_misplaced_and_overlapping_notes_fail(tmp_path: Path) -> None:
    paths = RepoPaths(tmp_path)
    doc = {**GOOD_MARK, "chapters": [dict(c) for c in GOOD_MARK["chapters"]]}
    doc["chapters"][3]["items"] = [
        {"verse": 1, "verseEnd": 20, "text": "a"},
        {"verse": 10, "text": "overlaps"},
        {"verse": 42, "text": "Mark 4 has 41 verses"},
    ]
    doc["chapters"].append({"number": 17, "items": [{"verse": 1, "text": "no chapter 17"}]})
    del doc["chapters"][14]  # chapter 15: a warning, not an error
    manifest = snapshot_with(paths, doc)
    report = check_sources(store=SourceStore.local(paths), manifest=manifest)
    assert not report.ok
    jfb = report.sources[1]
    assert jfb.errors == [
        "MRK 4:10: out of order or overlapping",
        "MRK 4:42-42: outside 1 to 41",
        "MRK 17: chapter out of range",
    ]
    assert "MRK: no notes on chapters [15]" in jfb.warnings


def test_cli_exit_codes(tmp_path: Path, monkeypatch: Any) -> None:
    paths = RepoPaths(tmp_path)
    monkeypatch.setattr(snapshot, "repo_paths", lambda: paths)
    snapshot_with(paths, GOOD_MARK)
    ok = CliRunner().invoke(app, ["sources", "check"])
    assert ok.exit_code == 0, ok.output
    assert "jamieson-fausset-brown [crosswire:JFB@3.0]: ok" in ok.output
    (paths.sources / "bsb" / "GEN.json").unlink()
    bad = CliRunner().invoke(app, ["sources", "check"])
    assert bad.exit_code == 2 and "bsb/GEN.json" in bad.output
