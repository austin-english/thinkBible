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

- [ ] T009 Copy `specs/001-content-pack-pipeline/contracts/{section,study-pack,verses,index}.schema.json`
  unchanged into `content/schema/`. These become the binding contract; the copies in contracts/
  are now only references.
- [ ] T010 [P] Create the fixtures, one file per case:
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

- [ ] T011 [P] Implement `shared/src/thinkbible_core/models/section.py`: Pydantic v2 models
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
- [ ] T012 [P] Implement the remaining models, matching the contract schemas field for field:
  - `shared/src/thinkbible_core/models/pack.py`: `StudyPack`, `Book`, `TranslationRef`, `Source`,
    `Build`;
  - `shared/src/thinkbible_core/models/verses.py`: `VerseText`;
  - `shared/src/thinkbible_core/models/index.py`: `PackIndex`.
- [ ] T013 [P] Implement `shared/src/thinkbible_core/ids.py`:
  - a USFM table for all 66 books (code, English name, lowercase code);
  - name aliases (`mark` → `MRK`, `matthew` → `MAT`, …);
  - ID builders and parsers: `section_id("MRK", 1, 1) == "mrk-1-1"`, `key_idea_id(sec, n)`,
    `question_id(sec, n)`, and `parse_item_id`.
- [ ] T014 [P] Implement `shared/src/thinkbible_core/refs.py`:
  - find, parse and validate `{{ref:C:V}}` and `{{ref:C:V-V}}` placeholders (R13);
  - `unresolved(text, verse_sets_by_translation)` returns placeholders missing from any
    translation.
- [ ] T015 Implement `shared/src/thinkbible_core/schema.py`:
  - load `content/schema/*.schema.json` into a `referencing.Registry` keyed by `$id`;
  - `validate(doc, kind)` returns a list of error messages, for `kind` in
    `section|study-pack|verses|index`.
- [ ] T016 Implement `shared/src/thinkbible_core/rules.py`. `cross_field_violations(pack)` returns
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
- [ ] T017 [P] Write the contract tests in `shared/tests/test_contract.py`:
  - every `fixtures/valid/*.json` validates against its JSON Schema **and** parses with the
    models;
  - every `fixtures/invalid/*.json` fails both;
  - `model_dump(by_alias=True, exclude_none=True)` of each valid fixture validates against the
    schema.
- [ ] T018 [P] Write unit tests for `ids.py`, `refs.py` and each rule in `rules.py` in
  `shared/tests/test_ids_refs_rules.py`.

### Pipeline framework (`thinkbible_pipeline`)

- [ ] T019 Create the config files and loader:
  - **`pipeline/config/settings.toml`**:
    - `region = "us-west-2"`;
    - models per stage: summaries/align/levels `us.anthropic.claude-haiku-5-5`,
      generate/review `us.anthropic.claude-sonnet-5-5`, refusal fallback
      `us.anthropic.claude-opus-5-5`;
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
- [ ] T020 Implement `pipeline/src/thinkbible_pipeline/paths.py`: find the repo root and expose
  content paths (`content/schema`, `content/sources`, `content/drafts/{book}`).
- [ ] T021 Implement source-snapshot models and the verifier:
  - **`pipeline/src/thinkbible_pipeline/sources/models.py`**: Pydantic `SourceManifest` with
    `bucket`, `apiVersion`, and per-source/per-book `file`, `s3Key`, `sha256`, `bytes`,
    `retrievedAt`, `snapshotId`, license fields and `tradition`. Plus `NormalizedTranslationBook`
    and `NormalizedCommentaryBook`, exactly as data-model.md §3.
  - **`pipeline/src/thinkbible_pipeline/sources/snapshot.py`**: `load_book(source, book)` checks
    sha256 against the manifest before returning parsed data. A mismatch raises
    `ChecksumMismatch` (CLI exit code 2). A missing cache file raises `MissingSource`, with the
    message "run `thinkbible-pipeline sources pull`".
- [ ] T022 Implement draft entities and storage:
  - **`pipeline/src/thinkbible_pipeline/drafts/models.py`**: `BookState`, `SectionMapEntry`,
    `SectionDraft`, `Flag`, `CheckResult`, `StageRecord`, `RunRecord`, `Approval`, with exactly
    the fields in data-model.md §2.
  - **`pipeline/src/thinkbible_pipeline/drafts/store.py`**: read and write `book.json`,
    `sections.json`, `sections/{id}.json`, `.generated/{id}.json`, `runs.json` (append) and
    `approval.json`. Write canonical JSON (sorted keys, 2-space indent, trailing newline) so git
    diffs stay small.
- [ ] T023 Implement the ModelRunner in `pipeline/src/thinkbible_pipeline/llm/runner.py`:
  - a `ModelRunner` Protocol:
    `async parse(stage, system: list[block], user: str, output_model: type[BaseModel]) -> (model, Usage)`;
  - **`BedrockRunner`**:
    - uses the Anthropic SDK `AnthropicBedrockMantle(aws_region=settings.region)` and
      `messages.parse` with structured output;
    - `cache_control` on the stable system prefix, and adaptive thinking with per-stage
      `output_config.effort`;
    - **asserts no `tools` key** in the request;
    - on `stop_reason == "refusal"`, retries once on the fallback model (client-side
      `BetaRefusalFallbackMiddleware`; check the exact API against the SDK docs). If that is also
      refused, it raises `Refused(category)`;
    - retries invalid structured output up to 2 times;
  - **`FakeRunner`**: replays recorded outputs from
    `pipeline/tests/fixtures/model_outputs/{stage}/{section_id}.json` for tests.
- [ ] T024 Implement `pipeline/src/thinkbible_pipeline/llm/budget.py` (R15):
  - `price(usage, model)` from `pricing.toml`;
  - `estimate(stage, n_sections, runs)`: median cost per section over the last 20 runs of that
    stage in `runs.json`, else the settings default;
  - a `Budget(cap)` with `add(cost)` and `can_start()`;
  - a `confirm(estimate, cap, yes)` helper that prints sections to process, sections skipped,
    the estimate and the cap.
- [ ] T025 Implement `pipeline/src/thinkbible_pipeline/llm/prompts.py`:
  - load `pipeline/prompts/{stage}/{version}.md` and `pipeline/prompts/question-guide/{version}.md`;
  - every system prompt starts with `pipeline/prompts/_shared/context-v1.md`;
  - return the prompt versions for recording.

  Also create `pipeline/prompts/_shared/context-v1.md` with the R6 "Context in every system
  prompt" text: the model is summarising published, public-domain Christian commentaries
  (Matthew Henry, Jamieson-Fausset-Brown, Adam Clarke, 18th–19th century) on canonical Scripture
  for a Bible-study app. Passages may describe violence, sexuality or judgement as part of the
  biblical text. The job is to restate what the commentators say.
- [ ] T026 Implement the stage runner in `pipeline/src/thinkbible_pipeline/stages/base.py`:
  - map an async stage function over sections with `asyncio.Semaphore(concurrency)`;
  - input hash = sha256 of canonical JSON of (inputs, prompt version, model ID). Skip a section
    when `stages[stage]` has the same `promptVersion` and `inputHash` and `status == "done"`,
    unless `--fresh`;
  - record a `StageRecord` per section; a failure marks only that section `failed`;
  - check the Budget before starting each section, stop starting new ones once the cap is passed,
    and let in-flight sections finish;
  - append a `RunRecord`;
  - return exit code 0, 3 (some sections failed) or 4 (cap reached).
- [ ] T027 Create the CLI skeleton in `pipeline/src/thinkbible_pipeline/cli.py`:
  - a Typer app with commands `import`, `sources push`, `sources pull`, `verify`, `run`,
    `status`, `approve`, `publish`, `eval`;
  - book argument resolution via `thinkbible_core.ids`;
  - an `ExitCode` enum with 0–5 exactly as in contracts/cli.md;
  - unimplemented commands exit 1 with "not implemented yet".
- [ ] T028 [P] Write the framework tests in `pipeline/tests/unit/`:
  - `test_budget.py`: estimate from history versus defaults; the cap stops new sections;
  - `test_stage_runner.py`: skip on the same hash; `--fresh` re-runs; one failure doesn't stop
    others; exit codes 3 and 4;
  - `test_no_tools.py`: the BedrockRunner request builder never includes `tools`;
  - `test_network_guard.py`: an AST scan of `pipeline/src` shows that only
    `sources/importer.py` imports `urllib`, `http.client`, `httpx`, `requests` or `socket`.

**Checkpoint**: `make test` passes, with contract tests green and the framework tested with
`FakeRunner`.

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
    "at most 2 questions per level", with the second `isAlternate: true`; a cap of 6; the
    whole-passage requirement is flagged.
  - **No prompt**: `noPrompt` with a reason when no idea is targetable.
  - **IDs**: counters never reuse IDs, even for rejected items.
- [ ] T043 [P] [US1] Write `pipeline/tests/unit/test_merge.py` (R9):
  - an untouched field takes the new machine value;
  - a human-edited field is kept and recorded in `humanEdits`;
  - when the machine value also changed, a `merge` flag is raised.
- [ ] T044 [US1] Write `pipeline/tests/integration/test_generate_fixture_book.py`:
  - create a 2-chapter fixture book (Mark 1–2, trimmed) in a temp content directory, with
    recorded model outputs;
  - `run --stage all` produces `book.json`, `sections.json`, `sections/*.json`, `.generated/*.json`
    and `review.html`;
  - a second run reports 0 sections to process and $0.00 (SC-005).

### Implementation for User Story 1

- [ ] T045 [US1] Implement `pipeline/src/thinkbible_pipeline/sections/builder.py` (R5). Write
  `content/drafts/{book}/sections.json` with `SectionMapEntry`
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
  example questions, taken from the Mark 1 mockup questions in `FeedHybrid.dc.html`. Start the
  file with "DRAFT: the owner must approve these examples before the first publish".
- [ ] T051 [P] [US1] Implement `pipeline/src/thinkbible_pipeline/drafts/ids.py`: per-section `k`
  and `q` counters in `book.json` `idCounters`, which only ever increase (R13).
- [ ] T052 [P] [US1] Implement `pipeline/src/thinkbible_pipeline/drafts/merge.py`: the three-way
  merge of `.generated` (old), the working copy and the new machine output (R9).
- [ ] T053 [US1] Implement `pipeline/src/thinkbible_pipeline/stages/summaries.py` (Haiku). It
  stores `summary` per section; the next section's prompt uses the previous section's summary.
- [ ] T054 [US1] Implement `pipeline/src/thinkbible_pipeline/stages/generate.py`. Per section:
  1. Gather the excerpts.
  2. Call 1 (`extract`).
  3. Post-process: the evidence check, `agreed`, ranking, allocating `k` IDs, `addedIn` unset
     until publish.
  4. If not `noPrompt`, call 2 (`questions`).
  5. Assign levels with the R11 rule, apply the pool rules, set alternates, allocate `q` IDs.
  6. Write `.generated/{id}.json` and merge into `sections/{id}.json`.
- [ ] T055 [US1] Implement `pipeline/src/thinkbible_pipeline/report/render.py` and
  `pipeline/src/thinkbible_pipeline/report/templates/review.html.j2` (R17). One self-contained
  HTML file at `content/drafts/{book}/review.html` (gitignored), containing:
  - flagged items first, grouped by section, with reasons;
  - every section with its passage (BSB/KJV toggle), key ideas with evidence quotes, questions
    by level with alternates marked, context, views differ and manuscript notes;
  - `noPrompt` reasons;
  - human edits highlighted;
  - run cost.
- [ ] T056 [US1] Connect `run --stage sections|summaries|generate|report|all` and `status` in
  `pipeline/src/thinkbible_pipeline/cli.py`:
  - `all` runs the implemented stages in the cli.md order and stops at `ready-for-review`;
  - `--sections`, `--fresh`, `--cap` and `--yes` work;
  - `BookState.status` follows the data-model.md state machine.
- [ ] T057 [US1] **Owner run** (needs Bedrock, after account verification):
  1. `make pipeline BOOK=mark STAGE=all`, confirming the estimate.
  2. Read `review.html`.
  3. Record the spike judgement against SC-004 (≥ 90% of ideas sound, ≥ 80% of questions worth
     answering) in `specs/001-content-pack-pipeline/spike-notes.md`.
  4. If needed, iterate prompts as new `v2.md` files.

**Checkpoint**: The content spike is possible. US1 works on its own (quickstart §3–§4).

---

## Phase 5: User Story 2 – Automatic checks and model review flag weak content (Priority: P1)

**Goal**: Deterministic checks plus a Sonnet quality review and a Haiku level check flag weak
items, with reasons. Approval is blocked while checks fail.

**Independent Test**: Seed a draft with a yes/no question, a question repeating a key idea word
for word, an idea with no source, and a broken placeholder. Each is flagged with the right reason,
and `approve` refuses.

### Tests for User Story 2 ⚠️

- [ ] T058 [P] [US2] Write `pipeline/tests/unit/test_checks.py`. Each seeded defect produces a
  `CheckResult(ok=False)` and a `check` flag with a reason:
  - length limits;
  - a question not ending in "?";
  - a yes/no question: it starts with Is/Are/Do/Does/Did/Can/Could/Will/Would/Was/Were/Has/Have/Should
    and has no open interrogative;
  - a key idea title or body repeated word for word in a question (a normalised substring of
    8+ words, or the whole title);
  - an idea with no source;
  - an unresolved placeholder in either translation;
  - a question targeting a missing idea;
  - a schema-invalid section;
  - a cross-field rule violation.
- [ ] T059 [P] [US2] Write `pipeline/tests/unit/test_levels_check.py` with `FakeRunner`: a covered
  Level 3 question moves to Level 2 with a `levels` flag, and an uncovered Level 1 question is
  flagged but keeps its level.

### Implementation for User Story 2

- [ ] T060 [US2] Implement `pipeline/src/thinkbible_pipeline/stages/checks.py`. It covers FR-016,
  with the exact list from spec Story 2 scenario 1, plus `thinkbible_core.rules`. It writes
  `checks[]` and `check` flags, and makes no model calls.
- [ ] T061 [P] [US2] Write the prompts:
  - **`pipeline/prompts/review/v1.md`**: grade each idea and question 1–5 against the quality
    rules and attribution neutrality, and give flag reasons.
  - **`pipeline/prompts/levels/v1.md`**: two parts, (a) answer as a typical reader using only the
    passage; (b) judge which target ideas the answer covers.

  Add `ReviewOut` and `LevelsAnswerOut`/`LevelsJudgeOut` to `llm/outputs.py`.
- [ ] T062 [US2] Implement `pipeline/src/thinkbible_pipeline/stages/review.py` (Sonnet). It stores
  `grades[itemId]` and flags items scoring ≤ `review_flag_threshold`.
- [ ] T063 [US2] Implement `pipeline/src/thinkbible_pipeline/stages/levels.py` (Haiku answer plus
  Haiku judge, R11). It moves covered L3 questions to L2 and flags uncovered L1 questions.
- [ ] T064 [US2] Add `check`, `review` and `levels` to `run` and `all` in
  `pipeline/src/thinkbible_pipeline/cli.py`. Make sure the report lists flagged items first.

**Checkpoint**: US1 and US2 both work. Quickstart §3 shows flags.

---

## Phase 6: User Story 3 – Human review gate and publishing (Priority: P1)

**Goal**: `approve` gates on checks and flags. `publish` runs the publish check against the last
published version (downloaded from S3), uploads a versioned pack plus `index.json`, and
invalidates the index in CloudFront.

**Independent Test**: Approve the reviewed fixture or Mark drafts, publish to dev (or moto), and
fetch `index.json`, `study.json` and both verse files. Unapproved drafts, edited drafts and
in-place text edits are all refused with exit code 5.

### Tests for User Story 3 ⚠️

- [ ] T065 [P] [US3] Write `pipeline/tests/unit/test_approve.py`:
  - `approve` refuses with check failures and lists unresolved flags;
  - a flag counts as resolved when the item was edited, rejected, or has `flagAccepted: true`;
  - `approval.json` has `draftsSha256`, `approvedAt` and `gitHead`;
  - `publish` refuses when the drafts' hash differs.
- [ ] T066 [P] [US3] Write `pipeline/tests/unit/test_publish_check.py`. Each data-model.md
  publish-check rule refuses publishing:
  - a missing section ID or a changed range;
  - a missing idea or question ID;
  - changed `title`, `body`, `text` or `textByTranslation`;
  - `retired` → `active`;
  - a reused ID;
  - `replaces` pointing to an item that isn't retired.

  A valid retire-plus-replace passes.
- [ ] T067 [P] [US3] Write `pipeline/tests/unit/test_build_pack.py`:
  - the study pack is built from approved drafts, without rejected items;
  - `addedIn` is set on new items, `packVersion` is `1.0.0` on first publish, and `minor` is
    bumped on later content changes;
  - `sources` and `build` provenance are filled in;
  - verse files include `omittedVerses`, `lines` and `paragraphStart`;
  - every output validates against the schemas.
- [ ] T068 [US3] Write `pipeline/tests/integration/test_publish_moto.py`:
  - publish the fixture book to moto S3: objects appear at `v1/books/mrk/1.0.0/study.json` and
    `…/verses/{bsb,kjv}.json` with `Cache-Control: public, max-age=31536000, immutable`, and
    `v1/index.json` with `public, max-age=300`;
  - a second publish downloads the previous `study.json` through the index;
  - a CloudFront invalidation is requested for `/v1/index.json` (stubbed client).

### Implementation for User Story 3

- [ ] T069 [US3] Implement `pipeline/src/thinkbible_pipeline/drafts/approval.py` and connect
  `approve` in `cli.py` (R18). It confirms by asking you to type the book name.
- [ ] T070 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/build.py`:
  - a `StudyPack` from approved drafts;
  - `VerseText` for `bsb` and `kjv` from the normalised snapshot;
  - the version rule: first publish `1.0.0`; added or retired content → minor; notes or verse
    text only → patch.
- [ ] T071 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/publish_check.py`
  (data-model.md "Publish check").
- [ ] T072 [US3] Implement `pipeline/src/thinkbible_pipeline/publish/upload.py` (boto3):
  - fetch the current `v1/index.json` and the previous `study.json`;
  - `put_object` each file with `ContentType="application/json"` and the cdn-layout.md
    Cache-Control values;
  - write `index.json` with each file's sha256 and byte size;
  - `create_invalidation(Paths=["/v1/index.json"])`.

  Bucket and distribution IDs come from `envs/{env}.toml`.
- [ ] T073 [P] [US3] Write Terraform:
  - **`infra/modules/cdn/`** (`main.tf`, `variables.tf`, `outputs.tf`): an
    `aws_cloudfront_distribution` with Origin Access Control to the packs bucket, `compress = true`,
    a cache policy that respects origin `Cache-Control`, `PriceClass_100`, HTTPS redirect, and the
    bucket policy allowing only this distribution. Outputs `distribution_id` and `domain_name`.
  - **`infra/envs/dev/main.tf`**: add `module "packs"` (storage, `thinkbible-packs-dev-522779858032`)
    and `module "cdn"`, with outputs for `envs/dev.toml`.
- [ ] T074 [US3] Connect `publish --book --env [--dry-run]` in `cli.py`. Its gates (no approval,
  drafts changed, publish check) all exit 5. `--dry-run` builds and checks without uploading.
- [ ] T075 [US3] **Owner run**:
  1. `terraform apply` in `infra/envs/dev`, then copy the outputs into
     `pipeline/config/envs/dev.toml`.
  2. `approve --book mark`, then `make publish BOOK=mark ENV=dev`.
  3. `curl https://<domain>/v1/index.json` (quickstart §6).

**Checkpoint**: Mark can be published to dev. The app (spec 002) can use the pack.

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
  - **`pipeline/src/thinkbible_pipeline/stages/checks.py`**: after a publish, drafts record
    `publishedIn` per item. Any change to a published item's `title`, `body`, `text` or
    `textByTranslation` is a check failure with the message "published text is frozen: retire
    and replace (FR-024)".
  - **Published-section guard** in `pipeline/src/thinkbible_pipeline/stages/base.py` and
    `pipeline/src/thinkbible_pipeline/stages/generate.py`:
    - a section with any published item is **excluded** from `generate`, `summaries` and
      `align`, whatever `--fresh` or a prompt-version change says, unless `--refresh` is given;
    - excluded sections are left out of the cost estimate and listed as
      "skipped: published (use --refresh)";
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

- [ ] T083 [P] Implement `eval` (R16):
  - `pipeline/evals/mark-sample.json` holds 8 section IDs chosen after T057 (narrative, teaching,
    miracle, parable, Mark 7 manuscript, Mark 16 ending, plus 2 more);
  - `pipeline/src/thinkbible_pipeline/evals/run.py` runs `generate`, `review` and `levels` for a
    candidate prompt set into a temp directory and renders a side-by-side report against the
    current drafts;
  - it costs money, so it is never run in CI.
- [ ] T084 [P] Update the docs:
  - `pipeline/CLAUDE.md` (commands, stage order);
  - `README.md` (a pipeline quick reference);
  - `docs/aws-setup.md` (sources bucket, packs bucket and CloudFront domain once created);
  - `specs/README.md` (001 status).
- [ ] T085 Run quickstart.md §0–§8 end to end and fix anything that fails. Record the results at
  the bottom of `specs/001-content-pack-pipeline/spike-notes.md`.
- [ ] T086 Security pass:
  - the hook in `.pre-commit-config.yaml` rejects staged source text;
  - `grep` confirms no secrets or account credentials in the repo;
  - the network-guard and no-tools tests are in CI;
  - the S3 buckets are private, with public access blocked (`aws s3api get-public-access-block`).

---

## Dependencies & execution order

### Phases

- **Setup (1)** comes first.
- **Foundational (2)** depends on Setup and **blocks every story**.
- **US4 (3)** depends on Foundational. Real runs of US1, US2, US3 and US5 need its snapshot, but
  their unit tests can use fixtures.
- **US1 (4)** depends on Foundational. Its owner run (T057) also needs US4's T038 and Bedrock
  access.
- **US2 (5)** depends on US1's drafts (checks and review read SectionDrafts).
- **US3 (6)** depends on US2, because `approve` gates on checks. Its owner run needs US1's drafts.
- **US5 (7)** depends on US1. It can run in parallel with US2 and US3.
- **US6 (8)** depends on US3 (publish and the publish check).
- **Polish (9)** comes after the stories you plan to ship.

### Within each story

Tests first, and confirm they fail. Then output models, prompts, stage logic, CLI wiring, and the
owner run.

### Critical path

T001 → T009–T016 → T019–T027 → T033–T038 (snapshot) → T045–T057 (generate and spike) →
T060–T064 → T069–T075 (publish).

---

## Parallel opportunities

- **Setup**: T002, T003, T005, T006, T007.
- **Foundational**: T010, T011, T012, T013, T014 together; then T017 and T018; T028 after T023–T026.
- **US4**: T029–T032 (tests) together; T037 (Terraform) alongside T033–T035.
- **US1**: T039–T043 (tests) together; T046, T048, T049, T051, T052 together.
- **US2**: T058 and T059 together; T061 alongside T060.
- **US3**: T065–T067 together; T073 (Terraform) alongside T069–T072.
- **After US1**: US5 can proceed in parallel with US2 and US3.

### Parallel example: User Story 1

```bash
# Tests together:
Task: "Write pipeline/tests/unit/test_sections_builder.py"
Task: "Write pipeline/tests/unit/test_crossrefs.py"
Task: "Write pipeline/tests/unit/test_gather.py"
Task: "Write pipeline/tests/unit/test_generate_postprocess.py"
Task: "Write pipeline/tests/unit/test_merge.py"

# Independent modules together:
Task: "Implement commentary/crossrefs.py"
Task: "Implement llm/outputs.py"
Task: "Write prompts extract/v1.md, questions/v1.md, summaries/v1.md"
Task: "Implement drafts/ids.py"
Task: "Implement drafts/merge.py"
```

---

## Implementation strategy

### MVP first: the content spike (Setup → Foundational → US4 → US1)

1. Phases 1–2 (no AWS needed).
2. Phase 3 (US4): import and push the snapshot. AWS is needed, Bedrock is not.
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
