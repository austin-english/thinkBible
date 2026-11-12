"""``import``: fetch and normalise the five sources once, into the local cache (research R1, R2).

This is the **only** module allowed to fetch text over the network (constitution II,
``tests/unit/test_network_guard.py``). It asks politely: one request at a time, about two per
second, with a generic User-Agent and exponential backoff on errors.

The output is ``content/sources/{source}/{BOOK}.json`` (gitignored) plus an updated
``content/sources/manifest.json`` (committed after ``sources push``). Each file gets a snapshot
ID (today's date), its sha256, and the S3 key it will have in the write-once sources bucket.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from thinkbible_core.ids import BOOKS
from thinkbible_pipeline.jsonio import canonical_json, read_json, sha256_hex, write_json
from thinkbible_pipeline.paths import RepoPaths, repo_paths
from thinkbible_pipeline.sources.models import BookFile, SourceEntry, SourceManifest
from thinkbible_pipeline.sources.normalize import (
    normalize_commentary_book,
    normalize_translation_book,
)
from thinkbible_pipeline.storage import LocalBlobStore

API_BASE = "https://bible.helloao.org"
CHANGELOG_URL = "https://raw.githubusercontent.com/HelloAOLab/bible-api/main/CHANGELOG.md"
USER_AGENT = "ThinkBible-import/1.0"


@dataclass(frozen=True)
class SourceSpec:
    kind: Literal["translation", "commentary"]
    api_id: str
    name: str
    tradition: str | None = None

    @property
    def api_root(self) -> str:
        return f"/api/{self.api_id}" if self.kind == "translation" else f"/api/c/{self.api_id}"

    def chapter_path(self, book: str, chapter: int) -> str:
        return f"{self.api_root}/{book}/{chapter}.json"


SOURCES: dict[str, SourceSpec] = {
    "bsb": SourceSpec("translation", "BSB", "Berean Standard Bible"),
    "kjv": SourceSpec("translation", "eng_kjv", "King James Version"),
    "matthew-henry": SourceSpec(
        "commentary", "matthew-henry", "Matthew Henry's Commentary", "Reformed (Presbyterian)"
    ),
    "jamieson-fausset-brown": SourceSpec(
        "commentary", "jamieson-fausset-brown", "Jamieson-Fausset-Brown", "Reformed-leaning"
    ),
    "adam-clarke": SourceSpec(
        "commentary", "adam-clarke", "Adam Clarke's Commentary", "Wesleyan (Methodist)"
    ),
}


class NotFound(Exception):
    pass


class FetchError(Exception):
    pass


class Fetcher(Protocol):
    def json(self, path: str) -> Any:
        """GET ``API_BASE + path`` (or an absolute URL) and parse JSON. Raises ``NotFound``."""
        ...

    def text(self, url: str) -> str: ...


Opener = Callable[[urllib.request.Request, float], Any]


def _open(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


class HttpFetcher:
    """Polite HTTP: one request at a time, ``min_interval`` apart, with exponential backoff."""

    def __init__(
        self,
        *,
        min_interval: float = 0.5,
        retries: int = 5,
        timeout: float = 30.0,
        opener: Opener = _open,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self.retries = retries
        self.timeout = timeout
        self._open = opener
        self._sleep = sleep
        self._clock = clock
        self._last = -1e9
        self.requests = 0

    def _get(self, url: str) -> bytes:
        if not url.startswith("https://"):
            url = API_BASE + url
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        delay = 1.0
        for attempt in range(self.retries + 1):
            wait = self._last + self.min_interval - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()
            self.requests += 1
            try:
                with self._open(request, self.timeout) as resp:
                    data: bytes = resp.read()
                    return data
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NotFound(url) from e
                if e.code != 429 and e.code < 500:
                    raise FetchError(f"{url}: HTTP {e.code}") from e
                error: Exception = e
            except (urllib.error.URLError, TimeoutError) as e:
                error = e
            if attempt == self.retries:
                raise FetchError(f"{url}: {error} (after {self.retries} retries)") from error
            self._sleep(delay)
            delay *= 2
        raise AssertionError("unreachable")

    def json(self, path: str) -> Any:
        return json.loads(self._get(path))

    def text(self, url: str) -> str:
        return self._get(url).decode("utf-8")


def latest_api_version(fetch: Fetcher) -> str:
    """The top ``## V…`` heading of the HelloAO CHANGELOG, e.g. ``V1.16.0``."""
    match = re.search(r"^##\s+(V\d+\.\d+\.\d+)", fetch.text(CHANGELOG_URL), re.MULTILINE)
    if not match:
        raise FetchError("no version heading in the HelloAO CHANGELOG; pass --api-version")
    return match.group(1)


def _license(meta: dict[str, Any], kind: str) -> str:
    if kind == "translation":
        lic = meta.get("license") or {}
        return "Public domain" if lic.get("publicDomain") else str(meta.get("licenseUrl", ""))
    url = str(meta.get("licenseUrl", ""))
    return "Public Domain Mark 1.0" if "publicdomain/mark/1.0" in url else url


@dataclass
class ImportResult:
    snapshot_id: str
    api_version: str
    written: list[str] = field(default_factory=list)  # "bsb/MRK"
    absent: list[str] = field(default_factory=list)  # books a commentary doesn't cover
    missing_chapters: list[str] = field(default_factory=list)  # "adam-clarke/MRK/3"


def import_sources(
    *,
    books: Iterable[str] | None = None,
    sources: Iterable[str] | None = None,
    bucket: str,
    fetch: Fetcher | None = None,
    paths: RepoPaths | None = None,
    api_version: str | None = None,
    now: datetime | None = None,
    echo: Callable[[str], None] = print,
) -> ImportResult:
    """Fetch, normalise and cache ``books`` (USFM codes; all 66 when None) for ``sources``."""
    fetch = fetch or HttpFetcher()
    paths = paths or repo_paths()
    now = now or datetime.now(UTC)
    snapshot_id = now.date().isoformat()
    wanted_books = list(books) if books is not None else [b.code for b in BOOKS]
    wanted_sources = list(sources) if sources is not None else list(SOURCES)
    unknown = [s for s in wanted_sources if s not in SOURCES]
    if unknown:
        raise ValueError(f"unknown sources {unknown}; expected {list(SOURCES)}")

    manifest = (
        SourceManifest.model_validate(read_json(paths.manifest))
        if paths.manifest.is_file()
        else SourceManifest(bucket=bucket, api_version="")
    )
    manifest.bucket = bucket
    manifest.api_version = api_version or latest_api_version(fetch)
    result = ImportResult(snapshot_id=snapshot_id, api_version=manifest.api_version)

    catalog: dict[str, dict[str, Any]] = {}
    if any(SOURCES[s].kind == "translation" for s in wanted_sources):
        for t in fetch.json("/api/available_translations.json")["translations"]:
            catalog[t["id"]] = t
    if any(SOURCES[s].kind == "commentary" for s in wanted_sources):
        for c in fetch.json("/api/available_commentaries.json")["commentaries"]:
            catalog[c["id"]] = c

    cache = LocalBlobStore(paths.sources)
    for key in wanted_sources:
        spec = SOURCES[key]
        meta = catalog.get(spec.api_id, {})
        entry = manifest.sources.get(key) or SourceEntry(
            kind=spec.kind, api_id=spec.api_id, name=spec.name, license=""
        )
        entry.name = spec.name
        entry.license = _license(meta, spec.kind)
        entry.license_url = meta.get("licenseUrl")
        entry.upstream_sha256 = meta.get("sha256")
        entry.tradition = spec.tradition
        available = {b["id"]: b for b in fetch.json(f"{spec.api_root}/books.json")["books"]}

        for book in wanted_books:
            info = available.get(book)
            if info is None:
                result.absent.append(f"{key}/{book}")
                continue
            first = int(info.get("firstChapterNumber") or 1)
            last = int(info.get("lastChapterNumber") or info["numberOfChapters"])
            raws = []
            for chapter in range(first, last + 1):
                try:
                    raws.append(fetch.json(spec.chapter_path(book, chapter)))
                except NotFound:
                    if spec.kind == "translation":
                        raise
                    result.missing_chapters.append(f"{key}/{book}/{chapter}")
            if spec.kind == "translation":
                doc = normalize_translation_book(book, raws).to_doc()
            else:
                intro = raws[0].get("book", {}).get("introduction") if raws else None
                doc = normalize_commentary_book(book, intro, raws).to_doc()
            data = canonical_json(doc).encode()
            rel = f"{key}/{book}.json"
            cache.put(rel, data)
            entry.books[book] = BookFile(
                file=rel,
                s3_key=f"snapshots/{snapshot_id}/{key}/{book}.json",
                sha256=sha256_hex(data),
                bytes=len(data),
                retrieved_at=now.isoformat(timespec="seconds"),
                snapshot_id=snapshot_id,
            )
            result.written.append(f"{key}/{book}")
            echo(f"  {key}/{book}: {len(raws)} chapters, {len(data):,} bytes")
        manifest.sources[key] = entry
        # Save after each source, so an interrupted import keeps what it finished.
        write_json(paths.manifest, manifest.to_doc())
    return result
