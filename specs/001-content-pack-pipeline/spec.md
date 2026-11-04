# Feature Specification: Content Pack Format and Batch Pipeline

**Feature Branch**: `001-content-pack-pipeline`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Content pack format and pipeline (brief spec 2): freeze the BSB, KJV
and three public-domain commentaries as checksummed sources; turn them, one book at a time, into
reviewed, versioned study content (sections, key ideas, leveled question pools, context and
views-differ notes, translation variants); run automatic checks and model review; stop at a human
review gate; publish versioned packs the app downloads and caches. Launch book: Mark."

**References**: [docs/brief.md](../../docs/brief.md) (Content sources and licensing, Content
pipeline, Question freshness, Data model); `content/schema/section.schema.json` (to be created by
this feature); constitution principles II, III, IV, VII.

## Clarifications

### Session 2026-11-04

- Q: During review, where will you read the generated content, make edits, and approve a book? →
  A: A generated review report (HTML or Markdown, flagged items first). Edits are made directly in
  the draft JSON files, and an `approve` command approves the book. Review happens as a git diff.
- Q: After a question or key idea has been published, can you still edit its text in a later pack
  version? → A: No (MVP). Published wording is frozen, typos included. A fix retires the item
  and adds a new one with a new ID that records which item it replaces. Drafts stay freely
  editable until first publish.
- Q: Once a book is published, can the verse ranges of its sections change in a later version? →
  A: No (MVP). A published section's ID and verse range are frozen. Boundaries can change freely
  during review before first publish.
- Q: Should a pipeline run protect you from an unexpectedly large model bill, and if so, how? →
  A: Show an estimate and ask for confirmation before the run, then stop the run if actual spend
  passes a per-run cap (default about 2× the estimate). The run can be resumed later.

## User Scenarios & Testing *(mandatory)*

The primary actor is the **content owner** (the developer acting as editor and reviewer). The
secondary actor is the **app**, which consumes published packs.

### User Story 1 - Generate and read a book's study content (Priority: P1)

The content owner runs the pipeline for one book (Mark) against the frozen sources. They get every
section of that book, each with its verse range, title, 1–5 key ideas attributed to commentators, a
leveled question pool, a context note and any "views differ" note. They can read it all in a
readable review document.

**Why this priority**: This is the brief's "step zero" content spike. If the key ideas aren't sound
and the questions aren't worth answering, nothing downstream matters. It also produces the first
real pack for every other feature to build against.

**Independent Test**: Run the generate stage for Mark on a dev machine. Confirm a draft study file
and a human-readable review document exist for every section, and that every key idea names at
least one of the three commentators.

**Acceptance Scenarios**:

1. **Given** the frozen Mark sources, **When** the owner runs generation for Mark, **Then** every
   section of Mark 1–16 has draft study content, and each section's verse range is contiguous,
   non-overlapping, and together the ranges cover every verse of the book exactly once.
2. **Given** a section whose commentary excerpts contain three ideas, **When** key ideas are
   extracted, **Then** each idea is in plain modern English and lists the commentators it came
   from. Ideas stated by two or more commentators are marked "agreed" and ranked first.
3. **Given** a section with N key ideas, **When** questions are written, **Then** the section gets
   Level 1 only (N = 1), Levels 1–2 (N = 2) or Levels 1–3 (N ≥ 3). Each level has one or two
   questions, each targeting at least one key idea, with at most 6 questions per section.
4. **Given** a genealogy such as Genesis 5, **When** it is generated, **Then** it goes through
   key-idea extraction like any other section, and its questions are scoped to the verses the
   commentaries discuss (for example Enoch in 5:21–24).
5. **Given** a section where extraction yields no key idea that a question could target and the
   reader could answer from the passage (for example a bare census total), **When** it is
   generated, **Then** it is flagged "no prompt", has a short context note instead of questions,
   and is listed in the review document so the owner can confirm or override the flag.
6. **Given** generation has already finished for some sections, **When** the owner re-runs the
   same book with the same prompt version, **Then** finished sections are skipped. Only missing or
   failed sections are generated.

---

### User Story 2 - Automatic checks and model review flag weak content (Priority: P1)

After generation, automatic checks and a second model pass run over the book. The owner gets a
list of flagged items with reasons, so they spend review time where it matters.

**Why this priority**: The constitution forbids publishing without checks and review. Flagging
makes human review of ~100 sections take an evening or two instead of a week.

**Independent Test**: Seed a draft book with known-bad items (a yes/no question, a question that
repeats a key idea word for word, an idea with no source, a broken verse placeholder). Confirm each
one is flagged with the right reason and that the book cannot move to "approved" while
check failures remain.

**Acceptance Scenarios**:

1. **Given** a draft book, **When** checks run, **Then** every item is checked against: length
   limits; questions end with "?"; no yes/no questions; no key idea repeated word for word in a
   question; every key idea has at least one source; every verse placeholder resolves in both
   translations; every question targets an existing key idea; the output is valid against the
   pack schema.
2. **Given** a draft book that passes checks, **When** model review runs, **Then** each question
   and key idea gets a grade against the question quality rules (open-ended, short, answerable
   from the passage, not leading, no tradition-specific assumptions). Weak items are flagged with
   a reason.
3. **Given** a question's level assigned by rule, **When** the level check answers it as a
   typical reader with only the passage, **Then** a Level 3 it answers easily is moved down and a
   Level 1 it struggles with is flagged.
4. **Given** a book with flagged items, **When** the owner opens the review document, **Then**
   flagged items appear first, grouped by section, with the reason for each flag.

---

### User Story 3 - Human review gate and publishing (Priority: P1)

The owner reviews the book, edits or rejects items, approves it, and publishes it as a versioned
pack. The app can then download it. Nothing reaches the app without this approval.

**Why this priority**: Publishing is how content reaches users. The human gate is
constitutionally required.

**Independent Test**: Approve a reviewed Mark draft and publish it to the dev environment. Confirm
the study file and both verse-text files are retrievable at versioned paths, with provenance, and
that an unapproved book cannot be published.

**Acceptance Scenarios**:

1. **Given** a book in "ready for review", **When** the owner tries to publish it without
   approving, **Then** publishing is refused.
2. **Given** the owner edits a question's wording during review, **When** the book is approved,
   **Then** the edited wording is what gets published, and the edit is recorded as a human change.
3. **Given** an approved book, **When** it is published, **Then** one study file (shared by both
   translations) and one verse-text file per translation are available at a path that includes
   the pack version. The study file records the source names, snapshot dates, checksums,
   prompt versions and question-guide version it was built from.
4. **Given** a published pack, **When** a newer version is published, **Then** the older version
   stays available, and the app can find the latest version for each book.

---

### User Story 4 - Frozen source snapshot (Priority: P2)

The owner imports the BSB and KJV texts and the Matthew Henry, Jamieson-Fausset-Brown and Adam
Clarke commentaries once, from the Free Use Bible API. The result is frozen files with checksums and
the retrieval date. From then on every pipeline step reads only that snapshot.

**Why this priority**: Required before Story 1 can run for real. Ranked P2 only because it runs
once and is simple. It can be done first in practice.

**Independent Test**: Run the import for Mark only. Confirm the source files and a checksum manifest
exist, then change one byte in a source file and confirm every pipeline stage refuses to run.

**Acceptance Scenarios**:

1. **Given** no snapshot, **When** the owner runs the import, **Then** source files for both
   translations and all three commentaries are stored in the private object store and the local
   cache. A manifest of checksums, storage keys, source URLs, licenses and retrieval date is
   committed to the repo. Requests are made at a polite rate.
2. **Given** a fresh clone with an empty local cache, **When** the owner pulls the snapshot,
   **Then** every file listed in the manifest is downloaded and passes its checksum.
3. **Given** a snapshot, **When** any pipeline stage starts, **Then** it verifies checksums first
   and stops with an error on any mismatch.
4. **Given** any pipeline stage, **When** it runs, **Then** it makes no network request for
   Scripture or commentary text. Model calls receive only the current section's excerpts and have
   no browsing or search tools.

---

### User Story 5 - Translation alignment (Priority: P2)

Study content is written once in neutral modern English with verse placeholders. Wherever a
question or key idea leans on wording that only one translation uses, the pipeline adds a
per-translation wording variant. Where a verse is present in one translation but missing or
bracketed in the other, it adds a short neutral manuscript note.

**Why this priority**: The app ships BSB (default) and KJV. Without alignment, some KJV readers see
questions that quote words their text doesn't contain.

**Independent Test**: Run alignment on Mark. Confirm that the sandals/shoes example (Mark 1:7)
gets a KJV variant, and that Mark 16:9–20 (bracketed in BSB) gets a manuscript note.

**Acceptance Scenarios**:

1. **Given** a question that names a word appearing only in the BSB rendering, **When** alignment
   runs, **Then** a KJV wording variant is added and the default text is unchanged.
2. **Given** a verse present in one translation and missing or bracketed in the other, **When**
   alignment runs, **Then** a short neutral manuscript note is attached to that section.
3. **Given** alignment output, **When** human review runs, **Then** every variant and manuscript
   note is listed for review.

---

### User Story 6 - Additive refreshes keep IDs stable (Priority: P3)

Later, the owner adds questions to a book that is already published: replacing weak questions,
topping up alternates, or a seasonal series. The existing questions keep their IDs and wording.
Weak questions are retired, never deleted.

**Why this priority**: Not needed for launch, but the pack format must support it from day one,
because saved reflections depend on IDs never changing.

**Independent Test**: Publish Mark v1, run a refresh that retires one question and adds one, and
publish v1.1. Confirm every v1 question ID is still present in v1.1 with unchanged text, the
retired one is marked retired, and no ID was reused. Then edit a published question's text in
place and confirm the publish check refuses the version.

**Acceptance Scenarios**:

1. **Given** a published pack, **When** a refresh retires a question, **Then** the question stays
   in the next pack version with status "retired" and the version it was retired in.
2. **Given** a refresh, **When** new questions are added, **Then** they get new IDs never used
   before in that book, and record the pack version they were added in.
3. **Given** any new pack version, **When** the publish check compares it with the previous
   published version, **Then** publishing fails if any question or key idea ID is missing, reused,
   or has different text.
4. **Given** a typo in a published key idea, **When** the owner fixes it, **Then** the old idea is
   retired, a new idea with a new ID records that it replaces the old one, any question that
   targets only the old idea is retired and replaced the same way, and the next version publishes.

### Edge Cases

- A section where the three commentaries group verses differently from the BSB headings: section
  boundaries follow the BSB headings, adjusted to Matthew Henry's divisions. Very short sections
  (fewer than ~3 verses) merge with the next, and long ones (more than ~12 verses) split at a
  natural break.
- A boundary turns out wrong after a book is published: it stays as published. Fixing it needs a
  future feature that maps readers' progress from old sections to new ones.
- A section where commentaries say almost nothing: fewer key ideas and fewer levels. The pipeline
  never invents an idea to fill a level.
- Commentators disagree on a point: the disagreement goes into a neutral "views differ" note, and
  questions on that point stay open.
- A genealogy with narrative asides (Genesis 5: "and he died", Enoch, Lamech naming Noah): it gets
  questions on those verses. Only a section with nothing for a question to target is "no prompt".
- A commentator gives Hebrew name meanings or other facts the English text doesn't show: they MAY
  become key ideas (in a "views differ" note if contested), but no question may depend on them,
  because the reader must be able to answer from the passage.
- A reading that none of the three commentators states, however popular (for example a "hidden
  message" in the Genesis 5 names): it cannot appear in the pack.
- A model call fails or returns invalid output: that section retries on its own. After repeated
  failures it is marked failed, and the rest of the book continues.
- A run hits its spending cap: it stops after the sections in progress finish. Completed sections
  are kept, and the report shows spend so far and what is left. Resuming asks for confirmation
  again with a fresh estimate.
- A key idea quotes translation wording: flagged by checks (ideas must be in neutral modern English).
- Prompt or model change: only sections affected by the changed prompt version are regenerated,
  as a new version, and they go through review again.
- A source checksum mismatch: every stage halts, and nothing is generated from altered text.
- A reader taps "Not a helpful question?": this never changes the pack. The tap is counted for the
  review queue (spec 007), and only the owner can retire the question in a later version.

## Requirements *(mandatory)*

### Functional Requirements

**Sources**

- **FR-001**: The system MUST import the BSB and KJV texts and the Matthew Henry,
  Jamieson-Fausset-Brown and Adam Clarke commentaries once. The files are stored write-once in a
  private object store and cached locally in `content/sources/`. A manifest committed to the
  repo (`content/sources/manifest.json`) records for each file: source name, origin URL, license,
  retrieval date, storage key and checksums.
- **FR-002**: Every pipeline stage MUST verify source checksums before running and MUST stop on any
  mismatch.
- **FR-003**: No pipeline stage may fetch Scripture or commentary text from the network, and model
  calls MUST receive only the current section's excerpts, with no browsing or search tools.

**Sections**

- **FR-004**: The system MUST define one shared set of sections per book (verse ranges valid in
  both translations), titled from BSB headings and checked against Matthew Henry's divisions, with
  merge and split rules for very short or long sections. Each section has a permanent ID. Once a
  book is published, its sections' IDs and verse ranges are frozen. Changing a boundary after
  publish is out of scope for the MVP.
- **FR-005**: Whether a section gets questions MUST be decided by its commentary, not by the kind of
  passage. Every section goes through key-idea extraction, including genealogies, lists, census
  and law passages. A section is marked "no prompt" only when no key idea can be targeted by a
  question the reader could answer from the passage alone. It then carries a short context note
  instead of questions. The owner MAY override the flag in either direction during review, and
  the override is recorded as a human change.

**Study content**

- **FR-006**: For each section the system MUST produce 1–5 key ideas. Each idea has a permanent ID,
  a short title, a one- or two-sentence body, the commentators it came from, an "agreed" flag
  (2+ commentators) and a verse scope (start–end within the section). Agreed and best-supported
  ideas rank first.
- **FR-007**: Key ideas MUST restate only what the commentators say: no new interpretations, and no
  quoted translation wording. Verse references are placeholders the app resolves.
- **FR-008**: For each prompted section the system MUST produce a question pool. Each question has a
  permanent ID, a type (noticing, meaning, application), a level (1–3), a verse scope, the key idea
  IDs it targets, a primary/alternate role within its level, a status (active or retired), the
  pack version it was added in, and optional per-translation wording.
- **FR-009**: The number of levels MUST follow the number of key ideas (1 → L1, 2 → L1–2,
  3+ → L1–3), with one or two questions per level and a cap of 6 per section. Every section with 2+
  levels MUST have at least one whole-passage question.
- **FR-010**: Each question MUST target at least one key idea without giving it away, be
  answerable from the passage alone, be open-ended, short, not leading, and free of
  tradition-specific doctrinal assumptions. Its shape follows the passage kind (story, letter,
  poetry, prophecy). In genealogies, lists and laws, questions are scoped to the verses the
  commentaries single out.
- **FR-011**: The level of each question MUST be set by a fixed rule from features the model
  records (verse span, how directly the answer is stated, outside knowledge needed, commentator
  agreement), then adjusted by the level check.
- **FR-012**: Each section MUST have a two-line context note (who wrote it, to whom, why) and, where
  commentators or traditions disagree, a short neutral "views differ" note.
- **FR-013**: Generation MUST be driven by versioned prompts and a versioned question guide (quality
  rules plus 10–20 approved example questions). Their versions are recorded with each output.
- **FR-014**: Generation inputs per section MUST include: the passage in both translations, the
  section's commentary excerpts, a one-line summary of the previous section, and, on refreshes,
  the existing questions.

**Alignment, checks and review**

- **FR-015**: The system MUST run the translation alignment step (Story 5) once per book, adding
  per-translation wording variants and manuscript notes. The expensive generation steps MUST NOT
  run per translation.
- **FR-016**: The system MUST run the automatic checks listed in Story 2, scenario 1, and block
  approval while any check fails.
- **FR-017**: The system MUST run a model review pass and a level check, and record a grade and any
  flag reason per item.
- **FR-018**: The system MUST track each section's stage (generated, checked, flagged, approved,
  published), keyed by book, section and prompt version, so runs are idempotent and resumable.
- **FR-019**: The pipeline MUST generate a review report per book (HTML or Markdown) listing flagged
  items first, grouped by section, with the reason for each flag. The owner edits or rejects items
  directly in the book's draft JSON files and approves the book with an `approve` command. Drafts
  and approvals are committed to the repo, so each review is visible as a git diff. No separate
  review application is built for the MVP.
- **FR-020**: Human edits MUST be recorded as human changes (detected by comparing the draft files
  with the pipeline's last generated output) and preserved by later re-runs.

**Cost control**

- **FR-027**: Before any run that calls a model, the pipeline MUST show an estimated cost (sections
  to process × expected cost per section, skipping finished sections) and wait for the owner's
  confirmation.
- **FR-028**: During a run, the pipeline MUST track actual model spend and stop the run once it
  passes a per-run cap (default 2× the estimate, configurable per run). Sections already
  finished are kept, and the run can be resumed later. The final spend is reported at the end of
  every run.

**Publishing and versioning**

- **FR-021**: Publishing MUST be a separate, owner-triggered step that requires an approved book.
- **FR-022**: A published pack MUST consist of one study file per book (shared by all translations)
  and one verse-text file per translation, at versioned paths. Older versions stay available, and
  a per-book pointer tells the app the latest version.
- **FR-023**: Every study file MUST record provenance: source names, snapshot dates, checksums,
  prompt versions, question-guide version and pack version.
- **FR-024**: Pack updates MUST be additive. IDs are never removed, changed or reused. Once
  published, the text of a question or key idea is frozen, typos included. A fix retires the item
  and adds a new item with a new ID that records the ID it replaces. Retired questions and key
  ideas stay in the pack with status "retired". Retiring a key idea also retires the active
  questions that target only that idea. Before every publish, a publish check compares the new
  version with the last published one and MUST fail if any published ID is missing, reused or
  has different text, or if any published section's verse range has changed. Drafts are freely
  editable until their first publish.
- **FR-025**: The pack format MUST be defined by a single schema, which pipeline output, backend
  models and app models are all validated against.
- **FR-026**: The pack format MUST allow optional per-verse notes (names, places, customs) for a
  later release. The MVP pipeline does not need to generate them.

### Key Entities

- **Source snapshot**: a frozen text (translation or commentary), with origin, license, retrieval
  date and checksum manifest.
- **Content pack**: one book's published study content at a version, plus provenance; paired with
  one verse-text file per translation.
- **Section**: a shared verse range in a book, with ID, reference, title, "no prompt" flag, key
  ideas, questions, context note, views-differ note, manuscript notes and optional verse notes.
- **Key idea**: a permanent ID, title, body, commentator sources, agreed flag, verse scope, status
  (active or retired), added-in version, retired-in version, and the ID it replaces, if any.
- **Question**: a permanent ID, type, level, verse scope, targeted key ideas, primary/alternate
  role, status, per-translation wording, added-in version, retired-in version, the ID it replaces
  (if any), optional series.
- **Pipeline state**: per book, section and prompt version: stage, grades, flags and human edits.
- **Question guide / prompt version**: versioned instructions recorded on every output.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For Mark, 100% of verses belong to exactly one section, and 100% of prompted sections
  have at least one Level 1 question and at least one key idea with a named source.
- **SC-002**: Generating Mark (~100 sections) end to end takes under 30 minutes on demand and costs
  under $15 in model usage.
- **SC-003**: The owner can complete the flagged-item review of Mark in two evenings or less, and a
  full read-through of the launch book in under a week.
- **SC-004**: In the content spike, the owner judges at least 90% of Mark's key ideas sound and at
  least 80% of questions worth answering before edits.
- **SC-005**: Re-running a finished book with an unchanged prompt version makes zero model calls.
- **SC-006**: Zero published packs violate ID permanence or lack provenance (enforced by the
  publish gate).
- **SC-007**: A published Mark pack (study file plus both verse-text files) is under 1 MB in total
  when compressed.
- **SC-008**: No pipeline run spends more than its cap plus the cost of the sections that were
  already in progress when the cap was hit.

## Assumptions

- Launch book is Mark. BSB is the default translation, KJV the alternate (brief open question;
  treated as decided for this spec).
- The Free Use Bible API provides the BSB, KJV and the three commentaries under the licenses noted
  in the brief. Spot verification against a printed or CCEL edition happens for Mark.
- MVP runs can happen on the owner's machine against the dev environment, using on-demand model
  calls while prompts are tuned. Cloud orchestration per book and batch inference follow when
  later books are generated. Both use the same stages and outputs.
- The pack shape follows DESIGN.md ("Data the UI reads"): key ideas have title, body and verse
  scope; questions have level, verse scope, targets, alternate role and status, and keep `type` as
  pipeline metadata (confirmed 2026-11-04; the brief's example section matches).
- Verse notes are stored in the format but not generated or shown in the MVP (DESIGN.md defers
  them to V2).
- Seasonal series, question refresh runs and analytics-driven swaps reuse this pipeline but are
  specified later (spec 007 and V2).
