"""``import``: fetch and normalise the five sources once, into the local cache (research R1, R2).

This is the **only** module allowed to fetch over the network (constitution II,
``tests/unit/test_network_guard.py``). Two upstreams:

- **Translations** (BSB, KJV): the Free Use Bible API (HelloAO), one JSON request per chapter.
- **Commentaries** (Henry, JFB, Clarke): CrossWire's public-domain SWORD modules, one zip per
  commentary (R2a). The zip is archived in the snapshot next to the books made from it, and
  ``sword.py`` reads it offline. HelloAO's commentary data was hand-copied and has shifted and
  missing chapters (R2a), so it isn't used.

It asks politely: one request at a time, about two per second, with a generic User-Agent and
exponential backoff on errors.

The output is ``content/sources/{source}/{BOOK}.json`` (gitignored) plus an updated
``content/sources/manifest.json`` (committed after ``sources push``). Each file gets a snapshot
ID (today's date), its sha256, and the S3 key it will have in the write-once sources bucket.

The manifest is saved after every book, and a re-run skips books that are already in it, came
from the same upstream edition (``origin``) and whose cached file still matches, so an interrupted
``import --all`` picks up where it stopped. A commentary re-run reads its archived module zip
instead of downloading it again. ``refresh=True`` (``--refresh``) downloads and converts
everything again.
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
from thinkbible_pipeline.sources.models import (
    BookFile,
    ModuleFile,
    SourceEntry,
    SourceManifest,
)
from thinkbible_pipeline.sources.normalize import normalize_translation_book
from thinkbible_pipeline.sources.sword import SwordCommentary
from thinkbible_pipeline.storage import LocalBlobStore

API_BASE = "https://bible.helloao.org"
CHANGELOG_URL = "https://raw.githubusercontent.com/HelloAOLab/bible-api/main/CHANGELOG.md"
CROSSWIRE_RAWZIP = "https://www.crosswire.org/ftpmirror/pub/sword/packages/rawzip"
USER_AGENT = "ThinkBible-import/1.0"


@dataclass(frozen=True)
class SourceSpec:
    """``api_id`` is the HelloAO translation ID, or the CrossWire module name for commentaries."""

    kind: Literal["translation", "commentary"]
    api_id: str
    name: str
    tradition: str | None = None

    @property
    def api_root(self) -> str:
        return f"/api/{self.api_id}"

    def chapter_path(self, book: str, chapter: int) -> str:
        return f"{self.api_root}/{book}/{chapter}.json"

    @property
    def module_url(self) -> str:
        return f"{CROSSWIRE_RAWZIP}/{self.api_id}.zip"


SOURCES: dict[str, SourceSpec] = {
    "bsb": SourceSpec("translation", "BSB", "Berean Standard Bible"),
    "kjv": SourceSpec("translation", "eng_kjv", "King James Version"),
    "matthew-henry": SourceSpec(
        "commentary", "MHC", "Matthew Henry's Commentary", "Reformed (Presbyterian)"
    ),
    "jamieson-fausset-brown": SourceSpec(
        "commentary", "JFB", "Jamieson-Fausset-Brown", "Reformed-leaning"
    ),
    "adam-clarke": SourceSpec(
        "commentary", "Clarke", "Adam Clarke's Commentary", "Wesleyan (Methodist)"
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

    def download(self, url: str) -> bytes: ...


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
        timeout: float = 120.0,
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

    def download(self, url: str) -> bytes:
        return self._get(url)


def latest_api_version(fetch: Fetcher) -> str:
    """The top ``## V…`` heading of the HelloAO CHANGELOG, e.g. ``V1.16.0``."""
    match = re.search(r"^##\s+(V\d+\.\d+\.\d+)", fetch.text(CHANGELOG_URL), re.MULTILINE)
    if not match:
        raise FetchError("no version heading in the HelloAO CHANGELOG; pass --api-version")
    return match.group(1)


def _translation_license(meta: dict[str, Any]) -> str:
    lic = meta.get("license") or {}
    return "Public domain" if lic.get("publicDomain") else str(meta.get("licenseUrl", ""))


@dataclass
class ImportResult:
    snapshot_id: str
    api_version: str
    written: list[str] = field(default_factory=list)  # "bsb/MRK"
    skipped: list[str] = field(default_factory=list)  # already imported and still matching
    absent: list[str] = field(default_factory=list)  # books a source doesn't cover
    modules: list[str] = field(default_factory=list)  # "JFB 3.0 (downloaded)" / "(archived)"


@dataclass
class _Context:
    paths: RepoPaths
    cache: LocalBlobStore
    fetch: Fetcher
    manifest: SourceManifest
    result: ImportResult
    snapshot_id: str
    now: datetime
    refresh: bool
    echo: Callable[[str], None]

    def matches(self, entry: SourceEntry, origin: str, book: str) -> bool:
        done = entry.books.get(book)
        return (
            not self.refresh
            and entry.origin == origin
            and done is not None
            and _cached_matches(self.paths, done)
        )

    def file(self, rel: str, data: bytes) -> BookFile:
        self.cache.put(rel, data)
        return BookFile(
            file=rel,
            s3_key=f"snapshots/{self.snapshot_id}/{rel}",
            sha256=sha256_hex(data),
            bytes=len(data),
            retrieved_at=self.now.isoformat(timespec="seconds"),
            snapshot_id=self.snapshot_id,
        )

    def save(self) -> None:
        write_json(self.paths.manifest, self.manifest.to_doc())


def import_sources(
    *,
    books: Iterable[str] | None = None,
    sources: Iterable[str] | None = None,
    bucket: str,
    fetch: Fetcher | None = None,
    paths: RepoPaths | None = None,
    api_version: str | None = None,
    now: datetime | None = None,
    refresh: bool = False,
    echo: Callable[[str], None] = print,
) -> ImportResult:
    """Fetch, normalise and cache ``books`` (USFM codes; all 66 when None) for ``sources``."""
    fetch = fetch or HttpFetcher()
    paths = paths or repo_paths()
    now = now or datetime.now(UTC)
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
    translations = [s for s in wanted_sources if SOURCES[s].kind == "translation"]
    if translations:  # the API version only describes the HelloAO translations
        manifest.api_version = api_version or latest_api_version(fetch)
    ctx = _Context(
        paths=paths,
        cache=LocalBlobStore(paths.sources),
        fetch=fetch,
        manifest=manifest,
        result=ImportResult(snapshot_id=now.date().isoformat(), api_version=manifest.api_version),
        snapshot_id=now.date().isoformat(),
        now=now,
        refresh=refresh,
        echo=echo,
    )
    if translations:
        listing = fetch.json("/api/available_translations.json")["translations"]
        catalog = {t["id"]: t for t in listing}
        for key in translations:
            _import_translation(ctx, key, catalog.get(SOURCES[key].api_id, {}), wanted_books)
    for key in wanted_sources:
        if SOURCES[key].kind == "commentary":
            _import_commentary(ctx, key, wanted_books)
    if ctx.result.skipped:
        echo(f"  skipped {len(ctx.result.skipped)} books already imported (--refresh to redo)")
    return ctx.result


def _entry(ctx: _Context, key: str, origin: str) -> SourceEntry:
    """The manifest entry for ``key``. A new upstream edition starts its book list afresh.

    Entries written before ``origin`` existed are adopted when the upstream ID is unchanged
    (the HelloAO translations); the old HelloAO commentaries had other IDs, so they're replaced.
    """
    spec = SOURCES[key]
    entry = ctx.manifest.sources.get(key)
    same = entry is not None and entry.api_id == spec.api_id and entry.origin in (None, origin)
    if entry is None or not same:
        entry = SourceEntry(kind=spec.kind, api_id=spec.api_id, name=spec.name, license="")
    entry.origin = origin
    entry.name = spec.name
    entry.tradition = spec.tradition
    ctx.manifest.sources[key] = entry
    return entry


def _import_translation(
    ctx: _Context, key: str, meta: dict[str, Any], wanted_books: list[str]
) -> None:
    spec = SOURCES[key]
    origin = f"helloao:{spec.api_id}"
    entry = _entry(ctx, key, origin)
    entry.license = _translation_license(meta)
    entry.license_url = meta.get("licenseUrl")
    entry.upstream_sha256 = meta.get("sha256")
    available = {b["id"]: b for b in ctx.fetch.json(f"{spec.api_root}/books.json")["books"]}
    for book in wanted_books:
        info = available.get(book)
        if info is None:
            ctx.result.absent.append(f"{key}/{book}")
            continue
        if ctx.matches(entry, origin, book):
            ctx.result.skipped.append(f"{key}/{book}")
            continue
        first = int(info.get("firstChapterNumber") or 1)
        last = int(info.get("lastChapterNumber") or info["numberOfChapters"])
        raws = [ctx.fetch.json(spec.chapter_path(book, ch)) for ch in range(first, last + 1)]
        data = canonical_json(normalize_translation_book(book, raws).to_doc()).encode()
        entry.books[book] = ctx.file(f"{key}/{book}.json", data)
        ctx.result.written.append(f"{key}/{book}")
        ctx.save()  # after each book, so an interrupted import keeps what it finished
        ctx.echo(f"  {key}/{book}: {len(raws)} chapters, {len(data):,} bytes")
    ctx.save()


def _module_zip(ctx: _Context, key: str) -> tuple[bytes, bool]:
    """The CrossWire module zip: the archived copy if it still matches, else a fresh download."""
    entry = ctx.manifest.sources.get(key)
    archived = entry.module if entry is not None else None
    if not ctx.refresh and archived is not None and _cached_matches(ctx.paths, archived):
        return (ctx.paths.sources / archived.file).read_bytes(), False
    return ctx.fetch.download(SOURCES[key].module_url), True


def _import_commentary(ctx: _Context, key: str, wanted_books: list[str]) -> None:
    spec = SOURCES[key]
    data, downloaded = _module_zip(ctx, key)
    module = SwordCommentary(data)
    conf = module.conf
    origin = f"crosswire:{conf.name}@{conf.version}"
    entry = _entry(ctx, key, origin)
    entry.license = conf.license
    entry.license_url = None
    entry.upstream_sha256 = sha256_hex(data)
    rel = f"{key}/_module/{conf.name}-{conf.version}.zip"
    if downloaded or entry.module is None or entry.module.file != rel:
        bf = ctx.file(rel, data)
        entry.module = ModuleFile(
            **bf.model_dump(), name=conf.name, version=conf.version, url=spec.module_url
        )
    how = "downloaded" if downloaded else "archived copy"
    ctx.result.modules.append(f"{conf.name} {conf.version} ({how})")
    ctx.echo(f"  {key}: CrossWire {conf.name} {conf.version}, {conf.license} ({how})")
    for book in wanted_books:
        if ctx.matches(entry, origin, book):
            ctx.result.skipped.append(f"{key}/{book}")
            continue
        normalized = module.book(book)
        if normalized is None:
            ctx.result.absent.append(f"{key}/{book}")
            continue
        out = canonical_json(normalized.to_doc()).encode()
        entry.books[book] = ctx.file(f"{key}/{book}.json", out)
        ctx.result.written.append(f"{key}/{book}")
        ctx.save()
        ctx.echo(f"  {key}/{book}: {len(normalized.chapters)} chapters, {len(out):,} bytes")
    ctx.save()


def _cached_matches(paths: RepoPaths, bf: BookFile) -> bool:
    """Is this file already in the cache, byte for byte as the manifest records it?"""
    cached = paths.sources / bf.file
    return cached.is_file() and sha256_hex(cached.read_bytes()) == bf.sha256
