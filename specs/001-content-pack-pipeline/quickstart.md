# Quickstart: validate the content pipeline end to end

These steps prove spec 001 works. Commands, data shapes and URLs are defined in
[contracts/](contracts/) and [data-model.md](data-model.md).

## Prerequisites

- `uv`, Python 3.12, Terraform ≥ 1.8, and the AWS CLI with a profile for the dev account.
- Bedrock model access granted in the dev account and region for Claude Sonnet 5.5 and Claude
  Haiku 5.5, plus Claude Opus 5.5 for the refusal fallback.
- `pipeline/config/pricing.toml` holds current Bedrock prices (R15), and
  `pipeline/config/envs/dev.toml` holds the bucket name and distribution ID from
  `terraform output`.

## 0. Bootstrap and offline tests (no AWS, no cost)

```bash
make bootstrap
make lint && make test
```

**Expected**: everything passes. That includes:
- the schema contract tests;
- the unit tests for sections, cross-references, checks, the publish check, the merge and the cost
  cap;
- the fake-model integration test, which runs a fixture book through `run` → `approve` →
  `publish` against moto S3.

## 1. Dev infrastructure (once)

```bash
cd infra/envs/dev && terraform init && terraform apply
```

**Expected**: a private packs bucket with a CloudFront distribution in front of it, and a
private sources bucket. Copy the outputs into `pipeline/config/envs/dev.toml`.

## 2. Freeze the sources (once, about 1 hour)

```bash
uv run --package thinkbible-pipeline thinkbible-pipeline import --all
uv run --package thinkbible-pipeline thinkbible-pipeline verify
uv run --package thinkbible-pipeline thinkbible-pipeline sources push
```

**Expected**:
- The local cache `content/sources/{bsb,kjv,matthew-henry,jamieson-fausset-brown,adam-clarke}/*.json`
  exists, and is gitignored.
- `manifest.json` lists every file with its S3 key and sha256, and `verify` reports all files OK.
- `bsb/MRK.json` has no 7:16 and does have the "BYZ and TR include 16" footnote. `kjv/MRK.json`
  has 7:16.
- `sources push` uploads every file. Running it again uploads nothing.

Commit **only the manifest** as `content: import source snapshot (Free Use Bible API V…)`.

**Fresh clone test**: delete the cache, then pull it back.

```bash
rm -rf content/sources/*/
thinkbible-pipeline sources pull
thinkbible-pipeline verify
```

**Expected**: the identical files are restored and `verify` passes.

**Tamper test (FR-002)**: change one character in `content/sources/adam-clarke/MRK.json` and run
`thinkbible-pipeline run --book mark --stage sections`. **Expected**: exit code 2, with nothing
written. Restore the file with `git checkout`.

## 3. Generate Mark (the content spike)

```bash
make pipeline BOOK=mark STAGE=all
```

**Expected**:
1. Before any model call, it prints an estimate (about $5–10 for about 100 sections) and the cap,
   and asks for confirmation.
2. It stops at "ready for review" with `content/drafts/mrk/` filled in.
3. `thinkbible-pipeline status --book mark` shows every section done or flagged, and the spend.
4. `content/drafts/mrk/review.html` opens with flagged items first.

**Spot checks**:
- `mrk-1-1`: KJV wording variant on the sandals question, and key ideas citing more than one
  commentator. This works because cross-references to Matthew 3 were followed.
- The Mark 7 section that contains 7:16 has a manuscript note. So does Mark 16 (ending after
  16:8).
- Every key idea has evidence quotes, and every question ends with "?".

## 4. Idempotency (SC-005)

```bash
make pipeline BOOK=mark STAGE=all
```

**Expected**: the estimate shows 0 sections to process and $0.00, and no model calls are made.

## 5. Review, edit, approve

1. Read `review.html`. Edit a question's text in `content/drafts/mrk/sections/mrk-1-1.json`.
2. Run `make pipeline BOOK=mark STAGE=report`. **Expected**: the edit shows as a human edit.
3. Run `make pipeline BOOK=mark STAGE=generate` with `--fresh --sections mrk-1-1`. **Expected**:
   your edit is kept (R9).
4. Run `thinkbible-pipeline approve --book mark`. **Expected**: unresolved flags are listed, and
   you confirm by typing `mark`. `approval.json` is written.
5. Commit the drafts.

## 6. Publish to dev

```bash
thinkbible-pipeline publish --book mark --env dev
curl -s https://<dev-distribution>/v1/index.json | jq .
```

**Expected**:
- `index.json` lists `MRK` at `1.0.0`, with the sha256 and size of `study.json`, `verses/bsb.json`
  and `verses/kjv.json`.
- The three files download and validate against the schemas.
- The total compressed size is under 1 MB (SC-007).
- Nothing was added under `content/` in git except draft and state changes.

## 7. Publish-check refusals (FR-024)

1. **Unapproved change**: edit a draft after approval, then run `publish`. **Expected**: exit
   code 5, "drafts changed since approval".
2. **Frozen text**: change the text of a published question in place, approve, then publish.
   **Expected**: exit code 5, "published text changed: mrk-1-1-q1".
3. **Retire and replace**: retire that question and add a replacement with `replaces`, then
   approve and publish. **Expected**: `1.1.0` publishes. The old ID is still present with
   `status: retired`, and `index.json` points to `1.1.0`.

## 8. Spend cap (FR-028)

```bash
thinkbible-pipeline run --book mark --stage review --fresh --cap 0.10 --yes
```

**Expected**: the run stops with exit code 4 after spend passes $0.10, finished sections are kept,
and `status` shows what is left.
