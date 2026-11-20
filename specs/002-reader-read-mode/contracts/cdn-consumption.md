# Contract: how the app reads a content channel

The producer's side is `specs/001-content-pack-pipeline/contracts/cdn-layout.md` and the JSON
Schemas in `content/schema/`. This file is the consumer's side: what the iOS app requests, what
it checks, and what it does when something fails. The app only reads; it never writes to the CDN.

## Base URL and channel

- `CONTENT_BASE_URL` (per build configuration, in `ios/Config/*.xcconfig`): the CloudFront
  domain, today `https://d2ne647g2cqb22.cloudfront.net`. A custom domain can replace it later
  without an app change to the paths.
- `CONTENT_CHANNEL`: `draft` (Debug, Beta) or `live` (Release). Fixed per build (research R3).

## Requests

| Request | When | Expect |
|---|---|---|
| `GET {base}/{channel}/v1/index.json` | launch and return to foreground, at most once an hour | a `PackIndex` (`index.schema.json`) |
| `GET {base}/{channel}/{entry.study.path}` | a book's `latest` is newer than the version it reads | a `StudyPack` |
| `GET {base}/{channel}/{entry.verses[tr].path}` | the same, once per translation | a `VerseText` |

Paths in the index are relative to the channel root (`v1/books/mrk/1.2.1/study.json`). Pack
version folders are immutable on the live channel, and may be replaced on the draft channel
(cdn-layout.md), so a file is always checked against the index it was listed in.

No other URL is fetched. There are no query strings, cookies or identifiers in these requests.

## Checks before a pack is used

1. Each file's byte count and sha256 equal the index entry's `bytes` and `sha256`.
2. The study pack and each verse file decode strictly and validate (research R8).
3. Every translation listed in the study pack's `translations` was downloaded and matches its
   `sha256` there too.
4. `formatVersion` is 1, and `minAppFormatVersion` (if present) is at most what the app supports.

Only then is the version `ready`; it becomes `active` at the next launch
(data-model.md, PackStore).

## Failure handling

| Case | App behavior |
|---|---|
| No network | Use the cached catalog and active packs, or the bundled ones. Nothing is shown to the reader |
| `index.json` returns 403 or 404 | The channel has nothing published (the live channel before the first promotion). Keep the previous catalog and the bundled books. Not an error |
| `index.json` 5xx, timeout, or invalid | Keep the previous catalog; retry at the next launch or return to foreground |
| A pack file's sha256 or size doesn't match | Delete the download, keep the current pack, log `pack_rejected(book, version, reason)` |
| A pack fails decoding or validation | Same as above |
| A book disappears from the index | Keep reading the version on the device; it is no longer listed as published for new readers |

The reading path never shows an error, a spinner over the page, or a blank card because of the
network (spec US4).

## Bundling (build time)

`make ios-packs CHANNEL=draft|live` fetches the same `index.json` and files with the same checks,
and writes them under `ios/ThinkBible/Resources/Packs/{channel}/` in the CDN's layout
(`v1/index.json`, `v1/books/...`). The folder is gitignored. The Xcode build fails if the folder is
missing or its channel differs from `CONTENT_CHANNEL`.
