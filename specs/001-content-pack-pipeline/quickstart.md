# Quickstart: validate the content pipeline end to end

These steps prove spec 001 works. Commands, data shapes and URLs are defined in
[contracts/](contracts/) and [data-model.md](data-model.md).

## Prerequisites

- `uv`, Python 3.12, Terraform ≥ 1.8, and the AWS CLI with a profile for the dev account
  (`export AWS_PROFILE=admin-thinkbible`).
- Bedrock model access granted in the dev account and region for Claude Sonnet 5.5 and Claude
  Haiku 5.5, plus Claude Opus 5.5 for the refusal fallback: the token-per-minute quotas must be
  above 0 (docs/aws-setup.md → Troubleshooting).
- `pipeline/config/pricing.toml` holds current Bedrock prices (R15), and
  `pipeline/config/envs/dev.toml` holds the bucket names, ledger table, state machine ARN and
  distribution ID from `terraform output`.

## 0. Bootstrap and offline tests (no AWS, no cost)

```bash
make bootstrap
make lint && make test
```

**Expected**: everything passes. That includes:
- the schema contract tests;
- the unit tests for sections, cross-references, checks, the publish check, the merge and the cost
  cap;
- the fake-model integration test, which runs a fixture book through `run` → the gate →
  publish to dev → `promote` against moto S3.

## 1. Dev infrastructure (once, and after code or prompt changes)

```bash
make lambda-bundle
cd infra/envs/dev && terraform init && terraform apply
```

**Expected**: private sources, drafts and packs buckets, a CloudFront distribution in front of
the packs bucket, the run ledger table, five pipeline Lambdas and the
`thinkbible-pipeline-dev` state machine. Copy the outputs into `pipeline/config/envs/dev.toml`.
Before the first promotion, `infra/envs/prod` adds the production packs bucket and CloudFront
(`pipeline/config/envs/prod.toml`).

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

## 3. Calibrate the grader (once)

```bash
thinkbible-pipeline run --book mark --stage summaries,generate --local --sections mrk-1-1,mrk-1-9,mrk-1-12 --yes
thinkbible-pipeline calibrate --label --book mark     # grade at least 30 items pass/fail
thinkbible-pipeline calibrate                         # run the grader on them
```

**Expected**: `pipeline/evals/calibration.json` holds your 30+ grades, and `calibrate` reports the
grader's agreement. At least 85% unlocks promotion (SC-009). Commit `calibration.json`.

## 4. Generate Mark (the content spike)

```bash
make pipeline BOOK=mark STAGE=all        # adds --wait
make status BOOK=mark                    # opens the scorecard
```

**Expected**:
1. Before starting the execution, it prints an estimate (about $8–14 for about 100 sections,
   including the Opus grader) and the cap, and asks for confirmation. Then it prints the
   execution ARN and a console link.
2. The run ends with the book published to dev (no failed sections).
3. The scorecard shows the pass rates against the thresholds (90% of ideas, 80% of questions:
   SC-004), every dropped item with its reason, the calibration agreement, and the cost.

**Prompt tuning** (no deploy): `thinkbible-pipeline run --book mark --stage generate,check,review
--local --sections mrk-1-1,mrk-1-9 --fresh` runs two sections in-process with the repo's prompts.

**Spot checks** (in the scorecard):
- `mrk-1-1`: KJV wording variant on the sandals question, and key ideas citing more than one
  commentator. This works because cross-references to Matthew 3 were followed.
- The Mark 7 section that contains 7:16 has a manuscript note. So does Mark 16 (ending after
  16:8).
- Every key idea has evidence quotes and a grade, and every question ends with "?".

## 5. Idempotency (SC-005)

```bash
make pipeline BOOK=mark STAGE=all
```

**Expected**: the estimate shows 0 sections to process and $0.00, and no model calls are made.

## 6. Read on dev, then promote

```bash
curl -s https://<dev-distribution>/v1/index.json | jq .
make promote BOOK=mark
curl -s https://<prod-distribution>/v1/index.json | jq .
```

**Expected**:
- Dev's `index.json` lists `MRK` at its version, with the sha256 and size of `study.json`,
  `verses/bsb.json` and `verses/kjv.json`; the three files validate against the schemas, and the
  total compressed size is under 1 MB (SC-007).
- After reading the book in the app on dev, `promote` copies the same files to production:
  prod's `index.json` shows the same version and sha256s.
- Nothing was added under `content/` in git except `calibration.json`.

## 7. Gate and promotion refusals (FR-021, FR-024)

1. **Failed section**: make one section fail (a recorded fake output with no usable Level 1
   question in the integration test). **Expected**: nothing is published to dev, exit code 3, and
   the scorecard names the section.
2. **Below threshold**: set `gate.min_question_pass_rate` above the book's rate and `promote`.
   **Expected**: exit code 5, "question pass rate 0.84 < 0.90".
3. **Stale calibration**: add a new grader prompt version, then `promote`. **Expected**: exit
   code 5, "grader calibration is for review v1; run `calibrate`".
4. **Frozen text in production**: after a promotion, change a promoted question's text and
   promote again. **Expected**: exit code 5, "published text changed: mrk-1-1-q1".
5. **Retire and replace**: retire that question and add a replacement with `replaces`, then run,
   publish to dev and promote. **Expected**: the next version is promoted. The old ID is still
   present with `status: retired`, and prod's `index.json` points to the new version.

## 8. Spend cap (FR-028)

```bash
thinkbible-pipeline run --book mark --stage review --fresh --cap 0.10 --yes
```

**Expected**: the run stops with exit code 4 after spend passes $0.10, finished sections are kept,
and `status` shows what is left.
