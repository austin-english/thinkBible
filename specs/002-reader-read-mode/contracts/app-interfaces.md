# Contract: the interfaces spec 002 gives later features

Specs 003–007 build on the reader. These are the seams they use, so they can be built without
changing spec 002's code. Swift signatures are indicative; names and shapes are what matter.

## ContentKit (public API)

```swift
// The content the app reads, after the launch-time activation (data-model.md, PackStore).
public protocol ContentLibrary: Sendable {
    var channel: ContentChannel { get }                 // .draft or .live
    func publishedBooks() -> [BookCatalogEntry]         // from the catalog, Bible order
    func studyPack(for book: String) async throws -> StudyPack
    func verses(for book: String, translation: TranslationID) async throws -> VerseText
    func section(id: String) async throws -> Section?   // by permanent ID
}

// Background updates (FR-019). Never changes what ContentLibrary returns until the next launch.
public protocol PackUpdater: Sendable {
    func checkForUpdates() async                        // fetch index, download, verify, mark ready
    func activateReadyVersions() throws                 // called once at launch, before the feed
}

// Pagination (research R5).
public protocol VerseMeasuring {
    func height(of verses: ClosedRange<Int>, in section: Section, firstPage: Bool) -> CGFloat
}
public func paginate(section: Section, verses: VerseText, measure: VerseMeasuring,
                     pageHeight: CGFloat) -> [Page]

// The feed's items, across chapters and books (data-model.md, FeedItem).
@Observable public final class FeedModel { /* items, appendNextBook(), index(of:) */ }

// The 66 books.
public enum Books { public static let all: [BookCatalogEntry] }
```

Contract tests: every `content/schema/fixtures/valid/*` decodes and validates; every
`fixtures/invalid/*` is rejected. They run with `swift test` in `ios/Packages/ContentKit`.

## Opening a section (FR-016, spec US3)

One entry point opens the feed with a section's card at the top. Spec 004 uses it for unlock
notifications, spec 005 for saved passages, and the chapter panel uses it now.

```swift
@MainActor protocol SectionOpening {
    func open(sectionId: String, page: Int?)   // scrolls the feed; loads the book if needed
}
```

URL form, for notifications and links: `thinkbible://section/{sectionId}` (for example
`thinkbible://section/mrk-1-21`). An unknown ID opens the nearest section by verse range, or the
book's first section.

## The card's footer slot (FR-004, FR-008)

`SectionPageCard` takes a footer view. Spec 002 passes a read-only `QuestionFooter` (the first
active question, or the context note for "no prompt" sections). Spec 003 replaces it with the
composer and reply thread without changing the card.

```swift
SectionPageCard(section: section, pages: pages, footer: { QuestionFooter(section: section) })
```

The card also exposes the hooks later specs fill:
- the action row's Save button (spec 005), hidden until a `SaveAction` is provided;
- the header's `…` button (US6, deferred), hidden until a menu is provided;
- a verse tint range for the question being composed (spec 003), drawn by `PageTextView`.

## Reader settings keys (spec 006 adds the screen)

`UserDefaults` keys, owned by spec 002 and read by spec 006's settings screen:
`reader.translation`, `reader.textSize`, `reader.justify`, `reader.accent`,
`reader.verseNumbers`, `reader.showQuestions`. The reading position uses `reader.position`
until spec 005 moves it to SwiftData behind `ReadingPositionStore`.
