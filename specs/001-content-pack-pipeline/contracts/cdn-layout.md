# Contract: published pack layout (S3 + CloudFront)

This is the interface the iPhone app (spec 002) reads. There is one packs bucket and one
CloudFront distribution, with two **channels** (revised 2026-11-13: one AWS environment):

- `draft/`: what `publish` writes after a passing gate. The owner's TestFlight and debug builds
  read it. It MAY be republished from scratch.
- `live/`: what readers get. Only `promote` writes it, copying a draft version byte for byte.
  Updates are additive (FR-024).

```
/{channel}/v1/index.json                                      → index.schema.json
/{channel}/v1/books/{book}/{packVersion}/study.json           → study-pack.schema.json
/{channel}/v1/books/{book}/{packVersion}/verses/{tr}.json     → verses.schema.json
```

- `{channel}` is `draft` or `live`. An App Store build reads only `live`.
- `{book}` is the lowercase USFM code (`mrk`). `{packVersion}` is semver (`1.0.0`). `{tr}` is the
  translation id (`bsb`, `kjv`).
- `v1` is the pack **format** major version. A breaking format change publishes under `/v2/` while
  `/v1/` stays for older app builds.

| Path | Cache-Control | Notes |
|---|---|---|
| `/{channel}/v1/index.json` | `public, max-age=300` | Rewritten on every publish or promotion. CloudFront invalidates this one path |
| `/live/v1/books/**` | `public, max-age=31536000, immutable` | Never overwritten. A new version gets a new path |
| `/draft/v1/books/**` | `public, max-age=300` | May be replaced when the draft channel is republished |

- **Compression**: CloudFront compression is on (gzip and brotli) for `application/json`.
- **Integrity**: `index.json` gives the sha256 and byte size of every file. The app checks the
  sha256 before replacing a cached pack.
- **Access**: the bucket is private, and only CloudFront can read it (origin access control).
  There is no listing, and the path layout is the API.
- **Record of what was published**: S3 itself. Live versioned paths are never overwritten, and
  bucket versioning is on. There is no copy in git. The publish check downloads the previous
  live version's `study.json` through `/live/v1/index.json`.
- **Bundled copy**: the app bundles the launch book's current version (spec 002). Its files are
  byte-identical to the published files.
