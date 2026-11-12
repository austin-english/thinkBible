---

description: "Task list for spec 001: content pack format and batch pipeline"
---

# Tasks: Content Pack Format and Batch Pipeline

**Input**: Design documents from `specs/001-content-pack-pipeline/`: [plan.md](plan.md),
[spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The constitution's quality gates and research R16 require contract tests for
the pack schema, unit tests for business rules, and a fake-model integration test. Write each
story's tests first and confirm they fail before implementing.

**Organization**: Tasks are grouped by user story. **US4 (frozen source snapshot, P2) is scheduled
before US1**, because every generation stage reads the snapshot (spec: "It can be done first in
practice"). After that, stories follow priority order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks).
- **[Story]**: US1–US6, as in spec.md.
- Paths are relative to the repo root.
- "Owner run" tasks are manual steps for you that need AWS and, for model stages, Bedrock.

---

## Phase 1: Setup (shared infrastructure)

**Purpose**: Make the uv workspace, lint, tests and CI work with the two Python packages this
feature adds.

- [X] T001 Update `pyproject.toml` (root):
  - set `[tool.uv.workspace] members = ["shared", "pipeline"]`, removing `backend` until spec 003;
  - set `[tool.mypy] packages = ["thinkbible_core", "thinkbible_pipeline"]` and add
    `mypy_path = "shared/src:pipeline/src"`;
  - set `[tool.pytest.ini_options] testpaths = ["shared/tests", "pipeline/tests"]`;
  - add `boto3-stubs[s3,cloudfront]>=1.35` to the dev group.
- [X] T002 [P] Create `shared/pyproject.toml`:
  - package `thinkbible-core`, `requires-python = ">=3.12"`, hatchling build, src layout;
  - deps `pydantic>=2.9`, `jsonschema>=4.23`, `referencing>=0.35`;
  - create `shared/src/thinkbible_core/__init__.py`, `shared/src/thinkbible_core/py.typed` and
    `shared/tests/__init__.py`.
- [X] T003 [P] Create `pipeline/pyproject.toml`:
  - package `thinkbible-pipeline`, src layout;
  - deps `thinkbible-core` (workspace), `anthropic[bedrock]`, `boto3>=1.35`, `typer>=0.12`,
    `jinja2>=3.1`, `pydantic>=2.9`;
  - script `thinkbible-pipeline = "thinkbible_pipeline.cli:app"`;
  - create `pipeline/src/thinkbible_pipeline/__init__.py`, `py.typed`, `__main__.py` (calls
    `app()`), `pipeline/tests/unit/__init__.py`, `pipeline/tests/integration/__init__.py` and
    `pipeline/tests/fixtures/`.
- [X] T004 Update the `Makefile`:
  - `pipeline:` → `uv run --package thinkbible-pipeline thinkbible-pipeline run --book $(BOOK) --stage $(STAGE)`;
  - add `publish:` → `… thinkbible-pipeline publish --book $(BOOK) --env $(ENV)`;
  - add `sources-pull:` → `… thinkbible-pipeline sources pull`;
  - keep `ENV ?= dev`.
- [X] T005 [P] Create `.pre-commit-config.yaml` with:
  - ruff (lint and format) and check-json;
  - a local hook that fails if any staged path matches `content/sources/` other than
    `content/sources/manifest.json` (CLAUDE.md: never commit source text).
- [X] T006 [P] Create `.github/workflows/python.yml`. On push and PR, it runs:
  `astral-sh/setup-uv`, `hashicorp/setup-terraform`, `make bootstrap`, `make lint`, `make test`.
  No AWS credentials and no model calls in CI.
- [X] T007 [P] Create `pipeline/CLAUDE.md` with these area rules:
  - only `src/thinkbible_pipeline/sources/importer.py` may fetch text from the network;
  - never pass `tools` to a model call;
  - prompts are versioned files: add `vN+1.md`, never edit a used version;
  - draft JSON in `content/drafts/` is edited by the owner, and the pipeline merges and never
    overwrites human edits;
  - no source text in git.

  Also create `shared/CLAUDE.md`: schema first (`content/schema/`), then models, then fixtures, in
  the same change.
- [X] T008 Install Terraform if it's missing (`brew install hashicorp/tap/terraform`). Then run
  `make bootstrap && make lint && make test` and confirm all three pass on the empty packages.

**Checkpoint**: The workspace syncs, lint and test pass, and CI is green.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The pack contract, the shared models, and the pipeline framework every stage uses.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Contract (schema first)

- [X] T009 Copy `specs/001-content-pack-pipeline/contracts/{section,study-pack,verses,index}.schema.json`
  unchanged into `content/schema/`. These become the binding contract; the copies in contracts/
  are now only references.
- [X] T010 [P] Create the fixtures, one file per case:
  - **Valid**, in `content/schema/fixtures/valid/`:
    - `study-pack-mark-sample.json`: Mark 1:1–8 from docs/brief.md, plus Mark 1:9–11 from
      `docs/design/screens/FeedHybrid.dc.html`. Use IDs `mrk-1-1`, `mrk-1-1-k1` and so on,
      `packVersion` "1.0.0", and a full `sources` table.
    - `verses-bsb-sample.json`, including `omittedVerses: [{"chapter":7,"verse":16}]`.
    - `index-sample.json`.
  - **Invalid**, in `content/schema/fixtures/invalid/`:
    - `question-no-question-mark.json`
    - `keyidea-no-sources.json`
    - `keyidea-unknown-commentator.json`
    - `bad-section-id.json`
    - `question-level-4.json`
    - `keyidea-body-too-long.json` (241 chars)
    - `extra-property.json`

### Shared models (`thinkbible_core`)

- [X] T011 [P] Implement `shared/src/thinkbible_core/models/section.py`: Pydantic v2 models
  `KeyIdea`, `Question`, `ManuscriptNote`, `VerseNote`, `Section`. Use camelCase aliases,
  `extra="forbid"`, and these constraints verbatim from data-model.md:
  - **KeyIdea**:
    - `title` "≤ 60 chars", `body` "≤ 240 chars";
    - `sources` "1–3, unique", from `matthew-henry | jamieson-fausset-brown | adam-clarke`;
    - `agreed` "`= len(sources) ≥ 2`";
    - `status` `active|retired`, "`retiredIn` is required when retired";
    - optional `replaces`.
  - **Question**:
    - `level` "1–3";
    - `type` `noticing|meaning|application|seasonal`;
    - `text` "10–160 chars, ends with `?`";
    - `targets` "≥ 1";
    - `isAlternate`; `textByTranslation` values follow the same text rule.
  - **Section**:
    - `title` "≤ 80 chars", `context` "≤ 280 chars", `viewsDiffer` "≤ 400 chars or null";
    - ID patterns `^[0-9a-z]{3}-[0-9]{1,3}-[0-9]{1,3}$`, `…-k[0-9]{1,3}$`, `…-q[0-9]{1,3}$`.
- [X] T012 [P] Implement the remaining models, matching the contract schemas field for field:
  - `shared/src/thinkbible_core/models/pack.py`: `StudyPack`, `Book`, `TranslationRef`, `Source`,
    `Build`;
  - `shared/src/thinkbible_core/models/verses.py`: `VerseText`;
  - `shared/src/thinkbible_core/models/index.py`: `PackIndex`.
- [X] T013 [P] Implement `shared/src/thinkbible_core/ids.py`:
  - a USFM table for all 66 books (code, English name, lowercase code);
  - name aliases (`mark` → `MRK`, `matthew` → `MAT`, …);
  - ID builders and parsers: `section_id("MRK", 1, 1) == "mrk-1-1"`, `key_idea_id(sec, n)`,
    `question_id(sec, n)`, and `parse_item_id`.
- [X] T014 [P] Implement `shared/src/thinkbible_core/refs.py`:
  - find, parse and validate `{{ref:C:V}}` and `{{ref:C:V-V}}` placeholders (R13);
  - `unresolved(text, verse_sets_by_translation)` returns placeholders missing from any
    translation.
- [X] T015 Implement `shared/src/thinkbible_core/schema.py`:
  - load `content/schema/*.schema.json` into a `referencing.Registry` keyed by `$id`;
  - `validate(doc, kind)` returns a list of error messages, for `kind` in
    `section|study-pack|verses|index`.
- [X] T016 Implement `shared/src/thinkbible_core/rules.py`. `cross_field_violations(pack)` returns
  violations of data-model.md "Cross-field rules" 1–9:
  1. ranges contiguous, non-overlapping, covering every verse in either translation;
  2. item ranges inside their section;
  3. IDs prefixed by the section ID and unique;
  4. `agreed` consistent;
  5. targets are active ideas in the same section;
  6. level count follows the number of active ideas, ≤ 6 active questions, a whole-passage
     question when there are 2+ levels;
  7. `noPrompt` ⇒ no active questions, else an active L1;
  8. placeholders resolve;
  9. retiring an idea retires the questions that target only it.
- [X] T017 [P] Write the contract tests in `shared/tests/test_contract.py`:
  - every `fixtures/valid/*.json` validates against its JSON Schema **and** parses with the
    models;
  - every `fixtures/invalid/*.json` fails both;
  - `model_dump(by_alias=True, exclude_none=True)` of each valid fixture validates against the
    schema.
- [X] T018 [P] Write unit tests for `ids.py`, `refs.py` and each rule in `rules.py` in
  `shared/tests/test_ids_refs_rules.py`.

### Pipeline framework (`thinkbible_pipeline`)

- [X] T019 Create the config files and loader:
  - **`pipeline/config/settings.toml`**:
    - `region = "us-west-2"`;
    - models per stage: summaries/align/levels `anthropic.claude-haiku-5-5`,
      generate/review `anthropic.claude-sonnet-5-5`, refusal fallback
      `anthropic.claude-opus-5-5` (Bedrock Mantle IDs; changed from the `us.` inference-profile
      IDs on 2026-11-10, see research R6);
    - effort per stage: generate/review `medium`, others `low`;
    - `concurrency = 10`, `excerpt_cap_tokens = 8000`, `review_flag_threshold = 2`;
    - default cost per section from R15: generate 0.06, review 0.02, levels 0.005,
      summaries 0.002, align 0.002.
  - **`pipeline/config/pricing.toml`**: $/MTok input, output, cache-read, cache-write (5-minute)
    and cache-write (1-hour) for each model ID.
    - Sonnet 5.5 uses the accepted Bedrock offer prices (checked 2026-11-04): input 2, output 10,
      cache read 0.10, cache write 2.50, cache write 1h 4.00.
    - Haiku 5.5 is 0.10/0.50 and Opus 5.5 is 4/20, with cache read 5% and cache write 125% of
      input.
    - Add a comment: "re-check with `aws bedrock list-foundation-model-agreement-offers`".
  - **`pipeline/config/envs/dev.toml`**: `sources_bucket = "thinkbible-sources-522779858032"`,
    `packs_bucket = "thinkbible-packs-dev-522779858032"`, `distribution_id = ""`,
    `cdn_base_url = ""`.
  - **`pipeline/src/thinkbible_pipeline/config.py`**: loads all three with `tomllib` into frozen
    dataclasses.
- [X] T020 Implement `pipeline/src/thinkbible_pipeline/paths.py`: find the repo root and expose
  content paths (`content/schema`, `content/sources`, `content/drafts/{book}`).
- [X] T021 Implement source-snapshot models and the verifier:
  - **`pipeline/src/thinkbible_pipeline/sources/models.py`**: Pydantic `SourceManifest` with
    `bucket`, `apiVersion`, and per-source/per-book `file`, `s3Key`, `sha256`, `bytes`,
    `retrievedAt`, `snapshotId`, license fields and `tradition`. Plus `NormalizedTranslationBook`
    and `NormalizedCommentaryBook`, exactly as data-model.md §3.
  - **`pipeline/src/thinkbible_pipeline/sources/snapshot.py`**: `load_book(source, book)` checks
    sha256 against the manifest before returning parsed data. A mismatch raises
    `ChecksumMismatch` (CLI exit code 2). A missing cache file raises `MissingSource`, with the
    message "run `thinkbible-pipeline sources pull`".
- [X] T022 Implement draft entities and storage:
  - **`pipeline/src/thinkbible_pipeline/drafts/models.py`**: `BookState`, `SectionMapEntry`,
    `SectionDraft`, `Flag`, `CheckResult`, `StageRecord`, `RunRecord`, `Approval`, with exactly
    the fields in data-model.md §2.
  - **`pipeline/src/thinkbible_pipeline/drafts/store.py`**: read and write `book.json`,
    `sections.json`, `sections/{id}.json`, `.generated/{id}.json`, `runs.json` (append) and
    `approval.json`. Write canonical JSON (sorted keys, 2-space indent, trailing newline) so git
    diffs stay small.
- [X] T023 Implement the ModelRunner in `pipeline/src/thinkbible_pipeline/llm/runner.py`:
  - a `ModelRunner` Protocol:
    `async parse(stage, system: list[block], user: str, output_model: type[BaseModel]) -> (model, Usage)`;
  - **`BedrockRunner`**:
    - uses the Anthropic SDK `AsyncAnthropicBedrockMantle(aws_region=settings.region)` and
      `beta.messages.parse(output_format=Model)` with structured output (the refusal middleware
      only handles `client.beta.messages`);
    - `cache_control` on the stable system prefix, and adaptive thinking with per-stage
      `output_config.effort`;
    - **asserts no `tools` key** in the request;
    - on `stop_reason == "refusal"`, retries once on the fallback model (client-side
      `BetaRefusalFallbackMiddleware`; check the exact API against the SDK docs). If that is also
      refused, it raises `Refused(category)`;
    - retries invalid structured output up to 2 times;
  - **`FakeRunner`**: replays recorded outputs from
    `pipeline/tests/fixtures/model_outputs/{stage}/{section_id}.json` for tests.
- [X] T024 Implement `pipeline/src/thinkbible_pipeline/llm/budget.py` (R15):
  - `price(usage, model)` from `pricing.toml`;
  - `estimate(stage, n_sections, runs)`: median cost per section over the last 20 runs of that
    stage in `runs.json`, else the settings default;
  - a `Budget(cap)` with `add(cost)` and `can_start()`;
  - a `confirm(estimate, cap, yes)` helper that prints sections to process, sections skipped,
    the estimate and the cap.
- [X] T025 Implement `pipeline/src/thinkbible_pipeline/llm/prompts.py`:
  - load `pipeline/prompts/{stage}/{version}.md` and `pipeline/prompts/question-guide/{version}.md`;
  - every system prompt starts with `pipeline/prompts/_shared/context-v1.md`;
  - return the prompt versions for recording.

  Also create `pipeline/prompts/_shared/context-v1.md` with the R6 "Context in every system
  prompt" text: the model is summarising published, public-domain Christian commentaries
  (Matthew Henry, Jamieson-Fausset-Brown, Adam Clarke, 18th–19th century) on canonical Scripture
  for a Bible-study app. Passages may describe violence, sexuality or judgement as part of the
  biblical text. The job is to restate what the commentators say.
- [X] T026 Implement the stage runner, driven by a `RunRequest` instead of CLI flags, so a later
  cloud trigger (API Gateway or Step Functions, spec 008) can call the same code with JSON input:
  - **`pipeline/src/thinkbible_pipeline/requests.py`**:
    - a frozen Pydantic `RunRequest` with `book`, `stages: list[str]` (`all` expands to the
      cli.md order), `sections: list[str] | None`, `fresh: bool = False`,
      `refresh: bool = False`, `cap_usd: float | None` (`None` = 2× the estimate),
      `auto_approve: bool = False`, `env: str = "dev"`;
    - `RunRequest.model_validate_json(...)` must accept the same JSON the cloud will send
      (camelCase aliases: `capUsd`, `autoApprove`);
    - also `PublishRequest(book, env, dry_run)` and `ApproveRequest(book)`.
  - **`pipeline/src/thinkbible_pipeline/stages/base.py`** (`run(request: RunRequest, deps) -> RunResult`):
    - `deps` holds the injected `ModelRunner`, the draft store, settings and an
      `approve_estimate(estimate, cap) -> bool` callback. Locally that callback is the
      `Proceed? [y/N]` prompt (or `True` with `auto_approve`); in the cloud it will be a
      Step Functions wait-for-approval step. The runner itself never reads stdin or argv.
    - map an async stage function over sections with `asyncio.Semaphore(concurrency)`;
  - input hash = sha256 of canonical JSON of (inputs, prompt version, model ID). Skip a section
    when `stages[stage]` has the same `promptVersion` and `inputHash` and `status == "done"`,
    unless `--fresh`;
  - record a `StageRecord` per section; a failure marks only that section `failed`;
  - check the Budget before starting each section, stop starting new ones once the cap is passed,
    and let in-flight sections finish;
  - append a `RunRecord`;
  - return a `RunResult` (sections done, skipped, failed, spend, `stopped_by`). The CLI maps it
    to exit code 0, 3 (some sections failed) or 4 (cap reached).
- [X] T027 Create the CLI skeleton in `pipeline/src/thinkbible_pipeline/cli.py`:
  - a **thin** Typer app with commands `import`, `sources push`, `sources pull`, `verify`, `run`,
    `status`, `approve`, `publish`, `eval`. Each command only parses flags into a request object
    (`RunRequest`, `PublishRequest`, `ApproveRequest`), calls the shared function, and maps the
    result to an exit code. No pipeline logic lives in `cli.py`;
  - book argument resolution via `thinkbible_core.ids`;
  - an `ExitCode` enum with 0–5 exactly as in contracts/cli.md;
  - unimplemented commands exit 1 with "not implemented yet".
- [X] T028 [P] Write the framework tests in `pipeline/tests/unit/`:
  - `test_budget.py`: estimate from history versus defaults; the cap stops new sections;
  - `test_stage_runner.py`: skip on the same hash; `fresh` re-runs; one failure doesn't stop
    others; results that map to exit codes 3 and 4; a rejected estimate makes zero model calls;
  - `test_requests.py`: `RunRequest` parses both CLI-style values and cloud-style JSON
    (`{"book":"mark","stages":["all"],"capUsd":20,"autoApprove":true}`), expands `all`, and
    rejects unknown stages and books;
  - `test_no_tools.py`: the BedrockRunner request builder never includes `tools`;
  - `test_network_guard.py`: an AST scan of `pipeline/src` shows that only
    `sources/importer.py` imports `urllib`, `http.client`, `httpx`, `requests` or `socket`.

**Checkpoint**: `make test` passes, with contract tests green and the framework tested with
`FakeRunner`.

---

## Phase 2b: Cloud foundation (added 2026-11-10, blocks real runs)

**Purpose**: Run the pipeline in AWS (research R7, R8, R19): drafts in S3, a DynamoDB spend ledger,
one Lambda per section per stage under Step Functions, and a CLI that estimates, starts runs and
syncs drafts. The stage code from Phase 2 is reused; only storage and orchestration change.

**Independent Test**: With moto (S3, DynamoDB) and `FakeRunner`, drive the five handlers through a
two-stage run of the fixture sections and get the same drafts and run records as `run --local`.
`drafts push` refuses after a cloud write. The state machine definition references exactly the
five handlers.

- [ ] T087 Implement `pipeline/src/thinkbible_pipeline/storage.py`:
  - a `BlobStore` protocol: `get(key) -> (bytes, etag) | None`, `put(key, data, *, if_match=None,
    if_none_match=False) -> etag`, `list(prefix) -> [(key, etag)]`, raising `PreconditionFailed`;
  - `LocalBlobStore(root)` (tests, the git mirror) and `S3BlobStore(bucket, prefix="")` (boto3,
    conditional writes with `IfMatch` / `IfNoneMatch`);
  - move `DraftStore` onto a `BlobStore` (same keys as data-model §2), and replace `runs.json`
    with one object per stage run, `runs/{runId}-{stage}.json`;
  - remove what the 2026-11-10 gate decision made obsolete: `.generated/`, `humanEdits`,
    `flags`/`Flag` and `Approval`; add `dropped`, `levelChanges` and `failed` to `SectionDraft`
    and `devVersion`/`lastPromoted` to `BookState` (data-model §2);
  - tests: the Phase 2 tests run on `LocalBlobStore`; `tests/integration/test_storage_s3.py`
    (moto) covers conditional writes.
- [ ] T088 Split the stage runner in `pipeline/src/thinkbible_pipeline/stages/base.py` into
  functions the cloud and local paths share:
  - `plan_stage(stage, request, deps) -> StagePlan` (hash and skip; book-level stages run here);
  - `run_one_section(stage, plan_item, deps) -> SectionOutcome` (cap check, execute, write the
    draft, add the cost);
  - `finish_stage(plan, outcomes, deps) -> StageResult` (write the RunRecord with `codeVersion`);
  - a `SpendLedger` protocol with `InMemoryLedger` (local) and `DynamoLedger`
    (`pipeline/src/thinkbible_pipeline/cloud/ledger.py`, atomic `ADD`, conditional start);
  - `run()` (local mode) composes them with asyncio exactly as today, so the T028 tests keep
    passing; add `tests/integration/test_ledger_dynamo.py` (moto).
- [ ] T089 Read sources through a `BlobStore` in `sources/snapshot.py`: the local cache for
  `import` and `--local`, the sources bucket in Lambdas. Every read is still checked against the
  manifest's sha256; the manifest is read from the repo, or from the bundle in a Lambda.
- [ ] T090 Implement the Lambda handlers in `pipeline/src/thinkbible_pipeline/cloud/handlers.py`
  with JSON in/out models in `cloud/messages.py`:
  - `start_run`, `plan_stage`, `run_section`, `finish_stage`, `finish_run` (R7 state machine);
  - configuration from `PIPELINE_ENV`, `DRAFTS_BUCKET`, `SOURCES_BUCKET`, `LEDGER_TABLE`;
  - `run_section` catches model errors and records a failed section; it lets Bedrock throttling
    escape so Step Functions retries it;
  - `tests/integration/test_handlers.py` (moto + `FakeRunner`): a two-stage fixture run through
    all five handlers matches a `--local` run; the cap marks later sections "not started"; a
    source checksum mismatch fails `start_run`.
- [ ] T091 [P] Write the state machine in `infra/modules/pipeline/state_machine.asl.json` (a
  Terraform template: function ARNs and `max_concurrency` are variables), with a `Retry` on
  `Bedrock*Throttling`/`TooManyRequests` for `RunSection` and a `Fail` state for source checksum
  errors. Add `pipeline/tests/unit/test_state_machine.py`: the ASL parses, every Task names one of
  the five handlers, the Stages map has `MaxConcurrency` 1.
- [ ] T092 [P] Implement `pipeline/scripts/build_bundle.py` and `make lambda-bundle` (R19):
  install the locked dependencies for `manylinux2014_aarch64` / Python 3.12 into a staging folder,
  add both packages plus `pipeline/config/`, `pipeline/prompts/`, `pipeline/evals/`,
  `content/schema/` and `content/sources/manifest.json`, write `BUILD_INFO.json` with the git
  HEAD, and zip to
  `pipeline/out/lambda.zip`.
- [ ] T093 Write Terraform `infra/modules/pipeline/` (`main.tf`, `iam.tf`, `variables.tf`,
  `outputs.tf`) and add `module "pipeline"` to `infra/envs/dev/main.tf` (needs T037's storage
  module and the sources bucket):
  - the drafts bucket via `modules/storage` (`thinkbible-drafts-dev-522779858032`);
  - DynamoDB `thinkbible-pipeline-runs-dev` (on-demand, key `runId`, TTL attribute `ttl`);
  - five `aws_lambda_function`s from the bundle (arm64, python3.12, timeouts per R19, env vars),
    with log groups (30-day retention);
  - the state machine `thinkbible-pipeline-dev` (Standard) from the ASL template, with logging;
  - IAM per R19 (confirm the Bedrock Mantle invoke action while applying);
  - outputs `drafts_bucket`, `ledger_table`, `state_machine_arn` for `envs/dev.toml`.
- [ ] T094 Connect the cloud path to the CLI in `pipeline/src/thinkbible_pipeline/cli.py` and
  `app.py`:
  - `run`: estimate with `plan_stage` (read-only) against the S3 drafts, confirm, `StartExecution`
    with `{runId, request, capUsd}`, print the ARN and console link; `--wait` polls and maps the
    output to exit codes 0/2/3/4; `--local` runs in-process against the same S3 drafts;
  - `status --book [--open]`: the ledger's latest runs, run records, the latest scorecard's pass
    rates and failed sections; `--open` downloads `review.html` and opens it;
  - replace `ApproveRequest` with `PromoteRequest` in `requests.py`;
  - `envs/dev.toml` gains `drafts_bucket`, `ledger_table`, `state_machine_arn`;
  - Makefile: `pipeline` adds `--wait`; new `lambda-bundle`, `status` and `promote` targets;
  - update `pipeline/src/thinkbible_pipeline/README.md` (cloud flow and gate diagrams).

**Checkpoint**: `make test` passes with handler, storage and ledger tests on moto. After T093 is
applied and Bedrock quotas are raised, a cloud run can start.

---

## Phase 3: User Story 4 – Frozen source snapshot (Priority: P2, scheduled first) 

**Goal**: Import BSB, KJV and the three commentaries once. Store them write-once in S3, cache them
locally, and commit only the checksum manifest.

**Independent Test**: Run `import --books MRK`, `verify` and `sources push`. Change one byte in a
cached file and confirm every stage exits with code 2. Delete the cache, run `sources pull`, and
confirm `verify` passes.

### Tests for User Story 4 ⚠️ (write first, confirm they fail)

- [ ] T029 [P] [US4] Save small trimmed copies of real API responses as fixtures in
  `pipeline/tests/fixtures/api/`:
  - `BSB_MRK_7.json` (verses 14–18 with the 7:16 gap and footnote);
  - `eng_kjv_MRK_7.json` (the same verses, including 7:16);
  - `BSB_MRK_16.json` (verse 8 footnote);
  - `matthew-henry_MRK_1.json`, `jamieson-fausset-brown_MRK_1.json`, `adam-clarke_MRK_1.json`
    (the first 3 items plus the chapter introduction).
- [ ] T030 [P] [US4] Write `pipeline/tests/unit/test_normalize.py`:
  - headings, verses, footnotes with chapter/verse, poem lines with indent, and paragraph starts;
  - BSB 7:16 is absent and KJV 7:16 is present;
  - commentary book/chapter introductions and items keyed by `verse`.
- [ ] T031 [P] [US4] Write `pipeline/tests/unit/test_snapshot_verify.py`: a one-byte change raises
  `ChecksumMismatch`, and a missing file raises `MissingSource` with the pull hint.
- [ ] T032 [P] [US4] Write `pipeline/tests/integration/test_sources_store.py` with moto S3:
  - `push` uploads with `If-None-Match: *`;
  - re-pushing the same file is a no-op;
  - a different checksum at the same key is refused;
  - `pull` restores byte-identical files.

### Implementation for User Story 4

- [ ] T033 [US4] Implement `pipeline/src/thinkbible_pipeline/sources/normalize.py`:
  - **Translations**: convert API chapter JSON (`chapter.content[]` items of type `heading`,
    `verse`, `line_break`; verse content strings, `{noteId}`, `{text, poem}`, `{lineBreak}`;
    `chapter.footnotes[]`) into `NormalizedTranslationBook`. Drop audio and navigation links.
  - **Commentaries**: convert to `NormalizedCommentaryBook` (book `introduction`, chapter
    `introduction`, `items[{verse, text}]`).
- [ ] T034 [US4] Implement `pipeline/src/thinkbible_pipeline/sources/importer.py`, the only network
  code:
  - **Sources**: `bsb→BSB`, `kjv→eng_kjv`, `matthew-henry`, `jamieson-fausset-brown`,
    `adam-clarke`, from `https://bible.helloao.org/api/...` (R1 URL patterns).
  - **Fetching**: one request at a time, about 2 per second, User-Agent `ThinkBible-import/1.0`,
    exponential backoff with 5 retries.
  - **Upstream checksums**: `upstreamSha256` comes from `available_translations.json` and
    `available_commentaries.json`. `--api-version` defaults to the top `V…` heading of the
    HelloAO CHANGELOG.
  - **Output**: `snapshotId` is today's date (YYYY-MM-DD). Write
    `content/sources/{source}/{BOOK}.json` and update `content/sources/manifest.json`, with
    `s3Key = snapshots/{snapshotId}/{source}/{BOOK}.json`.
  - **Traditions**: Henry "Reformed (Presbyterian)", JFB "Reformed-leaning", Clarke "Wesleyan
    (Methodist)".
  - **Gaps**: books a commentary lacks (for example, Clarke has 57) are recorded as absent, not
    as errors.
  - **Flags**: `--books` and `--all`.
- [ ] T035 [US4] Implement `pipeline/src/thinkbible_pipeline/sources/store.py`:
  - **`push`**: for each manifest file missing from S3, `put_object` with
    `IfNoneMatch="*"` and metadata `sha256`. On 412, compare the remote metadata: equal → skip,
    different → error.
  - **`pull [--books]`**: download missing or mismatched files, then verify.
  - The bucket comes from `envs/{env}.toml` `sources_bucket`.
- [ ] T036 [US4] Connect `import`, `sources push`, `sources pull` and `verify` to the CLI in
  `pipeline/src/thinkbible_pipeline/cli.py`. `verify` exits 2 on any mismatch.
- [ ] T037 [P] [US4] Write Terraform:
  - **`infra/modules/storage/`** (`main.tf`, `variables.tf`, `outputs.tf`): `aws_s3_bucket` with
    versioning on, public access block (all four true), SSE-S3 and
    `BucketOwnerEnforced`. Variables `name` and `tags`; outputs `id`, `arn`,
    `bucket_regional_domain_name`.
  - **`infra/envs/dev/`** (`main.tf`, `backend.tf`, `outputs.tf`):
    - S3 backend `bucket = "thinkbible-tfstate-522779858032"`,
      `key = "envs/dev/terraform.tfstate"`, `region = "us-west-2"`, `use_lockfile = true`;
    - provider `aws` with region `us-west-2`;
    - `module "sources"` named `thinkbible-sources-522779858032`.
- [ ] T038 [US4] **Owner run** (AWS, no Bedrock needed):
  1. `export AWS_PROFILE=admin-thinkbible`, then `cd infra/envs/dev && terraform init && terraform apply`.
  2. `thinkbible-pipeline import --all`, then `verify`, then `sources push`.
  3. Check Mark: BSB has no 7:16 and has the "BYZ and TR include 16" footnote, and KJV has 7:16.
     Note which of 9:44, 9:46, 11:26 and 15:28 BSB omits.
  4. Commit **only** `content/sources/manifest.json` as
     `content: import source snapshot (Free Use Bible API V…)`.

**Checkpoint**: The snapshot is in S3, the manifest is in git, and quickstart §2 passes.

---

## Phase 4: User Story 1 – Generate and read a book's study content (Priority: P1) 🎯 MVP

**Goal**: `run --book mark --stage all` produces draft sections, key ideas with evidence, question
pools, context and views-differ notes, plus an HTML review report. This is the content spike.

**Independent Test**: With `FakeRunner` on the 2-chapter fixture, every section has drafts and
every key idea names a commentator. Then, with Bedrock, Mark 1–16 is fully drafted and
`review.html` opens. Re-running makes 0 model calls.

### Tests for User Story 1 ⚠️

- [ ] T039 [P] [US1] Write `pipeline/tests/unit/test_sections_builder.py` (R5):
  - sections start at BSB headings and never cross a chapter;
  - ranges are contiguous, non-overlapping, and cover every verse in either translation
    (including KJV-only 7:16);
  - sections with fewer than 3 verses merge into the next (the last one in a chapter merges into
    the previous);
  - sections longer than 12 verses split at a Henry division start, else at the paragraph break
    nearest the middle;
  - IDs are `mrk-{C}-{V}`;
  - split pieces get the title "{heading} (cont.)" with `titleSource: "split"` and a flag.
- [ ] T040 [P] [US1] Write `pipeline/tests/unit/test_crossrefs.py`. These parse into references:
  - "See on Mat 3:1-3 (note)"
  - "See the note on Mat 3:4"
  - "See on Mat 7:28-29"
  - "( = Mat 3:1-12; Luke 3:1-18)"
  - "which we had before, Mat 8:2-4"

  Abbreviations Mat/Mt/Matthew/Mar/Mr/Mark/Lu/Luke/Joh/John map to USFM. Only one hop is
  followed.
- [ ] T041 [P] [US1] Write `pipeline/tests/unit/test_gather.py` (R4):
  - for each commentator, the excerpt includes items in range, the overlapping Henry division,
    and introduction sentences citing an overlapping range;
  - cross-reference targets are labelled "parallel passage note";
  - when the 8,000-token cap is exceeded, the excerpt is trimmed at an item boundary and flagged.
- [ ] T042 [P] [US1] Write `pipeline/tests/unit/test_generate_postprocess.py`:
  - **Evidence check (R10)**: a quote not found in that commentator's excerpt removes that source,
    and an idea left with no sources is rejected.
  - **Ideas**: `agreed = len(sources) ≥ 2`; agreed ideas rank first.
  - **Levels (R11 rule)**: L1 = span ≤ 2, `stated`, `none`; L3 = `outsideKnowledge=required` or
    `answerDirectness=beyond` or type `application`; else L2.
  - **Pool rules**: levels are capped by the number of ideas (1 → L1, 2 → L1–2, 3+ → L1–3);
    "at most 2 questions per level", with the second `isAlternate: true`; a cap of 6; a
    missing whole-passage question marks the section for regeneration (R11).
  - **No prompt**: `noPrompt` with a reason when no idea is targetable.
  - **IDs**: counters never reuse IDs, even for rejected items.
- T043 (removed 2026-11-10: no hand edits to drafts, so no three-way merge; research R9).
- [ ] T044 [US1] Write `pipeline/tests/integration/test_generate_fixture_book.py`:
  - create a 2-chapter fixture book (Mark 1–2, trimmed) in a temp content directory, with
    recorded model outputs;
  - `run --local --stage all` (on a `LocalBlobStore`) produces `book.json`, `sections.json`,
    `sections/*.json`, `runs/*.json`, `scorecard.json` and `review.html`;
  - a second run reports 0 sections to process and $0.00 (SC-005).

### Implementation for User Story 1

- [ ] T045 [US1] Implement `pipeline/src/thinkbible_pipeline/sections/builder.py` (R5). Write
  `sections.json` to the draft store with `SectionMapEntry`
  `{id, chapter, verseStart, verseEnd, title, titleSource, henryDivisions}`.
- [ ] T046 [P] [US1] Implement `pipeline/src/thinkbible_pipeline/commentary/crossrefs.py`
  (patterns as in T040).
- [ ] T047 [US1] Implement `pipeline/src/thinkbible_pipeline/commentary/gather.py` (R4). Estimate
  tokens as chars/4. Record `excerpts[commentator] = {sha256, tokens, items, crossRefs, trimmed}`
  in the draft; the text itself is not stored.
- [ ] T048 [P] [US1] Implement the output models in
  `pipeline/src/thinkbible_pipeline/llm/outputs.py`, as data-model.md §4:
  - `SummaryOut {summary ≤120}`;
  - `IdeasOut {keyIdeas[{title, body, sources, verseStart, verseEnd, evidence[{commentator, quote ≤30 words}]}], context, viewsDiffer?, noPrompt, noPromptReason?}`;
  - `QuestionsOut {questions[{text, type, verseStart, verseEnd, targets, answerDirectness, outsideKnowledge}]}`.
- [ ] T049 [P] [US1] Write the prompts:
  - **`pipeline/prompts/summaries/v1.md`**: one-line passage summary.
  - **`pipeline/prompts/extract/v1.md`**:
    - FR-006 and FR-007: 1–5 ideas, only what the commentators say, neutral modern English, no
      quoted translation wording, verses only as `{{ref:C:V}}`, evidence quotes per cited
      commentator;
    - FR-012: a two-line context note (who wrote it, to whom, why), and a neutral views-differ
      note;
    - FR-005: noPrompt only when nothing is targetable, decided from the commentary, never from
      the passage type;
    - treat "parallel passage note" excerpts as applying to this section's passage.
  - **`pipeline/prompts/questions/v1.md`**: FR-008–FR-010 (open-ended, short, answerable from the
    passage, not leading, no tradition-specific assumptions, targets ≥1 idea without giving it
    away), shape by passage kind (in genealogies, lists and laws, ask about the verses the
    commentaries single out), and the recorded features.
- [ ] T050 [US1] Write `pipeline/prompts/question-guide/v1.md`: the brief's quality rules plus 15
  example questions, taken from the Mark 1 mockup questions (`docs/design/screens/*.png`, and the
  older `FeedHybrid.dc.html`: `git show c85bd1e:docs/design/screens/FeedHybrid.dc.html`). Start the
  file with "DRAFT: the owner must approve these examples before the first publish".
- [ ] T051 [P] [US1] Implement `pipeline/src/thinkbible_pipeline/drafts/ids.py`: per-section `k`
  and `q` counters in `book.json` `idCounters`, which only ever increase (R13).
- T052 (removed 2026-11-10, with T043).
- [ ] T053 [US1] Implement `pipeline/src/thinkbible_pipeline/stages/summaries.py` (Haiku). It
  stores `summary` per section; the next section's prompt uses the previous section's summary.
- [ ] T054 [US1] Implement `pipeline/src/thinkbible_pipeline/stages/generate.py`. Per section:
  1. Gather the excerpts.
  2. Call 1 (`extract`).
  3. Post-process: the evidence check, `agreed`, ranking, allocating `k` IDs, `addedIn` unset
     until publish.
  4. If not `noPrompt`, call 2 (`questions`).
  5. Assign levels with the R11 rule, apply the pool rules, set alternates, allocate `q` IDs.
  6. Write `sections/{id}.json` (it replaces the previous machine output; IDs are never reused).
- [ ] T055 [US1] Implement `pipeline/src/thinkbible_pipeline/report/render.py` and
  `pipeline/src/thinkbible_pipeline/report/templates/review.html.j2` (R17): the read-only
  scorecard. It writes `scorecard.json` and one self-contained `review.html` to the draft store,
  containing:
  - the headline: idea and question pass rates against the thresholds, failed sections, the
    calibration agreement, and the run's cost;
  - dropped items with their reasons, grouped by section;
  - every section with its passage (BSB/KJV toggle), key ideas with evidence quotes and grades,
    questions by level with alternates marked, context, views differ and manuscript notes;
  - `noPrompt` sections with their reasons.

  Until the gate stages exist (US2), the pass rates show as "not graded".
- [ ] T056 [US1] Register `sections`, `summaries`, `generate` and `report` in
  `pipeline/src/thinkbible_pipeline/stages/__init__.py` so `run` (cloud and `--local`) and
  `status` handle them:
  - `all` runs the implemented stages in the cli.md order;
  - `--sections`, `--fresh`, `--cap` and `--yes` work;
  - `BookState.status` follows the data-model.md state machine.
- [ ] T057 [US1] **Owner run** (needs Bedrock quotas above 0, docs/aws-setup.md):
  1. `make lambda-bundle`, then `terraform apply` in `infra/envs/dev` (T093), and copy the
     outputs into `pipeline/config/envs/dev.toml`.
  2. Tune on two sections first: `thinkbible-pipeline run --book mark --stage summaries,generate
     --local --sections mrk-1-1,mrk-1-9`.
  3. `make pipeline BOOK=mark STAGE=all`, confirming the estimate; then `make status BOOK=mark`
     to open the scorecard and read the content.
  4. Record a first impression in `specs/001-content-pack-pipeline/spike-notes.md`. The SC-004
     judgement is made with the calibrated grader in T064.
  5. If needed, iterate prompts as new `v2.md` files (tune with `--local`, then redeploy).

**Checkpoint**: The content spike is possible. US1 works on its own (quickstart §3–§4).

---

## Phase 5: User Story 2 – The automatic quality gate keeps weak content out (Priority: P1)

**Goal** (revised 2026-11-10, constitution v1.2.0): rule checks, the evidence check, an Opus 5.5
grader and a Haiku level check **act** on what they find: failing items are dropped or replaced
by their alternate, a section left without usable content is regenerated once and then failed,
and every run ends with a scorecard. The grader is calibrated against the owner's grades.

**Independent Test**: Seed a draft with a yes/no question, a question repeating a key idea word
for word, an idea whose evidence quote isn't in the excerpt, a broken placeholder, and an item the
fake grader scores 1. Each is dropped with the right reason, alternates fill in, and a section left
without a usable Level 1 question is regenerated and then marked failed.

### Tests for User Story 2 ⚠️

- [ ] T058 [P] [US2] Write `pipeline/tests/unit/test_checks.py`. Each seeded defect is dropped and
  listed in `dropped` with `stage: "check"` and a reason:
  - length limits;
  - a question not ending in "?";
  - a yes/no question: it starts with Is/Are/Do/Does/Did/Can/Could/Will/Would/Was/Were/Has/Have/Should
    and has no open interrogative;
  - a key idea title or body repeated word for word in a question (a normalised substring of
    8+ words, or the whole title);
  - an idea with no source backed by an evidence quote;
  - an unresolved placeholder in either translation;
  - a question targeting a missing idea;
  - a schema-invalid section;
  - a cross-field rule violation.
- [ ] T059 [P] [US2] Write `pipeline/tests/unit/test_gate.py` with `FakeRunner`:
  - grades at or below the threshold drop the item; a dropped primary question is replaced by its
    alternate;
  - the level check moves a covered Level 3 question to Level 2 and drops an uncovered Level 1
    question (its alternate fills in);
  - a section left without a key idea, or a prompted section without an active Level 1 question,
    is regenerated once, then marked `failed`;
  - pass rates are computed before drops, as R16 defines.
- [ ] T095 [P] [US2] Write `pipeline/tests/unit/test_calibration.py`: agreement is computed as the
  share of pass/fail matches; a result is "current" only for the grader prompt version and model
  in settings; `calibrate --label` keeps a copy of each item.

### Implementation for User Story 2

- [ ] T060 [US2] Implement `pipeline/src/thinkbible_pipeline/stages/checks.py`. It covers FR-016,
  with the list from spec Story 2 scenario 1 (including the evidence check), plus
  `thinkbible_core.rules`. Failing items are dropped into `dropped`; no model calls.
- [ ] T061 [P] [US2] Write the prompts:
  - **`pipeline/prompts/review/v1.md`**: the grader rubric (R16). The grader sees the passage, the
    commentators' excerpts and each item, and grades 1–5 per rubric line with a short reason.
  - **`pipeline/prompts/levels/v1.md`**: two parts, (a) answer as a typical reader using only the
    passage; (b) judge which target ideas the answer covers.

  Add `ReviewOut` and `LevelsAnswerOut`/`LevelsJudgeOut` to `llm/outputs.py`. In
  `pipeline/config/settings.toml`, set `stages.review.model = "anthropic.claude-opus-5-5"` and add
  `[gate] min_idea_pass_rate = 0.90, min_question_pass_rate = 0.80`.
- [ ] T062 [US2] Implement `pipeline/src/thinkbible_pipeline/stages/review.py` (Opus) and
  `pipeline/src/thinkbible_pipeline/gate/outcomes.py`: store `grades[itemId]`, drop items at or
  below `review_flag_threshold`, promote alternates, and apply the regenerate-once-then-fail rule
  (FR-018).
- [ ] T063 [US2] Implement `pipeline/src/thinkbible_pipeline/stages/levels.py` (Haiku answer plus
  Haiku judge, R11). It moves covered L3 questions to L2, drops uncovered L1 questions, and records
  `levelChanges`.
- [ ] T096 [US2] Implement `pipeline/src/thinkbible_pipeline/gate/calibration.py` and the
  `calibrate [--label] [--book]` command (R16, FR-020): `--label` picks a mix of items from the
  drafts and records your pass/fail grades in `pipeline/evals/calibration.json`; without it, it
  runs the grader on the set and appends `{graderPromptVersion, graderModel, agreement, runAt}`.
- [ ] T097 [US2] Implement `pipeline/src/thinkbible_pipeline/gate/scorecard.py`: build
  `scorecard.json` (data-model §2) including `promotable`, and show it in `review.html` (T055).
- [ ] T064 [US2] Register `check`, `review` and `levels` in `stages/__init__.py` for `run` and
  `all`. **Owner step**: label the calibration set (`calibrate --label`, at least 30 items) and
  run `calibrate`; reach 85% agreement (tune `review/vN.md` if not). Then record the SC-004
  judgement for Mark in `spike-notes.md`.

**Checkpoint**: US1 and US2 both work. Quickstart §3–§4 show the scorecard.

---

## Phase 6: User Story 3 – Publish to dev, read in the app, promote to production (Priority: P1)

**Goal**: A run whose gate passes publishes the book to dev. `promote` copies that exact pack to
production after checking the thresholds, the calibration, and the additive production publish
check, then updates prod's index and invalidates it in CloudFront.

**Independent Test**: Run the fixture book through the gate and confirm it is published to dev
(moto). Promote it and confirm prod has byte-identical files. Promotion is refused below the
thresholds, with a stale calibration, and on an in-place text edit of a promoted item (exit 5).

### Tests for User Story 3 ⚠️

- [ ] T065 [P] [US3] Write `pipeline/tests/unit/test_promote.py`:
  - `promote` refuses when the scorecard isn't promotable (failed sections, pass rates below the
    thresholds) or the calibration is missing, under 85%, or for another grader version;
  - it copies the dev files without rebuilding (same sha256s).
- [ ] T066 [P] [US3] Write `pipeline/tests/unit/test_publish_check.py`. Each data-model.md
  publish-check rule refuses a promotion:
  - a missing section ID or a changed range;
  - a missing idea or question ID;
  - changed `title`, `body`, `text` or `textByTranslation`;
  - `retired` → `active`;
  - a reused ID;
  - `replaces` pointing to an item that isn't retired.

  A valid retire-plus-replace passes. Dev publishes skip the check.
- [ ] T067 [P] [US3] Write `pipeline/tests/unit/test_build_pack.py`:
  - the study pack is built from the drafts, without dropped items;
  - `addedIn` is set on new items, `packVersion` is `1.0.0` on first publish, and `minor` is
    bumped on later content changes;
  - `sources` and `build` provenance are filled in, including the gate's pass rates;
  - verse files include `omittedVerses`, `lines` and `paragraphStart`;
  - every output validates against the schemas.
- [ ] T068 [US3] Write `pipeline/tests/integration/test_publish_moto.py`:
  - a run ending with `report` and no failed section publishes to the dev packs bucket: objects
    appear at `v1/books/mrk/{version}/study.json` and `…/verses/{bsb,kjv}.json` with
    `Cache-Control: public, max-age=31536000, immutable`, and `v1/index.json` with
    `public, max-age=300`; a run with a failed section publishes nothing;
  - `promote` copies them to the prod bucket and updates prod's index;
  - a second promotion downloads the previous production `study.json` through the index;
  - a CloudFront invalidation is requested for `/v1/index.json` in each environment (stubbed).

### Implementation for User Story 3

- [ ] T070 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/build.py`:
  - a `StudyPack` from the drafts (dropped items excluded);
  - `VerseText` for `bsb` and `kjv` from the normalised snapshot;
  - the version rule: first publish `1.0.0`; added or retired content → minor; notes or verse
    text only → patch.
- [ ] T071 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/publish_check.py`
  (data-model.md "Publish check", production only).
- [ ] T072 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/upload.py` (boto3), used for
  dev publishes:
  - `put_object` each file with `ContentType="application/json"` and the cdn-layout.md
    Cache-Control values;
  - write `index.json` with each file's sha256 and byte size;
  - `create_invalidation(Paths=["/v1/index.json"])`;
  - call it from `finish_run` (cloud) and the local runner when the run included `report` and no
    section failed (R14).

  Bucket and distribution IDs come from `envs/{env}.toml`.
- [ ] T069 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/promote.py`: check the
  scorecard and calibration, fetch the current prod `index.json` and previous `study.json`, run
  the publish check, copy the dev files byte for byte, update prod's index and invalidate it.
  Set `BookState.lastPromoted`.
- [ ] T073 [P] [US3] Write Terraform:
  - **`infra/modules/cdn/`** (`main.tf`, `variables.tf`, `outputs.tf`): an
    `aws_cloudfront_distribution` with Origin Access Control to the packs bucket, `compress = true`,
    a cache policy that respects origin `Cache-Control`, `PriceClass_100`, HTTPS redirect, and the
    bucket policy allowing only this distribution. Outputs `distribution_id` and `domain_name`.
  - **`infra/envs/dev/main.tf`**: add `module "packs"` (storage, `thinkbible-packs-dev-522779858032`)
    and `module "cdn"`, with outputs for `envs/dev.toml`.
  - **`infra/envs/prod/`**: the production packs bucket and `module "cdn"`. Whether prod lives in
    the dev account for now or in the planned prod account (docs/aws-setup.md → Later) is decided
    at T075.
- [ ] T074 [US3] Connect `publish --book [--dry-run]` (dev) and `promote --book` in `cli.py`. Their
  gates (failed sections; thresholds, calibration, publish check) exit 5.
- [ ] T075 [US3] **Owner run**:
  1. `terraform apply` in `infra/envs/dev` (and `infra/envs/prod`), then copy the outputs into
     `pipeline/config/envs/{dev,prod}.toml`.
  2. Confirm the last Mark run published to dev: `curl https://<dev-domain>/v1/index.json`.
  3. Read Mark in the app on dev (once spec 002's reader exists; until then, the scorecard).
  4. `make promote BOOK=mark`, then `curl https://<prod-domain>/v1/index.json` (quickstart §6).

**Checkpoint**: Mark can be published to dev and promoted. The app (spec 002) can use the pack.

---

## Phase 7: User Story 5 – Translation alignment (Priority: P2)

**Goal**: KJV wording variants where an item leans on BSB-only words, and neutral manuscript notes
where verses differ, with all of them listed for review.

**Independent Test**: Run `align` on Mark. The sandals question for 1:7 gets a KJV variant, the
section containing 7:16 gets a manuscript note, and so does 16:9–20 (from the 16:8 footnote).

### Tests for User Story 5 ⚠️

- [ ] T076 [P] [US5] Write `pipeline/tests/unit/test_align_detect.py`:
  - BSB-only token detection (stopwords removed, light stemming) flags "sandals" for Mark 1:7,
    but not words present in both translations;
  - manuscript candidates come from the verse-presence diff (7:16) and from BSB footnotes matching
    "manuscripts", "BYZ and TR include" or "Some early manuscripts" (16:8).

### Implementation for User Story 5

- [ ] T077 [US5] Implement `pipeline/src/thinkbible_pipeline/stages/align.py` and
  `pipeline/prompts/align/v1.md` (R12, R3):
  - code-based detection;
  - one Haiku call per affected item writes `textByTranslation.kjv`; one call per candidate
    writes a ≤ 280-character neutral manuscript note;
  - every output gets an `align` flag for review.

  Add `AlignVariantOut` and `ManuscriptNoteOut` to `llm/outputs.py`.
- [ ] T078 [US5] Add `align` to `run` and `all` (after `generate`, before `check`) in `cli.py`. Add
  an "Alignment" section to `review.html.j2` listing every variant and note.

**Checkpoint**: Alignment output is reviewed together with the rest of the book.

---

## Phase 8: User Story 6 – Additive refreshes keep IDs stable (Priority: P3)

**Goal**: After the first publish, items can only be retired and replaced, never edited, and new
questions can be added without touching existing ones.

**Independent Test**: Publish 1.0.0. Retire a question, add a replacement with `replaces`, and
publish 1.1.0: every 1.0.0 ID is present and unchanged, and the old item is `retired`. An in-place
text edit is refused.

### Tests for User Story 6 ⚠️

- [ ] T079 [P] [US6] Write `pipeline/tests/integration/test_refresh_versions.py` (moto):
  - the 1.0.0 → retire+replace → 1.1.0 flow succeeds;
  - an in-place edit of published text fails at `check` (and again at `publish`);
  - **published-section guard**: after 1.0.0, `run --stage generate --fresh` and a run with a new
    prompt version both make **zero model calls** for published sections, report them as
    "skipped: published (use --refresh)", and leave their drafts byte-identical. With
    `--refresh`, the same sections only gain new items with new IDs.

### Implementation for User Story 6

- [ ] T080 [US6] Freeze published content in the pipeline:
  - **`pipeline/src/thinkbible_pipeline/stages/checks.py`**: after a promotion, drafts record
    `publishedIn` per item. Any change to a promoted item's `title`, `body`, `text` or
    `textByTranslation` is a check failure with the message "published text is frozen: retire
    and replace (FR-024)".
  - **Published-section guard** in `pipeline/src/thinkbible_pipeline/stages/base.py` and
    `pipeline/src/thinkbible_pipeline/stages/generate.py`:
    - a section with any promoted item is **excluded** from `generate`, `summaries` and
      `align`, whatever `--fresh` or a prompt-version change says, unless `--refresh` is given;
    - excluded sections are left out of the cost estimate and listed as
      "skipped: in production (use --refresh)";
    - `check`, `review`, `levels` and `report` still run on them, because they don't rewrite
      content.
- [ ] T081 [US6] Add `retire --book B --item ID [--replace]` to `cli.py`, implemented in
  `pipeline/src/thinkbible_pipeline/drafts/retire.py`:
  - it sets `status: retired`; `retiredIn` is set at publish;
  - with `--replace`, it copies the item into a new item with a new ID and `replaces: <old>`;
  - retiring a key idea also retires the active questions that target only that idea (FR-024).
- [ ] T082 [US6] Add `--refresh` to `run --stage generate` in
  `pipeline/src/thinkbible_pipeline/stages/generate.py` and `pipeline/src/thinkbible_pipeline/cli.py`.
  It passes the existing questions into the questions prompt (FR-014), adds only new questions,
  and never modifies existing items.

**Checkpoint**: All stories work on their own.

---

## Phase 9: Polish and cross-cutting concerns

- [ ] T083 [P] Implement `eval` (R16, FR-029):
  - `pipeline/evals/mark-sample.json` holds 15–25 section IDs chosen after T057 (narrative,
    teaching, miracle, parable, a list, Mark 7 manuscript, Mark 16 ending, and more);
  - `pipeline/src/thinkbible_pipeline/evals/run.py` runs `generate`, `review` and `levels` in
    local mode for the current and a candidate prompt set into temporary `LocalBlobStore`s,
    grades both with the calibrated grader, and renders a side-by-side report with pass rates per
    rubric line;
  - it costs money, so it is never run in CI.
- [ ] T084 [P] Update the docs:
  - `pipeline/CLAUDE.md` (commands, stage order);
  - `README.md` (a pipeline quick reference);
  - `docs/aws-setup.md` (sources, drafts and packs buckets, ledger table, state machine and
    CloudFront domain once created);
  - `specs/README.md` (001 status).
- [ ] T085 Run quickstart.md §0–§8 end to end and fix anything that fails. Record the results at
  the bottom of `specs/001-content-pack-pipeline/spike-notes.md`.
- [ ] T086 Security pass:
  - the hook in `.pre-commit-config.yaml` rejects staged source text;
  - `grep` confirms no secrets or account credentials in the repo;
  - the network-guard and no-tools tests are in CI;
  - the S3 buckets are private, with public access blocked (`aws s3api get-public-access-block`);
  - the pipeline Lambda role can invoke only the three Claude 5.5 models and touch only its own
    buckets and table.

---

## Dependencies & execution order

### Phases

- **Setup (1)** comes first.
- **Foundational (2)** depends on Setup and **blocks every story**.
- **Cloud foundation (2b)** depends on Foundational. Its code tasks (T087–T092, T094) block real
  runs of every story; T093 (Terraform) also needs T037's storage module and sources bucket.
  Story unit tests don't need it.
- **US4 (3)** depends on Foundational. Real runs of US1, US2, US3 and US5 need its snapshot, but
  their unit tests can use fixtures.
- **US1 (4)** depends on Foundational. Its owner run (T057) also needs Phase 2b, US4's T038 and
  Bedrock quotas.
- **US2 (5)** is the quality gate. Its owner step (T064) labels the calibration set.
- **US2 (5)** depends on US1's drafts (checks and review read SectionDrafts).
- **US3 (6)** depends on US2, because publishing and `promote` read the gate's scorecard and the
  calibration. Its owner run needs US1's drafts.
- **US5 (7)** depends on US1. It can run in parallel with US2 and US3.
- **US6 (8)** depends on US3 (publish and the publish check).
- **Polish (9)** comes after the stories you plan to ship.

### Within each story

Tests first, and confirm they fail. Then output models, prompts, stage logic, CLI wiring, and the
owner run.

### Critical path

T001 → T009–T016 → T019–T027 → T087–T094 (cloud) → T033–T038 (snapshot) → T045–T057 (generate
and spike) → T060–T064, T095–T097 (gate and calibration) → T069–T075 (publish to dev, promote).

---

## Parallel opportunities

- **Setup**: T002, T003, T005, T006, T007.
- **Foundational**: T010, T011, T012, T013, T014 together; then T017 and T018; T028 after T023–T026.
- **Cloud foundation**: T091 and T092 alongside T087–T090; T093 after T037.
- **US4**: T029–T032 (tests) together; T037 (Terraform) alongside T033–T035.
- **US1**: T039–T042 (tests) together; T046, T048, T049, T051 together.
- **US2**: T058, T059 and T095 together; T061 alongside T060.
- **US3**: T065–T067 together; T073 (Terraform) alongside T069–T072.
- **After US1**: US5 can proceed in parallel with US2 and US3.

### Parallel example: User Story 1

```bash
# Tests together:
Task: "Write pipeline/tests/unit/test_sections_builder.py"
Task: "Write pipeline/tests/unit/test_crossrefs.py"
Task: "Write pipeline/tests/unit/test_gather.py"
Task: "Write pipeline/tests/unit/test_generate_postprocess.py"

# Independent modules together:
Task: "Implement commentary/crossrefs.py"
Task: "Implement llm/outputs.py"
Task: "Write prompts extract/v1.md, questions/v1.md, summaries/v1.md"
Task: "Implement drafts/ids.py"
```

---

## Implementation strategy

### MVP first: the content spike (Setup → Foundational → US4 → US1)

1. Phases 1–2 (no AWS needed), then Phase 2b's code and tests (moto, no AWS).
2. Phase 3 (US4): import and push the snapshot, and apply the Terraform (T037, T093). AWS is
   needed, Bedrock is not.
3. Phase 4 (US1): generate Mark and read `review.html`. **Stop and validate**: are the key ideas
   sound and the questions worth answering (SC-004)? Tune prompts before going further.

### Incremental delivery

4. US2: flags make review fast.
5. US3: publish Mark to dev. Spec 002 (the reader) can then build against a real pack.
6. US5: KJV variants and manuscript notes. These are needed before the KJV switch ships.
7. US6: retire and replace. Only needed after the first publish.

### Notes

- Commit after each task or logical group, with scope prefixes `pipeline:`, `infra:`,
  `content:`, `docs:`.
- Never commit source text. Commit `content/sources/manifest.json` only after `sources push`.
- Model-calling owner runs always show an estimate and respect the cap. CI never calls models.
