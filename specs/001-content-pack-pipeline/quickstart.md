# Quickstart: validate the content pipeline end to end

These steps prove spec 001 works. Commands, data shapes and URLs are defined in
[contracts/](contracts/) and [data-model.md](data-model.md). Revised 2026-11-20 (T085) for the
Claude API, batch runs and one AWS environment; the last run's results are in
[spike-notes.md](spike-notes.md) §9.

`tp` below is `uv run --package thinkbible-pipeline thinkbible-pipeline`.

**Mark and Philippians are real content on the draft channel.** Steps that change content (§7,
§8) use other books, so they never touch them.

## Prerequisites

- `uv`, Python 3.12, Terraform ≥ 1.8, and the AWS CLI with a profile for the ThinkBible account
  (`export AWS_PROFILE=admin-thinkbible`).
- The Claude API key in the SSM SecureString `anthropic-api-key` (docs/aws-setup.md). Runs read
  it at run time; it is never in the repo, Terraform state or logs.
  (The `bedrock` profile, `THINKBIBLE_PROFILE=bedrock`, needs Bedrock quotas above 0 instead.)
- `pipeline/config/pricing.toml` holds current prices (R15), and `pipeline/config/aws.toml`
  holds the bucket names, ledger table, state machine ARN, distribution ID and CDN URL from
  `terraform output`.

## 0. Bootstrap and offline tests (no AWS, no cost)

```bash
make bootstrap
make lint && make test
```

**Expected**: everything passes (373 tests on 2026-11-20). No test calls a model (`FakeRunner`)
or AWS (moto). That includes:
- the schema contract tests;
- the unit tests for sections, cross-references, checks, the publish check, the cost cap and
  running out of API credit;
- the fixture book end to end (`test_generate_fixture_book.py`): `run` → the gate → publish to
  the draft channel → `promote`, and a second run with nothing to do;
- batch runs (`test_batch.py`): a batch run writes exactly what a standard run writes, at half
  the price of the batch stages, and the cloud batch loop (`test_handlers.py`).

## 1. Infrastructure (once, and after any code, config or prompt change)

```bash
make deploy        # the Lambda bundle, then terraform apply in infra/ (owner's OK)
```

**Expected**: private, HTTPS-only sources, drafts and packs buckets; a CloudFront distribution
in front of the packs bucket; the run ledger table; seven pipeline Lambdas; and the
`thinkbible-pipeline` state machine. Copy the outputs into `pipeline/config/aws.toml` the first
time. There is one environment: draft and live are the `draft/` and `live/` channels of the one
packs bucket (contracts/cdn-layout.md).

## 2. The frozen sources

**Import (once, about 25 minutes; already done):**

```bash
tp import --all
make sources-publish    # sources check → verify → sources push → verify --remote
```

Commit **only the manifest** as
`content: import source snapshot (BSB/KJV HelloAO V…, commentaries CrossWire)`.

**Check the snapshot (free, any time):**

```bash
tp sources check
tp verify
tp verify --remote
```

**Expected**:
- `sources check` passes for all five sources with 66 books each. The KJV has 31,102 verses and
  116 psalm titles; the BSB has 31,086 and lists its 16 omitted verses (including MRK 7:16).
  Each commentary reports its coverage.
- `verify` and `verify --remote` report all 333 files matching `manifest.json`, in the local
  cache and in the sources bucket.

**Fresh clone test**: move the cache aside (don't delete it until the pull has verified), then
pull it back.

```bash
mkdir -p /tmp/sources-aside && mv content/sources/*/ /tmp/sources-aside/
tp sources pull
tp verify
diff -rq /tmp/sources-aside content/sources | grep -v manifest   # prints nothing
rm -rf /tmp/sources-aside
```

**Expected**: 333 files downloaded (about a minute), `verify` passes and the files are
identical.

**Tamper test (FR-002)**: keep a copy of `content/sources/adam-clarke/MRK.json`, change one
character in it, and run `tp run --book mark --stage sections --local`. **Expected**: exit code
2, "does not match manifest … Nothing was generated". Restore the copy (or `tp sources pull`)
and run `tp verify`. The cache is gitignored, so `git checkout` can't restore it.

## 3. Calibrate the grader (once per grader, and per new kind of book)

```bash
tp calibrate --label --book mark     # grade at least 30 items pass/fail
tp calibrate                         # run the grader on the held-out items (costs money)
```

**Expected**: `pipeline/evals/calibration.json` holds your grades, and `calibrate` reports the
grader's agreement. At least 85% unlocks promotion (SC-009). Commit `calibration.json`. Done for
Mark: 89% on 36 held-out items with Opus 5.5 and `review/v14`. Re-run after any grader change,
and run a short rating round on the first book of a new kind (a letter, poetry, law, prophecy)
before promoting it (research.md R11, "Genres").

## 4. Generate a book

```bash
make pipeline BOOK=philippians STAGE=all   # a cloud run: estimate, confirm, start, wait
make status BOOK=philippians               # runs, spend, and the scorecard (review.html)
```

**Expected**:
1. Before starting, it prints an estimate and the cap (twice the estimate) and asks for
   confirmation. Cloud runs use Message Batches for `generate` and `review` by default (half
   price; `--no-batch` for the standard API), and it says so. Then it prints the execution ARN and
   a console link.
2. The run ends with the book published to the draft channel (no failed sections). A batch run
   takes about 40 minutes for a short book: each batch round is about 10 minutes.
3. The scorecard shows the measures against their thresholds (SC-004: 90% of key ideas pass,
   90% of sections lead with a question graded 4 or 5, 95% have a full set of questions), every
   dropped item with its reason, the calibration agreement, and the cost.

Measured: Mark, 100 sections on the standard API, about $19 and 30 minutes; Philippians, 14
sections in batches, $1.67 and 38 minutes.

**Prompt tuning** (no deploy, standard API):
`tp run --book mark --stage generate,check,review --local --sections mrk-1-1,mrk-1-9 --fresh`
writes into the real drafts, so use it on sections you're willing to regenerate. To compare a
prompt change without touching drafts, use `eval` (pipeline/evals/candidates/README.md).

**Spot checks** (Mark, in the scorecard or the drafts):
- `mrk-7-14` has a manuscript note on 7:16 (in the KJV, not the BSB), and `mrk-16-9` one on the
  ending after 16:8.
- KJV wording variants where an item quotes BSB-only wording: 13 sections, for example
  `mrk-1-40` ("If thou wilt").
- Every key idea has evidence quotes and a grade, many cite more than one commentator (316 of
  533), and every question ends with "?".

## 5. Idempotency (SC-005)

```bash
make pipeline BOOK=mark STAGE=all
```

**Expected**: it starts without an estimate or a Proceed? prompt, since no stage would call a
model. Every content stage reports all sections skipped, and the run ends with `spent $0.000`.
The `report` stage still runs. If the drafts changed since the last publish (for example a later
`align` run), it publishes them as a new version on the draft channel.

## 6. Read on the draft channel, then promote

```bash
curl -s https://<cdn>/draft/v1/index.json | jq .
# after reading the book in the app (spec 002):
make promote BOOK=mark
curl -s https://<cdn>/live/v1/index.json | jq .
```

**Expected**:
- The draft channel's `index.json` lists each book at its version, with the sha256 and size of
  `study.json`, `verses/bsb.json` and `verses/kjv.json`. The downloaded files match those
  sha256s, validate against `content/schema/`, and total under 1 MB compressed (SC-007).
- Before anything is promoted, the live index returns 403 (the bucket is private, so a missing
  object reads as forbidden). The app treats that as "no books yet".
- `promote` copies the same files to live: the live channel's `index.json` shows the same
  version and sha256s. Promotion freezes the book's text (FR-024): only promote after reading
  it.
- Nothing was added under `content/` in git except `calibration.json`.

## 7. Gate and promotion refusals (FR-021, FR-024)

**On real infrastructure (free, writes nothing):** `make promote BOOK=2jn`. 2 John was a batch
test whose grader failed 2 of its 3 sections, and it was never published. **Expected**: exit code
5, listing the scorecard's blockers and "2 John isn't on the draft channel; publish it".

**The rest are tested offline** (they would freeze real content if run on live):

| Refusal | Expected | Test |
|---|---|---|
| A section failed | nothing published, exit code 3, the scorecard names it | `test_publish_moto.py::test_a_book_with_a_failed_section_publishes_nothing` |
| Below a threshold | exit code 5, the measure and its bar | `test_gate.py::test_a_weak_first_question_blocks_promotion`, `test_publish_moto.py::test_promote_refuses_an_unpromotable_book` |
| Drafts changed since publishing | exit code 5, "run `publish` first" | `test_publish_moto.py::test_promote_refuses_drafts_changed_since_publishing` |
| Stale calibration | not promotable until `calibrate` runs for the current grader | `test_calibration.py::test_only_a_result_for_the_current_grader_prompt_and_model_counts` |
| Changed live text | exit code 5, "published text changed" | `test_publish_check.py::test_each_rule_refuses`, `test_refresh_versions.py::test_changed_live_wording_fails_check_and_cannot_publish` |
| Retire and replace | promoted as a minor version; the old ID stays, `status: retired` | `test_refresh_versions.py::test_retire_and_replace_goes_live_as_a_minor_version` |

## 8. Spend cap (FR-028)

Use a book not yet generated, and only the cheap stages, so the test costs a fraction of a cent
and what it writes is reusable:

```bash
tp run --book romans --stage sections,summaries --local --cap 0.001 --yes
tp status --book romans
```

**Expected**: the estimate (about $0.12 for 58 sections; the default of $0.002 a section, since
Romans has no history) and `cap $0.001`. The run stops with exit code 4 once spend passes the cap
("summaries: 13 done … stopped: cap reached (45 not started)"); sections already in flight
finish (SC-008), finished summaries are kept, and `status` shows what is left. Running it again
without `--cap` finishes the rest.
