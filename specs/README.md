# ThinkBible specs

Spec Kit feature specs, in build order. The constitution lives at
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md) (v1.0.0).

| # | Feature | Status | Open clarifications |
|---|---|---|---|
| 001 | [Content pack format and batch pipeline](001-content-pack-pipeline/spec.md) | Draft | Review surface for human review |
| 002 | [Chapter reader and Read mode](002-reader-read-mode/spec.md) | Draft | none |
| 003 | [Reflection, comparison and live compare API](003-reflection-live-compare/spec.md) | Draft | Crisis resources; voice input in MVP? |
| 004 | [Question levels and re-reads](004-question-levels-rereads/spec.md) | Draft | none |
| 005 | [Contents, saved reflections and progress](005-contents-progress/spec.md) | Draft | none |
| 006 | [Subscription, paywall and Settings](006-subscription-paywall-settings/spec.md) | Draft | none |
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

## Doc discrepancies to fix

These were found while drafting. The specs follow the resolution shown here, so update the source
docs to match:

1. **Free tier.** The brief and the paywall spec say 3 free reflections in total.
   `docs/design/DESIGN.md` (Submit, edit and cost rules: "free tier is 1 reflection a day") and the
   brief's data model (Entitlement: "daily free reflection used") are stale. The specs use 3 in
   total.
2. **Live follow-up questions.** Brief principle 3 says the live model "writes follow-up questions".
   That conflicts with "no live question generation". The constitution forbids it.
3. **Pack shape.** The brief's example section JSON (question `type`, idea as one `idea` string)
   predates DESIGN.md, which has `level`, `title`/`body`, verse scope and `isAlternate`. Spec 001
   follows DESIGN.md and keeps `type`. Reconcile the brief's example when the schema lands.
4. **"Try a different question".** It is still in the brief's MVP table but was replaced by levels
   and "Not a helpful question?". The specs drop it.
5. **Translations in MVP.** The brief's MVP summary says "one translation", but the MVP table and
   DESIGN.md include the BSB / KJV switch. The specs include both.
6. **Verse notes.** Pipeline step 6 generates them, but DESIGN.md defers them to V2. The pack
   format allows them, and the MVP doesn't generate or show them.
7. **"Compare is the only live API".** Analytics (spec 007) may need a second endpoint. See its
   clarification.
8. **Files referenced but not yet created:** `api/openapi.yaml`, `content/schema/section.schema.json`,
   the per-area `CLAUDE.md` files, `ios/README.md`, `.github/workflows/`. Specs 001 and 003 produce
   the first two during `/speckit-plan`.
