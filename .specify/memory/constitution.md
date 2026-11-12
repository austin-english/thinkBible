# ThinkBible Constitution

## Core Principles

### I. Scripture Is Never Paywalled

- Bible text, plain reading (questions off) and navigation of every published book MUST remain
  free, with no sign-in, no trial and no count limit.
- Only the study experience (live comparison beyond the free allowance, unlocked Level 2–3
  questions, premium series) MAY be paid.
- Reflections a user already saved MUST stay viewable after their free allowance runs out
  or their subscription lapses.

Rationale: the most common complaint about competing apps is a paywall around the text.
Trust depends on the Bible itself being freely readable.

### II. Closed-World Content Sourcing (NON-NEGOTIABLE)

- All Scripture and commentary text MUST come from the frozen source snapshot. The snapshot
  is stored write-once in a private S3 bucket and cached locally in `content/sources/`. Every
  file is verified against the checksums in `content/sources/manifest.json`, which is
  committed to git. No app, Lambda, pipeline job or agent fetches Bible or commentary text
  from the web at runtime.
- Model calls MUST receive only the excerpts for the section being processed and MUST NOT
  be given browsing, search or other retrieval tools.
- Adding or updating a source is a deliberate, reviewed change: a new snapshot uploaded
  under a new snapshot ID, with its checksums and retrieval date committed in the manifest. Agents MUST NOT add or refresh sources
  on their own initiative.
- Every content pack MUST record the source names, snapshot dates and checksums it was
  built from.

Rationale: fewer, fixed sources mean fewer chances for wrong or slanted content, and every
idea can be traced to a known text.

### III. Batch Generates, Live Only Compares

- Every question, key idea, context note and "views differ" note MUST be generated in the
  batch pipeline, pass the automatic quality gate (rule checks, the evidence check and a
  calibrated model grader), and ship in a content pack.
- The live model MUST only compare a user's answer with that section's stored key ideas
  and return the fields defined in `api/openapi.yaml` (covered idea IDs, a highlight phrase
  quoted from the user's answer, a short note, a contradicts-text flag). It MUST NOT
  generate questions, interpretations, verses or facts.
- Follow-up questions are the section's next-level questions from the reviewed pool, already in
  the content pack. The app unlocks the next level on the device 24 hours after the previous
  level is answered; reopening or re-reading a section never advances it. They are never
  generated or adapted live.
- The live model MUST receive the answer, the question, the stored key ideas and context,
  and never raw commentary text.
- The live note MUST pass code checks (length limit, only commentator names attached to
  matched ideas); on failure a template note is used.

Rationale: the product's promise is "grounded, not invented". Keeping generation in a
reviewed batch path is what makes that promise checkable.

### IV. Every Idea Is Attributed

- Every key idea shown in the app MUST carry at least one named commentator source taken
  from the content pack.
- Citations on the comparison card MUST be assembled by app code from pack data, never
  taken from model output.
- Content that cannot be stored or summarised under its license (for example Enduring
  Word) is link-out only.

Rationale: users must be able to see who said what; an invented citation would break trust.

### V. Offline-First Study

- Reading, navigation and the comparison card MUST work offline from cached content packs.
- When the live comparison is unavailable (offline, error, timeout, daily cap), the app MUST
  immediately show the stored key ideas as "Here's what commentators noticed", save the
  answer, and fill in the personal result later when possible.
- A failed or unavailable live check MUST NOT consume a free reflection or a re-check.

Rationale: a study habit cannot depend on signal; the factual content is already on the phone.

### VI. Reflections Belong to the User

- Answer text MUST live only on the device and in the user's own iCloud.
- The backend MAY hold answer text in memory only for the duration of a compare call. It
  MUST NOT log, persist, or send it anywhere except the comparison model. Logs, traces,
  metrics and error reports MUST be scrubbed of answer text. Result caching MUST be keyed
  by a hash of the answer, never the answer itself.
- No user accounts. Entitlements use StoreKit and per-device App Attest only.
- The app MUST tell users, before their first submission, that answers are processed by a
  third-party AI model. Reflection data is never sold or shared.

Rationale: reflections on faith are personal. The safest data is data the server never keeps.

### VII. One Content Contract, Permanent IDs

- `content/schema/section.schema.json` is the single contract for packs. A change MUST
  update the schema first, then `shared/` models, pipeline output and Swift `ContentKit`
  models in the same change, with contract tests on both sides.
- Question and key idea IDs are permanent and never reused, in any environment. Retired
  questions stay in packs, marked retired. Production pack updates are additive and
  versioned; nothing a user has answered is ever deleted. Dev is a staging environment and
  MAY be republished from scratch.
- Saved reflections MUST snapshot the question and key ideas exactly as shown, so they stay
  complete whatever later packs change.
- No pack reaches production without passing the automatic quality gate and the owner's
  explicit promotion from dev, made after reading that content in the app.

Rationale: users' saved reflections must never break, and three codebases read the same data.

### VIII. Guide, Never Judge

- The app and every prompt MUST lead with what the person noticed, never call an answer
  "wrong", never preach, and keep personal notes under 60 words in plain, warm language.
- Where commentators or traditions disagree, content MUST present the main views neutrally.
  The launch commentary set (Reformed and Wesleyan, Protestant) MUST be disclosed plainly.
- Answers that suggest distress or crisis MUST receive a caring response with support
  resources instead of a comparison.

Rationale: users must not feel graded on their faith; the app has no authority to rule
between traditions.

### IX. Bounded Live Cost

- Every live AI call MUST be bounded: minimum answer length before Submit, a per-question
  re-check limit, no call for an unchanged answer (server cache), a per-device daily cap
  enforced server-side with App Attest, and the free allowance enforced server-side.
- Over any limit, the app falls back to stored key ideas at zero AI cost.
- AI spend and abusive devices MUST be alarmed.

Rationale: a subscriber must cost cents a month to serve, even under misuse.

### X. Accessible and Token-Driven UI

- Every screen MUST support Dynamic Type, VoiceOver labels on every card and icon-only
  button, and 44pt minimum touch targets.
- Colors MUST come from DesignSystem tokens (light and dark). Prices MUST come from StoreKit.
  No hard-coded colors or prices in app code.
- `docs/design/README.md` (the "book feel" design) and `docs/design/DESIGN.md` (paywall,
  fallback rules, copy), with the screens in `docs/design/screens/`, are the UI source of truth.
  UI specs MUST link the relevant section and screen.

Rationale: a reading app is used by people of every age and eyesight; tokens keep dark mode
and future theming correct by construction.

## Technology & Platform Constraints

- **iOS app:** Swift 6 (strict concurrency), SwiftUI with Observation, SwiftData with CloudKit,
  StoreKit 2, Swift Testing. iPhone, iOS 17 minimum. Local Swift packages: DesignSystem,
  ContentKit, ReflectionKit, APIClient.
- **Backend:** Python 3.12 AWS Lambdas (`compare`, `authorizer`) behind API Gateway, AWS Lambda
  Powertools for logging, validation and tracing, Amazon Bedrock (Haiku-class model) for
  comparison, DynamoDB for operational data only (caps, cache, pipeline state, anonymous
  question stats). `api/openapi.yaml` is the only live API contract.
- **Pipeline:** Python 3.12 batch jobs, one book per run, Step Functions Standard, Bedrock
  (Sonnet-class model, batch inference where possible). Prompts are versioned files in
  `pipeline/prompts/`; outputs are keyed by book, section and prompt version, so re-runs are
  idempotent.
- **Content delivery:** versioned packs in S3 behind CloudFront; one study file per book shared
  by all translations, plus one verse-text file per translation.
- **Infrastructure:** Terraform only (modules `api`, `pipeline`, `storage`, `cdn`; envs `dev`,
  `prod`), least-privilege IAM per function. No console-only resources.
- **Python tooling:** uv workspace, ruff, mypy `--strict`, pytest.
- **Secrets:** never in the repo. No `.env` files, Terraform state or signing keys committed.

## Development Workflow & Quality Gates

- **Spec-driven:** each feature goes through Spec Kit:
  `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` →
  `/speckit-implement`. Each feature is built on its own `NNN-short-name` branch.
- **Constitution Check:** every plan MUST state how it satisfies each relevant principle.
  Any violation needs a justification in the plan's Complexity Tracking table, or a
  constitution amendment.
- **Testing:**
  - Contract tests MUST cover the pack schema (pipeline output and app decoding) and the
    compare API (backend and APIClient).
  - Business rules MUST have unit tests: free count, re-check limits, level selection,
    caching, fallbacks.
  - Prompt changes MUST be evaluated against a fixed set of sample sections before a new
    prompt version is used for publishing.
  - The model grader in the quality gate MUST be calibrated against the owner's own grades
    (at least 85% agreement on at least 30 items) before its scores gate a production
    promotion, and recalibrated whenever its prompt or model changes.
- **Gates before merge:** `make lint` and `make test` pass. `make ios-test` passes for app
  changes. Schema changes include updated models on all three sides.
- **Commits:** small, with a scope prefix (`ios:`, `backend:`, `pipeline:`, `infra:`,
  `content:`, `docs:`).
- **Content review:** every book passes the automatic quality gate and is published to dev.
  The owner reads it in the app and promotes it to production. After launch, reader feedback
  ("not helpful" flags, problem reports) drives retire-and-replace in later versions.

## Governance

- This constitution supersedes other practices. Area `CLAUDE.md` files and specs MUST NOT
  contradict it; where they do, the constitution wins until it is amended.
- Amendments are made with `/speckit-constitution`, in their own commit
  (`docs: amend constitution to vX.Y.Z`), with a Sync Impact Report and updates to any
  dependent templates or docs.
- Versioning follows semver: MAJOR removes or redefines a principle, MINOR adds a principle
  or materially expands guidance, PATCH clarifies wording.
- Reviews of every plan and PR verify compliance. `/speckit-analyze` is run before
  implementing any feature that touches content, privacy or payments.
- Runtime guidance for agents lives in the root `CLAUDE.md` and per-area `CLAUDE.md` files.

**Version**: 1.2.0 | **Ratified**: 2026-11-03 | **Last Amended**: 2026-11-10
