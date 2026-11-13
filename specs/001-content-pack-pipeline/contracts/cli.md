# Contract: `thinkbible-pipeline` CLI

You run the pipeline from the repo root with
`uv run --package thinkbible-pipeline thinkbible-pipeline <command> …`, or with `make` (below).

Every command:
- accepts a book as a name (`mark`) or a USFM code (`MRK`);
- verifies source checksums before doing any work (FR-002), except `import` and `sources`. If a
  needed cache file is missing, the command says to run `sources pull`;
- exits non-zero on failure.

The CLI is a thin front door. Each command parses its flags into a request object (`RunRequest`,
`PublishRequest`, `PromoteRequest` in `thinkbible_pipeline/requests.py`) and calls shared code.
Full runs execute in AWS (research R7): `run` estimates the cost, asks you, and starts a Step
Functions execution whose input carries the same request as JSON:

| CLI | JSON request |
|---|---|
| `run --book mark --stage all` | `{"book": "mark", "stages": ["all"]}` |
| `--sections mrk-1-1,mrk-1-9` | `"sections": ["mrk-1-1", "mrk-1-9"]` |
| `--fresh` / `--refresh` | `"fresh": true` / `"refresh": true` |
| `--cap 20` | `"capUsd": 20` |
| `--yes` (skip the confirmation prompt) | `"autoApprove": true`, recorded on the run. The CLI asks before starting the execution, so the workflow never pauses |

## Commands

| Command | Purpose | Network | Model calls |
|---|---|---|---|
| `import [--books MRK,MAT,…\|--all] [--sources bsb,kjv,matthew-henry,…] [--refresh]` | Fetch and normalise source text into the local cache `content/sources/` under today's snapshot ID, and update `manifest.json` after every book. Translations come from the Free Use Bible API; commentaries from CrossWire module zips, archived in the snapshot (R2a). A re-run skips books already imported from the same edition and reads archived zips instead of downloading; `--refresh` redoes everything. **The only command that fetches text from the web.** | Free Use Bible API, CrossWire | No |
| `sources check [--verbose]` | Check the cached snapshot is complete and in place: every book against the KJV versification, commentary notes in range, in order and not overlapping; report omitted verses and coverage. Exit 2 on errors | No | No |
| `sources push` | Upload cache files listed in the manifest but missing from S3. Write-once (`If-None-Match: *`); refuses if an existing object's checksum differs | S3 (sources bucket) | No |
| `sources pull [--books …]` | Download manifest files missing from the local cache, then verify them | S3 (sources bucket) | No |
| `verify` | Re-check every cached file against `manifest.json` | No | No |
| `run --book B --stage S [--sections ID,…] [--fresh] [--cap USD] [--yes] [--wait] [--local]` | Run one stage or all of them (see below). By default: estimate from the S3 drafts, confirm, then start the Step Functions execution and print its ARN and console link. `--wait` polls until it finishes and exits with its code. `--local` runs in-process against the same S3 drafts, for a few sections while tuning prompts | Step Functions, S3, DynamoDB (cloud); Bedrock, S3 (`--local`) | Yes, except `sections`, `check` and `report` |
| `status --book B [--open]` | Book status, the latest runs (from the ledger and run records) with spend and counts, the latest scorecard's pass rates and failed sections, and what is left. `--open` downloads `review.html` and opens it | S3, DynamoDB, Step Functions | No |
| `publish --book B [--dry-run]` | Build the pack from the S3 drafts and publish it to **dev** (no additive check on dev). A run that includes `report` does this automatically when no section failed; this command repeats it by hand | S3 / CloudFront (dev) | No |
| `promote --book B` | Copy the book's current dev version, byte for byte, to **production**: refuses (exit 5) unless the gate passed, pass rates meet the thresholds, the grader calibration is current and at least 85%, and the production publish check passes. Then updates prod's index and invalidates it (FR-021, FR-024) | S3 / CloudFront (dev → prod) | No |
| `calibrate [--label] [--book B]` | `--label`: show calibration candidates (item, passage, excerpts) and record your pass/fail grade for each, until the set has at least 30. Without it: run the grader on the set and record its agreement for the current grader prompt and model (R16) | Bedrock only | Yes (without `--label`) |
| `eval --sample mark-sample --candidate PROMPT_SET [--yes]` | Run the current and candidate prompt sets in local mode on a fixed sample of 15–25 sections, grade both with the calibrated grader, and render a side-by-side report (FR-029) | Bedrock only | Yes |

## Cloud and local runs

| | Cloud (default) | `--local` |
|---|---|---|
| Where it runs | Step Functions + one Lambda per section per stage | This process (asyncio) |
| Drafts | S3 pipeline state | The same S3 pipeline state |
| Prompts | The deployed bundle (`make lambda-bundle` + `terraform apply`) | The repo's `pipeline/prompts/` |
| Spend ledger | DynamoDB, shared by all section Lambdas | In memory |
| Meant for | Whole books, overnight runs | A few sections while tuning prompts |

Both record the same stage records and run records, so a section done locally is skipped by the
next cloud run if nothing changed.

## Stages (`run --stage`)

Stages run in this order. `all` runs `sections` through `report`, then publishes the book to dev
if no section failed (R14). `check`, `review` and `levels` together are the quality gate (R16):
they drop failing items and record why.

| Stage | Reads | Writes | Model |
|---|---|---|---|
| `sections` | BSB headings, Henry divisions | `drafts/{book}/sections.json` | none |
| `summaries` | Passage text | one-line summary per section | Haiku 5.5 |
| `generate` | Passage (BSB + KJV), commentary excerpts (+ one-hop cross-references), previous summary, question guide | key ideas + evidence, context, views differ, no-prompt decision, then the question pool | Sonnet 5.5 |
| `align` | Draft items, both translations, BSB footnotes | KJV wording variants, manuscript notes | Haiku 5.5 |
| `check` | Drafts | `checks` per item; failing items dropped with the reason (FR-016) | none |
| `review` | Drafts, passage, excerpts, rubric | grade per item; items at or below the threshold dropped, alternates promoted (FR-017) | Opus 5.5 |
| `levels` | Questions, passage | level adjustments; unanswerable Level 1 questions dropped (FR-011) | Haiku 5.5 |
| `report` | Drafts, calibration | `scorecard.json` and `review.html` (FR-019) | none |

## Re-runs and published sections

- **Unchanged inputs**: a stage skips any section whose recorded prompt version and input hash
  match. That means zero model calls (SC-005).
- **`--fresh`**: forces regeneration, but **only for sections with nothing promoted to
  production yet**. Dev-only content is regenerated freely.
- **Promoted sections**: after a section has any item in production, `generate`, `summaries` and
  `align` skip it, even with `--fresh` or a new prompt version, and report
  "skipped: in production (use --refresh)".
- **Failed sections**: a section the gate failed is regenerated once in the same run, then left
  failed; the next run tries it again.
- **`--refresh`**: the only way to add to a published section. It adds new questions with new
  IDs, reuses the stored key ideas, and never changes existing items (FR-024, US6).
- **Gate stages**: `check`, `review` and `levels` re-run whenever a section's content changed,
  and skip unchanged sections like any other stage. `report` always runs.

## Cost behaviour (FR-027, FR-028)

1. Before any stage that calls a model, the CLI prints:
   - sections to process;
   - sections skipped because they're already done;
   - the estimated cost;
   - the cap.

   It then asks `Proceed? [y/N]`. `--yes` skips the prompt; CI never runs these stages. For a
   multi-stage run the first stage's count is exact; later stages count every section whose
   inputs will change, which is all sections an earlier stage in the run will process.
2. When spend passes the cap (default 2× the estimate), no new sections start. Sections in flight
   finish, and the run stops with status `stopped: cap reached`. `status` shows what is left.
3. Every stage run writes a record to `drafts/{book}/runs/`: stage, sections, tokens by kind,
   cost, models, prompt versions and code version.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (for a cloud run without `--wait`: the execution started) |
| 1 | Usage error |
| 2 | Source checksum mismatch: nothing was generated |
| 3 | Some sections failed. The rest succeeded, and `status` lists the failures |
| 4 | Spend cap reached. The run can be resumed |
| 5 | Gate refused: `publish` with failed sections; `promote` with pass rates below the thresholds, a missing or stale calibration, or a failing production publish check |

## Make targets

```bash
make lambda-bundle                       # → pipeline/out/lambda.zip, then terraform apply (R19)
make pipeline BOOK=mark STAGE=all        # → run --book mark --stage all --wait (cloud)
make pipeline BOOK=mark STAGE=generate   # → run --book mark --stage generate --wait
make status BOOK=mark                    # → status --book mark --open (scorecard)
make promote BOOK=mark                   # → promote --book mark (dev → production)
```
