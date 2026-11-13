"""The importer (T034, T034a), driven by recorded API responses and synthetic CrossWire modules:
no network in tests."""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from thinkbible_pipeline.jsonio import read_json, write_json
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources.importer import (
    SOURCES,
    FetchError,
    HttpFetcher,
    NotFound,
    import_sources,
)
from thinkbible_pipeline.sources.models import (
    NormalizedCommentaryBook,
    NormalizedTranslationBook,
    SourceManifest,
)
from thinkbible_pipeline.sources.snapshot import SourceStore, load_book, verify

API = Path(__file__).resolve().parents[1] / "fixtures" / "api"
NOW = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
COMMENTARIES = ("matthew-henry", "jamieson-fausset-brown", "adam-clarke")


def fixture(name: str) -> Any:
    return json.loads((API / f"{name}.json").read_text(encoding="utf-8"))


class FakeFetcher:
    """Serves recorded fixtures and synthetic CrossWire modules; other chapters are made up."""

    def __init__(self, sword_zip: Any, missing: set[str] | None = None, version: str = "1.0"):
        self.missing = missing or set()
        self.paths: list[str] = []
        self.downloads: list[str] = []
        self._sword_zip = sword_zip
        self.version = version

    def json(self, path: str) -> Any:
        self.paths.append(path)
        if path in self.missing:
            raise NotFound(path)
        if path == "/api/available_translations.json":
            return fixture("available_translations")
        if path in ("/api/BSB/books.json", "/api/eng_kjv/books.json"):
            return fixture("BSB_books")
        source, book, chapter = path.removeprefix("/api/").removesuffix(".json").split("/")
        name = f"{source}_{book}_{chapter}"
        if (API / f"{name}.json").is_file():
            return fixture(name)
        return {
            "chapter": {
                "number": int(chapter),
                "footnotes": [],
                "content": [{"type": "verse", "number": 1, "content": ["Text."]}],
            }
        }

    def text(self, url: str) -> str:
        return "# Changelog\n\n## V1.16.0\n\n### API Changes\n\n## V1.15.0\n"

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        module = url.rsplit("/", 1)[-1].removesuffix(".zip")
        entries = {
            ("MRK", 1, 1): f"<hi>{module} on Mark 1:1</hi>",
            ("MRK", 1, 2): f"{module} on Mark 1:2-3",
            (
                "MRK",
                3,
                0,
            ): '<reference osisRef="Matt.12.9-Matt.12.21">See on Mt 12:9-21</reference>',
        }
        return bytes(
            self._sword_zip(
                entries, name=module, version=self.version, links={("MRK", 1, 3): ("MRK", 1, 2)}
            )
        )


def run(paths: RepoPaths, fetch: FakeFetcher, **kw: Any) -> Any:
    return import_sources(bucket="b", fetch=fetch, paths=paths, now=NOW, echo=lambda _l: None, **kw)


def test_imports_mark_from_all_five_sources(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    fetch = FakeFetcher(sword_zip)
    result = run(paths, fetch, books=["MRK"])
    assert result.api_version == "V1.16.0" and result.snapshot_id == "2026-11-12"
    assert sorted(result.written) == sorted(f"{s}/MRK" for s in ("bsb", "kjv", *COMMENTARIES))
    manifest = SourceManifest.model_validate(read_json(paths.manifest))
    assert manifest.bucket == "b" and manifest.api_version == "V1.16.0"
    bsb = manifest.sources["bsb"]
    assert bsb.upstream_sha256 and bsb.upstream_sha256.startswith("788081b7")
    assert bsb.license == "Public domain" and bsb.origin == "helloao:BSB"
    bf = bsb.books["MRK"]
    assert bf.s3_key == "snapshots/2026-11-12/bsb/MRK.json" and bf.file == "bsb/MRK.json"
    # Commentaries: one CrossWire module zip each, archived next to the books made from it.
    assert sorted(fetch.downloads) == sorted(SOURCES[c].module_url for c in COMMENTARIES)
    clarke = manifest.sources["adam-clarke"]
    assert clarke.origin == "crosswire:Clarke@1.0" and clarke.api_id == "Clarke"
    assert clarke.tradition == "Wesleyan (Methodist)" and clarke.license == "Public Domain"
    assert clarke.module is not None and clarke.module.version == "1.0"
    assert clarke.module.file == "adam-clarke/_module/Clarke-1.0.zip"
    assert clarke.module.s3_key == "snapshots/2026-11-12/adam-clarke/_module/Clarke-1.0.zip"
    # Every file written (books and modules) matches the manifest.
    store = SourceStore.local(paths)
    assert verify(store=store, manifest=manifest) == []
    book = load_book("bsb", "MRK", store=store, manifest=manifest)
    assert isinstance(book, NormalizedTranslationBook)
    seven = next(c for c in book.chapters if c.number == 7)
    assert 16 not in [v.number for v in seven.verses()]
    henry = load_book("matthew-henry", "MRK", store=store, manifest=manifest)
    assert isinstance(henry, NormalizedCommentaryBook)
    one = henry.chapters[0]
    assert [(i.verse, i.verse_end) for i in one.items] == [(1, None), (2, 3)]
    three = henry.chapters[1]
    assert three.introduction is not None and three.introduction.refs == ["MAT 12:9-21"]
    # One chapter request per chapter for the translations: 16 each.
    assert sum(1 for p in fetch.paths if "/MRK/" in p) == 2 * 16


def test_books_a_commentary_lacks_are_absent_not_errors(tmp_path: Path, sword_zip: Any) -> None:
    result = run(RepoPaths(tmp_path), FakeFetcher(sword_zip), books=["MRK", "DEU"],
                 sources=["adam-clarke"])  # fmt: skip
    assert result.written == ["adam-clarke/MRK"]
    assert result.absent == ["adam-clarke/DEU"]


def test_missing_translation_chapter_is_an_error(tmp_path: Path, sword_zip: Any) -> None:
    fetch = FakeFetcher(sword_zip, missing={"/api/BSB/MRK/3.json"})
    with pytest.raises(NotFound):
        run(RepoPaths(tmp_path), fetch, books=["MRK"], sources=["bsb"])


def test_reimport_keeps_other_sources_in_the_manifest(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["bsb"])
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["jamieson-fausset-brown"])
    manifest = SourceManifest.model_validate(read_json(paths.manifest))
    assert set(manifest.sources) == {"bsb", "jamieson-fausset-brown"}
    assert manifest.api_version == "V1.16.0"  # a commentary-only import leaves it alone


def test_rerun_skips_books_already_imported(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["bsb"])
    again = FakeFetcher(sword_zip)
    result = run(paths, again, books=["MRK", "GEN"], sources=["bsb"])
    assert result.skipped == ["bsb/MRK"] and result.written == ["bsb/GEN"]
    assert not any("/MRK/" in p for p in again.paths)
    manifest = SourceManifest.model_validate(read_json(paths.manifest))
    assert set(manifest.sources["bsb"].books) == {"MRK", "GEN"}


def test_commentary_rerun_uses_the_archived_module(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["adam-clarke"])
    again = FakeFetcher(sword_zip)
    result = run(paths, again, books=["MRK", "JHN"], sources=["adam-clarke"])
    assert again.downloads == []  # no network: the archived zip is read
    assert result.skipped == ["adam-clarke/MRK"] and result.modules == [
        "Clarke 1.0 (archived copy)"
    ]
    refreshed = FakeFetcher(sword_zip)
    result = run(paths, refreshed, books=["MRK"], sources=["adam-clarke"], refresh=True)
    assert len(refreshed.downloads) == 1 and result.written == ["adam-clarke/MRK"]


def test_new_module_version_reimports_every_book(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["adam-clarke"])
    newer = FakeFetcher(sword_zip, version="2.0")
    result = run(paths, newer, books=["MRK"], sources=["adam-clarke"], refresh=True)
    assert result.written == ["adam-clarke/MRK"]
    entry = SourceManifest.model_validate(read_json(paths.manifest)).sources["adam-clarke"]
    assert entry.origin == "crosswire:Clarke@2.0"
    assert entry.module is not None and entry.module.file.endswith("Clarke-2.0.zip")


def test_old_helloao_commentary_entries_are_replaced(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["bsb"])
    manifest = read_json(paths.manifest)
    bsb = manifest["sources"]["bsb"]
    del bsb["origin"]  # written before `origin` existed: adopted, not re-fetched
    manifest["sources"]["adam-clarke"] = {**bsb, "kind": "commentary", "apiId": "adam-clarke"}
    write_json(paths.manifest, manifest)
    fetch = FakeFetcher(sword_zip)
    result = run(paths, fetch, books=["MRK"], sources=["bsb", "adam-clarke"])
    assert result.skipped == ["bsb/MRK"] and result.written == ["adam-clarke/MRK"]
    after = SourceManifest.model_validate(read_json(paths.manifest)).sources
    assert after["bsb"].origin == "helloao:BSB"
    assert after["adam-clarke"].api_id == "Clarke"


def test_changed_cache_file_or_refresh_fetches_again(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["bsb"])
    (paths.sources / "bsb" / "MRK.json").write_text("{}")
    assert run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["bsb"]).written
    refreshed = run(paths, FakeFetcher(sword_zip), books=["MRK"], sources=["bsb"], refresh=True)
    assert refreshed.written == ["bsb/MRK"] and refreshed.skipped == []


def test_interrupted_import_keeps_finished_books(tmp_path: Path, sword_zip: Any) -> None:
    paths = RepoPaths(tmp_path)
    fetch = FakeFetcher(sword_zip, missing={"/api/BSB/GEN/2.json"})
    with pytest.raises(NotFound):
        run(paths, fetch, books=["MRK", "GEN"], sources=["bsb"])
    manifest = SourceManifest.model_validate(read_json(paths.manifest))
    assert set(manifest.sources["bsb"].books) == {"MRK"}


class Response(io.BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_a: object) -> None:
        self.close()


def test_http_fetcher_retries_politely() -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def opener(request: urllib.request.Request, timeout: float) -> Response:
        calls.append(request.full_url)
        assert request.get_header("User-agent") == "ThinkBible-import/1.0"
        if len(calls) <= 2:
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)  # type: ignore[arg-type]
        return Response(b'{"ok": true}')

    clock = iter(float(i) for i in range(100))
    fetch = HttpFetcher(opener=opener, sleep=sleeps.append, clock=lambda: next(clock))
    assert fetch.json("/api/BSB/MRK/1.json") == {"ok": True}
    assert calls[0] == "https://bible.helloao.org/api/BSB/MRK/1.json" and len(calls) == 3
    assert [s for s in sleeps if s >= 1] == [1.0, 2.0]  # exponential backoff


def test_http_fetcher_404_and_giving_up() -> None:
    def not_found(request: urllib.request.Request, timeout: float) -> Response:
        raise urllib.error.HTTPError(request.full_url, 404, "nope", {}, None)  # type: ignore[arg-type]

    with pytest.raises(NotFound):
        HttpFetcher(opener=not_found, sleep=lambda _s: None).json("/api/x.json")

    def down(request: urllib.request.Request, timeout: float) -> Response:
        raise urllib.error.URLError("unreachable")

    with pytest.raises(FetchError, match="after 2 retries"):
        HttpFetcher(opener=down, retries=2, sleep=lambda _s: None).json("/api/x.json")
