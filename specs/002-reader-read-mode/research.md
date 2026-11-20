# Research: Book-Feel Feed and Chapter Panel (spec 002)

Decisions for the first iOS feature. Each has the decision, why, and what else was considered.
The spec's clarifications (2026-11-20) are taken as given.

## R1. The Xcode project

**Decision**: bootstrap `ios/ThinkBible.xcodeproj` once with XcodeGen, then commit the project and
stop using the generator. The app target uses a **folder-synchronized group** (Xcode 16+), so a
Swift file added under `ios/ThinkBible/` is part of the target with no project-file edit. The two
local packages are referenced from the project. XcodeGen is installed with `brew install xcodegen`
for the bootstrap only.

**Why**: most of the code lives in `Package.swift` packages, which are plain text that agents and
reviewers can read. With a synchronized folder, the project file almost never changes after the
bootstrap, so there's no generator to keep in step with it.

**Alternatives**:
- *Keep XcodeGen's `project.yml` as the source and regenerate on every change*: two files that
  can drift, and every contributor needs XcodeGen.
- *Tuist*: more capable than one app needs, with its own toolchain.
- *Writing `project.pbxproj` by hand*: fragile and unreviewable.

## R2. Packages and what goes where

**Decision**: two local packages now.
- **DesignSystem**: the book-feel tokens (light and dark, accent Blue/Red), the type scale
  (New York serif via `Font.system(design: .serif)` / `UIFontDescriptor.SystemDesign.serif`, SF Pro
  for UI), metrics (margins, radii, 44 pt targets).
- **ContentKit**: pack models and validation, the 66-book table, the catalog, the pack store,
  bundled packs, the paginator and the feed model. No UIKit except in one place: the TextKit
  measurer lives in the app target and is injected through `VerseMeasuring`.

`ReflectionKit` and `APIClient` start in spec 003, the first feature that uses them.

**Why**: the logic that needs tests (validation, the store's swap rules, pagination, feed order)
runs under `swift test` without a simulator. Views stay in the app target, where previews work best.

## R3. Which channel a build reads (clarification 1)

**Decision**: the channel is fixed at build time by the build configuration, through an
`xcconfig` setting `CONTENT_CHANNEL` that is copied into `Info.plist`:

| Configuration | Channel | Used for |
|---|---|---|
| Debug | draft | running from Xcode |
| Beta | draft | archives uploaded for TestFlight testing |
| Release | live | archives submitted to the App Store (also testable in TestFlight) |

The bundled packs (R6) come from the same channel. A test checks that the Release configuration
says `live`.

**Why**: TestFlight and the App Store distribute the **same binary**: a build is uploaded once,
tested in TestFlight, and then submitted. So "TestFlight reads draft, App Store reads live" can't
be decided by where the app was installed; the packs bundled inside it were chosen when it was
built. Separate Beta and Release archives give exactly the clarified behavior: what testers get
for a review round is a Beta build, and what ships is a Release build.

**Alternatives**:
- *Detect TestFlight at run time* (StoreKit's `AppTransaction.environment` is `sandbox` in
  TestFlight): it can't change which packs were bundled, it may need the network on first launch,
  and a mistake would show draft content to App Store users.
- *One configuration with a hidden switch*: rejected in clarification 1.

## R4. Page text: TextKit 2

**Decision**: `PageTextView`, a `UIViewRepresentable` around a non-editable, non-scrolling
`UITextView` using TextKit 2 (`NSTextLayoutManager`). It is built from an `NSAttributedString`:
- Scripture in New York at the Dynamic Type size for the Text size setting, line height 1.6,
  `.justified` alignment, `usesDefaultHyphenation = true`, old-style figures (font feature
  "number case: lower case");
- verse numbers as SF 10 bold, rubric color, raised with `baselineOffset` (no number on the
  drop-cap verse);
- the drop cap as a separate label, 2 lines deep, with an exclusion path on the text container
  so the first lines wrap around it; leading quote marks are stripped before taking the letter,
  and the accessibility label carries the whole first word;
- justification turns off at the largest accessibility sizes (spec edge case).

**Why**: SwiftUI `Text` can't justify, hyphenate or wrap around a floating drop cap
(`docs/design/CLAUDE_CODE_PROMPT.md`). TextKit 2 is the current UIKit text system and handles
exclusion paths.

**Alternative**: Core Text drawing: full control, but no selection, VoiceOver or Dynamic Type
for free.

## R5. Pagination (FR-006, SC-004)

**Decision**: a pure function in ContentKit:

```text
paginate(verses, firstPage: heading + drop cap, measure: VerseMeasuring, pageHeight) -> [Page]
```

It adds verses to a page while the measured height of the page's text fits `pageHeight`. A verse
that doesn't fit starts the next page. A verse taller than a whole page gets a page to itself and
that page grows (spec edge case). Measurement is a protocol: the app's implementation lays out the
same attributed string as `PageTextView` at the card's text width, and tests use a fake that
returns heights from a table.

- **Page height**: the feed's visible height minus the card header, action row and an allowance
  for the question footer, with a minimum of 300 pt (design: min height 300). On the mockup's
  screen this leaves the first page, the action row and the question visible together. The
  allowance is tuned against the screenshots.
- **Caching**: results are cached per (section, translation, text size, width), so scrolling never
  re-measures.
- **Re-split**: a change of text size or translation recomputes the pages, and the card shows the
  page holding the first verse that was on screen (spec US1-5 and edge case).

**Tests**: with the fake measurer, every verse appears exactly once across a section's pages, in
order, and no page breaks inside a verse; with the real measurer, the same holds for every Mark
section at every text size (SC-004; runs when the bundled packs are present).

## R6. Bundled packs (clarification 5)

**Decision**: `make ios-packs CHANNEL=draft|live` runs `ios/scripts/fetch_packs.py`. It
downloads the channel's `index.json` and every listed file, checks each file's sha256 and size
against the index, and writes them to `ios/ThinkBible/Resources/Packs/` (gitignored) in the same
layout as the CDN. An Xcode build phase fails the build with a clear message if that folder is
missing or its channel doesn't match `CONTENT_CHANNEL`, so a build can't ship with no books or the
wrong channel's books.

At run time `BundledPacks` reads that folder as a read-only pack source.

**Why**:
- Published packs live only in S3 (root `CLAUDE.md`), so they can't be committed.
- Downloading in an Xcode build phase would make every build depend on the network and conflicts
  with Xcode's script sandboxing.
- Mark is 178 KB compressed; the whole Bible would add about 15–20 MB.

**Alternative**: bundle only the launch book (rejected in clarification 5).

## R7. The pack store and updates (FR-018, FR-019, clarification 4)

**Decision**: `PackStore` keeps each book's packs under
`Application Support/Packs/{channel}/{book}/{version}/` and a small `active.json` per channel
naming each book's active version. On every launch, before the feed is built, it **activates**
any downloaded version that is newer than the active one and fully verified. While the app runs,
it only downloads.

A download goes to a temporary folder. Each file's sha256 and size must match the catalog, then
all files must decode and validate (R8). Only then is the folder moved into place (one atomic
rename) and marked **ready**. Anything that fails is deleted and logged; the good pack stays.

The pack a book reads is the newest of: the active downloaded version and the bundled version.
Old versions are deleted one launch after they stop being active.

**When it checks**: on launch and on returning to the foreground, at most once an hour, with one
GET of `index.json` (the CDN caches it for 5 minutes, `contracts/cdn-layout.md`).

**Why**: switching at launch means the open feed never changes under the reader (clarification 4),
and the swap is a single file write, so a crash can't leave a half-switched book.

## R8. Validating packs in Swift (FR-019, constitution VII)

**Decision**: strict `Codable` models that mirror `content/schema/`:
- unknown keys are rejected (a custom decoding check, since `Codable` ignores extra keys);
- enums for closed sets (commentators, status, idea kind);
- after decoding, a `validate()` pass with the schema's own limits (lengths, patterns, ID
  formats, a question ending in "?"), the single-object rules the Python models enforce (`agreed`
  matches sources, `retiredIn` present when retired, ranges not backwards), and the cross-field
  rules 1–9 in `specs/001-content-pack-pipeline/data-model.md` ("Cross-field rules", implemented
  in `thinkbible_core/rules.py`), including at most 3 active questions and no more than the
  section's active key ideas (`max_questions`).

No JSON Schema library is added.

**Tests**: every file in `content/schema/fixtures/valid/` decodes and validates, and every file in
`fixtures/invalid/` is rejected, matching the Python side's contract tests.

**Alternative**: a JSON Schema validator package: a third-party dependency for checks the models
must express anyway to decode.

## R9. The feed (FR-001, FR-002, FR-002a)

**Decision**: `ReaderFeedView` is a SwiftUI `ScrollView` with a `LazyVStack` of feed items from
ContentKit's `FeedModel`, which produces, per book: the "About <Book>" card when the pack has an
introduction, then for each chapter a title row, one card per section and an end-of-chapter page,
then an end-of-book page. The model appends the next published book's items when the reader nears
the end (clarification 3), and the end-of-book page offers the book list when no later book is
published.

- **Position and jumps**: `scrollPosition(id:anchor: .top)` (iOS 17) tracks the item at the top
  and scrolls to a section by ID for resume, panel rows and later deep links.
- **Header pill**: shows the chapter of the item at the top.
- **Horizontal pages**: a horizontal `ScrollView` with `.scrollTargetBehavior(.paging)` inside each
  card; dots and an "n/N" counter.
- **Performance**: cards are lazily created; pagination is cached (R5); page text views are
  plain, non-scrolling `UITextView`s. If Instruments shows hitches, the fallback is precomputing
  a chapter's pagination when the chapter title row appears.

## R10. The chapter panel and book list (FR-011–FR-015)

**Decision**: an overlay anchored under the header, with a dimmed backdrop that closes it. One
`ScrollView` holds either the Chapters view or the Books view:
- the chapter grid is an 8-column `LazyVGrid`;
- the Books view is a `LazyVStack(pinnedViews: .sectionHeaders)` with Old and New Testament
  headers, scrolled to the current book with `ScrollViewReader`.

The 66 books, their testaments and chapter counts come from ContentKit's book table (for
unpublished books, which have no pack); whether a book is published comes only from the catalog.
Section status pills (spec 005) show nothing yet.

## R11. Reading position (FR-016)

**Decision**: a `ReadingPositionStore` protocol with a `UserDefaults` implementation storing
`{book, sectionId, updatedAt}`, written when the top card changes (debounced). Launch opens that
section, or the "About Mark" post when there is none (Mark 1:1–8 if Mark has no
introduction). If a saved section ID is missing from a newer pack, the
feed opens the section whose verse range contains the saved section's first verse (spec edge
case). Spec 005 replaces the implementation with SwiftData and CloudKit sync behind the same
protocol.

## R12. What the card shows before specs 003–006

- **Question footer**: the section's first active question as the "ThinkBible · question on
  verse N" comment, read-only (no composer). For "no prompt" sections, the context note (FR-008).
  This lets the owner read the questions in the app, which promoting a book needs.
- **Save**: hidden until spec 005, so there is no button that does nothing.
- **Avatar**: a person symbol in the rubric circle, since there are no accounts; no streak badge
  until spec 005. It opens a placeholder "You & settings" sheet until spec 006.
- **Settings the reader follows** (translation, text size, justify, accent, verse numbers): a
  `ReaderSettings` model with the design's defaults (BSB, the system text size, justify on, Blue,
  numbers on), stored in `UserDefaults`. Its screen is spec 006. For testing the KJV before then,
  Debug builds accept launch arguments (`-translation kjv`).

## R13. Testing and the merge gate

**Decision**:
- **Packages**: Swift Testing, `swift test` in each package (fast, no simulator).
- **App**: a test target on the simulator for resume, jumping from the panel, the end-of-book
  flow and launching with no network (the app's channel client is replaced with one that fails).
- **Visual**: SwiftUI previews for every drawn state, compared by eye with `screens/01`, `02`,
  `07`, `08`, `09`; differences listed in the PR.
- `make ios-test` runs both (package tests, then `xcodebuild test` on `iPhone 16 Pro`) and joins
  the merge gate for app changes. GitHub's Python CI is unchanged; a macOS CI job is left for
  later (macOS runner minutes cost 10 times as much).

## R14. Dark mode and accessibility

**Decision**: DesignSystem defines every book-feel token with the proposed dark values from
`docs/design/README.md`. A DesignSystem test computes the contrast of each text/background pair
used by the feed and fails under 4.5:1 in either mode; values that fail are adjusted and recorded
in `docs/design/README.md`. VoiceOver follows FR-021: chapter tiles read "Mark chapter 1", section
rows read the range, title and state, the drop cap is decorative with the full first word read,
page dots are hidden and the counter reads "Page 1 of 2".

## R15. iPhone and iPad sizes (constitution v1.4.0)

**Decision**: one adaptive layout, no size-class branches:
- **Reading column**: the feed, cards and chapter panel are limited to 680 pt wide and centered on
  the `desk` background; the header spans the window. 680 pt keeps Scripture lines at about 70–80
  characters at the default size, a comfortable book measure.
- **Range**: 320 pt (iPad Slide Over and the narrowest Split View pane) to 1376 pt (iPad Pro 13"
  landscape); 667 pt the shortest height (iPhone SE). At 320 pt the card's side margins stay 12 pt
  and the page padding shrinks from 30 to 18 so a line still holds about 30 characters.
- **Orientation**: iPhone portrait only (a reading feed); iPad every orientation, which Split View
  and Slide Over require.
- **Size changes**: pagination is keyed by width (research R5), so a rotation or a Split View
  resize re-splits pages and the feed keeps the same section and verse on screen.
- **Mac**: nothing to build. After launch, "Make available on Mac" in App Store Connect offers the
  iPad app on Apple-silicon Macs.

**Why**: a centered column is how a printed page sits on a desk, which is the book-feel design's
idea; a separate iPad layout (sidebar, two columns) would be a second design to build and test.

**Testing**: previews at 320, 375, 440 pt and on an iPad in both orientations; the all-Mark
pagination test at 320, 393 and 680 pt; app tests also run on the `iPad Pro 13-inch (M4)`
simulator.
