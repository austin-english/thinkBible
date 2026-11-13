# `thinkbible_pipeline`

## About

The batch content pipeline behind ThinkBible (spec 001). It takes the frozen source snapshot (the
BSB and KJV texts and three public-domain commentaries) and, one book at a time, writes the study
content the app shows:
- sections;
- key ideas attributed to the commentators;
- levelled questions;
- context and "views differ" notes.

An automatic quality gate checks every item before a book is published.

Runs execute in AWS: a Step Functions state machine with one Lambda per section per stage, drafts
in S3 and a spend ledger in DynamoDB. The CLI on your machine shows the cost estimate, starts
runs, and reports their status. The same code also runs in-process (`run --local`) for a few
sections at a time while tuning prompts.

Design docs: [`specs/001-content-pack-pipeline/`](../../../specs/001-content-pack-pipeline/) (plan,
research, data model, [CLI contract](../../../specs/001-content-pack-pipeline/contracts/cli.md)).
Rules for agents working here: [`pipeline/CLAUDE.md`](../../CLAUDE.md).

## File structure

```text
pipeline/
├── CLAUDE.md                       # area rules: no network outside the importer, never tools, …
├── pyproject.toml                  # package thinkbible-pipeline; CLI script `thinkbible-pipeline`
├── config/
│   ├── settings.toml               # model, effort, prompt version, default cost per stage; concurrency
│   ├── pricing.toml                # Bedrock USD per million tokens, per model
│   └── aws.toml                    # buckets, ledger table, state machine ARN (from `terraform output`)
├── prompts/
│   └── _shared/context-v1.md       # opening text of every system prompt; stages add {stage}/vN.md
├── scripts/
│   └── build_bundle.py             # `make lambda-bundle`: builds pipeline/out/lambda.zip
├── src/thinkbible_pipeline/
│   ├── README.md                   # this file
│   ├── __main__.py                 # `python -m thinkbible_pipeline`
│   ├── cli.py                      # Typer CLI: import, sources, verify, run, status, publish, promote, …
│   ├── app.py                      # wiring for the CLI: local deps, start a cloud run, wait for it
│   ├── requests.py                 # RunRequest / PublishRequest / PromoteRequest (CLI and cloud JSON)
│   ├── exitcodes.py                # exit codes 0–5 from the CLI contract
│   ├── config.py                   # loads config/*.toml into frozen dataclasses
│   ├── paths.py                    # repo paths (in a Lambda, /var/task is laid out like the repo)
│   ├── jsonio.py                   # canonical JSON, hashing, the camelCase base model
│   ├── storage.py                  # BlobStore: a local folder or S3, with conditional writes
│   ├── ledger.py                   # SpendLedger: a run's cap and spend (in memory for local runs)
│   ├── stages/
│   │   ├── base.py                 # shared steps: estimate, plan, run one section, finish; local run()
│   │   └── __init__.py             # registry() of stage implementations (filled in by US1+)
│   ├── cloud/
│   │   ├── handlers.py             # the five Lambda handlers the state machine calls
│   │   ├── messages.py             # JSON payloads between the state machine's steps
│   │   └── ledger.py               # DynamoLedger: the spend ledger in DynamoDB
│   ├── llm/
│   │   ├── runner.py               # BedrockRunner (Claude on Bedrock) and FakeRunner (tests)
│   │   ├── budget.py               # pricing, cost estimate, the Proceed? [y/N] prompt
│   │   └── prompts.py              # assembles the versioned system prompt for a stage
│   ├── drafts/
│   │   ├── models.py               # BookState, SectionDraft, RunRecord, … (data-model §2)
│   │   └── store.py                # DraftStore: reads and writes {book}/… in a BlobStore
│   └── sources/
│       ├── models.py               # source manifest and normalised book formats (data-model §3)
│       ├── importer.py             # `import`: the ONLY network code; fetches the five sources once
│       ├── normalize.py            # HelloAO chapter JSON → normalised translation books
│       ├── sword.py                # CrossWire module zip → normalised commentary books (offline)
│       ├── refs.py                 # tagged Scripture references → "MAT 12:9-21"
│       ├── versification.py        # KJV verses per chapter (1,189 chapters, 31,102 verses)
│       ├── check.py                # `sources check`: complete and in place?
│       ├── snapshot.py             # reads source files and checks each against the manifest
│       └── store.py                # `sources push` / `sources pull`: cache ↔ write-once S3 bucket
└── tests/
    ├── unit/                       # runner, budget, requests, state machine, bundle, guards
    ├── integration/                # on moto: storage, DynamoDB ledger, handlers, CLI cloud path
    └── fixtures/                   # trimmed API responses (api/) and recorded model outputs

infra/modules/pipeline/             # Terraform for the cloud side
├── main.tf                         # drafts bucket, ledger table, the five Lambdas, the state machine
├── iam.tf                          # least-privilege roles for the Lambdas and Step Functions
├── state_machine.asl.json.tftpl    # the state machine definition (a Terraform template)
├── variables.tf
└── outputs.tf                      # values to copy into config/aws.toml
```

Later user stories add `sections/`, `commentary/`, `gate/`, `report/`, `publish/` and the
individual stages (US1–US3).

## How a run flows

```mermaid
flowchart TD
    CLI["cli.py run<br/>parse flags → RunRequest"] --> EST["app.start_cloud_run<br/>estimate_run() on the S3 drafts"]
    EST --> OK{"Proceed? [y/N]"}
    OK -- no --> STOP(["nothing starts"])
    OK -- yes --> SFN["StartExecution<br/>{runId, request, capUsd}"]

    subgraph aws ["AWS: state machine thinkbible-pipeline"]
        SR["StartRun<br/>check sources vs manifest, create ledger item"]
        SR --> ST["Stages (one at a time)"]
        ST --> PS["PlanStage<br/>hash inputs, list sections to run"]
        PS --> SEC["Sections (10 at a time)<br/>RunSection: one Lambda per section"]
        SEC --> FS["FinishStage<br/>write run record, stop at the cap"]
        FS --> ST
        ST --> FR["FinishRun<br/>status, counts, exit code"]
    end

    SFN --> SR
    FR --> WAIT["--wait: app.wait_for_execution<br/>→ exit 0 / 2 / 3 / 4"]
```

Every step inside AWS calls one shared function in `stages/base.py`. `run --local` calls the same
functions in-process. What one `RunSection` does:

```mermaid
flowchart TD
    IN(["sectionId"]) --> CAP{"ledger.can_start()<br/>spend under cap?"}
    CAP -- no --> NS["not_started"]
    CAP -- yes --> EXEC["stage.execute()<br/>→ llm/runner.parse() → Bedrock"]
    EXEC -- "Throttled" --> RETRY["raised: Step Functions retries with backoff"]
    EXEC -- "other error" --> FAIL["StageRecord failed<br/>(other sections continue)"]
    EXEC -- ok --> SAVE["price() → StageRecord done<br/>write draft to S3, ledger.add(cost)"]
```

Things to know:
- **Unchanged work is skipped.** Each stage hashes everything a section's output depends on (its
  inputs, the prompt version and the model). If the hash matches the last successful run, the
  section is skipped. Re-running an unchanged book makes no model calls; `--fresh` forces it.
- **One bad section doesn't stop the book.** It's recorded as failed, the rest carry on, and the
  next run retries it.
- **Spend has a cap,** by default twice the estimate. Once spend reaches it, no new section starts;
  sections already running finish.

## Freezing the sources (once)

| Source | Upstream | How |
|---|---|---|
| BSB, KJV | Free Use Bible API (HelloAO) | one JSON request per chapter (~25 min) |
| Matthew Henry, JFB, Adam Clarke | CrossWire SWORD modules MHC, JFB, Clarke (public domain, from CCEL and Wikisource) | one zip per commentary, read offline by `sword.py` |

HelloAO also serves commentaries, but theirs were hand-copied and have shifted and missing
chapters, so the commentaries come from CrossWire (research R2a).

Two steps, with `AWS_PROFILE=admin-thinkbible` set and the infrastructure deployed:

```bash
uv run --package thinkbible-pipeline thinkbible-pipeline import --all   # saves after every book; a re-run resumes
make sources-publish                    # check, verify, push, then verify what's in S3
```

`make sources-publish` runs these in order and stops at the first failure:

| Step | Command | Proves |
|---|---|---|
| 1 | `sources check` | The cache is complete and in place (versification, order, coverage) |
| 2 | `verify` | Every cached file matches `content/sources/manifest.json` |
| 3 | `sources push` | Uploads what S3 doesn't have yet (write-once; safe to re-run) |
| 4 | `verify --remote` | Downloads every file from the sources bucket and checks it against the manifest |

It never moves or changes the local cache. Commit `content/sources/manifest.json` once it
passes. `sources push` on its own uploads only what's missing, so re-running it after a
partial upload is safe.

- **Nothing upstream can break the snapshot later.** Each file is checksummed and stored
  write-once. Each commentary's module zip is archived next to its books, so re-runs (and parser
  fixes, with `--refresh`) never need CrossWire again.
- **Each source records its edition** as `origin` (`helloao:BSB`, `crosswire:JFB@3.0`). Importing
  a new edition re-imports all of that source's books.
- `verify` proves files haven't changed since import; `sources check` proves they were right to
  begin with.

Commit only `content/sources/manifest.json`. On a new machine, `sources pull` restores the cache.
`import` is the only command that fetches text from the web, and it isn't run again unless a
source is deliberately added (constitution II).

## Running it

```bash
make pipeline BOOK=mark STAGE=all       # in AWS: estimate, confirm, start, wait for the result
make status BOOK=mark                   # latest runs, spend, and the scorecard
uv run --package thinkbible-pipeline thinkbible-pipeline run --book mark --stage generate \
  --local --sections mrk-1-1,mrk-1-9    # in-process, two sections, using the repo's prompts
```

Before the pipeline is deployed, `run` says so and points you to `--local`, which then keeps
drafts in `content/drafts/` instead of S3.

## Deploying

```bash
export AWS_PROFILE=admin-thinkbible
make deploy                                     # make lambda-bundle, then terraform apply in infra/
terraform -chdir=infra output                   # first time: copy into pipeline/config/aws.toml
```

The first time on a machine, run `terraform -chdir=infra init` before `make deploy`.

Rebuild and re-apply after any change to pipeline code, config or prompts. The Lambdas only see
what was in the zip. `--local` runs read the repo directly, which is why they're the fast way to
tune prompts.

### What `make lambda-bundle` does

It runs `pipeline/scripts/build_bundle.py`, which builds `pipeline/out/lambda.zip` (about 25 MB,
gitignored):

1. **Lists the dependencies.** It exports the exact locked versions the pipeline uses from
   `uv.lock` (`anthropic`, `pydantic`, `boto3`, …), without dev tools.
2. **Downloads Lambda's builds of them.** The Lambdas run Linux on ARM (arm64, Python 3.12), not
   macOS. Packages with compiled code, such as `pydantic-core`, are fetched as Linux arm64 wheels.
3. **Adds our code:** the `thinkbible_core` and `thinkbible_pipeline` packages.
4. **Adds the files the code reads at runtime,** laid out like the repo so the code finds them the
   same way it does locally:
   - `pipeline/config/` and `pipeline/prompts/`;
   - `content/schema/`, the content pack contract;
   - `content/sources/manifest.json`, the source checksums (from US4; until then the build warns
     that it's missing);
   - `pipeline/evals/`, the grader calibration set (from US2).
5. **Writes `BUILD_INFO.json`** with the git commit it was built from. Every run record stores it
   as `codeVersion`, so you can tell which code produced a draft. There's deliberately no build
   timestamp: the same commit gives a byte-identical zip, so `terraform apply` only redeploys the
   Lambdas when the code changed.
6. **Zips it** and fails if the zip is over 50 MB, Lambda's limit for a direct upload.

The five Lambdas share this one zip; each starts at a different handler in `cloud/handlers.py`.
`terraform apply` uploads it to all five when it changed.

## Writing a stage

A stage implements four methods; the runner does the rest, in the cloud and locally:

| Method | What it returns |
|---|---|
| `prompt_version()` | The prompt version it uses (recorded and hashed) |
| `model()` | The Bedrock model ID it calls, or `None` if it calls no model |
| `inputs()` | Everything its output depends on, as JSON-ready data. Hashed to decide skips |
| `execute()` | Does the work, updates the section's draft in place, and returns the token usage |

Whole-book stages (`sections`, `report`) subclass `BookStage` and implement `run_book()` instead.
Register a stage in `stages/__init__.py`.

## Rules the tests enforce

- Only `sources/importer.py` (US4) may import networking modules (`test_network_guard.py`).
- No model request carries `tools` (`test_no_tools.py`).
- The state machine calls exactly the five handlers (`test_state_machine.py`).
- Terraform allows exactly the models and concurrency in `settings.toml` (`test_infra_sync.py`).
- Tests never call models. They use `FakeRunner`, and AWS is mocked with moto.
