# Data model: Book-Feel Feed and Chapter Panel (spec 002)

Three kinds of data:
1. **Pack models**: the content contract decoded into Swift.
2. **Device state**: the catalog, the pack store, reading position and settings.
3. **View models**: the feed items and pages derived from the other two.

Nothing here holds personal text: answers arrive in spec 003.

## 1. Pack models (ContentKit, mirror `content/schema/`)

Field for field with the JSON Schemas, in Swift naming. They are decoded strictly (unknown keys
rejected) and validated after decoding (research R8). The schemas are the authority. This lists
what the feature uses.

| Model | Fields used by spec 002 | Notes |
|---|---|---|
| `PackIndex` | `formatVersion`, `generatedAt`, `books: [IndexEntry]` | the channel's catalog |
| `IndexEntry` | `book: BookRef`, `latest: PackVersion`, `study: PackFile`, `verses: [TranslationID: PackFile]`, `minAppFormatVersion?` | a book is **published** iff it has an entry |
| `PackFile` | `path`, `sha256`, `bytes` | `path` is relative to the channel root |
| `StudyPack` | `book`, `packVersion`, `introduction?`, `translations`, `sources`, `sections` | `build` is decoded but unused |
| `BookIntroduction` | `text`, `sources: [CommentatorID]`, `quotes: [Quote]` | the "About <Book>" post (FR-002a) |
| `Section` | `id`, `ref`, `chapter`, `verseStart`, `verseEnd`, `title`, `noPrompt`, `context`, `manuscriptNotes`, `keyIdeas`, `questions` | `viewsDiffer` and key ideas are decoded for spec 003 |
| `Question` | `id`, `verseStart`, `verseEnd`, `text`, `textByTranslation?`, `targets`, `status` | shown read-only: the first `active` one |
| `KeyIdea` | decoded in full | used from spec 003 |
| `ManuscriptNote` | `chapter`, `verseStart`, `verseEnd`, `text` | shown where a translation lacks a verse (FR-017) |
| `VerseText` | `book`, `translation {id, name, abbreviation}`, `packVersion`, `chapters`, `omittedVerses` | one per translation |
| `Chapter` | `number`, `title?`, `verses` | `title`: a psalm's title, shown before verse 1 |
| `Verse` | `number`, `text`, `paragraphStart?`, `lines?` | poetry lines with indent 0–4 |

**Closed sets as enums**: `CommentatorID` (`matthew-henry`, `jamieson-fausset-brown`,
`adam-clarke`), `ItemStatus` (`active`, `retired`), `IdeaKind` (`key`, `background`).
`TranslationID` and `PackVersion` are validated strings (`^[a-z][a-z0-9_]{1,15}$`, `x.y.z`).
`PackVersion` is `Comparable` by number.

**Validation** (after decoding): every schema limit, plus the single-object and cross-field rules
1–9 from `specs/001-content-pack-pipeline/data-model.md`. A pack that fails is never used.

**Display text for the reader's translation**: a question's text is
`textByTranslation[translation] ?? text`. A translation's verses come from its `VerseText`, and a
verse in `omittedVerses` is skipped with the section's manuscript note shown at that point.

## 2. Device state

### BookCatalogEntry (ContentKit, static: the 66 books)

| Field | Type | Notes |
|---|---|---|
| `code` | String | USFM, e.g. `MRK` (matches `thinkbible_core.ids`) |
| `name` | String | "Mark" |
| `shortName` | String | the avatar's letters, "Mk" |
| `testament` | `.old` / `.new` | for the Books view headers |
| `chapterCount` | Int | for the chapter grid of unpublished books |
| `order` | Int | 1–66, Bible order (the feed continues in this order) |

Tests: 66 books, 39 Old Testament, 27 New, 1,189 chapters in total, codes unique.

### Catalog (ContentKit)

The channel's `PackIndex`, as last fetched, with the time it was fetched. It's stored as
`Packs/{channel}/index.json`. Before the first fetch, the bundled index stands in.

| State | Meaning |
|---|---|
| `bundled` | no fetch has succeeded; the bundled `index.json` is used |
| `fresh(fetchedAt)` | the last fetch succeeded |
| `stale(fetchedAt, error)` | the last fetch failed (offline, 403, 404, 5xx, invalid); the previous catalog is kept |

A 403 or 404 means "nothing published on this channel yet", not an error to show. It keeps the
previous catalog, and bundled books stay readable (spec edge case).

### PackStore (ContentKit)

On disk: `Application Support/Packs/{channel}/{book}/{version}/{study.json, verses/*.json}` and
`Packs/{channel}/active.json` (`{book: version}`).

Each downloaded version moves through these states:

```text
            download + sha256 + decode + validate OK
 (absent) ──────────────────────────────────────────▶ ready ──(next launch)──▶ active
    │                                                   │                        │
    │ any check fails: delete, keep the good pack       │ newer version ready     │ superseded
    ▼                                                   ▼                        ▼
 (absent)                                           (replaced)            retired → deleted
                                                                          one launch later
```

- **Activation happens only at launch** (clarification 4): before the feed is built, each book's
  newest `ready` version becomes `active` with one atomic write of `active.json`.
- **Which pack a book reads**: the newer of its active downloaded version and its bundled version.
- **Rule**: a version is `ready` only after every file matched the catalog's sha256 and size and
  the whole pack decoded and validated. A partial or invalid download is never visible.
- A version whose `minAppFormatVersion` is above the app's supported format is not downloaded.

### BundledPacks (ContentKit)

A read-only pack source over `Resources/Packs/{channel}/` in the app bundle, with its own
`index.json`, written by `make ios-packs` (research R6). Its channel must equal the build's
`CONTENT_CHANNEL`, which the build checks.

### ReadingPosition (app, `UserDefaults` until spec 005)

| Field | Type | Notes |
|---|---|---|
| `book` | String | USFM code |
| `sectionId` | String | a permanent section ID, e.g. `mrk-1-21` |
| `updatedAt` | Date | |

- Written when the card at the top of the feed changes, debounced by about a second.
- Missing: open the launch book's first item: `mrk-intro` ("About Mark"), or `mrk-1-1` when the
  pack has no introduction.
- The section ID is missing from the book's current pack: open the section whose range contains
  the saved section's first verse, which is parsed from the ID (`{book}-{chapter}-{startVerse}`).

### ReaderSettings (app, `UserDefaults`; the screen is spec 006)

| Setting | Default | Effect in this feature |
|---|---|---|
| `translation` | `bsb` (the pack's first translation) | verse text and question wording |
| `textSize` | the system Dynamic Type size | type sizes; re-pagination |
| `justify` | on (off at the largest accessibility sizes) | page alignment |
| `accent` | Blue | `rubric` color |
| `verseNumbers` | on | verse numbers shown |
| `showQuestions` | on | question footers shown (spec 006 adds the switch) |

## 3. View models

### FeedItem (ContentKit `FeedModel`)

The feed is an ordered list of items, each with a stable `id` used by `scrollPosition` (`{book}` is the lowercase book code, as in section IDs):

| Item | id | Shown as |
|---|---|---|
| `bookIntro(book)` | `"{book}-intro"` | "About <Book>" card (FR-002a), only when the pack has an introduction |
| `chapterTitle(book, chapter, sectionCount)` | `"{book}-{chapter}-title"` | "Mark 1 · 9 sections" |
| `section(Section)` | the section ID | a page card |
| `chapterEnd(book, chapter, next)` | `"{book}-{chapter}-end"` | "End of Mark 1 · Keep scrolling for Mark 2" |
| `bookEnd(book, nextBook?)` | `"{book}-end"` | "End of Mark · Keep scrolling for Philippians", or "End of Mark" with "Choose a book" when `nextBook` is nil |

Order: per book, `bookIntro?`, then for each chapter `chapterTitle`, its `section`s and
`chapterEnd` (the last chapter's end is `bookEnd` instead). After `bookEnd`, the next **published**
book in `order` follows (unpublished books are skipped). Chapters with no sections in the pack
(none in published books today) are listed in the panel with "Start <Book> <n> at verse 1 ›".

### Page (ContentKit `Paginator` output)

| Field | Type | Notes |
|---|---|---|
| `index` | Int | 0-based |
| `verses` | ClosedRange of verse numbers | never splits a verse |
| `isFirst` | Bool | page 1 carries the heading and drop cap |
| `folio` | String | "1:1–4" |
| `oversized` | Bool | a single verse taller than a page; the page grows |

Invariant (tested): concatenating every page's verses gives the section's verses for the chosen
translation exactly once, in order.

Cache key: `(sectionId, translation, textSize, contentWidth, pageHeight)`.

### PanelState (app)

`closed` | `chapters(book, selectedChapter)` | `books(scrolledTo: book)`. Tapping a section row
closes the panel and scrolls the feed to that section. Picking a book goes to `chapters(book, 1)`,
or to the book's reading position if it has one.
