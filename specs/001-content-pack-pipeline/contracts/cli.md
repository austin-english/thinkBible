# Contract: `thinkbible-pipeline` CLI

You run the pipeline from the repo root with
`uv run --package thinkbible-pipeline thinkbible-pipeline <command> …`, or with `make` (below).

Every command:
- accepts a book as a name (`mark`) or a USFM code (`MRK`);
- verifies source checksums before doing any work (FR-002), except `import` and `sources`. If a
  needed cache file is missing, the command says to run `sources pull`;
- exits non-zero on failure.

The CLI is a thin front door. Each command parses its flags into a request object (`RunRequest`,
`PublishRequest`, `ApproveRequest` in `thinkbible_pipeline/requests.py`) and calls shared code. A
future cloud trigger (API Gateway or Step Functions) sends the same request as JSON:

| CLI | JSON request |
|---|---|
| `run --book mark --stage all` | `{"book": "mark", "stages": ["all"]}` |
| `--sections mrk-1-1,mrk-1-9` | `"sections": ["mrk-1-1", "mrk-1-9"]` |
| `--fresh` / `--refresh` | `"fresh": true` / `"refresh": true` |
| `--cap 20` | `"capUsd": 20` |
| `--yes` (skip the confirmation prompt) | `"autoApprove": true`. Otherwise the cloud workflow pauses for approval after the estimate |

## Commands

| Command | Purpose | Network | Model calls |
|---|---|---|---|
| `import [--books MRK,MAT,…\|--all] [--sources bsb,kjv,matthew-henry,…]` | Fetch and normalise source text into the local cache `content/sources/` under a new snapshot ID, and update `manifest.json`. **The only command that fetches text from the web.** | Free Use Bible API | No |
| `sources push` | Upload cache files listed in the manifest but missing from S3. Write-once (`If-None-Match: *`); refuses if an existing object's checksum differs | S3 (sources bucket) | No |
| `sources pull [--books …]` | Download manifest files missing from the local cache, then verify them | S3 (sources bucket) | No |
| `verify` | Re-check every cached file against `manifest.json` | No | No |
| `run --book B --stage S [--sections ID,…] [--fresh] [--cap USD] [--yes]` | Run one stage or all of them (see below) | Bedrock only | Yes, except `sections`, `check` and `report` |
| `status --book B` | Book status, per-stage counts (done, failed, flagged), spend so far, and what is left | No | No |
| `approve --book B` | Gate: zero check failures, list unresolved flags, ask you to type the book name, write `approval.json` (FR-019) | No | No |
| `publish --book B --env dev\|prod [--dry-run]` | Download the last published version from S3, run the publish check, build the pack, upload it, update the index, invalidate the index in CloudFront (FR-021–FR-024) | S3 / CloudFront | No |
| `eval --sample mark-sample --candidate PROMPT_SET [--yes]` | Compare a candidate prompt set against the current one on a fixed sample and render a side-by-side report | Bedrock only | Yes |

## Stages (`run --stage`)

Stages run in this order. `all` runs `sections` through `report` and stops at "ready for review".

| Stage | Reads | Writes | Model |
|---|---|---|---|
| `sections` | BSB headings, Henry divisions | `drafts/{book}/sections.json` | none |
| `summaries` | Passage text | one-line summary per section | Haiku 5.5 |
| `generate` | Passage (BSB + KJV), commentary excerpts (+ one-hop cross-references), previous summary, question guide | key ideas + evidence, context, views differ, no-prompt decision, then the question pool | Sonnet 5.5 |
| `align` | Draft items, both translations, BSB footnotes | KJV wording variants, manuscript notes | Haiku 5.5 |
| `check` | Drafts | `checks` per item (FR-016) | none |
| `review` | Drafts, quality rules | grade and flags per item (FR-017) | Sonnet 5.5 |
| `levels` | Questions, passage | level adjustments and flags (FR-011) | Haiku 5.5 |
| `report` | Drafts | `drafts/{book}/review.html` | none |

## Re-runs and published sections

- **Unchanged inputs**: a stage skips any section whose recorded prompt version and input hash
  match. That means zero model calls (SC-005).
- **`--fresh`**: forces regeneration, but **only for sections with nothing published yet**.
- **Published sections**: after a section has any published item, `generate`, `summaries` and
  `align` skip it, even with `--fresh` or a new prompt version, and report
  "skipped: published (use --refresh)".
- **`--refresh`**: the only way to add to a published section. It adds new questions with new
  IDs, reuses the stored key ideas, and never changes existing items (FR-024, US6).
- **Read-only stages**: `check`, `review`, `levels` and `report` always run, because they don't
  rewrite content.

## Cost behaviour (FR-027, FR-028)

1. Before any stage that calls a model, the CLI prints:
   - sections to process;
   - sections skipped because they're already done;
   - the estimated cost;
   - the cap.

   It then asks `Proceed? [y/N]`. `--yes` skips the prompt; CI never runs these stages.
2. When spend passes the cap (default 2× the estimate), no new sections start. Sections in flight
   finish, and the run stops with status `stopped: cap reached`. `status` shows what is left.
3. Every run appends a record to `drafts/{book}/runs.json`: stage, sections, tokens by kind,
   cost, model and prompt versions.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Usage error |
| 2 | Source checksum mismatch: nothing was generated |
| 3 | Some sections failed. The rest succeeded, and `status` lists the failures |
| 4 | Spend cap reached. The run can be resumed |
| 5 | Gate refused: `approve` with failing checks, or `publish` without approval, with changed drafts, or failing the publish check |

## Make targets

```bash
make pipeline BOOK=mark STAGE=all        # → run --book mark --stage all
make pipeline BOOK=mark STAGE=generate   # → run --book mark --stage generate
make publish BOOK=mark ENV=dev           # → publish --book mark --env dev
```
