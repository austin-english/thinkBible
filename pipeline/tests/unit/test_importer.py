"""The importer (T034), driven by recorded API responses: no network in tests."""

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from thinkbible_pipeline.jsonio import read_json
from thinkbible_pipeline.paths import RepoPaths
from thinkbible_pipeline.sources.importer import (
    FetchError,
    HttpFetcher,
    NotFound,
    import_sources,
)
from thinkbible_pipeline.sources.models import NormalizedTranslationBook, SourceManifest
from thinkbible_pipeline.sources.snapshot import SourceStore, load_book, verify

API = Path(__file__).resolve().parents[1] / "fixtures" / "api"
NOW = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)


def fixture(name: str) -> Any:
    return json.loads((API / f"{name}.json").read_text(encoding="utf-8"))


class FakeFetcher:
    """Serves the recorded fixtures; any other chapter gets a tiny synthetic one."""

    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.paths: list[str] = []

    def json(self, path: str) -> Any:
        self.paths.append(path)
        if path in self.missing:
            raise NotFound(path)
        if path == "/api/available_translations.json":
            return fixture("available_translations")
        if path == "/api/available_commentaries.json":
            return fixture("available_commentaries")
        if path in ("/api/BSB/books.json", "/api/eng_kjv/books.json"):
            return fixture("BSB_books")
        if path.endswith("/books.json"):
            return fixture("adam-clarke_books")
        parts = path.removeprefix("/api/").removesuffix(".json").split("/")
        if parts[0] == "c":
            _, source, book, chapter = parts
            name = f"{source}_{book}_{chapter}"
            if (API / f"{name}.json").is_file():
                return fixture(name)
            return {
                "book": {"introduction": "Intro"},
                "chapter": {"number": int(chapter), "content": []},
            }
        source, book, chapter = parts
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


def test_imports_mark_from_all_five_sources(tmp_path: Path) -> None:
    paths = RepoPaths(tmp_path)
    fetch = FakeFetcher()
    result = import_sources(
        books=["MRK"],
        bucket="thinkbible-sources-test",
        fetch=fetch,
        paths=paths,
        now=NOW,
        echo=lambda _l: None,
    )
    assert result.api_version == "V1.16.0" and result.snapshot_id == "2026-11-12"
    assert sorted(result.written) == sorted(
        f"{s}/MRK" for s in ("bsb", "kjv", "matthew-henry", "jamieson-fausset-brown", "adam-clarke")
    )
    manifest = SourceManifest.model_validate(read_json(paths.manifest))
    assert manifest.bucket == "thinkbible-sources-test" and manifest.api_version == "V1.16.0"
    bsb = manifest.sources["bsb"]
    assert bsb.upstream_sha256 and bsb.upstream_sha256.startswith("788081b7")
    assert bsb.license == "Public domain"
    bf = bsb.books["MRK"]
    assert bf.s3_key == "snapshots/2026-11-12/bsb/MRK.json" and bf.file == "bsb/MRK.json"
    clarke = manifest.sources["adam-clarke"]
    assert clarke.tradition == "Wesleyan (Methodist)"
    assert clarke.license == "Public Domain Mark 1.0"
    # Every file written matches the manifest, and Mark 7 in BSB has no verse 16.
    store = SourceStore.local(paths)
    assert verify(store=store, manifest=manifest) == []
    book = load_book("bsb", "MRK", store=store, manifest=manifest)
    assert isinstance(book, NormalizedTranslationBook)
    seven = next(c for c in book.chapters if c.number == 7)
    assert 16 not in [v.number for v in seven.verses()]
    assert len(book.chapters) == 16
    # One chapter request per chapter: 16 per source.
    assert sum(1 for p in fetch.paths if "/MRK/" in p) == 5 * 16


def test_books_a_source_lacks_are_absent_not_errors(tmp_path: Path) -> None:
    result = import_sources(
        books=["MRK", "DEU"],
        sources=["adam-clarke"],
        bucket="b",
        fetch=FakeFetcher(),
        paths=RepoPaths(tmp_path),
        now=NOW,
        echo=lambda _l: None,
    )
    assert result.written == ["adam-clarke/MRK"]
    assert result.absent == ["adam-clarke/DEU"]


def test_missing_commentary_chapter_is_recorded(tmp_path: Path) -> None:
    fetch = FakeFetcher(missing={"/api/c/adam-clarke/MRK/3.json"})
    result = import_sources(
        books=["MRK"],
        sources=["adam-clarke"],
        bucket="b",
        fetch=fetch,
        paths=RepoPaths(tmp_path),
        now=NOW,
        echo=lambda _l: None,
    )
    assert result.missing_chapters == ["adam-clarke/MRK/3"]


def test_missing_translation_chapter_is_an_error(tmp_path: Path) -> None:
    fetch = FakeFetcher(missing={"/api/BSB/MRK/3.json"})
    with pytest.raises(NotFound):
        import_sources(
            books=["MRK"],
            sources=["bsb"],
            bucket="b",
            fetch=fetch,
            paths=RepoPaths(tmp_path),
            now=NOW,
            echo=lambda _l: None,
        )


def test_reimport_keeps_other_sources_in_the_manifest(tmp_path: Path) -> None:
    paths = RepoPaths(tmp_path)
    kw: dict[str, Any] = {
        "bucket": "b",
        "fetch": FakeFetcher(),
        "paths": paths,
        "now": NOW,
        "echo": lambda _l: None,
    }
    import_sources(books=["MRK"], sources=["bsb"], **kw)
    import_sources(books=["MRK"], sources=["kjv"], **kw)
    manifest = SourceManifest.model_validate(read_json(paths.manifest))
    assert set(manifest.sources) == {"bsb", "kjv"}


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
