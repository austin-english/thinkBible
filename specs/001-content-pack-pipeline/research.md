# Research: Content Pack Format and Batch Pipeline

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-11-04

All Technical Context unknowns are resolved below. Facts about the Free Use Bible API were checked
against the live API on 2026-11-04: docs, `available_translations.json`,
`available_commentaries.json`, and BSB, Matthew Henry, JFB and Adam Clarke chapters of Mark.

## R1. Where the source text comes from, and how it is fetched

**Decision** (commentaries revised 2026-11-13, see R2a): a one-time `import` command fetches the
whole Bible for five sources. The two translations come from the Free Use Bible API
(`https://bible.helloao.org/api/...`, run by HelloAO) as per-chapter JSON. The three commentaries
come from CrossWire's SWORD modules, one zip each:

| Source | Upstream | Fetched as | License |
|---|---|---|---|
| Berean Standard Bible | HelloAO `BSB` | `/api/BSB/{BOOK}/{ch}.json` | Public domain (CC0), `https://berean.bible/` |
| King James Version | HelloAO `eng_kjv` | `/api/eng_kjv/{BOOK}/{ch}.json` | Public domain in the US (eBible `eng-kjv2006`) |
| Matthew Henry | CrossWire `MHC` 2.2 | `…/packages/rawzip/MHC.zip` | Public Domain (from CCEL) |
| Jamieson-Fausset-Brown | CrossWire `JFB` 3.0 | `…/packages/rawzip/JFB.zip` | Public Domain (from CCEL) |
| Adam Clarke | CrossWire `Clarke` 2.0 | `…/packages/rawzip/Clarke.zip` | Public Domain (from Wikisource) |

- Book IDs are USFM codes (`MRK`, `MAT`, `GEN`).
- Requests run one at a time at about 2 per second, with a generic User-Agent. The API states it
  has no rate limits, but the brief asks for a polite rate.
- That is about 2,400 translation requests (under 25 minutes) and three module downloads.
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

## R2a. Commentaries from CrossWire, and `sources check` (2026-11-13)

**Finding**: HelloAO's commentary data is unreliable. The first full import (snapshot 2026-11-13)
showed:
- JFB on Mark from chapter 3 on: every chapter filed one number off (the chapter labelled 3 held
  Mark 4, and so on up to 14, which held Mark 16). Mark 3 and 15 were missing, and what was left
  was 0.1 to 2.5k characters per chapter, against 7 to 20k from the other commentators.
- JFB Matthew 24–26 shifted the same way, and Psalm 146 missing.
- Henry: no Song of Songs, and several chapters shifted or misfiled (Isaiah 58's introduction
  filed as "Isaiah 68").
- Clarke: no Judges, Malachi or Matthew.

The raw API responses had the same problems, so the normaliser wasn't the cause. HelloAO's
maintainer explains in their issue #131 that the commentaries "were copied by hand into an excel
spreadsheet and so it has many issues". Their own Clarke fix (PR #122) points to CrossWire's
module as the complete text, and an open PR (#133) adds support for reading SWORD modules.

**Decision**: take all three commentaries from CrossWire's SWORD modules, and keep HelloAO only
for the BSB and KJV, which passed every check (31,102 KJV verses; the BSB's 31,086 omit exactly
the 16 verses modern translations leave out; 116 psalm titles each).

- **Upstream**: CrossWire (crosswire.org), the open-source Bible software project. Its modules are
  the standard digital editions: MHC 2.2 and JFB 3.0 are prepared from CCEL, Clarke 2.0 from
  Wikisource, all marked Public Domain. This matches the brief's plan to spot-check against CCEL.
- **Format**: `zCom`/`zCom4`, zlib-compressed OSIS, indexed by verse in the KJV versification
  (1,189 chapters, 31,102 verses). `sources/sword.py` reads the zip offline. It refuses any module
  whose index doesn't match the KJV scheme entry for entry, so a note can't land on the wrong
  verse the way HelloAO's did.
- **Linked notes**: a note on a range of verses (Henry's passages, e.g. Mark 1:1–8) is stored once
  with every verse pointing at it. It becomes one item with `verse` and `verseEnd`. No note spans
  two chapters in any of the three modules.
- **References**: every Scripture reference is tagged (`osisRef`), so notes carry them as compact
  `refs` (`MAT 12:9-21`). JFB deliberately covers parallel passages once ("See on Mt 12:9-21" for
  Mark 3), and those pointers now arrive tagged for the cross-reference step (R4). Clarke uses
  older abbreviations (`Psa`, `Joh`) and Henry some shorthand lists; `sources/refs.py` handles
  both. Rare tagging slips upstream exist (JFB tags a bare "2" in Mark 4:1 as 2 Cor 13:2). They
  affect only the reference list, not the text.
- **Archived, not re-fetched**: each module zip is stored in the snapshot next to the books made
  from it (`{source}/_module/{Name}-{Version}.zip`, pushed to S3 and checksummed like the books).
  Re-runs read the archived zip, so the snapshot never depends on CrossWire being online again,
  and a parser fix can be re-applied offline with `import --refresh`.
- **Editions are recorded**: each manifest source has an `origin` (`helloao:BSB`,
  `crosswire:JFB@3.0`). A new module version changes the origin, which re-imports every book of
  that source.
- **`sources check`**: `verify` proves files haven't changed since import; `sources check` proves
  they were right to begin with. It checks every book against the KJV versification and fails on
  out-of-range or overlapping notes, missing translation books, chapters or duplicate verses. It
  reports omitted verses and each commentary's coverage. The snapshot of 2026-11-13 passes:
  Henry 4,249 notes covering 100% of verses (39.0M characters), JFB 16,882 notes covering 80%
  (10.2M), Clarke 21,051 notes covering 68% (20.0M); every commentator has all 66 books.

**Alternatives considered**:
- Keep HelloAO's commentaries and exclude the bad chapters. Rejected: Mark, the launch book,
  would lose JFB for 13 of 16 chapters, and the defects are in the data itself, not one parse.
- CrossWire for the translations too. Not now: HelloAO's translations are generated from the
  publishers' files and pass every check, and CrossWire's main KJV module is GPL-licensed (its
  Strong's markup), while its public-domain KJV (`kjvpce`) has no paragraphs. CrossWire's BSB (CC0,
  third printing) and `sword.py`'s shared index reader keep that move small if it's ever needed.
- API.Bible. Rejected: a live, key-based API whose terms limit stored text, and it doesn't carry
  these commentaries.

**Other public-domain commentaries CrossWire offers** (for later; adding one is a `SOURCES`
entry plus the commentator list in the pack schema): Calvin's Collected Commentaries, Barnes'
Notes (NT), Keil & Delitzsch (OT), Spurgeon's Treasury of David (Psalms), the Catena Aurea
(Gospels, the Church Fathers via Aquinas), Wesley's Notes, Matthew Henry's Concise Commentary,
the People's New Testament and the Treasury of Scripture Knowledge (cross-references only).
Robertson's Word Pictures and Kingcomments are copyrighted. Barnes, Wesley and the People's NT are
ThML, not OSIS, and would need a small second converter.

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
- **Client** (revised 2026-11-12): Amazon Bedrock's **`bedrock-runtime`** endpoint through the
  official Anthropic Python SDK (`anthropic[bedrock]`, `AsyncAnthropicBedrock`), as the
  constitution requires. `settings.toml` `endpoint` can switch to `bedrock-mantle`
  (`AsyncAnthropicBedrockMantle`), but:
  - AWS recommends `bedrock-runtime` for new applications; Mantle is for features only it has
    (server-side tools, background inference, Projects), which the pipeline doesn't use. Both run
    on the same inference engine at the same per-token price (AWS "Endpoints supported by Amazon
    Bedrock").
  - This account can't use Mantle: every Mantle call was refused or "does not exist", for 5.5 and
    for Haiku 4.5. Mantle doesn't support cross-region inference profiles, and every Claude quota
    on this account is a cross-region one, which is the likely reason.
  - Model IDs are config values: the US cross-region inference profiles, e.g.
    `us.anthropic.claude-sonnet-4-6`.
- **Model access** (2026-11-12): the Claude 5.5 models are blocked for this account (quota 0;
  AWS declined the increase citing "account history, and usage patterns", which "is subject to
  change automatically as time passes"). Until then the stages run on **Claude 4.x**, which the
  account can use: a live smoke test of all three models through `BedrockRunner` passed on
  2026-11-12. Moving to 5.5 later is a `settings.toml` change plus the Terraform model list.
  - The organization's region policy allows Bedrock invoke in every region and everything else
    only in us-west-2 (docs/aws-setup.md → Regions). So all ThinkBible resources live in
    us-west-2, and CloudFront and its ACM certificate in us-east-1.
- **Models by stage** (target 5.5; running on 4.x until access opens):

  | Stage | Model (target) | Now | Reason |
  |---|---|---|---|
  | `summaries` (one-line passage summary) | Haiku 5.5 | Haiku 4.5 | Cheap, and parallel, since it reads only the passage |
  | `generate` (key ideas, context, views differ, then questions) | Sonnet 5.5 | Sonnet 4.6 | Quality-critical |
  | `align` (wording variants, manuscript notes) | Haiku 5.5 | Haiku 4.5 | The brief's "small model call" |
  | `review` (the quality gate's grader, R16) | Opus 5.5 | Opus 4.6 | A stronger model than the generator grades its output (revised 2026-11-10) |
  | `levels` (typical-reader check) | Haiku 5.5 | Haiku 4.5 | Stands in for a typical reader |

- **Structured outputs**: each call uses `client.messages.parse(...)` with a Pydantic output model
  (supported on Bedrock). Invalid output is retried up to 2 times, then the section is marked
  failed.
- **Thinking and effort**: set per stage in config (`thinking`, `effort`), starting at `medium`
  effort for `generate` and `review`. The 5.5 models always think adaptively; Sonnet and Opus 4.6
  need `thinking = "adaptive"` set explicitly; Haiku 4.5 rejects an effort setting, so its stages
  send neither. Tune during the Mark spike, since thinking tokens dominate cost.
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
  `BetaRefusalFallbackMiddleware` retries a refused request once on the fallback model (Opus). If that is
  also refused, the section is marked failed and flagged with the refusal category. This exists
  because Old Testament passages with violence could trip safety classifiers. Remove it if you'd
  rather review those sections by hand.
- **Batch inference**: deferred. Stages call a `ModelRunner` interface so that a Bedrock
  batch-inference runner can replace the on-demand runner for later books without changing stage
  code.

**Alternatives considered**: the first-party Claude API, which offers Message Batches and
server-side fallbacks. Rejected for now because the constitution names Bedrock and the rest of
the stack is AWS. This is a config switch if that ever changes.

## R7. Orchestration (revised 2026-11-10: cloud-first)

**Decision**: full runs execute in AWS. Local runs are for small, fast prompt tuning.

- **Step Functions Standard**, one execution per run request (one book, its stages in order), as
  the constitution requires. State machine `thinkbible-pipeline-{env}`:

  ```
  input: {runId, request: RunRequest, capUsd}
  StartRun     Lambda start_run: verify every source file the book needs against the manifest
               (FR-002; mismatch → Fail "SourceChecksum", exit 2), create the run's ledger item
  Stages       Map over request.stages, MaxConcurrency 1 (stages run in order):
    PlanStage    Lambda plan_stage: book-level stages (sections, report) run here and return no
                 sections; per-section stages hash inputs and return the section IDs to run
                 (R8). Returns nothing once the run has been stopped by the cap
    Sections     Map over those IDs, MaxConcurrency = settings.concurrency (10):
      RunSection   Lambda run_section: check the ledger (cap reached → "not started"), run the
                   stage for one section, write its draft to S3, add the cost to the ledger.
                   Model errors are caught and recorded as a failed section. Bedrock throttling
                   is retried by Step Functions with backoff
    FinishStage  Lambda finish_stage: write the stage's RunRecord, mark the run stopped if the cap
                 was reached
  FinishRun    Lambda finish_run: final counts, status and scorecard → execution output
               (exit code 0/3/4). When the run included `report` and no section failed, it
               publishes the book to dev (R14)
  ```

  One Lambda per section per stage keeps each invocation far below the 15-minute limit, and a
  failed or throttled section never costs the others.
- **Starting a run**: `thinkbible-pipeline run` reads the S3 drafts, computes the estimate with
  the same planning code (read-only), asks `Proceed? [y/N]`, then calls `StartExecution` with
  `capUsd`. It prints the execution ARN and console link; `--wait` polls and maps the output to
  the CLI exit codes. There is no in-workflow approval step or callback infrastructure.
- **Local mode**: `run --local` runs the same plan/run/finish functions in-process (asyncio, the
  same concurrency limit) against the same S3 drafts, with an in-memory spend ledger. It is meant
  for a few sections at a time while tuning prompts, and uses the repo's prompt files directly.
  Tests run the local mode against a temporary folder instead of S3.
- **Stage code is shared**: stages implement `inputs()` and `execute()` for one section (R8);
  only the orchestration differs between cloud and local.

**Rationale**: AWS is the end state and is already set up (us-west-2, Terraform state bucket,
naming conventions in docs/aws-setup.md). Per-section Lambdas fit the time limit, parallelism and
retries come from Step Functions, and runs don't depend on a laptop staying awake.

**Alternatives considered**: (a) one Lambda per stage looping over sections: a Sonnet `generate`
over ~100 sections can exceed 15 minutes. (b) a pause-for-approval step with a task token: needs
a callback path; the CLI estimate covers it. (c) the local async runner as the main path (the
original plan): rejected on 2026-11-10 in favour of the cloud end state.

## R8. Pipeline state, idempotency and resuming (revised 2026-11-10)

**Decision**:
- **Drafts live in S3** (`thinkbible-drafts-{env}-{account}`, versioned, private), under
  `drafts/{book}/` with the layout in data-model §2. Lambdas read and write them there.
- **Drafts are pipeline state, not a review surface** (revised 2026-11-10): no one edits them by
  hand, and they are not mirrored into git. The scorecard (R17) and the app on dev are where
  content is read. S3 versioning keeps every earlier draft recoverable.
- Each section draft records, per stage: prompt version, model ID, input hash (sha256 of the
  canonical JSON of all inputs) and cost. A stage skips a section when the recorded prompt
  version and input hash match, so an unchanged re-run makes zero model calls (SC-005).
  `--fresh` forces regeneration.
- **Run records** are one object per stage run (`runs/{runId}-{stage}.json`), not one appended
  file, so concurrent writers never collide.
- **Spend ledger**: a DynamoDB table `thinkbible-pipeline-runs-{env}` (on-demand, TTL 90 days),
  one item per run: `{runId, book, executionArn, capUsd, spentUsd, status, counts}`. Section
  Lambdas add their cost with an atomic `ADD` and check `spentUsd < capUsd` before starting.
  This is the brief's `PipelineState`, reduced to what orchestration needs.
- Book-level status stays in `drafts/{book}/book.json`.

**Rationale**: the Lambdas need a shared working copy, and S3 versioning keeps every machine
write recoverable. Git-based review (the original Clarification Q1) was dropped on 2026-11-10 in
favour of the automatic quality gate and in-app review.

## R9. Human edits (superseded 2026-11-10)

The original decision, a three-way merge of hand edits with regenerated output, is dropped: drafts
are no longer edited by hand. To change content, change the prompt (a new version) and regenerate,
or after a production publish, retire and replace (US6).

## R10. Checking that ideas really come from the commentators (FR-007, constitution IV)

**Decision**:
- For each key idea, the extraction output must include **evidence**: one short quote (≤ 30
  words) from each cited commentator's excerpt.
- An automatic check confirms each quote appears in that commentator's excerpt, after normalising
  whitespace and punctuation.
- An idea with a cited commentator whose quote isn't found loses that source. If no sources
  remain, the idea is rejected.
- Evidence stays in the drafts and the scorecard, and is **not** published.

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
    section is regenerated once, then failed (FR-018).
- **Level check**:
  - Haiku answers each question as a typical reader with only the passage.
  - A second Haiku call judges whether the answer covers the question's target ideas.
  - A Level 3 question that is covered is moved down to Level 2 automatically. A Level 1
    question that isn't covered is dropped and replaced by its alternate if it has one. Both are
    listed in the scorecard.

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

## R14. Publishing and delivery (revised 2026-11-10)

**Decision**:
- **Dev publish is automatic**: a run that includes `report` and has no failed section ends by
  building the pack from the drafts and publishing it to the dev packs bucket. It writes one study
  file and one verse-text file per translation under `/v1/books/{book}/{version}/…` with immutable
  cache headers, rewrites dev's `/v1/index.json` (short cache) and invalidates that path. Dev
  runs no additive publish check, so a book can be regenerated and republished freely before its
  first production publish; IDs are still never reused (R13 counters only increase).
- **Promotion to production is explicit**: `promote --book B` copies the exact files of the
  book's current dev version (same bytes, same sha256) to the production packs bucket, after:
  the gate passed with pass rates at or above the thresholds (R16); the grader calibration is at
  or above 85% for its current prompt and model; and the production publish check passes against
  the last production version, downloaded through prod's `index.json` (data-model "Publish
  check"). Then it rewrites prod's `index.json` and invalidates it.
- Published packs are **not** copied into git. S3 is the record of what was published: versioned
  paths are never overwritten, and bucket versioning is on.
- Infrastructure is Terraform:
  - the `storage` module (a private, versioned S3 bucket), used for sources, drafts and packs;
  - the `cdn` module (CloudFront with origin access control, compression on), in front of each
    environment's packs bucket;
  - plus `envs/dev` (and `envs/prod` before the first promotion).
- The full URL layout is in [contracts/cdn-layout.md](contracts/cdn-layout.md).

## R15. Cost estimate and cap (FR-027, FR-028)

**Decision**:
- **Estimate**: sections still to run × expected cost per section for each stage.
  - The expected cost is the median of the last 20 recorded runs for that stage, from the
    book's run records (`drafts/{book}/runs/`).
  - With no history, it falls back to the config defaults: generate $0.06, review $0.02, levels
    $0.005, summaries and align $0.002.
- **Spend tracking**:
  - Each response's `usage` is multiplied by per-model prices in `pipeline/config/pricing.toml`.
  - The accepted Bedrock offer for Sonnet 5.5 (checked 2026-11-04) is $2 input / $10 output per
    million tokens, cache reads $0.10 (5% of input), cache writes $2.50 (5-minute) or $4.00
    (1-hour). Haiku 5.5 is $0.10 / $0.50, with the same cache ratios. Re-check with
    `aws bedrock list-foundation-model-agreement-offers --model-id <id>`.
- **Cap and stop**:
  - The cap defaults to 2× the estimate and can be changed with `--cap`.
  - When spend passes the cap, no new sections start. Sections in flight finish, and the run
    stops with a resumable status. In the cloud the check uses the run's DynamoDB ledger (R8);
    locally an in-memory ledger.
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
- **Integration test**: a 2-chapter fixture book runs the whole flow (`run --local --stage all`
  → gate → publish to dev → `promote`) with a fake `ModelRunner` (recorded outputs) and S3 mocked
  by moto. The Lambda handlers are driven through the same flow (Phase 2b).
- **The quality gate's grader** (revised 2026-11-10; replaces manual review):
  - Opus 5.5 grades every key idea and question 1–5 against a fixed rubric in
    `pipeline/prompts/review/vN.md`. Key ideas: says only what the cited commentators say, neutral
    across traditions, plain modern English, no quoted translation wording. Questions:
    open-ended, short, answerable from the passage alone, not leading, no tradition-specific
    assumptions, aimed at its target ideas without giving them away.
  - The grader sees the passage, the commentators' excerpts and the item, so it can judge
    faithfulness. Items graded at or below `review_flag_threshold` (2) are dropped (R11 alternates
    fill in).
  - Book pass rates (ideas and questions graded above the threshold, before drops) are compared
    with `gate.min_idea_pass_rate` (0.90) and `gate.min_question_pass_rate` (0.80) for promotion.
- **Grader calibration** (constitution v1.2.0):
  - `pipeline/evals/calibration.json`: at least 30 items from Mark (ideas and questions, a mix
    of good and weak), each with the owner's grade (pass or fail, with a note). The owner grades
    them once with `calibrate --label`, which shows each item with its passage and excerpts.
  - `calibrate` runs the grader on the set and records its agreement (pass/fail match) with the
    grader prompt version and model. Promotion requires at least 85% on the current version; a
    change to either requires re-running `calibrate` (labels are reused).
- **Prompt evaluation** (before a new prompt version is used for a production book):
  - `eval` runs `generate`, `review` and `levels` in local mode on a fixed sample of 15–25 Mark
    sections (`pipeline/evals/mark-sample.json`): narrative, teaching, miracle, parable, a
    genealogy-like list, and Mark 7 and Mark 16 for manuscript cases.
  - It grades the current and candidate prompt versions with the calibrated grader and renders a
    side-by-side report with pass rates per rubric line. A candidate is adopted only if it scores
    at least as well (FR-029).
  - It costs money (about $1–2 per comparison), so it is run by hand and never in CI.
- **CI**: GitHub Actions runs `make lint` and `make test` on pushes and PRs.

## R17. Scorecard (revised 2026-11-10; was the review report)

**Decision**:
- `report` renders one self-contained, read-only HTML file per book with Jinja2:
  - the headline: idea and question pass rates against the thresholds, failed sections, the
    grader's calibration agreement, and the run's cost;
  - dropped items with their reasons, grouped by section;
  - then every section in order, with the passage (BSB and KJV toggle), key ideas with evidence
    quotes and grades, questions by level with alternates marked, context, views differ, and
    manuscript notes;
  - "no prompt" sections with their reason.
- It is written to `drafts/{book}/review.html` in S3. `status --book B --open` downloads it to a
  temporary file and opens it. It has no editing workflow.

## R18. Approval (superseded 2026-11-10)

There is no `approve` command. The automatic gate (R16) decides what is published to dev, and
`promote` (R14) is the owner's explicit decision to publish to production, made after reading
the book in the app.

## R19. Lambda packaging and deploy (added 2026-11-10)

**Decision**:
- **One bundle, five handlers**: a single zip for Python 3.12 on arm64 holds `thinkbible_core`,
  `thinkbible_pipeline`, their dependencies (`anthropic`, `pydantic`, `jinja2`; `boto3` comes from
  the runtime), and the data the code reads: `pipeline/config/`, `pipeline/prompts/`,
  `content/schema/` and the committed `content/sources/manifest.json`. The five Lambdas
  (`start_run`, `plan_stage`, `run_section`, `finish_stage`, `finish_run`) share it with
  different handlers.
- **Build**: `make lambda-bundle` runs `pipeline/scripts/build_bundle.py`, which installs the
  locked dependencies for `manylinux2014_aarch64` into a staging folder and zips it to
  `pipeline/out/lambda.zip` (gitignored). The bundle records the git HEAD it was built from, and
  every RunRecord stores it as `codeVersion`.
- **Deploy**: Terraform `infra/modules/pipeline` uploads the zip and creates the functions, the
  state machine, the drafts bucket, the ledger table and IAM. A prompt change is a new prompt
  version file plus a redeploy; `--local` runs read prompts from the repo, so tuning needs no
  deploy.
- **Configuration**: handlers read `PIPELINE_ENV`, `DRAFTS_BUCKET`, `SOURCES_BUCKET` and
  `LEDGER_TABLE` from environment variables set by Terraform. Lambdas read source files straight
  from the sources bucket and check each against the bundled manifest (FR-002).
- **IAM** (least privilege): Bedrock invoke on the three Claude 5.5 models only, read on the
  sources bucket, read/write on the drafts bucket, read/write on the ledger table, CloudWatch
  Logs. On `bedrock-runtime` that is `bedrock:InvokeModel` on each inference profile and the
  foundation models it routes to; Mantle would need `bedrock-mantle:CreateInference` instead (AWS
  endpoints page), available through the module's `extra_bedrock_actions`.
- **Timeouts**: `run_section` 900 s (model calls use shorter SDK timeouts so a hung call fails
  cleanly), the others 60–300 s.
