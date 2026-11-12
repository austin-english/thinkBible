# Implementation Plan: Content Pack Format and Batch Pipeline

**Branch**: `001-content-pack-pipeline` | **Date**: 2026-11-04, revised 2026-11-10 (cloud-first runs) | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-content-pack-pipeline/spec.md`

## Summary

This feature builds the batch content pipeline and the pack contract every other feature depends
on:

- A one-time importer freezes the BSB, KJV and three public-domain commentaries from the Free
  Use Bible API. The files go to a private S3 bucket, and their checksum manifest is committed to
  git.
- A Step Functions workflow in AWS turns one book at a time into draft study content, one Lambda
  per section per stage. A thin local CLI estimates the cost, starts the run, shows the
  scorecard and promotes books. The same stage code also runs in-process (`run --local`) for
  quick prompt tuning on a few sections:
  - sections from BSB headings and Matthew Henry's divisions;
  - key ideas with verified commentator evidence;
  - levelled question pools, context and views-differ notes;
  - KJV wording variants and manuscript notes.
- An automatic quality gate replaces manual review (revised 2026-11-10, constitution v1.2.0):
  rule checks, the evidence check, an Opus 5.5 grader calibrated against the owner's grades, and
  a level check drop weak items and record why. Each run ends with a read-only scorecard.
- A run whose gate passes publishes the book to dev. The owner reads it in the app and runs
  `promote`, which copies that exact pack to production after an additive "publish check"
  against the last production version. Packs are versioned JSON in S3 behind CloudFront.
- Model calls go to Claude Sonnet 5.5 (generate), Haiku 5.5 (summaries, align, levels) and Opus
  5.5 (the grader, refusal fallback) on Bedrock, with structured outputs and no tools. Each run
  shows a cost estimate before it starts and stops at a spending cap.

## Technical Context

**Language/Version**: Python 3.12 (uv workspace members `shared`, `pipeline`)

**Primary Dependencies**:
- `pydantic` v2 (models and structured outputs)
- `anthropic[bedrock]` (`AsyncAnthropicBedrock`, the `bedrock-runtime` endpoint; research R6)
- `boto3` (S3, CloudFront, DynamoDB, Step Functions)
- `typer` (CLI)
- `jinja2` (scorecard report)
- `jsonschema` (contract validation)
- Dev only: `pytest`, `moto`, `ruff`, `mypy --strict`

**Storage**:
- S3: the source snapshot (private bucket, write-once), the drafts / pipeline state (private,
  versioned, R8) and published packs (behind CloudFront)
- DynamoDB: one table holding each run's spend ledger and status (R8, R15)
- Git: `content/sources/manifest.json` (source checksums) and `pipeline/evals/calibration.json`
  (the owner's grades for calibrating the grader)
- Local, gitignored: the source cache in `content/sources/{source}/`, used by `import` and
  `--local` runs

**Testing**:
- pytest: contract tests against shared schema fixtures, unit tests, and a fake-model
  integration test with moto S3
- A manual, paid `eval` command for prompt changes (R16)

**Target Platform**: AWS in `dev` and `prod` (us-west-2): Step Functions Standard, Lambda
(Python 3.12, arm64), S3, DynamoDB, Bedrock, CloudFront. The CLI runs on the developer's Mac

**Project Type**: cloud batch pipeline (Step Functions + Lambda) with a thin CLI, a shared models
library, and infrastructure

**Performance Goals**: Mark (~100 sections) end to end in under 30 minutes on demand, with 10
sections in parallel (SC-002). Re-running an unchanged book makes 0 model calls (SC-005)

**Constraints**:
- No network for text outside `import`, and no tools in model calls (constitution II)
- A spending cap on every run (FR-028)
- A published Mark pack under 1 MB compressed (SC-007)
- Published IDs, text and section ranges are frozen (FR-004, FR-024)

**Scale/Scope**:
- 66 books and about 3,100 sections eventually. Mark (673 BSB verses / 678 KJV) for this feature
- About 5,600 source chapter files imported once

No unknowns remain. All decisions are in [research.md](research.md) R1–R18.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design, and again on
2026-11-10 for cloud-first runs. Result: **PASS**, with one documented deviation (batch inference
deferred, see Complexity Tracking).*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Scripture never paywalled | No app surface here. Verse-text files are published separately from study content, so the app can always read them | ✅ N/A |
| II. Closed-world sourcing | `import` is the only code that fetches text from the web. The snapshot is stored in a private S3 bucket, cached locally, and verified against the manifest in git (constitution v1.0.2, R2). Every stage verifies checksums first (exit code 2). Excerpts are per section from the snapshot only, and cross-references stay inside the snapshot (R4). No `tools` in any request, checked by a unit test (R6). The manifest records license, retrieval date and upstream sha256 | ✅ |
| III. Batch generates, live only compares | All questions, ideas and notes are generated here and published only after passing the automatic quality gate (rule checks, evidence check, calibrated grader) | ✅ |
| IV. Every idea attributed | `sources` needs ≥ 1 commentator, each backed by an evidence quote checked against that commentator's excerpt (R10). The pack's `sources` table gives display names, so the app builds citations from the pack | ✅ |
| V. Offline-first | Packs are static, versioned JSON with sha256s in the index, so the app can cache them and check integrity (cdn-layout) | ✅ |
| VI. Reflections belong to the user | No user data is involved | ✅ N/A |
| VII. One contract, permanent IDs | JSON Schemas are written first (contracts → `content/schema/`), with Pydantic models and contract tests from shared fixtures. Production-only additive publish check, frozen text and ranges in production, `replaces` links, IDs never reused anywhere; production only through `promote` after the gate and the owner's in-app read (v1.2.0) | ✅ |
| VIII. Guide, never judge | The question guide holds the tone and neutrality rules, the grader enforces them, and views-differ notes stay neutral. The tradition of each commentary is recorded in `sources` for the About page | ✅ |
| IX. Bounded live cost | Not live. The batch equivalent is the estimate, confirm and cap (FR-027, FR-028) | ✅ |
| X. Accessible, token UI | No UI | ✅ N/A |
| Tech constraints | Python 3.12, uv, ruff, mypy strict, pytest. Bedrock (Sonnet-class for batch). Prompts versioned in `pipeline/prompts/`. Output keyed by book, section and prompt version. Terraform for S3, CloudFront, DynamoDB, Lambda and Step Functions. Step Functions Standard, one execution per book run (R7). **Deviation:** on-demand Bedrock calls instead of batch inference for now | ⚠️ See Complexity Tracking |
| Quality gates | Contract tests for the pack schema. Unit tests for business rules. Prompt changes go through `eval` before publishing. `make lint` and `make test` run in CI | ✅ |

**Post-design re-check**: the data model, contracts and quickstart add no new deviations. The
Swift side of the contract tests can't exist yet. Spec 002 must build `ContentKit` against the
same `content/schema/` files and fixtures.

## Project Structure

### Documentation (this feature)

```text
specs/001-content-pack-pipeline/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R18 decisions
├── data-model.md        # published, draft and source entities; rules; state machine
├── quickstart.md        # end-to-end validation
├── contracts/
│   ├── section.schema.json      # → content/schema/section.schema.json
│   ├── study-pack.schema.json   # → content/schema/study-pack.schema.json
│   ├── verses.schema.json       # → content/schema/verses.schema.json
│   ├── index.schema.json        # → content/schema/index.schema.json
│   ├── cli.md
│   └── cdn-layout.md
├── checklists/requirements.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
content/
├── schema/                       # the binding contract (copied from contracts/ in task 1)
│   ├── section.schema.json  study-pack.schema.json  verses.schema.json  index.schema.json
│   └── fixtures/{valid,invalid}/*.json   # shared with Swift ContentKit tests (spec 002)
├── sources/manifest.json         # checksums of the S3 snapshot (in git, R2)
├── sources/{source}/{BOOK}.json  # local cache pulled from S3 (gitignored)
                                  # drafts / pipeline state and published packs live only in S3

shared/                           # uv package thinkbible-core
├── pyproject.toml
├── src/thinkbible_core/
│   ├── models/                   # StudyPack, Section, KeyIdea, Question, VerseText, PackIndex
│   ├── ids.py                    # ID formats and parsing
│   ├── refs.py                   # {{ref:C:V}} placeholders
│   └── schema.py                 # load and validate content/schema/*.json
└── tests/                        # contract tests (fixtures ↔ schema ↔ models)

pipeline/                         # uv package thinkbible-pipeline
├── pyproject.toml                # script: thinkbible-pipeline
├── CLAUDE.md                     # area rules: only sources/importer.py may fetch text, never add tools
├── config/
│   ├── settings.toml             # models per stage, effort, concurrency, region, cost defaults
│   ├── pricing.toml              # $/Mtok per model (Bedrock prices)
│   └── envs/{dev,prod}.toml      # buckets, ledger table, state machine ARN, distribution id
├── prompts/
│   ├── question-guide/v1.md      # quality rules + 10–20 approved examples
│   └── {summaries,extract,questions,align,review,levels}/v1.md
├── evals/mark-sample.json        # 15–25 fixed sections for prompt evaluation
├── evals/calibration.json        # the owner's grades for ≥ 30 items; grader agreement per version
├── src/thinkbible_pipeline/
│   ├── cli.py                    # thin: estimate + start execution, --local, status, promote, calibrate, eval
│   ├── config.py
│   ├── storage.py                # BlobStore: local folder or S3 (drafts, sources)
│   ├── cloud/                    # Lambda handlers (start_run, plan_stage, run_section, finish_stage, finish_run), ledger.py (DynamoDB)
│   ├── sources/                  # importer.py (only web fetch), normalize.py, store.py (S3 push/pull), snapshot.py (verify/load)
│   ├── sections/builder.py
│   ├── commentary/               # gather.py, crossrefs.py
│   ├── llm/                      # runner.py (ModelRunner + Bedrock impl), outputs.py, prompts.py, budget.py
│   ├── stages/                   # base.py (plan / run one section / finish), summaries, generate, align, checks, review, levels
│   ├── drafts/                   # store.py, ids.py (counters)
│   ├── gate/                     # rubric outcomes, drops, alternates, scorecard.py, calibration.py
│   ├── report/                   # render.py + templates/review.html.j2 (read-only scorecard)
│   ├── evals/                    # run.py (prompt eval)
│   └── publish/                  # build.py, publish_check.py, upload.py (dev), promote.py (dev → prod)
├── scripts/build_bundle.py       # Lambda zip: packages + config + prompts + content/schema + manifest
└── tests/{unit,integration,fixtures}

infra/
├── modules/storage/              # private versioned S3 bucket (sources, drafts, packs)
├── modules/cdn/                  # CloudFront + OAC, compression, cache policies (packs bucket only)
├── modules/pipeline/             # drafts bucket, ledger table, Lambdas, Step Functions state machine, IAM
├── envs/dev/                     # sources, packs + cdn, pipeline; S3 remote state (bucket created by hand once)
└── envs/prod/                    # production packs + cdn (before the first promotion)

.github/workflows/python.yml      # make lint + make test
```

**Structure Decision**:
- This is the monorepo layout from the brief and CLAUDE.md. The feature touches `content/`,
  `shared/`, `pipeline/`, `infra/` and CI.
- `backend/` and `ios/` are untouched. Until spec 003 creates `backend/`, the root
  `pyproject.toml` workspace members and the mypy `packages` list must leave out `backend` and
  `thinkbible_api`, so that `make bootstrap` and `make lint` work. Spec 003 adds them back.
- mypy also needs `mypy_path = shared/src:pipeline/src`.
- The Makefile `pipeline` target changes to the `run --book --stage` form in contracts/cli.md,
  and a `publish` target is added.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| On-demand Bedrock calls instead of the constitution's "Bedrock batch inference where possible" | Batch inference returns results hours later. During the Mark spike, prompts change several times a day and need same-session feedback. Runs already use Step Functions Standard, one execution per book run, as the constitution requires (revised 2026-11-10) | Batch inference halves the model cost but needs a submit/poll/collect workflow per stage. Stages call a `ModelRunner` interface (R6), so a batch runner can replace the on-demand one inside the same state machine without changing stage logic. **Follow-up**: add it before generating a second book |
