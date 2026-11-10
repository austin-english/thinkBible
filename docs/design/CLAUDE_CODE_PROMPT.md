# Prompt for Claude Code

Paste this into Claude Code from the repo root after unzipping.

---

We're replacing the iOS reader UI with the "book-feel" design in `docs/design/book-feel/`. Read `README.md` there and look at every PNG in `screens/` before planning. The `source/*.dc.html` files are design-tool sources: use them only to look up exact values and copy, and don't port their code.

Scope: **iOS only.** No backend, pipeline, infra or schema changes. If something in the design seems to need one, stop and tell me instead of changing it.

1. **Check the contracts first.**
   - Confirm `api/openapi.yaml` and `content/schema/section.schema.json` already provide everything the design shows:
     - section title
     - verse range
     - question verse scope
     - the key ideas: title, body, sources and scope for each
     - the evaluation result: which ideas were caught, the short reply note, and the phrase in the user's answer that matched
   - Report anything missing. Don't add it. For a missing field, the UI should degrade gracefully: no highlight if there's no matched phrase, and a generic note if there's no reply note.
2. **Plan.** Update `docs/design/DESIGN.md`: replace the Home/Reader sections with a short summary that points to `book-feel/README.md`, and keep everything else. Then write a plan using Spec Kit in this repo: views, models, and the order you'll build them. Wait for my OK.
3. **Build.** Suggested pieces:
   - `ReaderFeedView`: a `ScrollView` with a `LazyVStack` of `SectionPageCard`, flowing through chapters endlessly, plus the fixed `ReaderHeader`.
   - `PassagePager`: horizontal paging (`.scrollTargetBehavior(.paging)`), with pages split between verses by measured height.
   - `PageTextView`: a TextKit 2 `UIViewRepresentable` for justified, hyphenated serif text, the drop cap (exclusion path), superscript rubric verse numbers and the question-scope tint. SwiftUI `Text` can't do justification plus a floating drop cap.
   - `QuestionFooter`, `AnswerComposer`, `ReflectionThread`, all inline in the card.
   - `ChapterPanel`: a top drop-down overlay with a single scroll. Chapters view and Books view (`LazyVStack(pinnedViews: .sectionHeaders)` + `ScrollViewReader` to the current book).
   - `SectionProgress` SwiftData model and the derived counts described in the README.
   - `YouView` for You & settings.
   - `UnlockScheduler`: the 24-hour next-level unlock from the README. It's local notifications only, one pending per chapter (cancel and reschedule on each answer), folded into the daily reminder when that's on. It handles the in-card permission prompt and the deep link from a tapped notification to the first unlocked section.
   - Tokens in one `Theme` with light values from the README and the proposed dark values, with Accent color (Blue/Red) as a user setting.
4. **Keep existing rules:**
   - 15-character minimum
   - 3 free reflections, then the paywall on Post
   - 2 re-checks
   - Level 2/3 questions **unlock 24 hours after the previous level is answered**, not on re-read. This replaces the old re-read rule.
   - hidden alternates via "Not a helpful question?" in the `…` menu
   - translation only in settings
5. **Verify.**
   - Build and run the app.
   - Add SwiftUI previews for every state in `screens/`.
   - Add unit tests for:
     - pagination: never splits a verse
     - progress derivation: read never overrides reflected; chapter fractions
     - unlock logic: both gates, one notification per chapter, rescheduling on each new answer, nothing after Level 3. Inject a clock so tests don't depend on real time.
   - Compare simulator screenshots against the PNGs and list any differences.
