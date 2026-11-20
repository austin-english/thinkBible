# Implementation Plan: Book-Feel Feed and Chapter Panel

**Branch**: `002-reader-read-mode` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-reader-read-mode/spec.md` (clarified 2026-11-20)

## Summary

The first iOS feature, and the first code in `ios/`. The app opens on one vertical feed of page
cards: each section of a book is a card set like a book page (italic heading, drop cap, justified
and hyphenated serif text, rubric verse numbers, folio). Long passages split between verses into
pages swiped sideways. The feed runs chapter to chapter and on into the next published book. A
"Mark 1 ▾" pill opens the chapter panel (chapter grid, sections, the 66-book list). The app
reopens where the reader left off and reads fully offline.

Content comes only from the content packs spec 001 publishes to the CDN: there is **no backend
work** in this feature. Every book on the build's channel is bundled into the app at build time,
updates download in the background and take effect at the next launch, and the build fixes the
channel (draft for Debug and TestFlight builds, live for App Store builds).

Technical approach (research.md):
- an Xcode project bootstrapped once with XcodeGen, using a folder-synchronized app target, with
  the logic in two local Swift packages: **DesignSystem** (tokens, type) and **ContentKit** (pack
  models and validation, catalog, pack store, bundled packs, pagination, feed model);
- pages drawn by a TextKit 2 view (justification around a floating drop cap), paginated by a pure
  function over measured verse heights, so "never split a verse" is unit-tested;
- a SwiftUI `ScrollView` + `LazyVStack` feed with `scrollPosition(id:)` for resume and jumps.

The question footer shows the section's current question as read-only text (or the context note
for "no prompt" sections). The composer, the reply thread and the compare API are spec 003.

## Technical Context

**Language/Version**: Swift 6 language mode (strict concurrency), Xcode 27.2, Swift 6.4 toolchain

**Primary Dependencies**: SwiftUI with Observation, UIKit TextKit 2 (page text), Foundation
URLSession and CryptoKit (pack downloads and sha256). No third-party packages. XcodeGen (one-time
project bootstrap, a developer tool, not a dependency of the app)

**Storage**: packs as files in Application Support (`Packs/{channel}/…`) plus the bundled packs in
the app bundle; small preferences and the reading position in `UserDefaults`. No SwiftData in
this feature (it arrives with reflections and progress in specs 003 and 005)

**Testing**: Swift Testing in both packages (`swift test` and the Xcode test plan); app-level
tests for resume and jumps; contract tests decode every fixture in `content/schema/fixtures/`
(valid must decode, every invalid must be rejected); a pagination test over every Mark section
at every text size when the bundled packs are present

**Target Platform**: iPhone and iPad, iOS 17 minimum (constitution v1.4.0), one adaptive layout
from 320 pt wide to iPad Pro landscape with a centered reading column up to 680 pt (research
R15). Mac later via "Designed for iPad", with no Mac-specific work. Bundle ID
`com.austinenglish.thinkbible` (registered by the owner), Apple team `LM5PGHSW42`

**Project Type**: mobile app (iOS) reading a static CDN contract

**Performance Goals**: cold launch to the saved section in under 2 s (SC-001); scrolling and
paging Mark 1 without hitches: Instruments "Hitches" hitch-time ratio under 5 ms/s on a physical
iPhone 16 or older (SC-002)

**Constraints**: works offline from first launch (bundled packs); never splits or drops a verse
(SC-004); no colors outside DesignSystem tokens; Dynamic Type at every size; 44 pt targets; no
paywall or sign-in anywhere in the reading path

**Scale/Scope**: 2 books published today (Mark 100 sections, Philippians 14), up to 66 books and
about 3,000 sections later; about 200 KB compressed per book; about 10 views

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan satisfies it |
|---|---|
| I. Scripture never paywalled | The reading path (feed, panel, book list, Send) has no paywall, sign-in or count. There is no StoreKit code in this feature. A test asserts the reading views never reference entitlement state |
| II. Closed-world content | The app shows only pack content from the project's CDN and the bundle. It fetches no commentary or Bible text from anywhere else |
| III. Batch generates, live only compares | No live AI in this feature. Questions are shown exactly as the pack has them |
| IV. Every idea attributed | The "About Mark" post shows its commentators and their own words, from the pack only |
| V. Offline-first | Every published book is bundled; downloads are verified (sha256 and validation) before use and switch only at launch; a failed or invalid download never replaces a good pack; a missing or forbidden catalog keeps the cached and bundled books |
| VI. Reflections belong to the user | No answers exist yet. Reading position stays on the device |
| VII. One content contract | ContentKit's Swift models decode `content/schema/` exactly, and reject every invalid fixture; the contract tests run on the shared fixtures. IDs are used as permanent keys (position, cache) |
| VIII. Guide, never judge | No feedback copy in this feature |
| IX. Bounded live cost | No live calls. Catalog checks are one small cached GET at launch and on returning to the foreground |
| X. Accessible, token-driven UI | Book-feel tokens with light and dark values in DesignSystem; Dynamic Type; VoiceOver labels per spec FR-021; 44 pt targets; contrast checked in both modes. The UI follows `docs/design/README.md` and `screens/01`, `02`, `07`–`09` |
| Workflow: tests and gates | `make ios-test` added to the merge gate for app changes; contract tests on both sides of the pack schema |

**Result: pass.** One point needs care, recorded in research R3: App Store and TestFlight builds
of the same archive are one binary, so the channel can't follow "where it was installed from".
It follows the build configuration instead (Debug and Beta read draft, Release reads live), which
meets the clarified spec and the constitution's channel rule.

Post-design re-check (after Phase 1): still pass. The contracts add no network endpoint, the data
model stores no personal text, and ContentKit's public API keeps the pack contract the only data
source.

## Project Structure

### Documentation (this feature)

```text
specs/002-reader-read-mode/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R14
├── data-model.md        # Phase 1: Swift models, feed items, stores, state transitions
├── quickstart.md        # Phase 1: how to build, run and verify the feature
├── contracts/
│   ├── cdn-consumption.md   # how the app reads the channel (URLs, checks, failures)
│   └── app-interfaces.md    # ContentKit's public API and the entry points later specs use
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
ios/
├── CLAUDE.md                     # iOS rules for agents (new)
├── ThinkBible.xcodeproj          # bootstrapped once with XcodeGen, then committed
├── Config/
│   ├── Debug.xcconfig            # CONTENT_CHANNEL = draft
│   ├── Beta.xcconfig             # CONTENT_CHANNEL = draft (TestFlight uploads)
│   └── Release.xcconfig          # CONTENT_CHANNEL = live (App Store submissions)
├── ThinkBible/                   # app target (folder-synchronized: new files need no project edit)
│   ├── App/                      # ThinkBibleApp, AppModel (launch, pack activation, position)
│   ├── Feed/                     # ReaderHeader, ReaderFeedView, feed rows
│   ├── Card/                     # SectionPageCard, PassagePager, PageTextView (TextKit 2),
│   │                             # QuestionFooter (read-only), ActionRow, AboutBookCard
│   ├── Panel/                    # ChapterPanel, ChaptersView, BooksView
│   ├── Resources/                # Assets.xcassets; Packs/ is generated (gitignored)
│   └── Previews/                 # preview fixtures for every drawn state
├── ThinkBibleTests/              # app-level tests: resume, jump, end-of-book, offline launch
├── Packages/
│   ├── DesignSystem/             # tokens (light/dark, accent Blue/Red), type scale, metrics
│   │   ├── Sources/DesignSystem/
│   │   └── Tests/DesignSystemTests/   # every token has light and dark; contrast ≥ 4.5:1
│   └── ContentKit/
│       ├── Sources/ContentKit/
│       │   ├── Models/           # StudyPack, Section, KeyIdea, Question, VerseText, PackIndex
│       │   ├── Validation/       # strict decoding + the contract's cross-field rules
│       │   ├── Books/            # the 66 books: code, name, testament, chapter count
│       │   ├── Store/            # PackStore, Catalog, BundledPacks, ChannelClient
│       │   ├── Pagination/       # Paginator (pure), VerseMeasuring protocol
│       │   └── Feed/             # FeedModel: items across chapters and books
│       └── Tests/ContentKitTests/     # contract fixtures, store, pagination, feed order
└── scripts/
    └── fetch_packs.py            # build step: download the channel's packs into Resources/Packs
```

`ReflectionKit` and `APIClient` (named by the constitution) are created by spec 003, which is the
first feature that needs them.

**Structure Decision**: a thin app target for views and wiring, with the testable logic in local
Swift packages so most tests run with `swift test` in seconds and agents edit plain Swift files
and `Package.swift`, not the project file. The Makefile gains `ios-packs` (fetch the channel's
packs for bundling) and `ios-project` is not needed after the bootstrap. `make ios-test`'s
simulator changes to one that exists (`iPhone 16 Pro`), and it also runs the app tests on
`iPad Pro 13-inch (M4)`.

## Complexity Tracking

No constitution violations.

| Decision | Why needed | Simpler alternative rejected because |
|---|---|---|
| A TextKit 2 `UIViewRepresentable` for page text | Justified, hyphenated text flowing around a 2-line drop cap with superscript verse numbers | SwiftUI `Text` can't justify or wrap around a floating drop cap |
| A build step that downloads packs before archiving | Every published book bundled from the build's channel (clarification 5) | Committing packs to git breaks the rule that published packs live only in S3 |
| Three build configurations (Debug, Beta, Release) | TestFlight and App Store builds are the same binary, so the channel must be fixed at archive time | Detecting TestFlight at run time can't change which packs were bundled, and fails offline |
