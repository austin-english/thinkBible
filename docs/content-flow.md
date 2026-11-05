# Content flow: from frozen sources to the app

How study content is made (the batch pipeline, spec 001), what a content pack contains, and how
the iPhone app uses it (specs 002–004, planned). For stage-level detail, see
[`specs/001-content-pack-pipeline/`](../specs/001-content-pack-pipeline/). For example files,
see [`content/schema/fixtures/valid/`](../content/schema/fixtures/valid/).

## The big picture

```mermaid
flowchart LR
    SRC["Frozen sources<br/>Bible text + 3 commentaries"]
    PIPE["Pipeline<br/>AI drafts key ideas<br/>and questions"]
    REV{{"You review<br/>and approve"}}
    PACK[("Content pack<br/>per book, versioned")]
    APP["iPhone app<br/>read + reflect"]
    API["Compare API<br/>which ideas you caught"]

    SRC --> PIPE --> REV --> PACK --> APP
    APP <--> API
```

- **Sources** are downloaded once and frozen. Nothing reads from the web after that.
- The **pipeline** drafts the study content for one book at a time. AI only summarises what the
  commentators say.
- **You** review the drafts and approve them before anything is published.
- A **content pack** is published per book and version, and the app downloads it and keeps it
  offline.
- The **app** compares a reader's answer with the pack's key ideas. That is the only live AI call.

## What's in a pack

```mermaid
flowchart LR
    INDEX["index.json<br/>latest version per book"]
    STUDY["study.json<br/>one per book"]
    VERSES["verses/bsb.json<br/>verses/kjv.json"]
    SEC["Sections<br/>Mark 1:1-8, ..."]
    IDEAS["Key ideas<br/>with commentator sources"]
    QS["Questions<br/>levels 1-3"]

    INDEX --> STUDY & VERSES
    STUDY --> SEC --> IDEAS & QS
    QS -. targets .-> IDEAS
```

- **`study.json`** is shared by every translation. **`verses/*.json`** holds the text, one file
  per translation.
- **IDs never change** (`mrk-1-1`, `mrk-1-1-k3`, `mrk-1-1-q4`). Weak items are retired, never
  deleted.
- The contract is the set of JSON Schemas in [`content/schema/`](../content/schema/).

## How the app uses it

```mermaid
flowchart LR
    GET["Download pack<br/>(Mark is bundled)"]
    READ["Show verses<br/>+ section headers"]
    ASK["Ask the next question<br/>for this read"]
    CMP["Compare answer<br/>with key ideas"]
    CARD["Results card<br/>caught / missed + sources"]
    SAVE["Save reflection<br/>on device + iCloud"]

    GET --> READ --> ASK --> CMP --> CARD --> SAVE
```

- Reading and the results card work **offline** from the pack. Only the personal note needs the
  compare API.
- The compare API receives just the answer and two IDs. It never stores the answer.
- Each saved reflection keeps a copy of what was shown, so it stays complete after pack updates.
