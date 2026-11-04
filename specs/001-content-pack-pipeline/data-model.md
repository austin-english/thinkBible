# Data Model: Content Pack Format and Batch Pipeline

**Feature**: [spec.md](spec.md) · **Research**: [research.md](research.md)

There are three groups of data:
1. **Published** data, the contract the app reads. It is defined by the JSON Schemas in
   [contracts/](contracts/) and moves to `content/schema/` during implementation.
2. **Draft and pipeline** data in `content/drafts/{book}/`, which you review in git.
3. **Source** data in `content/sources/`.

Field names are camelCase in JSON and snake_case in the Python models (Pydantic aliases).

---

## 1. Published (contract)

### StudyPack ([study-pack.schema.json](contracts/study-pack.schema.json))

| Field | Type | Rules |
|---|---|---|
| `formatVersion` | int | `1` |
| `book` | `{id, name}` | `id` is a USFM code (`MRK`) |
| `packVersion` | semver | Increases on every publish (R13) |
| `publishedAt` | datetime | |
| `translations[]` | `{id, name, abbreviation, path, sha256}` | The first entry is the default (BSB). `sha256` matches the verse file |
| `sources[]` | Source | Every translation and commentary used, with license and checksums (FR-023) |
| `build` | `{promptVersions, questionGuideVersion, models}` | Recorded per stage (FR-013) |
| `sections[]` | Section | In reading order. Together they cover every verse of the book exactly once (SC-001) |

### Section ([section.schema.json](contracts/section.schema.json))

| Field | Type | Rules |
|---|---|---|
| `id` | `mrk-1-1` | Permanent. Frozen after first publish (FR-004) |
| `ref` | string | Display reference, e.g. "Mark 1:1-8" |
| `chapter`, `verseStart`, `verseEnd` | int | Within one chapter. `verseStart ≤ verseEnd`. Frozen after first publish |
| `title` | ≤ 80 chars | From the BSB heading, or edited during review |
| `noPrompt` | bool | True only when no key idea can be targeted (FR-005). Then the section has no active questions |
| `context` | ≤ 280 chars | Required |
| `viewsDiffer` | ≤ 400 chars or null | Neutral |
| `manuscriptNotes[]` | `{chapter, verseStart, verseEnd, text}` | From alignment (R3) |
| `verseNotes[]` | optional | Reserved for V2 |
| `keyIdeas[]` | KeyIdea | Retired ideas stay in the list |
| `questions[]` | Question | Retired questions stay in the list |

### KeyIdea

| Field | Type | Rules |
|---|---|---|
| `id` | `mrk-1-1-k3` | Permanent. Never reused |
| `title` | ≤ 60 chars | Frozen once published |
| `body` | ≤ 240 chars | Frozen once published. Neutral modern English, with no quoted translation wording |
| `sources[]` | commentator ids | 1–3, unique. Each one is backed by an evidence quote in the draft (R10) |
| `agreed` | bool | `= len(sources) ≥ 2` |
| `verseStart`, `verseEnd` | int | Within the section |
| `status` | `active` or `retired` | |
| `addedIn`, `retiredIn` | semver | `retiredIn` is required when retired |
| `replaces` | key idea id | Optional. Must name a retired idea in the same section |

### Question

| Field | Type | Rules |
|---|---|---|
| `id` | `mrk-1-1-q4` | Permanent. Never reused |
| `level` | 1–3 | Set by the R11 rule, then adjusted by the level check |
| `type` | noticing, meaning, application, seasonal | Pipeline metadata |
| `verseStart`, `verseEnd` | int | Within the section. The full section range means "whole passage" |
| `text` | 10–160 chars, ends with `?` | Frozen once published. Not yes/no. Does not repeat a target idea word for word |
| `textByTranslation` | `{kjv: "…?"}` | Optional variants (R12) |
| `targets[]` | key idea ids | ≥ 1. All in the same section and active at publish time |
| `isAlternate` | bool | At most one primary and one alternate per level, among active questions |
| `status`, `addedIn`, `retiredIn`, `replaces`, `series` | as for KeyIdea | |

### VerseText ([verses.schema.json](contracts/verses.schema.json))

One file per translation per book: chapters → verses `{number, text, paragraphStart?, lines?}`,
plus `omittedVerses[]`.

### PackIndex ([index.schema.json](contracts/index.schema.json))

The latest version per book, with the path, sha256 and byte size of every file.

### Cross-field rules (enforced by checks and Pydantic validators, not by JSON Schema)

1. All section ranges in a book are contiguous and non-overlapping, and cover every verse
   present in either translation.
2. Every key idea's and question's verse range lies inside its section.
3. Every ID begins with its section's ID. IDs are unique across the whole book's history.
4. `agreed == (len(sources) >= 2)`.
5. Question targets name active key ideas in the same section.
6. Level count follows the number of active key ideas (1 → L1, 2 → L1–2, 3+ → L1–3), with ≤ 6
   active questions. A section with 2+ levels has at least one whole-passage question (FR-009).
7. A `noPrompt` section has no active questions. A section that is not `noPrompt` has at least
   one active Level 1 question.
8. Every `{{ref:C:V(-V)}}` placeholder resolves in every published translation.
9. Retiring a key idea also retires the active questions that target only that idea (FR-024).

### Publish check (previous published version → new version)

The previous version's `study.json` is downloaded from S3 through `index.json`. The publish
fails, with exit code 5, if any of these hold:
- a section ID from the previous version is missing, or its chapter or verse range changed;
- a key idea or question ID is missing;
- `title`, `body`, `text` or `textByTranslation` changed on a previously published item;
- an item went from `retired` back to `active`;
- a new item reuses an ID that was ever used before;
- a `replaces` reference points to an item that isn't retired.

---

## 2. Drafts and pipeline state (`content/drafts/{book}/`, committed)

```
content/drafts/mrk/
├── book.json            # BookState
├── sections.json        # SectionMap (editable until first publish)
├── sections/mrk-1-1.json      # SectionDraft — working copy you edit
├── .generated/mrk-1-1.json    # SectionDraft — last machine output (for the 3-way merge, R9)
├── runs.json            # RunRecord[]
├── approval.json        # Approval (after `approve`)
└── review.html          # gitignored, generated by `report`
```

### BookState (`book.json`)

| Field | Notes |
|---|---|
| `book` | `{id, name}` |
| `status` | See the state machine below |
| `lastPublished` | semver or null |
| `idCounters` | `{sectionId: {k: n, q: n}}`. Only ever increases (R13) |

**State machine**:

```
(none) → sectioned → generating → generated → checked ─┬→ ready-for-review → approved → published
                                     ▲          │       │        │
                                     │          └ flagged ┘        │ (any draft edit changes the
                                     └──────────── re-run ─────────┘  drafts hash → back to checked)
```

- `approved` requires zero check failures and every flag resolved (R18).
- `published` is recorded with its version. Later edits start a new cycle toward the next version.

### SectionMap entry (`sections.json`)

`{id, chapter, verseStart, verseEnd, title, titleSource: "bsb-heading"|"split"|"human",
henryDivisions: [startVerse…]}`

### SectionDraft (`sections/{id}.json` and `.generated/{id}.json`)

| Field | Notes |
|---|---|
| `section` | The publishable Section fields (as above), including draft-only `status: "rejected"` for items you reject before first publish |
| `evidence` | `{keyIdeaId: [{commentator, quote}]}`. Not published (R10) |
| `excerpts` | `{commentator: {sha256, tokens, items[], crossRefs[], trimmed}}`. A record of model inputs, not the text |
| `summary` | One-line passage summary (from `summaries`) |
| `noPromptReason` | Set when `noPrompt` is true |
| `features` | `{questionId: {answerDirectness, outsideKnowledge, verseSpan, agreement}}` (R11) |
| `checks` | `[{itemId, check, ok, detail}]` |
| `flags` | `[{itemId, source: "check"\|"review"\|"levels"\|"align"\|"merge"\|"budget", reason, accepted: bool}]` |
| `grades` | `{itemId: {score: 1-5, notes}}` from `review` |
| `humanEdits` | `[{itemId, field, at}]`, computed by comparing with `.generated` (R9) |
| `stages` | `{stage: {promptVersion, model, inputHash, completedAt, costUsd, status: "done"\|"failed", error?}}` (R8) |

### RunRecord (`runs.json`)

`{runId, book, stage, startedAt, endedAt, sections: {done, skipped, failed}, estimateUsd, capUsd,
spentUsd, tokens: {input, output, cacheRead, cacheWrite}, models, promptVersions, stoppedBy:
null|"cap"|"error"}`

### Approval (`approval.json`)

`{book, approvedAt, draftsSha256, gitHead, acceptedFlags: [itemId…]}`

---

## 3. Sources (manifest in git, files in S3, local cache in `content/sources/`)

### SourceManifest (`content/sources/manifest.json`, committed)

```
{ "bucket": "thinkbible-sources",
  "apiVersion": "V1.16.0",
  "sources": {
    "bsb": { "kind": "translation", "apiId": "BSB", "name", "license", "licenseUrl",
             "upstreamSha256",
             "books": { "MRK": { "file": "bsb/MRK.json",
                                 "s3Key": "snapshots/2026-11-05/bsb/MRK.json",
                                 "sha256", "bytes", "retrievedAt", "snapshotId": "2026-11-05" } } },
    "kjv": { "apiId": "eng_kjv", ... },
    "matthew-henry": { "kind": "commentary", "tradition": "Reformed (Presbyterian)", ... },
    "jamieson-fausset-brown": { "tradition": "Reformed-leaning", ... },
    "adam-clarke": { "tradition": "Wesleyan (Methodist)", ... } } }
```

Rules:
- `file` is the path in the local cache (gitignored). `s3Key` is the write-once object.
- An entry is added only together with its upload, or before the upload when you work offline,
  with `sources push` still to run.
- Every read is checked against `sha256`.

### Normalised translation book (`{tr}/{BOOK}.json`)

`{book, chapters: [{number, items: [heading{text} | verse{number, text, lines?, noteIds[]} |
break{paragraph}], footnotes: [{noteId, text, chapter, verse}]}]}`

### Normalised commentary book (`{commentator}/{BOOK}.json`)

`{book, introduction?, chapters: [{number, introduction?, items: [{verse, text}]}]}`

---

## 4. Model call outputs (internal, Pydantic `output_format` models)

| Stage | Output model |
|---|---|
| `summaries` | `{summary: str ≤ 120}` |
| `generate` (1) ideas | `{keyIdeas: [{title, body, sources[], verseStart, verseEnd, evidence: [{commentator, quote}]}], context, viewsDiffer?, noPrompt: bool, noPromptReason?}` |
| `generate` (2) questions | `{questions: [{text, type, verseStart, verseEnd, targets[] (indexes or ids), answerDirectness, outsideKnowledge}]}`. Code assigns levels, alternates and IDs |
| `align` | `{kjvText: str}` per item, or `{note: str}` per manuscript candidate |
| `review` | `{items: [{itemId, score 1-5, flags: [reason]}]}` |
| `levels` | `{answer: str}`, then `{coveredTargetIds: []}` |
