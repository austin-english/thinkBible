# Test fixtures

- `api/`: small, trimmed copies of Free Use Bible API responses (US4 tests).
- `model_outputs/{stage}/{section_id}.json`: recorded model outputs replayed by `FakeRunner`.

Fixtures may contain short excerpts of public-domain text. Never put a full source book here; the
frozen snapshot lives in S3 and the local cache `content/sources/` (gitignored).
