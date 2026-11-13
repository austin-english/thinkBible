# ThinkBible: monorepo guide for agents

ThinkBible is an iPhone app for reading the Bible one section at a time.
1. After each section the reader answers a question in their own words.
2. A small live AI call compares the answer with key ideas that were prepared ahead of time from three public-domain commentaries (Matthew Henry, Jamieson-Fausset-Brown, Adam Clarke).
3. The app shows what they caught and what they missed.

Read these before any non-trivial change:
- `docs/brief.md`: product and architecture brief (exported; the online doc is the source of truth).
- `docs/design/README.md`: the "book feel" UI spec (feed, chapter panel, unlocks, You & settings), tokens and progress model, with screens in `docs/design/screens/`.
- `docs/design/DESIGN.md`: the UI rules the book-feel design kept: paywall, fallback and offline states, question scope, cost limits, copy.
- `api/openapi.yaml`: the only live API (compare).
- `content/schema/section.schema.json`: the content pack contract shared by the pipeline, backend and app.

## Layout

| Path | What | Open in |
|---|---|---|
| `ios/` | SwiftUI app + local Swift packages (DesignSystem, ContentKit, ReflectionKit, APIClient) | Xcode |
| `backend/` | Python Lambdas: `compare` (live AI) and `authorizer` (App Attest) | VS Code |
| `pipeline/` | Python batch jobs that turn frozen sources into reviewed content packs | VS Code |
| `shared/` | Python package `thinkbible_core`: pack models used by backend + pipeline | VS Code |
| `infra/` | Terraform, one AWS environment: the root (`main.tf`) and modules `api`, `pipeline`, `storage`, `cdn` | VS Code |
| `content/` | `schema/` (contract), `sources/manifest.json` (checksums of the S3 snapshot; the text itself is a gitignored local cache), `drafts/` (reviewed drafts). Published packs live only in S3 | VS Code |
| `api/` | OpenAPI spec for the compare endpoint | VS Code |
| `docs/` | Brief and design handoff | either |
| `specs/`, `.specify/` | Spec Kit features (created by `specify init`) | either |

Run Claude Code from the repo root. Each area has its own `CLAUDE.md` with local rules; follow the most specific one.

## Rules that apply everywhere

- **Content comes only from the frozen source snapshot.** It is stored in a private S3 bucket, cached in `content/sources/` (`thinkbible-pipeline sources pull`), and verified against `content/sources/manifest.json`. No agent, job or Lambda fetches commentary or Bible text from the web at runtime, and models get no browsing tools.
- **No live question generation.** Every question, key idea and context note is generated in the batch pipeline, reviewed, and shipped in a content pack. The live AI only compares an answer with stored key ideas.
- **The content contract is `content/schema/section.schema.json`.** Change it first, then update `shared/` models, the pipeline output, and the Swift `ContentKit` models in the same change.
- **Never log or store answer text on the server.** The backend sees it only for the length of a compare call. Answers live on the device and in the user's iCloud.
- **IDs are permanent.** Question and key idea IDs never change or get reused. Retired questions stay in packs, marked retired.
- **No hard-coded colors or prices in the app.** Colors come from DesignSystem tokens, and prices come from StoreKit.

## Commands

```bash
make bootstrap    # uv sync for shared/backend/pipeline, pre-commit hooks
make lint         # ruff + mypy (Python), terraform fmt -check
make test         # pytest for shared, backend, pipeline
make ios-test     # xcodebuild test (after the Xcode project exists)
make pipeline BOOK=mark STAGE=all   # run batch jobs in AWS (or `run --local` for a few sections)
make deploy       # Lambda bundle + terraform apply in infra/
make sources-publish   # after an import: check, verify, push, verify the S3 copy
```

## Spec Kit

Initialise once from the repo root: `specify init . --integration claude`.
Suggested feature order (from the brief):
1. constitution
2. content pack format and pipeline
3. reader and Read mode
4. reflection, comparison and live API
5. question levels and re-reads
6. contents, saved reflections and progress
7. subscription, paywall and Settings
8. feedback and question analytics

UI specs should link `docs/design/README.md` (or `DESIGN.md` for the paywall and fallback rules) and the matching screen in `docs/design/screens/`.

## Git

Use small commits with a scope prefix: `ios:`, `backend:`, `pipeline:`, `infra:`, `content:`, `docs:`.
Never commit secrets, `.env` files, Terraform state, or source text. Only `content/sources/manifest.json` is committed, and only together with the matching snapshot upload (`sources push`).
