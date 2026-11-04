# Research: Content Pack Format and Batch Pipeline

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-11-04

All Technical Context unknowns are resolved below. Facts about the Free Use Bible API were checked
against the live API on 2026-11-04: docs, `available_translations.json`,
`available_commentaries.json`, and BSB, Matthew Henry, JFB and Adam Clarke chapters of Mark.

## R1. Where the source text comes from, and how it is fetched

**Decision**: a one-time `import` command fetches per-chapter JSON from the Free Use Bible API
(`https://bible.helloao.org/api/...`) for five sources, for the whole Bible:

| Source | API id | URL pattern | License (as stated by the API) |
|---|---|---|---|
| Berean Standard Bible | `BSB` | `/api/BSB/{BOOK}/{ch}.json` | Public domain (CC0), `https://berean.bible/` |
| King James Version | `eng_kjv` | `/api/eng_kjv/{BOOK}/{ch}.json` | Public domain in the US (eBible `eng-kjv2006`) |
| Matthew Henry | `matthew-henry` | `/api/c/matthew-henry/{BOOK}/{ch}.json` | Public Domain Mark 1.0 |
| Jamieson-Fausset-Brown | `jamieson-fausset-brown` | `/api/c/jamieson-fausset-brown/{BOOK}/{ch}.json` | Public Domain Mark 1.0 |
| Adam Clarke | `adam-clarke` | `/api/c/adam-clarke/{BOOK}/{ch}.json` | Public Domain Mark 1.0 |

- Book IDs are USFM codes (`MRK`, `MAT`, `GEN`).
- Requests run one at a time at about 2 per second, with a generic User-Agent. The API states it
  has no rate limits, but the brief asks for a polite rate.
- That is about 5,600 requests, which takes under an hour.
- `eng_kja` (KJV with Apocrypha) is ignored.
- `import` is the only code path allowed to make network requests for text (constitution II).

**Rationale**: per-chapter files are small, can be retried individually, and match how the
pipeline reads text. The API publishes a sha256 for each translation and commentary, and the
manifest records it for provenance.

**Alternatives considered**:
- `api.zip` (1.5 GB) or `bible.eng.db` (1.5 GB SQLite) as a bulk download. Rejected: we need 5
  sources, not 1,256 translations. Kept as a fallback if the per-chapter endpoints change.
- Pulling only the launch book's text. Rejected: commentaries on Mark point to Matthew and Luke
  (R4), and the brief plans a single whole-Bible snapshot.

## R2. How the frozen snapshot is stored

**Decision**: the text lives in S3, and the checksums live in git.

- **Files**: one **normalised** JSON file per source per book. Normalising removes audio links,
  navigation links and other presentation-only fields. It keeps verses, headings, paragraph
  breaks, poetry indent, footnotes, and commentary introductions and items.
- **S3**: the files are stored in a private, versioned bucket (`thinkbible-sources`, in the dev
  account for now) under `snapshots/{snapshotId}/{source}/{BOOK}.json`.
  - `snapshotId` is the import date, for example `2026-11-05`.
  - Uploads are conditional writes (`If-None-Match: *`), so an object is never overwritten. A
    re-import creates a new snapshot ID.
- **Git**: only `content/sources/manifest.json` is committed. Per file it records: source ID, S3
  key, sha256 of the normalised file, upstream sha256, retrieval date, API version (the top entry
  of the HelloAO CHANGELOG at import time), name, license and license URL.
- **Local cache**: `content/sources/{source}/{BOOK}.json` on your machine is gitignored.
  `sources pull` downloads missing files, and every stage checks every file it reads against the
  manifest before doing any work.
- **Without AWS**: `import` writes the local cache and the manifest. `sources push` uploads the
  files once the bucket exists.

**Rationale**:
- About 60–80 MB of text that never changes belongs in object storage, not in every clone.
- The manifest keeps source changes reviewable in git, as CLAUDE.md requires, and keeps tamper
  detection: a changed S3 object or cache file fails its checksum.
- The future cloud runner reads the same objects.

**Alternatives considered**:
- Plain git. Rejected because of size: every clone and CI checkout would carry the whole
  snapshot.
- Git LFS. Rejected because it adds tooling and storage quotas, and still ties the text to the
  git host.
- S3 with no manifest in git. Rejected because source changes would no longer be reviewed.

## R3. Verse numbering, omitted verses and manuscript notes

**Findings**:
- BSB omits verses that modern critical texts drop. Mark 7:16 has no verse object, and the
  chapter jumps from 15 to 17. The variant is described in a footnote on 7:15 ("BYZ and TR
  include 16 …").
- The other usual Mark candidates (9:44, 9:46, 11:26, 15:28) are expected to behave the same way
  and are checked at import.
- Mark 16:9–20 is present as normal verses with no brackets. A footnote on 16:8 says some early
  manuscripts end there.
- KJV includes all these verses.

**Decision**:
- Manuscript notes come from two signals:
  1. a code diff of which verses exist in each translation;
  2. BSB footnotes that mention manuscripts (patterns such as "manuscripts", "BYZ and TR include",
     "Some early manuscripts").
- Each candidate becomes a short, neutral note written by the alignment step, and is always
  listed for human review.
- Verse-text files carry `omittedVerses` so the app can render the gap correctly.

## R4. Commentary structure and gathering excerpts per section

**Findings** (Mark 1):

| Commentary | Text granularity | Chapter introduction | Words in Mark 1 |
|---|---|---|---|
| Matthew Henry | One item per **division**, keyed by its first verse: 1, 9, 14, 23, 29, 40 | Outline with verse ranges | ~7,600 |
| Jamieson-Fausset-Brown | Sparse per-verse items. The introduction holds heading lines with parallels ("= Mat 3:1-12; Luke 3:1-18") and the first paragraph | Yes | ~2,200 |
| Adam Clarke | Per verse, with gaps | Summary with verse ranges | ~2,900 |

- JFB and Clarke often point to their notes on the parallel Gospel instead of repeating them, for
  example Clarke's "See on Mat 3:1-3 (note)" or JFB's "See on Mat 7:28-29". Henry's text says
  "which we had before, Mat 8:2-4".

**Decision**:
- A section's excerpt for each commentator is:
  - (a) items whose key verse falls inside the section;
  - (b) for Henry, the whole division overlapping the section, with the part about the section's
    verses highlighted when the division is longer;
  - (c) chapter-introduction sentences that cite a verse range overlapping the section;
  - (d) **one hop** of cross-references. The pattern parser recognises "See on {Book} {c}:{v}",
    "See the note on …" and "( = Mat …)". The target is that commentator's note on the parallel
    passage, read from the same frozen snapshot and labelled "parallel passage note" in the
    prompt.
- Excerpts are capped at 8k tokens per commentator. When the cap is hit, the excerpt is trimmed
  at item boundaries, the section is flagged, and the trim is recorded.

**Rationale**: without step (d), JFB and Clarke contribute almost nothing to many Mark sections,
and the "agreed by 2+ commentators" signal falls apart. Cross-references stay inside the closed
world (constitution II).

**Cost implication**: excerpts are about 3–6k tokens per section including cross-references, well
below the brief's assumed ~12k. The brief's cost estimates are therefore conservative.

## R5. Building sections (FR-004, FR-005)

**Decision**: a deterministic code step in the `sections` stage:

1. Start with the BSB headings in each chapter. Each heading begins a candidate section.
2. Sections never cross chapter boundaries, because the reader scrolls one chapter at a time. A
   heading that starts mid-chapter in the previous chapter is cut at the chapter start.
3. Compare against Henry's division start verses. If a candidate is longer than 12 verses and
   contains a Henry boundary, split it there. If it has no Henry boundary, split it at the
   paragraph break nearest its middle.
4. Merge candidates shorter than 3 verses into the next section in the same chapter. A section at
   the end of a chapter merges into the previous one instead.
5. The title is the BSB heading. Split pieces get a provisional title "{heading} (cont.)", which
   is flagged so you can retitle it during review.
6. The section ID is `{book}-{chapter}-{startVerse}` in lowercase USFM, for example `mrk-1-1`.

The output is `content/drafts/{book}/sections.json`. You can edit it freely before first publish.
Once published, IDs and verse ranges are frozen and enforced by the publish check (FR-024).

Every section, genealogies included, goes on to key-idea extraction. "No prompt" is decided
later, from the extraction result (FR-005).

## R6. Model access and request design

**Decision**:
- **Client**: Amazon Bedrock through the official Anthropic Python SDK
  (`anthropic[bedrock]`, `AnthropicBedrockMantle(aws_region="us-west-2")`), as the constitution
  requires.
  - Model IDs are config values. The defaults are the US cross-region inference profiles
    `us.anthropic.claude-sonnet-5-5`, `us.anthropic.claude-haiku-5-5` and
    `us.anthropic.claude-opus-5-5` (fallback), confirmed available on 2026-11-04.
  - The organization's region policy allows Bedrock invoke in every region and everything else
    only in us-west-2 (docs/aws-setup.md → Regions). So all ThinkBible resources live in
    us-west-2, and CloudFront and its ACM certificate in us-east-1.
- **Models by stage**:

  | Stage | Model | Reason |
  |---|---|---|
  | `summaries` (one-line passage summary) | Haiku 5.5 | Cheap, and parallel, since it reads only the passage |
  | `generate` (key ideas, context, views differ, then questions) | Sonnet 5.5 | Quality-critical |
  | `align` (wording variants, manuscript notes) | Haiku 5.5 | The brief's "small model call" |
  | `review` (quality grading) | Sonnet 5.5 | Needs judgement |
  | `levels` (typical-reader check) | Haiku 5.5 | Stands in for a typical reader |

- **Structured outputs**: each call uses `client.messages.parse(...)` with a Pydantic output model
  (supported on Bedrock). Invalid output is retried up to 2 times, then the section is marked
  failed.
- **Thinking and effort**: Sonnet 5.5 runs with adaptive thinking, which is on by default. Effort
  is set per stage in config, starting at `medium` for `generate` and `review` and `low` for the
  Haiku stages. Tune during the Mark spike, since thinking tokens dominate cost.
- **Prompt caching**: the system prompt and question guide are a stable prefix with a
  `cache_control` breakpoint. Per-section content comes after it.
- **Context in every system prompt**: each stage's system prompt opens by stating the task. The
  model is summarising published, public-domain Christian commentaries (Matthew Henry,
  Jamieson-Fausset-Brown, Adam Clarke, 18th–19th century) on canonical Scripture for a
  Bible-study app. Passages may describe violence, sexuality or judgement as part of the biblical
  text, and the job is to restate what the commentators say about them. The passage reference
  and the commentators' text are always included. A passage is never sent stripped of this
  context.
- **No tools, ever**: requests never include `tools`. A unit test asserts this for every stage
  (constitution II).
- **Refusals**: Bedrock has no server-side `fallbacks`, so the SDK's client-side
  `BetaRefusalFallbackMiddleware` retries a refused request once on `claude-opus-5-5`. If that is
  also refused, the section is marked failed and flagged with the refusal category. This exists
  because Old Testament passages with violence could trip safety classifiers. Remove it if you'd
  rather review those sections by hand.
- **Batch inference**: deferred. Stages call a `ModelRunner` interface so that a Bedrock
  batch-inference runner can replace the on-demand runner for later books without changing stage
  code.

**Alternatives considered**: the first-party Claude API, which offers Message Batches and
server-side fallbacks. Rejected for now because the constitution names Bedrock and the rest of
the stack is AWS. This is a config switch if that ever changes.

## R7. Orchestration for the MVP

**Decision**:
- A **local async runner**. `asyncio` maps over sections with a concurrency limit, default 10.
- It is driven by a Typer CLI (`thinkbible-pipeline`, see [contracts/cli.md](contracts/cli.md)).
- The Step Functions per-book workflow is deferred until later books (see Complexity Tracking in
  the plan).

**Rationale**: the spec's assumption, and the speed of tuning prompts on Mark. Each stage is a pure
function from inputs to outputs, keyed by section and prompt version, so moving to Step Functions
later only changes the orchestration.

## R8. Pipeline state, idempotency and resuming

**Decision**:
- State lives **in the draft files**, not in DynamoDB. Each section draft records, per stage:
  prompt version, model ID, input hash (sha256 of the canonical JSON of all inputs) and cost.
- A stage skips a section when the recorded prompt version and input hash match. That makes
  SC-005 true: an unchanged re-run makes zero model calls.
- `--fresh` forces regeneration.
- Book-level status lives in `content/drafts/{book}/book.json`.

**Rationale**: the review flow is git-based (Clarification Q1). Keeping state in the reviewed
files means a fresh clone knows exactly what is done. DynamoDB `PipelineState` (brief) returns
with the Step Functions runner.

## R9. Keeping human edits across re-runs (FR-020)

**Decision**: a three-way merge.
- Each section has a working file `sections/{id}.json`, which you edit, and a machine file
  `.generated/{id}.json`, which the pipeline rewrites.
- On re-generation, if a working field still equals the old machine value, it takes the new
  machine value.
- If it differs, it is a human edit. It is kept, recorded under `humanEdits`, and flagged if the
  new machine value also changed.
- Both files are committed, so `git diff` shows exactly what you changed.

## R10. Checking that ideas really come from the commentators (FR-007, constitution IV)

**Decision**:
- For each key idea, the extraction output must include **evidence**: one short quote (≤ 30
  words) from each cited commentator's excerpt.
- An automatic check confirms each quote appears in that commentator's excerpt, after normalising
  whitespace and punctuation.
- An idea with a cited commentator whose quote isn't found loses that source. If no sources
  remain, the idea is rejected.
- Evidence stays in drafts for review and is **not** published.

**Rationale**: a cheap, deterministic guard against invented attribution, which is the core trust
risk.

## R11. Setting question levels (FR-011)

**Decision**:
- **Features**: the model records `answerDirectness` (`stated`, `inferred` or `beyond`) and
  `outsideKnowledge` (`none`, `some` or `required`). Code computes verse span from the scope, and
  commentator agreement from the target ideas' sources.
- **Rule**:
  - **Level 1**: span ≤ 2 verses, `stated`, `none`.
  - **Level 3**: `outsideKnowledge = required`, or `answerDirectness = beyond`, or type
    `application`.
  - **Level 2**: everything else.
- **Pool rules**:
  - Levels are capped by the number of key ideas (FR-009).
  - At most 2 questions per level. The second is `isAlternate: true`.
  - A section with 2+ levels must include a whole-passage question. If none qualifies, the
    section is flagged.
- **Level check**:
  - Haiku answers each question as a typical reader with only the passage.
  - A second Haiku call judges whether the answer covers the question's target ideas.
  - A Level 3 question that is covered is moved down to Level 2 automatically, and the move is
    flagged. A Level 1 question that isn't covered is flagged only.

## R12. Detecting wording that leans on one translation (Story 5)

**Decision**:
- Code tokenises each question and key idea, removing stopwords and lightly stemming.
- A token is "BSB-only" if it appears in the scoped BSB verses and not in the scoped KJV verses.
  Example: "sandals" in Mark 1:7, where the KJV says "shoes".
- Only items with a BSB-only token go to a Haiku call, which writes a KJV wording variant into
  `textByTranslation.kjv`. Every variant is listed for review.
- Manuscript notes are covered in R3.

## R13. IDs, versions and placeholders

**Decision**:
- **IDs**:
  - Section: `mrk-1-1`. Key idea: `mrk-1-1-k3`. Question: `mrk-1-1-q4`.
  - The number after `k` or `q` comes from a per-section counter stored in the drafts. It always
    increases and is never reused, even for items you rejected before they were ever published.
- **Pack version**: semver per book, recorded as `packVersion` (`1.0.0`) together with a separate
  `book` field.
  - Minor: content added or retired.
  - Patch: verse-text or note fixes.
  - Major: incompatible format change, coordinated with the app.
- **Placeholders**: text may reference verses only as `{{ref:C:V}}` or `{{ref:C:V-V}}`. The app
  renders these as "verse 7" in the current chapter, or "1:7" otherwise. A check verifies every
  placeholder exists in both translations.
- **Doc update**: the brief's example section used `mk-1-1` and `mark-1.0.0`. Update it to
  `mrk-1-1` and `1.0.0`.

## R14. Publishing and delivery

**Decision**:
- `publish` builds the pack from approved drafts. It writes one study file and one verse-text
  file per translation.
- It runs the publish check against the last published version, downloading that version's
  `study.json` from S3 through `index.json`.
- It then uploads to S3 under `/v1/books/{book}/{version}/…` with immutable cache headers. After
  that it rewrites `/v1/index.json` (short cache) and invalidates that one path in CloudFront.
- Published packs are **not** copied into git. S3 is the record of what was published: versioned
  paths are never overwritten, and bucket versioning is on.
- Infrastructure is Terraform:
  - the `storage` module (a private, versioned S3 bucket), used twice: once for packs, once for
    sources;
  - the `cdn` module (CloudFront with origin access control, compression on), in front of the
    packs bucket only;
  - plus `envs/dev`.
- The full URL layout is in [contracts/cdn-layout.md](contracts/cdn-layout.md).

## R15. Cost estimate and cap (FR-027, FR-028)

**Decision**:
- **Estimate**: sections still to run × expected cost per section for each stage.
  - The expected cost is the median of the last 20 recorded runs for that stage, from
    `content/drafts/{book}/runs.json` (committed, small).
  - With no history, it falls back to the config defaults: generate $0.06, review $0.02, levels
    $0.005, summaries and align $0.002.
- **Spend tracking**:
  - Each response's `usage` is multiplied by per-model prices in `pipeline/config/pricing.toml`.
  - Bedrock prices must be filled in from the AWS pricing page. Anthropic list prices are the
    placeholder: Sonnet 5.5 at $2 / $10, Haiku 5.5 at $0.10 / $0.50 per million tokens, with
    cache reads at 10%.
- **Cap and stop**:
  - The cap defaults to 2× the estimate and can be changed with `--cap`.
  - When spend passes the cap, no new sections start. Sections in flight finish, and the run
    stops with a resumable status.
- **Confirmation**: required unless `--yes` is given. CI never calls models.

## R16. Testing strategy

**Decision**:
- **Contract tests** (`shared/tests`):
  - Fixture packs in `content/schema/fixtures/{valid,invalid}/` validate against the JSON
    Schemas.
  - Pydantic models accept every valid fixture and reject every invalid one.
  - `model_dump` output validates against the JSON Schemas.
  - The same fixtures will be reused by the Swift `ContentKit` tests in spec 002.
- **Unit tests** (`pipeline/tests/unit`):
  - section builder, cross-reference parser, excerpt gathering;
  - checks, level rule, BSB-only token detection;
  - ID allocation, three-way merge, publish check;
  - cost estimate and cap;
  - the no-tools and no-network guards.
- **Integration test**: a 2-chapter fixture book runs the whole flow (`run --stage all` → approve
  → publish) with a fake `ModelRunner` (recorded outputs) and S3 mocked by moto.
- **Prompt evaluation** (constitution: before a new prompt version is used for publishing):
  - `eval` runs `generate`, `review` and `levels` on a fixed sample of 8 Mark sections. The sample
    mixes a narrative, a teaching, a miracle and a parable section, plus Mark 7 and Mark 16 for
    manuscript cases.
  - It renders a side-by-side report of the candidate prompt version against the current one.
  - It costs money, so it is run by hand and never in CI.
- **CI**: GitHub Actions runs `make lint` and `make test` on pushes and PRs.

## R17. Review report

**Decision**:
- `report` renders one self-contained HTML file per book with Jinja2:
  - flagged items first, grouped by section, each with its reasons;
  - then every section in order, with the passage (BSB and KJV toggle), key ideas with evidence
    quotes, questions by level with alternates marked, context, views differ, and manuscript
    notes;
  - "no prompt" sections with their reason;
  - human edits highlighted;
  - run cost.
- The output path is `content/drafts/{book}/review.html`, which is gitignored and can always be
  regenerated.

## R18. Approval

**Decision**:
- `approve` fails if any automatic check fails.
- It lists model-review and level-check flags that haven't been resolved. A flag is resolved by
  editing the item, rejecting it, or setting `"flagAccepted": true` on it. You confirm the
  approval by typing the book name.
- It writes `content/drafts/{book}/approval.json` with the sha256 of all drafts, the approval
  timestamp and the git HEAD.
- `publish` refuses if the drafts' hash no longer matches the approval.
