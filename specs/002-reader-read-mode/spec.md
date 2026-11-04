# Feature Specification: Chapter Reader and Read Mode

**Feature Branch**: `002-reader-read-mode`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Reader and Read mode (brief spec 3): one continuous scroll per chapter,
split into passage sections with sticky section headers, superscript verse numbers, a Study / Read
switch, a BSB / KJV switch, content packs downloaded per book and cached for offline use, and a
Home screen with a Continue card and chapter grid to get into the reader. Reading is always free."

**References**: [docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Home, Chapter reader → Layout,
States with no mockup); mockups [Main.dc.html](../../docs/design/screens/Main.dc.html) and
[FeedHybrid.dc.html](../../docs/design/screens/FeedHybrid.dc.html); constitution principles I, V,
X. Depends on spec 001 (pack format and a published Mark pack, or a fixture pack).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read a chapter as one continuous scroll (Priority: P1)

A reader opens Mark 1 and scrolls through the whole chapter like a printed Bible: a chapter title,
then each section with its reference and title, then its verses with small superscript verse
numbers. As they scroll, the current section's header pins to the top until the next section's
header replaces it.

**Why this priority**: Reading is the free core of the app and the surface every study feature is
attached to.

**Independent Test**: With a bundled or downloaded Mark pack, open Mark 1 and scroll from top to
bottom. Every section header pins while its section is on screen, and all verses appear in order
with their numbers.

**Acceptance Scenarios**:

1. **Given** the Mark pack is available, **When** the reader opens Mark 1, **Then** they see the
   chapter title, then every section of Mark 1 in order, each with its sticky header (reference in
   uppercase accent, title in serif) and its verses.
2. **Given** the reader is scrolling through a section, **When** that section's header reaches the
   top, **Then** it stays pinned until the next section's header pushes it away.
3. **Given** the reader reaches the end of a chapter, **When** they keep scrolling, **Then** they
   can continue into the next chapter without going back to Home.
4. **Given** a section marked "no prompt" (one where the commentaries give nothing to ask about,
   such as a bare census list), **When** it is displayed, **Then** a one-line context note appears
   under its verses.

---

### User Story 2 - Switch between Study and Read modes (Priority: P1)

A reader who just wants to read taps "Read" in the top bar, and every study element disappears,
leaving only headers and text. Tapping "Study" brings them back. Study is the default.

**Why this priority**: Read mode is the always-free, no-homework path and a key answer to
reflection fatigue. The study elements themselves arrive in spec 003. This feature provides the
switch and the slot each section's study element occupies.

**Independent Test**: Toggle Study / Read in Mark 1. In Read mode no section shows a study
element; in Study mode each prompted section shows its (placeholder or real) study row. The
reading position is kept across toggles.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the reader opens a chapter, **Then** Study mode is
   selected.
2. **Given** Study mode, **When** the reader switches to Read, **Then** every section's study
   element is hidden, and the verse at the top of the screen stays at the top.
3. **Given** the reader chose Read and leaves the reader, **When** they return, **Then** the mode
   they last used, or the "Open in" setting from spec 006 once it exists, is applied.

---

### User Story 3 - Switch translation (Priority: P2)

A reader taps the "BSB ▾" pill and switches to KJV. The same sections, with the same headers,
show the KJV text, and the reading position is kept.

**Why this priority**: Two translations are in MVP scope, and sections are shared across both.

**Independent Test**: In Mark 1, scroll to 1:9, switch to KJV, and confirm 1:9 is still at the top
showing KJV wording. Switch back, and the BSB wording returns.

**Acceptance Scenarios**:

1. **Given** BSB is showing, **When** the reader selects KJV, **Then** all verse text in the
   chapter changes to KJV, section boundaries and titles stay the same, and the position is kept.
2. **Given** a verse present in one translation but bracketed or missing in the other, **When**
   it is displayed, **Then** the pack's neutral manuscript note is shown at that point.
3. **Given** the reader switched to KJV, **When** they reopen the app, **Then** KJV is still
   selected.

---

### User Story 4 - Get into the reader from Home (Priority: P2)

On launch, Home shows the ThinkBible wordmark, a settings gear, a Continue card for where the
reader left off ("Continue · Mark 1:21–28", the section title, an estimate like "About 3 min ·
1 question", a play button), and a Contents area with a book picker and a chapter grid. Tapping the
Continue card or a chapter opens the reader at that place.

**Why this priority**: The reader needs an entry point. The full contents list with per-section
status, reflections and streak comes in spec 005.

**Independent Test**: Read into Mark 2, leave and relaunch. Home's Continue card points to the
section the reader was in, and tapping it opens the reader scrolled to that section.

**Acceptance Scenarios**:

1. **Given** nothing has been read yet, **When** Home opens, **Then** the Continue card reads
   "Start · Mark 1:1–8".
2. **Given** the reader last stopped in Mark 1:21–28, **When** Home opens, **Then** the Continue
   card reads "Continue · Mark 1:21–28" with that section's title, and tapping it opens the reader
   scrolled to that section.
3. **Given** the chapter grid, **When** the reader taps chapter 4, **Then** the grid shows it
   selected, and opening it shows the reader at the top of Mark 4. Chapters already started show as
   outlined, others as neutral.
4. **Given** the settings gear, **When** it is tapped, **Then** Settings opens (pushed). The
   Settings contents are specified in spec 006.

---

### User Story 5 - Read offline (Priority: P1)

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
   scrolls, **Then** headers and verses are shown right away, and each study element shows a small
   inline spinner, never a full-screen loader.

### Edge Cases

- A pack download fails or is interrupted: keep using the cached version. Never show a half-written
  pack.
- A downloaded pack fails schema validation: discard it, keep the previous version, and report it.
- A section ID referenced by a saved position no longer exists in a newer pack: open the nearest
  section by verse range. Packs are additive, so this should not happen.
- Very large Dynamic Type sizes: verse text wraps, headers stay readable, and nothing is clipped.
- Jumping to a section deep in a long chapter must land exactly on that section's header.
- A book not yet released: it is not shown in the book picker. Only published books are listed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST present each chapter as one continuous vertical scroll: the chapter
  title, then for each section a sticky header (uppercase reference, serif title, status-chip slot),
  its verses with superscript verse numbers, and a slot for its study element.
- **FR-002**: Section headers MUST pin while their section is on screen and be replaced by the next
  section's header.
- **FR-003**: The reader MUST provide a fixed top bar with Back, a Study / Read segmented control
  (Study by default) and a translation pill (BSB / KJV).
- **FR-004**: Read mode MUST hide every study element. It is always available and never paywalled.
- **FR-005**: Switching mode or translation MUST keep the reading position (the verse at the top of
  the screen).
- **FR-006**: The app MUST support BSB (default) and KJV, using one shared set of sections, and show
  the pack's manuscript notes where translations differ in verse presence.
- **FR-007**: Sections marked "no prompt" MUST show their one-line context note under the verses
  and no study element.
- **FR-008**: The reader MUST support continuing from the end of one chapter into the next.
- **FR-009**: The app MUST remember the last section the reader was in and open Home's Continue
  card to it, with "Start · Mark 1:1–8" when nothing has been read.
- **FR-010**: Home MUST show the header (wordmark with "Bible" in accent, a streak-pill slot, the
  settings gear), the Continue card, and Contents with a book picker and an 8-column chapter grid
  (selected = filled, started = outlined, others neutral).
- **FR-011**: The launch book's pack MUST be readable on first launch without network. Other books
  and updates are downloaded per book and cached for offline use.
- **FR-012**: The app MUST check for newer pack versions when online, download them in the
  background, validate them against the schema, and switch atomically. A failed or invalid
  download never replaces a good cached pack.
- **FR-013**: Scripture text MUST use the serif face at the DESIGN.md default sizes, scale with
  Dynamic Type, and later respond to the text size, font and verse-number settings (spec 006).
- **FR-014**: All colors MUST come from design tokens with light and dark values. The reader MUST
  render correctly in both appearances.
- **FR-015**: VoiceOver MUST read each section header as a heading. Every icon-only button has a
  label, and every tap target is at least 44pt.
- **FR-016**: The app MUST open a specific section from an external entry (Home row, Continue card,
  later a notification) scrolled so that section's header is at the top.

### Key Entities

- **Book / Chapter / Section** (from the pack): section ID, reference, title, verse range,
  "no prompt" flag, context note, manuscript notes.
- **Verse text** (per translation): book, chapter, verse number, text.
- **Reading position** (on device): book, chapter, section ID, last-opened time.
- **Pack cache** (on device): book, pack version, translation files, validation status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a cold launch, a returning reader reaches their Continue section in two taps or
  fewer and under 2 seconds on a recent iPhone.
- **SC-002**: Scrolling a full chapter (Mark 1, 45 verses) stays smooth, with no visible stutter on
  an iPhone two generations old.
- **SC-003**: 100% of Mark is readable in both translations in airplane mode on first launch.
- **SC-004**: Switching translation or mode keeps the same verse within one line of the top of the
  screen in 100% of tests.
- **SC-005**: Zero paywall or sign-in prompts appear anywhere in the reading path (Read mode,
  navigation, translation switch).
- **SC-006**: VoiceOver users can navigate a chapter by section heading.

## Assumptions

- The launch book's pack (study content and both translations) is bundled with the app so first
  launch works offline. Later books download on demand.
- Verse notes (tap a dotted word) are not in the MVP reader (DESIGN.md defers them to V2).
- The streak pill and the per-section contents list are placeholders here and filled in by spec 005.
  Study elements are placeholders here and filled in by spec 003.
- "Reading position" is stored on the device and synced with progress in spec 005.
- The brief's MVP table says "one translation", but DESIGN.md and the reader mockups include the
  BSB / KJV switch. This spec includes both.
- Only one book (Mark) is published at launch. The book picker lists published books only.
