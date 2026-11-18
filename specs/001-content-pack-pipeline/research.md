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
- **S3**: the files are stored in a private, versioned bucket (`thinkbible-sources-<account id>`) under `snapshots/{snapshotId}/{source}/{BOOK}.json`.
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
  `crosswire:JFB@3.0/reader2`). A new module version, or a new `sword.py` reader version, changes
  the origin, which re-imports every book of that source (from the archived zip; no download).
- **Notes the index lost** (found 2026-11-16, reader 2): CrossWire's JFB module holds about 1M
  characters (10% of JFB, 1,294 places in 53 books) in its compressed blocks that no index entry
  points at, so a plain SWORD reader never shows them. Example: after the note on Mark 1:2-3 sit the
  rest of the note on verse 3 and JFB's headings for 1:9-20 with their pointers ("Mr 1:12, 13.
  Temptation of Christ. ( = Mt 4:1-11; Lu 4:1-13). See on Mt 4:1-11."). Henry has 6 such gaps and
  Clarke 2. Every gap opens with the commentator's verse number ("5. they all brought us…",
  "Verse 5"), so `sword.py` splits each gap at those numbers and adds each piece to that verse of
  the chapter; text before the first number continues the preceding note. In 543 gaps that is the
  preceding verse, in 744 an earlier verse whose index entry was lost. Without this, JFB gave
  nothing on 29 of Mark's 100 sections; with it, it covers all of them.
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

**Decision** (revised 2026-11-16 for the CrossWire modules, `commentary/gather.py`):
- Every note and chapter introduction is split into **blocks**: a paragraph that opens with a
  passage of the same chapter ("Mr 3:13-19. The Twelve…") starts a block for that passage; text
  before it belongs to the note's own verses (or, in an introduction, to the whole chapter). JFB
  files the headings of following passages at the end of an earlier note, so this is what brings
  "Mr 1:12, 13. Temptation of Christ… See on Mt 4:1-11" to section 1:12-15 rather than 1:1-11.
- A section's excerpt for each commentator is, in this order:
  - (a) every block whose passage overlaps the section. Henry's notes carry their division's
    range (1:1-8), so a division that only partly overlaps comes in whole;
  - (b) the chapter introduction's opening text (Henry's outline);
  - (c) **one hop** of pointers (`commentary/crossrefs.py`): "See on {Book} {c}:{v}", "See the
    note(s) on …", "See also …", Henry's "which we had before, Matt. viii. 2-4" (Roman-numeral
    chapters) and "parallel place (…)", and JFB's "( = Mt …; Lu …)" lists. The target is that
    commentator's own note on the parallel passage, read from the same frozen snapshot and given
    to the model as one part labelled "Parallel passage note, {passage}: … applying to this
    section's passage". A tagged reference to the same chapter makes the range exact.
    Explicit pointers are always followed; "( = …)" lists only when the commentator's own notes
    on the section are under 250 tokens; at most 4 pointers per commentator; a pointer to a whole
    chapter brings only that chapter's introduction.
- Excerpts are capped at 8k tokens per commentator. When the cap is hit, the excerpt is trimmed
  at a part boundary (pointers go first), and the trim is recorded.
- `thinkbible-pipeline excerpts --book mark --section mrk-1-12` prints exactly what each
  commentator contributes to a section.
- **Mark** (snapshot 2026-11-16): 100 sections; per section Henry 0.9k-7.8k tokens (mean 3.2k),
  JFB 0.1k-7.9k (mean 2.4k), Clarke 0-6.9k (mean 1.0k; Clarke has no notes on 3:28-30,
  13:24-27 and 15:12-15). About 6.6k tokens per section in all; 7 of 300 excerpts trimmed.

**Rationale**: without step (d), JFB and Clarke contribute almost nothing to many Mark sections,
and the "agreed by 2+ commentators" signal falls apart. Cross-references stay inside the closed
world (constitution II).

**Cost implication**: excerpts are about 6.6k tokens per section for Mark including
cross-references, below the brief's assumed ~12k. The brief's cost estimates are therefore
conservative.

## R5. Building sections (FR-004, FR-005)

**Decision**: a deterministic code step in the `sections` stage:

1. Start with the BSB headings in each chapter. Each heading begins a candidate section.
2. Sections never cross chapter boundaries, because the reader scrolls one chapter at a time. A
   heading that starts mid-chapter in the previous chapter is cut at the chapter start.
3. Compare against Henry's division start verses. If a candidate is longer than 12 verses and
   contains a Henry boundary, split it there. If it has no Henry boundary, split it at the
   paragraph break nearest its middle.
4. Merge candidates shorter than 3 verses into the next section in the same chapter, under the
   longer piece's title. A section at the end of a chapter merges into the previous one instead.
   Merging runs before splitting (step 3), so a merge can't leave a section over 12 verses, and
   splits always leave at least 3 verses on each side. Without a Henry boundary or paragraph
   break, a long section splits at its middle verse.
5. The title is the BSB heading. Split pieces get a provisional title "{heading} (cont.)", which
   is flagged so you can retitle it during review.
6. The section ID is `{book}-{chapter}-{startVerse}` in lowercase USFM, for example `mrk-1-1`.
7. A chapter whose first heading comes after verse 1 starts with a piece of the previous chapter's
   last heading, titled "{heading} (cont.)".
8. Ranges cover every verse of the KJV versification, so KJV-only verses (Mark 7:16) belong to a
   section even though the BSB omits them.

The output is `sections.json` in the drafts store (`sections/builder.py`, the `sections` stage).
Mark gives 100 sections of 3-12 verses (mean 6.8), 10 with a provisional "(cont.)" title; the
whole Bible gives 4,187, all 3-12 verses except Psalm 117 (2 verses). The map is rebuilt on every
run until the book is live; then IDs and verse ranges are frozen and enforced by the publish
check (FR-024).

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

- **The Claude API directly, now the default** (2026-11-18): while Bedrock's 5.5 quota stays at 0
  for this account, the pipeline runs on the Claude API (Haiku 5.5 summaries, Sonnet 5.5 generate
  at effort high, Opus 5.5 review at effort high). On the same 10 Mark sections the 5.5 questions
  read more naturally, and the Opus 5.5 grader agreed with the owner on 92% of the held-out
  ratings (Opus 4.6: 75-83%). `[profiles.bedrock]` keeps the Claude 4.x Bedrock setup
  (`THINKBIBLE_PROFILE=bedrock`); when Bedrock opens 5.5, that profile only needs its model IDs
  changed, and calibration carries over because results match on the bare model ID. The API key
  is an SSM SecureString (`anthropic-api-key`) read at run time with the caller's AWS
  credentials, or by the Lambda role (`ssm:GetParameter` on that one parameter); it is never in
  the repo, Terraform state or logs. Refusals fall back server-side (`fallbacks: "default"`).
  Section concurrency is 3 (settings and Step Functions) until the account's limits rise.
- **The book introduction** (2026-11-18): the commentators' prefaces to a book (who wrote it, to
  whom, why) sit at the start of their first note in the SWORD modules, so only the first section
  saw them, and every other section's context note filled "who wrote this book, to whom, and why"
  from general knowledge: the same sentence in every section, and an invented purpose that failed
  Mark 1:16-20. Now `commentary/preface.py` splits each preface from the first note when the
  pipeline reads the snapshot (the snapshot is unchanged; prefaces found in 64/66 books for Henry,
  48/66 for JFB, whose others have only a title, and 63/66 for Clarke). The `intro` stage writes
  the introduction once per book, on the first section's draft (so it gets estimates, spend
  tracking, skips and cloud runs like any section stage); the evidence check and the grader
  (`prompts/intro-review`) apply, with one rewrite before it is reported as a blocker. The app
  shows it as the book's first post ("About Mark"). `extract/v13` keeps section context notes
  about the passage.
- **Writer: Sonnet 5.5, not Opus 5.5** (owner decision, 2026-11-18): on 5 fresh Mark passages
  Opus wrote somewhat sharper questions in places (notably Mark 1:40-45) and fewer weak candidates,
  but the owner saw no large difference, and Opus doubles the writing cost (about $10 more per
  Mark, about $500 more for the whole Bible). The grader's higher scores for Opus were not counted:
  Opus would be grading its own writing. If some sections keep coming out weak, regenerating just
  those is the cheaper lever.
- **Pacing and throttling** (2026-11-17): this account's quotas are 10 requests a minute for
  Sonnet 4.6 and Haiku 4.5 and 5 for Opus 4.6. The runner paces requests per model to the
  `requests_per_minute` set per stage (stages sharing a model share it) and retries a throttled
  request with backoff (10s, 20s, 40s, then 60s; `throttle_retries`) before raising `Throttled`.
  In the cloud each Lambda paces only itself, and Step Functions retries what still comes back
  throttled. The first 10-section `--local` run failed four sections on 429s before this.
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
               publishes the book to the draft channel (R14)
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
  hand, and they are not mirrored into git. The scorecard (R17) and the app on the draft channel are where
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
or after a live publish, retire and replace (US6).

## R10. Checking that ideas really come from the commentators (FR-007, constitution IV)

**Decision**:
- For each key idea, the extraction output must include **evidence**: one short quote (≤ 30
  words) from each cited commentator's excerpt.
- An automatic check confirms each quote appears in that commentator's excerpt, after normalising
  whitespace and punctuation and setting aside bracketed citations such as "(Mr 1:12)", which
  models often leave out of a quote (revised 2026-11-16). A quote longer than 30 words is accepted
  when it is found verbatim (up to 80 words), and stored cut to its first 30 words.
- An idea with a cited commentator whose quote isn't found loses that source. If no sources
  remain, the idea is rejected.
- ~~Evidence stays in the drafts and the scorecard, and is **not** published.~~ Revised
  2026-11-17: each idea publishes its evidence quotes as `quotes`, shown under "In their words" as
  nested replies in the app. Because readers see them, the extract prompt (`extract/v8`) asks for
  8-30 words that read well on their own (a whole sentence or clause, not a Bible verse the
  commentator quotes, not Greek or Hebrew, not a fragment), and the grader checks them (`quotes`
  line, `review/v4`). The public-domain texts allow this; the words are never modernised.
  For display (`generate_rules.display_quote`), a long quote is cut at a clause break rather than
  mid-phrase (`short_quote`), "…" marks a quote that starts or stops mid-sentence, and JFB's old
  "--" becomes a dash. The words themselves stay the commentator's.

**Rationale**: a cheap, deterministic guard against invented attribution, which is the core trust
risk.

## R11. Choosing a section's questions (FR-008, FR-009; revised 2026-11-17)

**Decision**: questions are an ordered list with no levels and no hidden alternates.
- **Count**: up to 3 active questions per section, and never more than its active key ideas
  (`thinkbible_core.rules.max_questions`).
- **Order**: the order a reader meets them. The app asks the first on the first read and unlocks
  each next one a week after the previous answer. "Not a helpful question?" moves to the next.
- **Length** (2026-11-17): questions may be up to 200 characters (was 160). On the first run
  without levels, 10 of 28 dropped questions were 161-170 characters, and they were mostly the
  whole-passage questions, which need a longer framing sentence. The prompt (`questions/v5`) asks
  for 200 at most and shorter where possible.
- **Limits in words** (2026-11-17, `extract/v6`, `questions/v6`): models count characters
  poorly, so prompts give word limits with headroom (question 30 words, idea title 8 and body 30,
  context 35, views differ 55) and a "say it short" section with long-then-short examples. Code
  still checks the characters the schema allows.
- **Generation** (`questions/v7`, question guide v3): the writer sees the passage, the
  commentators' notes (added 2026-11-17; before that only the 30-word idea summaries, which lost
  the commentators' angles) and the kept ideas. It writes up to 6 candidates in reading order,
  aimed at the passage's main ideas. The first opens the main idea, usually on the whole passage;
  later ones take up other ideas and may connect to the rest of Scripture or to life. v7's rules,
  from a read of the v6 output: **specific** (no stems that fit any passage), the **opening
  sentence says what happens, not what it means**, background only when the reader needs it and
  never the commentators' reading, and **worth answering**. Recall questions are never written.
- **Choosing** (revised 2026-11-17: the grader picks): the writer drafts up to 8; every one that
  passes the checks is kept as a candidate (`candidates` on the draft, not published). `review`
  grades them all and keeps the best 3 above the threshold (`gate.outcomes.pick_best`): first the
  best graded aimed at a key idea not yet covered, then the best of the rest, returned in the
  writer's order. The others are recorded as "not chosen: graded N". Until review runs, the
  section holds the writer's first ones (`generate_rules.choose`), so it is valid at every stage.
  The question pass rate on the scorecard now counts every candidate. About $0.02-0.05 more per
  section. (A whole-passage swap was removed on 2026-11-17 after it replaced Mark 1:16-20's only
  'fishers of men' question with a weaker repeat.)
- **Key and background ideas** (2026-11-17, `extract/v8`): ideas a careful reader can't reach from
  the passage alone (only Mark records…, the original word is sharper…, two prophets centuries
  apart) were being counted as "missed". Each idea now has a `kind`: `key` (up to 5; questions
  target only these, the app counts them) or `background` (up to 2; shown under "More from the
  commentators", never counted). The grader's `reachable` line drops a key idea that isn't
  reachable. The app also scores an answer against the question's own targets, not every idea
  (spec 003).
- **Deeper meaning** (2026-11-17, owner decision after rating 51 Mark 1 questions): the app's
  focus is uncovering what lies beneath the surface of a passage, which a casual reading misses.
  Superseding the "reachable" rule above: key ideas are the deeper meanings the commentators draw
  (what the passage shows about God, Jesus, salvation, following him, including links to other
  Scripture the commentator makes); background ideas are facts that are not meanings (another
  Gospel, the original word, a custom). Questions are **approachable** rather than answerable
  from the passage alone: one concrete handle in the text, plus one plain fact if needed, and a
  short plain question about what it reveals; the reply supplies the depth. Questions **stand
  alone** (a week apart), naming their people. Prompts: `extract/v10`, `questions/v10`, question
  guide v4 (the owner's 11 favorites; no longer a draft), `review/v6` (rubric rewritten: deeper,
  approachable, focused, stands-alone, plain, not-leading).
- **Calibration from the ratings**: the owner's 48 ratings are the grader's calibration set
  (`pipeline/evals/calibration.json`): "Love it" and "Fine" count as pass, "Not this" as fail.
  Under `review/v5` the grader agreed about 70% of the time (it passed 15 of 16 rejects). Each
  question item keeps the ideas it aims at (`targetIdeas`), so it grades after regeneration.
  Under `review/v6` agreement fell to 60%: the rubric over-punished "vague" (the owner ships some
  questions they tag vague) and still could not hear clunky wording. So the grader now learns from
  the owner's verdicts directly: round 1 (48 ratings) is written into `review/v7` as worked
  examples (`role: "example"`), and a second round on the `questions/v10` output (36 ratings) is
  the held-out set (`role: "test"`) that `calibrate` measures; a grader is never measured on a
  judgment it was shown. Each result also records the grader's score per test item. Round 2: the
  owner would ship 13 of the 15 questions kept (8 of 14 in round 1).
  `review/v7` reached 83% on the held-out round 2 (from 60%). `review/v8` adds three things the
  owner rejects however good the idea (an abstract-noun ending, an obvious or one-word answer, a
  custom or detail that leads to no key idea), using invented examples so the held-out set isn't
  leaked into the rubric, and tells the grader to match the owner's judgment, not the topics of
  the Mark examples. `questions/v11` adds the owner's favorite form ("What would be missing
  if…?"), concrete endings, the obvious-answer test, and never mentioning the commentators (also
  a code check, `checks-v3`). Because the rubric was tuned against round 2, the next confirmation
  uses fresh ratings on passages never rated (Mark 1:35-2:20).
- **Purpose first** (2026-11-18, owner's observation): every wording rule added since v7 made the
  writer contort its sentences to satisfy them all at once, and the favorite form ("What would be
  missing if…") became a template in 9 of 10 sections. `questions/v12` and `review/v9` are
  rewrites, not additions: they lead with what a question is for (the moment the reader stops and
  wonders about a meaning beneath the surface), give the writer a three-step method (find the
  clue the reader passes over, say plainly what happens, ask what a curious friend would ask),
  and keep only a few firm limits (length, open, names its people, no verse numbers, never
  mentions the commentators, translation-neutral wording, no doctrine assumed). The grader asks the
  same question first, then whether it is said simply; the owner's verdicts remain its examples.
- **Genres**: the worked examples are all Mark narrative. Each new kind of book (a letter, poetry,
  law, prophecy) gets a short rating round on its first sections, split into examples and a
  held-out set, and `calibrate` re-runs before that book is promoted.
- **Quality first** (2026-11-17, revised the same day): each of the 3 places goes to the
  highest-graded candidate left, so a lower grade never beats a higher one
  (`gate.outcomes.pick_best`). Among equal grades: one aimed at a key idea not yet covered, then one
  about at least half the passage, then the writer's order. Two earlier rules were removed after a
  Mark run: covering every idea before looking at grades kept a 3 over a 5, and a place reserved
  for a whole-passage question let broad questions beat sharper ones.
- **The first question opens the central meaning** (2026-11-18, `extract/v13`, `questions/v13`):
  the first question decides whether a reader comes back, so it should open what the passage as a
  whole is about. The extract call names one key idea as the central meaning (`centralIdea`): what
  the commentators treat as the point of the whole passage (their summary before the verse notes,
  the point they keep returning to). Shared points are support, not the test, since all three may
  note a place or a custom. Code puts that idea first among the key ideas and the draft keeps its
  ID (pipeline only; no contract change). The writer gives two or three candidates on it. In
  `review`, the best-graded of those takes the first place if it grades 4 or more
  (`gate.outcomes.pick_opener`); the other places stay quality first. With none at 4, the
  best-graded kept question goes first (ties to the one spanning most of the passage), and the
  report flags the section.
  Unlike the removed whole-passage reservation, this one is for the central idea, not for breadth,
  and it needs a 4.
- **Christ in the Old Testament** (2026-11-18, `extract/v14`, `questions/v14`, `review/v10`):
  Isaiah 53:1-8 came out as "the servant" throughout, though all three commentators say in those
  notes that it foretells Jesus. The neutrality rules ("where the commentators or traditions
  disagree") had been read to cover the Jewish reading the commentators mention only to answer
  it. "Traditions" means Christian traditions (the brief: Reformed, Wesleyan, later Catholic), so
  neutral now means not taking sides between the commentators or between Christian traditions. A
  prophecy or picture of Jesus that the commentators give, uncontradicted by another of them, is a
  key idea (usually the central one) that names Jesus with the New Testament link they give.
  Where one rejects it (Clarke on the bronze serpent as a type, Numbers 21), the idea keeps to what
  they share and `viewsDiffer` describes the difference. Questions let the reader make the
  connection and ask what it opens up, never only "who is this about?". The prompts' example is
  the Passover lamb, not either test passage.
- **Giveaway check**: code drops a question that repeats an idea's title word for word. A check
  for an 8-word run from the idea's body was removed (`checks-v2`): a plain question describes
  the same scene the body does, and it dropped Mark 1:21-28's best question. The grader's
  `not-leading` line judges giveaways.
- **Plain wording** (2026-11-17, `questions/v9`, `review/v5` `natural`): questions had started
  turning people and actions into abstract nouns ("Why might a true confession still be
  rejected?", "What does that distinction say about the limits of John's ministry?"). v9 asks about
  the people by name with plain verbs in one simple clause, with a read-aloud test and
  before-and-after pairs; v7's "what each word adds" example, which taught a stilted "What does X
  add to…" shape, is gone.
- **Deferred: a question about the reader's own life.** The grader drops "in your own life"
  questions as generic, so none survive. A specific application question as a section's third
  question may help engagement, but it complicates tuning; revisit once the first two are steady
  (owner, 2026-11-17).
- **Notes are graded** (`review/v4`): the grader also scores the context and views-differ notes.
  A weak views-differ note is removed; a weak context note regenerates the section once.
- **Gate**: a question the grader drops leaves a gap the others close up; questions left aiming
  at no kept idea, or beyond the one-per-idea cap, are dropped. A section left with no question is
  regenerated once, then failed (FR-018). The grader's rubric gained `big-picture` (`review/v2`),
  then a stricter `not-leading` and the `specific` and `engaging` lines (`review/v3`).

**Why the levels went** (history):
- 2026-11-16: levels were redefined by reach (L1 a detail, L2 the passage, L3 beyond it), set by
  a rule from features the model recorded (`answerDirectness`, `outsideKnowledge`), with a
  primary and an alternate per level and a typical-reader level check (Haiku) that moved easy
  Level 3 questions down and dropped Level 1 questions a reader couldn't reach.
- 2026-11-17: on a 10-section Mark run, 5 sections failed because Level 3 ended up empty, and the
  "at most 2 per level" rule threw away many good big-picture questions. Difficulty depends on the
  reader, so neither the rule nor the check could measure it reliably. Dropping levels removed the
  `levels` stage (two Haiku calls per section), the features, alternates and level changes, and the
  most common cause of failed sections.

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
  - The number after `k` or `q` comes from a per-section counter stored in that section's draft
    (`ids`; not in `book.json`, since sections run in parallel in the cloud). It always
    increases and is never reused, even for items dropped before they were ever published.
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
- **One environment, two channels** (revised 2026-11-13): a single packs bucket and CloudFront
  distribution serve `draft/` (the owner's own builds) and `live/` (readers). An idle second AWS
  environment would add complexity, not safety; the channels keep what matters, that unreviewed
  content never reaches readers.
- **Draft publish is automatic**: a run that includes `report` and has no failed section ends by
  building the pack from the drafts and publishing it to the draft channel. It writes one study
  file and one verse-text file per translation under `/draft/v1/books/{book}/{version}/…`,
  rewrites `/draft/v1/index.json` (short cache) and invalidates that path. The draft channel
  runs no additive publish check, so a book can be regenerated and republished freely before its
  first live publish; IDs are still never reused (R13 counters only increase).
- **Promotion to live is explicit**: `promote --book B` copies the exact files of the
  book's current draft version (same bytes, same sha256) to `live/`, with immutable cache headers, after:
  the gate passed with pass rates at or above the thresholds (R16); the grader calibration is at
  or above 85% for its current prompt and model; and the live publish check passes against
  the last live version, downloaded through `/live/v1/index.json` (data-model "Publish
  check"). Then it rewrites `/live/v1/index.json` and invalidates it.
- Published packs are **not** copied into git. S3 is the record of what was published: live
  versioned paths are never overwritten, and bucket versioning is on.
- Infrastructure is Terraform:
  - the `storage` module (a private, versioned S3 bucket), used for sources, drafts and packs;
  - the `cdn` module (CloudFront with origin access control, compression on), in front of the
    packs bucket;
  - all in the one root, `infra/`.
- The full URL layout is in [contracts/cdn-layout.md](contracts/cdn-layout.md).

## R15. Cost estimate and cap (FR-027, FR-028)

**Decision**:
- **Estimate**: sections still to run × expected cost per section for each stage.
  - The expected cost is the median of the last 20 recorded runs for that stage, from the
    book's run records (`drafts/{book}/runs/`).
  - With no history, it falls back to the config defaults: generate $0.06, review $0.02,
    summaries and align $0.002.
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
  - checks, question choice, BSB-only token detection;
  - ID allocation, three-way merge, publish check;
  - cost estimate and cap;
  - the no-tools and no-network guards.
- **Integration test**: a 2-chapter fixture book runs the whole flow (`run --local --stage all`
  → gate → publish to the draft channel → `promote`) with a fake `ModelRunner` (recorded outputs) and S3 mocked
  by moto. The Lambda handlers are driven through the same flow (Phase 2b).
- **Rule checks** (`gate/checks.py`, added 2026-11-17): lengths, a "?" at the end, no yes/no
  questions, no key idea repeated word for word in a question (a run of 8 words from its body, or
  its whole title), no commentator names in idea text or questions, evidence-backed sources,
  placeholders that resolve in both translations, targets that exist. They run inside `generate`
  before the questions are chosen, so failing items are replaced by the next candidate or the
  regenerate-once loop, and are recorded with `stage: "check"`. The `check` stage then re-verifies each finished
  section (the item checks again, the pack schema, the shared cross-field rules). A section that
  fails there is flagged `regenerate`; the next run's `generate` regenerates it once, and a second
  failure marks it failed (FR-018).
- **The quality gate's grader** (revised 2026-11-10; replaces manual review):
  - Opus 5.5 grades every key idea and question 1–5 against a fixed rubric in
    `pipeline/prompts/review/vN.md`. Key ideas: says only what the cited commentators say, neutral
    across traditions, plain modern English, no quoted translation wording. Questions:
    open-ended, short, approachable from the passage, not leading, no tradition-specific
    assumptions, aimed at its target ideas without giving them away (revised by `review/v6`,
    below).
  - The grader sees the passage, the commentators' excerpts and the item, so it can judge
    faithfulness. Items graded at or below `review_flag_threshold` (2) are dropped (the other
    questions keep their order, R11).
  - Book pass rates (ideas and questions graded above the threshold, before drops) are compared
    with `gate.min_idea_pass_rate` (0.90) and `gate.min_question_pass_rate` (0.80) for promotion.
- **Managed alternatives considered** (2026-11-17): Bedrock Guardrails' contextual grounding
  check scores whether a text is supported by a source (0 to 1, through `ApplyGuardrail` with no
  model call, about $0.10 per 1,000 characters). It covers only faithfulness, penalises the
  paraphrase and "why it matters" the key ideas are written in, and returns no reason; the
  evidence check and the grader already cover faithfulness. Not used; it remains a cheap second
  opinion to add if calibration shows the grader misjudging faithfulness. Bedrock Evaluations
  (LLM-as-a-judge jobs) fits `eval` (comparing prompts or models), not the in-run gate.
- **Implementation** (2026-11-17): `review` makes one Opus call per section, grading every item
  with the rubric lines it breaks and a reason. Drops go through `gate/outcomes.py`, which also
  drops questions left without a kept idea or over the cap, and flags a section left unusable for
  one regeneration on the next run. (A `levels` stage with two Haiku calls per section was built
  and removed the same day, R11.)
- **Grader calibration** (constitution v1.2.0):
  - `pipeline/evals/calibration.json`: at least 30 items from Mark (ideas and questions, a mix
    of good and weak), each with the owner's grade (pass or fail, with a note). The owner grades
    them once with `calibrate --label`, which shows each item with its passage and excerpts.
  - `calibrate` runs the grader on the set and records its agreement (pass/fail match) with the
    grader prompt version and model. Promotion requires at least 85% on the current version; a
    change to either requires re-running `calibrate` (labels are reused).
- **Prompt evaluation** (before a new prompt version is used for a live book):
  - `eval` runs `generate` and `review` in local mode on a fixed sample of 15–25 Mark
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
    quotes and grades, questions in reading order, context, views differ, and
    manuscript notes;
  - "no prompt" sections with their reason.
- It is written to `drafts/{book}/review.html` in S3. `status --book B --open` downloads it to a
  temporary file and opens it. It has no editing workflow.

## R18. Approval (superseded 2026-11-10)

There is no `approve` command. The automatic gate (R16) decides what is published to the draft channel, and
`promote` (R14) is the owner's explicit decision to publish to live, made after reading
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
- **Configuration**: handlers read `DRAFTS_BUCKET`, `SOURCES_BUCKET` and
  `LEDGER_TABLE` from environment variables set by Terraform. Lambdas read source files straight
  from the sources bucket and check each against the bundled manifest (FR-002).
- **IAM** (least privilege): Bedrock invoke on the three Claude 5.5 models only, read on the
  sources bucket, read/write on the drafts bucket, read/write on the ledger table, CloudWatch
  Logs. On `bedrock-runtime` that is `bedrock:InvokeModel` on each inference profile and the
  foundation models it routes to; Mantle would need `bedrock-mantle:CreateInference` instead (AWS
  endpoints page), available through the module's `extra_bedrock_actions`.
- **Timeouts**: `run_section` 900 s (model calls use shorter SDK timeouts so a hung call fails
  cleanly), the others 60–300 s.
