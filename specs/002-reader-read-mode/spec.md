# Feature Specification: Book-Feel Feed and Chapter Panel

**Feature Branch**: `002-reader-read-mode` (folder name kept from the earlier "Reader and Read mode"
draft)

**Created**: 2026-11-03

**Updated**: 2026-11-10, rewritten for the "book feel" design. It replaces Home, the sticky-header
chapter reader and the Study / Read switch.

**Status**: Draft

**Input**: User description: "Book-feel feed and chapter panel (brief spec 3): one vertical feed
of page cards, one card per passage section, flowing through a book chapter after chapter. Each
card is set like a book page (italic heading, drop cap, justified serif text, superscript verse
numbers, verse-range folio), and long passages split between verses into pages you swipe
sideways. A fixed header holds the wordmark, a 'Mark 1 ▾' chapter pill and the avatar. The pill
drops down a chapter panel that is the table of contents: chapter grid, the chapter's sections,
and a book list of all 66 books. Content packs are downloaded per book and cached for offline use.
Reading is always free."

**References**: [docs/design/README.md](../../docs/design/README.md) (Header, Feed, Card, Chapter
panel, Send, Accessibility); screens
[01-feed.png](../../docs/design/screens/01-feed.png),
[02-page-2.png](../../docs/design/screens/02-page-2.png),
[07-chapter-picker.png](../../docs/design/screens/07-chapter-picker.png),
[08-book-list.png](../../docs/design/screens/08-book-list.png),
[09-genesis.png](../../docs/design/screens/09-genesis.png);
[docs/design/DESIGN.md](../../docs/design/DESIGN.md) (States with no mockup, Design tokens);
constitution principles I, V, X. Depends on spec 001 (pack format and a published Mark pack, or a
fixture pack).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read a book as a feed of pages (Priority: P1)

A reader opens the app and lands where they left off in Mark. The fixed header shows the
ThinkBible wordmark, a dark "Mark 1 ▾" pill and their avatar. Below it, "Mark 1 · 9 sections",
then one cream page card per section. Each card has a header row (a "Mk" book avatar, "Mark
1:1–8", the section title, a `…` button), then the passage set as a book page: an italic heading
with a short rule under it, a drop cap on the first word, justified serif text with small rubric
verse numbers, and the folio "1:1–4" at the foot. The passage runs over two pages, so the card
shows dots and a "1/2" counter, and the reader swipes sideways to page 2. Scrolling down moves to
the next section's card. After the last section, an "End of Mark 1 · Keep scrolling for Mark 2"
page leads straight into Mark 2.

**Why this priority**: Reading is the free core of the app and the surface every study feature
attaches to.

**Independent Test**: With a bundled or downloaded Mark pack, scroll Mark 1 from top to bottom and
on into Mark 2. Every section appears once, in order, as one card. Every verse appears exactly once
across that card's pages, with no verse split between pages.

**Acceptance Scenarios**:

1. **Given** the Mark pack is available, **When** the feed shows Mark 1, **Then** it shows the
   chapter title row ("Mark 1" and "N sections"), then one card per section in order, each with
   its header row, its pages, an action row and a footer slot (filled by spec 003).
2. **Given** a card's first page, **When** it is drawn, **Then** it shows the italic section
   heading with a rubric rule under it, a two-line drop cap on the first word of the first verse
   (leading quote marks are stripped before taking the cap), justified and hyphenated serif text,
   rubric superscript verse numbers (none on the drop-cap verse), and the page's verse-range folio.
3. **Given** a passage taller than one page at the current text size, **When** the card is drawn,
   **Then** it splits into pages **between verses only**, shows a dots row inside the page area and
   a "1/2" counter capsule top-right, and the reader can swipe sideways between pages. Later pages
   have no heading or drop cap.
4. **Given** the reader reaches the last section of a chapter, **When** they keep scrolling,
   **Then** an "End of Mark 1 · Keep scrolling for Mark 2" page appears and the feed continues into
   Mark 2 without any navigation. The header pill updates to the chapter on screen.
5. **Given** the reader changes text size or translation in settings (spec 006), **When** they
   return to the feed, **Then** pages are re-split for the new text and the same section is on
   screen.

---

### User Story 2 - Jump anywhere with the chapter panel (Priority: P1)

The reader taps "Mark 1 ▾". A panel drops down from under the header over a dimmed feed. It shows
a dark "Mark" book button, a CHAPTERS grid (8 columns, the current chapter filled), and "SECTIONS
IN MARK 1": one row per section with its range, title and a status pill. Tapping "Mark 1:21–28"
closes the panel and scrolls the feed to that card. Tapping the book button turns the same panel
into a list of all 66 books under "OLD TESTAMENT" and "NEW TESTAMENT" headers, scrolled to Mark,
with a "Ready" tag on published books.

**Why this priority**: With no Home screen, the panel is the only table of contents and the way to
move around a book.

**Independent Test**: Open the panel, pick chapter 4, pick its third section, and confirm the feed
lands on that card. Open the book list, pick Mark again, and confirm it returns to the chapters
view.

**Acceptance Scenarios**:

1. **Given** the feed, **When** the reader taps the chapter pill, **Then** the panel drops down
   (chevron rotates), the feed behind is dimmed, and tapping the dimmed area closes it. The panel
   scrolls as one list and never nests a second scroll.
2. **Given** the chapters view, **When** the reader taps a chapter tile, **Then** the sections list
   shows that chapter's sections. Chapter tiles show only the number (plus the "new question" dot
   from spec 004), never counts.
3. **Given** a section row, **When** it is tapped, **Then** the panel closes and the feed scrolls so
   that section's card is at the top. Row status pills come from spec 005.
4. **Given** the book button, **When** it is tapped, **Then** the panel shows the 66-book list with
   sticky testament headers, opened at the current book, with "Ready" on published books and a
   check on the current one. Unpublished books show in secondary ink and are still tappable.
5. **Given** the reader picks a published book, **When** it has no reading position, **Then** the
   chapters view for that book appears. A chapter without section data shows one button, "Start
   Mark 2 at verse 1 ›".
6. **Given** the reader picks an unpublished book (Genesis), **When** the chapters view shows,
   **Then** it shows the chapter grid and "Genesis is coming soon · Notify me". Tapping it changes
   to "✓ We'll let you know when Genesis is ready" and stores the book locally. When a later
   catalog update publishes that book, the app shows an in-app banner.
7. **Given** the panel's bottom rows, **When** shown, **Then** they are "Saved passages" with a
   count (spec 005) and "You & settings" (spec 006).

---

### User Story 3 - Open where I left off (Priority: P1)

The reader closes the app in Mark 1:21–28 and opens it the next day. The feed opens on that card.
On a first launch, it opens on Mark 1:1–8.

**Why this priority**: There's no Home or Continue card any more, so resuming has to be automatic.

**Independent Test**: Scroll to Mark 2, kill the app, relaunch, and confirm the feed opens on the
same card. On a fresh install, confirm it opens on Mark 1:1–8.

**Acceptance Scenarios**:

1. **Given** nothing has been read, **When** the app opens, **Then** the feed opens at Mark 1:1–8.
2. **Given** the reader last had Mark 1:21–28 on screen, **When** the app opens, **Then** the feed
   opens with that card at the top.
3. **Given** an external entry (a notification from spec 004, a saved passage, a panel row), **When**
   it targets a section, **Then** the feed opens with that section's card at the top.

---

### User Story 4 - Read offline (Priority: P1)

A reader on a plane opens the app. Everything they downloaded before reads normally. On first
launch with no network, the launch book is still readable.

**Why this priority**: Offline-first is a constitutional principle, and reading must never fail.

**Independent Test**: Install the app, turn on airplane mode before first launch, and read Mark 1
to 16 in both translations.

**Acceptance Scenarios**:

1. **Given** first launch with no network, **When** the reader opens Mark, **Then** the full text
   in both translations is readable.
2. **Given** a newer pack version is published, **When** the app is online, **Then** it downloads
   the update in the background and switches to it without losing the reading position or any
   saved data.
3. **Given** text is shown but the study content for a book is still loading, **When** the reader
   scrolls, **Then** page cards are shown right away, and each question footer shows a small inline
   spinner, never a full-screen loader.

---

### User Story 5 - Share a passage (Priority: P2)

Under the pages, each card has an action row with Send (paper plane) on the left and Save
(bookmark) on the right, and nothing else. Send opens the system share sheet with the passage text,
the reference, the translation code and a `thinkbible.app` link.

**Why this priority**: A light way to share Scripture. Save is specified in spec 005.

**Independent Test**: Tap Send on Mark 1:1–8 and confirm the share sheet holds the passage, "Mark
1:1–8 (BSB)" and the link, and no answer text.

**Acceptance Scenarios**:

1. **Given** a card, **When** Send is tapped, **Then** the share sheet opens with the passage text,
   reference, translation code and link. The reader's answer is never included unless they add it.

---

### User Story 6 - The card's `…` menu (Priority: P3)

The `…` button in a card's header row opens a menu with Copy passage and Report a problem, plus
"Not a helpful question?" when spec 004 allows it.

**Why this priority**: Secondary actions, kept off the page. The menu is not drawn yet.

**Acceptance Scenarios**:

1. **Given** a card, **When** `…` is tapped, **Then** a menu shows Copy passage and Report a
   problem. Copy passage copies the text with its reference and translation code.
2. **Given** spec 004 says the current question has an unused alternate, **When** the menu opens,
   **Then** "Not a helpful question?" is also shown.

### Edge Cases

- A pack download fails or is interrupted: keep using the cached version. Never show a half-written
  pack.
- A downloaded pack fails schema validation: discard it, keep the previous version, and report it.
- A saved position's section ID no longer exists in a newer pack: open the nearest section by verse
  range. Packs are additive, so this should not happen.
- A single verse taller than one page at a very large text size: it gets a page to itself and the
  page grows to fit. Verses are never split.
- Very large Dynamic Type sizes: justified text turns off at the largest size (spec 006), nothing is
  clipped, and page count grows.
- Jumping to a section deep in a long book must land exactly on that card's top.
- A verse present in one translation but bracketed or missing in the other: the pack's neutral
  manuscript note is shown at that point.
- Changing translation while a card is on page 2: the card resets to the page that holds the first
  verse previously on screen.

## Requirements *(mandatory)*

### Functional Requirements

**Header and feed**

- **FR-001**: The app MUST open on the feed, with a fixed header: wordmark ("Think" ink + "Bible"
  rubric), the chapter pill showing the chapter on screen, and the avatar (the user's initial with
  the streak badge from spec 005). The pill opens the chapter panel; the avatar opens You &
  settings (spec 006).
- **FR-002**: The feed MUST be one vertical scroll through the whole book: for each chapter, a
  title row and one page card per section, then an end-of-chapter page, then the next chapter.
- **FR-003**: There MUST be no translation control, mode switch or text-size control in the header
  or on cards. Those live in You & settings.

**Page card**

- **FR-004**: Each card MUST show a header row (book avatar, reference, title on one line, `…`
  button), the pages, an action row (Send, Save) and a footer slot for the question (spec 003).
- **FR-005**: Pages MUST be set as book pages: first-page italic heading with a rubric rule, a
  decorative drop cap on the first word, justified and hyphenated serif text with old-style figures,
  rubric superscript verse numbers, and a verse-range folio on every page.
- **FR-006**: Passages MUST be split into pages by measured height at the current text size,
  breaking only between verses. Multi-page cards MUST show dots and an "n/N" counter, and page
  horizontally.
- **FR-007**: Justification, verse numbers, accent color and text size MUST follow the settings in
  spec 006.
- **FR-008**: Sections marked "no prompt" MUST show their one-line context note in the footer slot
  instead of a question.
- **FR-009**: Send MUST open the system share sheet with the passage text, reference, translation
  code and a `thinkbible.app` link, never the reader's answer.
- **FR-010**: The `…` menu MUST offer Copy passage and Report a problem, and host "Not a helpful
  question?" when spec 004 allows it.

**Chapter panel**

- **FR-011**: The chapter pill MUST open a drop-down panel under the header over a dimmed feed,
  closed by tapping the backdrop. It MUST scroll as one list and show one view at a time: Chapters
  or Books.
- **FR-012**: The Chapters view MUST show the book button, an 8-column chapter grid (current
  chapter filled, numbers only), the selected chapter's sections (range, title, trailing status
  from spec 005), and bottom rows for Saved passages and You & settings. Tapping a section MUST
  close the panel and scroll the feed to that card.
- **FR-013**: Reflection counts MUST appear only on the section rows. Chapter tiles, the sections
  header and the book list carry no counts.
- **FR-014**: The Books view MUST list all 66 books with sticky Old and New Testament headers,
  opened at the current book, with "Ready" tags on published books (from the content catalog, not
  a hard-coded list) and a check on the current book. Picking a book returns to the Chapters view
  for it.
- **FR-015**: For an unpublished book, the panel MUST show "<Book> is coming soon · Notify me".
  Notify me MUST be stored on the device only and trigger an in-app banner when a catalog update
  publishes that book. No push or server call.

**Position, packs and offline**

- **FR-016**: The app MUST remember the section on screen and reopen the feed there, defaulting to
  Mark 1:1–8. It MUST open any section from an external entry with that card at the top.
- **FR-017**: The app MUST support BSB (default) and KJV with one shared set of sections, and show
  the pack's manuscript notes where translations differ in verse presence.
- **FR-018**: The launch book's pack MUST be readable on first launch without network. Other books
  and updates are downloaded per book and cached for offline use.
- **FR-019**: The app MUST check for newer pack versions when online, download them in the
  background, validate them against the schema, and switch atomically. A failed or invalid
  download never replaces a good cached pack.

**Design and accessibility**

- **FR-020**: All colors MUST come from DesignSystem tokens (book-feel tokens in
  `docs/design/README.md`) with light and dark values, and the feed MUST render correctly in both.
- **FR-021**: Every control MUST be a real button with a label and a 44pt target. Chapter tiles read
  "Mark chapter 1". Section rows read the range, title and state. The drop cap is decorative and
  VoiceOver reads the whole first word. Page dots are hidden and the counter announces "Page 1 of
  2". Text contrast is at least 4.5:1 in both modes.

### Key Entities

- **Book / Chapter / Section** (from the pack): section ID, reference, title, verse range,
  "no prompt" flag, context note, manuscript notes.
- **Catalog** (from the CDN, cached): books and whether each is published.
- **Verse text** (per translation): book, chapter, verse number, text.
- **Reading position** (on device, synced in spec 005): book, chapter, section ID, last-opened time.
- **Book notify request** (on device): book ID, requested time.
- **Pack cache** (on device): book, pack version, translation files, validation status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a cold launch, a returning reader sees the section they left in under 2 seconds
  on a recent iPhone, with no taps.
- **SC-002**: Scrolling a full chapter (Mark 1) and paging its cards stays smooth on an iPhone two
  generations old.
- **SC-003**: 100% of Mark is readable in both translations in airplane mode on first launch.
- **SC-004**: In pagination tests across every Mark section at every text size, 0 verses are split
  across pages and 0 verses are dropped or repeated.
- **SC-005**: Zero paywall or sign-in prompts appear anywhere in the reading path (feed, panel,
  book list, Send, Copy).
- **SC-006**: A reader can reach any section of Mark from anywhere in 3 taps or fewer (pill,
  chapter, section).

## Assumptions

- The launch book's pack (study content and both translations) is bundled with the app so first
  launch works offline. Later books download on demand.
- The old Study / Read switch is gone. Plain reading is the "Show questions" setting (spec 006).
  Hiding questions removes the footers; it never touches the text.
- Pages are drawn with a TextKit 2 view, since SwiftUI `Text` can't justify around a floating drop
  cap (`docs/design/CLAUDE_CODE_PROMPT.md`).
- The `…` menu is not drawn yet. Its contents follow `docs/design/README.md`.
- Verse notes (tap a dotted word) are not in the MVP (V2).
- "Notify me" for unpublished books is local only in v1. Push needs backend work and is out of
  scope.
- The brief's MVP summary says "one translation", but the MVP table and the design include BSB and
  KJV. This spec includes both, with the switch in settings.
