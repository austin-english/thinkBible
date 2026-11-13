# ThinkBible specs

Spec Kit feature specs, in build order. The constitution lives at
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md) (v1.2.0).

| # | Feature | Status | Open clarifications |
|---|---|---|---|
| 001 | [Content pack format and batch pipeline](001-content-pack-pipeline/spec.md) | Draft | Review surface for human review |
| 002 | [Book-feel feed and chapter panel](002-reader-read-mode/spec.md) | Draft | none |
| 003 | [Question footer, reply thread and live compare API](003-reflection-live-compare/spec.md) | Draft | Crisis resources; voice input in MVP? |
| 004 | [Question levels and 24-hour unlocks](004-question-levels-rereads/spec.md) | Draft | none |
| 005 | [Section status, saved passages and progress](005-contents-progress/spec.md) | Draft | none |
| 006 | [Subscription, paywall and You & settings](006-subscription-paywall-settings/spec.md) | Draft | none |
| 007 | [Feedback and question analytics](007-feedback-question-analytics/spec.md) | Draft | Event ingestion path |

Before any of this, the brief's **step zero** applies: a content spike on Mark. Spec 001's
Story 1 is that spike, so 001 comes first.

## Working on a feature

All seven specs were drafted together on `main` as a backlog. Build each one on its own branch:

```bash
git checkout main && git pull
git checkout -b 001-content-pack-pipeline
```

Then in Claude Code, from the repo root:

1. `/speckit-clarify`: resolve the `[NEEDS CLARIFICATION]` markers and any other gaps.
2. `/speckit-plan`: research, data model, contracts (pack schema, `api/openapi.yaml`), quickstart.
3. `/speckit-tasks`: dependency-ordered tasks.
4. `/speckit-analyze`: consistency check against the spec and constitution.
5. `/speckit-implement`.

Spec Kit finds the active feature through `.specify/feature.json`, which is local and gitignored.
When you switch features, point it at the new folder:

```bash
printf '{\n  "feature_directory": "specs/002-reader-read-mode"\n}\n' > .specify/feature.json
```

Or set `SPECIFY_FEATURE_DIRECTORY=specs/002-reader-read-mode` for one session.

New features after these use `/speckit-specify <description>`. Its git hook creates the branch and
picks the next number.

## Decisions

Confirmed by the product owner on 2026-11-04 and applied to `docs/brief.md`, `DESIGN.md`, the
constitution and these specs:

- **Free tier:** 3 reflections in total per device. After that, the reader must subscribe.
- **Follow-up questions:** a section's next, harder question from the reviewed pool. The live
  model never writes questions. *Superseded 2026-11-10:* it now unlocks 24 hours after the previous
  level is answered, not on a re-read (see below).
- **Pack shape:** follows DESIGN.md ("Data the UI reads"). Questions have `level`, verse scope,
  `targets`, `isAlternate` and `status`, and keep `type` as pipeline metadata. Key ideas have
  `title`, `body` and verse scope. The brief's example section now uses this shape.

### Spec 001: cloud runs and an automatic quality gate (2026-11-10)

- **Runs execute in AWS**: Step Functions with one Lambda per section per stage, drafts in S3, a
  DynamoDB spend ledger. The CLI estimates, confirms and starts runs; `--local` runs a few
  sections in-process for prompt tuning.
- **No manual review of generated JSON.** Rule checks, the evidence check, an Opus 5.5 grader and
  a level check drop weak items and write a read-only scorecard. The grader is calibrated once
  against the owner's grades (≥ 85% agreement on ≥ 30 items).
- **Draft, then live.** A run whose gate passes publishes to the draft channel; the owner reads it
  in the app and runs `promote`. Frozen text and the additive publish check apply to live only.
- Constitution amended to v1.2.0 for this. In v1.2.1 (2026-11-13), draft and live became two
  channels of one packs bucket in a single AWS environment, instead of two environments.

### Book-feel redesign (2026-11-10)

Specs 002–007 were updated to the "book feel" design in
[`docs/design/README.md`](../docs/design/README.md) and `docs/design/screens/*.png`.
`docs/design/DESIGN.md` now covers only what that design left unchanged (paywall, fallback and
offline rules, question scope, cost limits, data the UI reads). Spec folder names are kept so
existing branches still match; the titles changed.

- **No Home, no Study / Read switch, no Skip.** The app opens on a feed of page cards. The chapter
  panel is the table of contents. Plain reading is Settings › Show questions. Scrolling past an
  unanswered card marks it Read, and analytics count it as "passed".
- **Levels unlock 24 hours after an answer**, with one local notification per chapter. All on the
  device; no backend change.
- **Settings:** translation and text size live only in You & settings. Scripture font, "Open in"
  and "Open questions automatically" are gone. Accent color, Justify text, Show questions and
  Harder-question alerts are new.
- **No backend, API or schema changes.** Spec 001 and the compare-service requirements in spec 003
  are unchanged.

## Doc discrepancies to fix

These were found while drafting. The specs follow the resolution shown here, so update the source
docs to match:

1. **"Try a different question".** It is still in the brief's MVP table but was replaced by levels
   and "Not a helpful question?". The specs drop it.
2. **Translations in MVP.** The brief's MVP summary says "one translation", but the MVP table and
   DESIGN.md include the BSB / KJV switch. The specs include both.
3. **Verse notes.** Pipeline step 6 generates them, but DESIGN.md defers them to V2. The pack
   format allows them, and the MVP doesn't generate or show them.
4. **"Compare is the only live API".** Analytics (spec 007) may need a second endpoint. See its
   clarification.
5. **Files referenced but not yet created:** `api/openapi.yaml`, `content/schema/section.schema.json`,
   the per-area `CLAUDE.md` files, `ios/README.md`, `.github/workflows/`. Specs 001 and 003 produce
   the first two during `/speckit-plan`.
6. ~~Constitution behind the book-feel design.~~ Resolved in v1.1.0 (2026-11-10): Read mode is
   gone (plain reading is "questions off"), follow-ups unlock 24 hours after the previous level is
   answered, and the UI source of truth is `docs/design/README.md` plus `DESIGN.md`.
7. **Design handoff paths.** `docs/design/README.md` cites `source/PostBook.dc.html`,
   `source/YouBook.dc.html` and `source/UnlockNotification.dc.html`, which aren't in the repo, and
   `docs/design/CLAUDE_CODE_PROMPT.md` refers to `docs/design/book-feel/`. The files were placed in
   `docs/design/` directly. Add the `source/` files, or drop the references.
8. **Not drawn yet (settled iteratively during the UI features):** the `…` menu, dark mode for the book-feel layout (proposed values only), where
   the context and views-differ notes sit in the reply (specs put them in the expanded reply), and
   the text-size steps (specs keep the earlier 5 steps).
