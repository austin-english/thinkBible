# Contract: published pack layout (S3 + CloudFront)

This is the interface the iPhone app (spec 002) reads. One bucket and one CloudFront distribution
exist per environment (`dev`, `prod`).

```
/v1/index.json                                      → index.schema.json
/v1/books/{book}/{packVersion}/study.json           → study-pack.schema.json
/v1/books/{book}/{packVersion}/verses/{tr}.json     → verses.schema.json
```

- `{book}` is the lowercase USFM code (`mrk`). `{packVersion}` is semver (`1.0.0`). `{tr}` is the
  translation id (`bsb`, `kjv`).
- `v1` is the pack **format** major version. A breaking format change publishes under `/v2/` while
  `/v1/` stays for older app builds.

| Path | Cache-Control | Notes |
|---|---|---|
| `/v1/index.json` | `public, max-age=300` | Rewritten on every publish. CloudFront invalidates this one path |
| `/v1/books/**` | `public, max-age=31536000, immutable` | Never overwritten. A new version gets a new path |

- **Compression**: CloudFront compression is on (gzip and brotli) for `application/json`.
- **Integrity**: `index.json` gives the sha256 and byte size of every file. The app checks the
  sha256 before replacing a cached pack.
- **Access**: the bucket is private, and only CloudFront can read it (origin access control).
  There is no listing, and the path layout is the API.
- **Record of what was published**: S3 itself. Versioned paths are never overwritten, and
  bucket versioning is on. There is no copy in git. The publish check downloads the previous
  version's `study.json` through `index.json`.
- **Bundled copy**: the app bundles the launch book's current version (spec 002). Its files are
  byte-identical to the published files.
