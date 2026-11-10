# Feature Specification: Section Status, Saved Passages and Progress

**Feature Branch**: `005-contents-progress` (folder name kept from the earlier "Contents, saved
reflections and progress" draft)

**Created**: 2026-11-03

**Updated**: 2026-11-10, rewritten for the "book feel" design: Home's contents list is replaced by
status pills on the chapter panel's section rows, saved passages, the streak on the avatar, and the
profile and book progress at the top of You & settings.

**Status**: Draft

**Input**: User description: "Saved passages, reflections and progress (brief spec 6): each section
has a progress record on the device (none, read, reflected; ideas caught; level; unlock time;
saved). The chapter panel's section rows show it as a pill (✓ 3/3, Read, Reading) with a bookmark
for saved passages. Reflection counts appear only there. The avatar shows the reading streak. You &
settings opens with a profile card (streak, reflections, ideas caught), your books with progress,
and saved passages. Past reflections stay in each card's thread. Everything is saved on the device
and synced through the user's own iCloud, with no account, and never disappears."

**References**: [docs/design/README.md](../../docs/design/README.md) (Chapter panel, Action row,
You & settings, Progress model); screens
[07-chapter-picker.png](../../docs/design/screens/07-chapter-picker.png),
[10-you-settings.png](../../docs/design/screens/10-you-settings.png),
[15-panel-new.png](../../docs/design/screens/15-panel-new.png);
[docs/design/DESIGN.md](../../docs/design/DESIGN.md) (You & settings → Your reflections, Suggested
state); brief "Data model → Why answers never disappear"; constitution principles I, VI, VII.
Depends on 002, 003 and 004.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See where I am in a chapter (Priority: P1)

The reader opens the chapter panel on Mark 1. Under "SECTIONS IN MARK 1" each row shows its range,
title and one trailing state:
- **Reflected:** a rubric pill "✓ 3/3" (ideas caught / total);
- **Read:** an outline pill "Read";
- **Current, unanswered:** a tint pill "Reading";
- **Not yet read:** nothing.

Saved sections show a small filled bookmark before the pill. Chapter tiles, the sections header and
the book list show no counts.

**Why this priority**: The panel replaces Home's contents list and a separate journal. It's how
readers see their progress and find their past thinking.

**Independent Test**: Seed progress for Mark 1 (some reflected, some read, one saved) and confirm
each row's pill and bookmark, and that tapping a row opens the feed at that card.

**Acceptance Scenarios**:

1. **Given** a section with an evaluated answer, **When** its row shows, **Then** it shows "✓ c/t"
   with the ideas caught across all levels and the section's total, even "✓ 0/4" when nothing
   matched.
2. **Given** a section whose last page was on screen and that scrolled past without an answer,
   **When** its row shows, **Then** it shows "Read".
3. **Given** the section currently on screen in the feed is unanswered, **When** the panel opens,
   **Then** its row shows "Reading".
4. **Given** a reflected section, **When** it is later scrolled past again, **Then** it stays
   reflected. Read never downgrades reflected.
5. **Given** a section with an unlocked level (spec 004), **When** its row shows, **Then** "New"
   appears before the pill.

---

### User Story 2 - Review a past reflection (Priority: P1)

The reader taps a reflected section in the panel. The feed opens at that card, where the thread
shows their answer, highlight, reply and the ideas caught and missed exactly as they were shown,
even if the pack has since changed or the translation was switched.

**Why this priority**: "Your answers never disappear" is a core promise and a privacy-respecting
alternative to a server-side journal.

**Independent Test**: Save a reflection, then install a pack update that retires that question and
rewords an idea's body. Switch translation. Confirm the saved thread still shows the original
question and ideas from its snapshot.

**Acceptance Scenarios**:

1. **Given** a saved reflection, **When** its card shows, **Then** the thread shows the question,
   answer, highlight, note and idea list from the saved snapshot.
2. **Given** the reader's free reflections are used up and they are not subscribed, **When** they
   open a saved reflection, **Then** it is fully viewable.
3. **Given** a section with reflections at several levels, **When** reviewed, **Then** the newest
   thread shows first and each earlier one is reachable through "Show more" (spec 004).

---

### User Story 3 - Save a passage (Priority: P2)

The reader taps the bookmark in a card's action row. It fills. The passage appears under "Saved
passages" in the chapter panel's bottom row count and in You & settings, newest first, with its
reference and italic title. Tapping one opens the feed at that card. Tapping the bookmark again
unsaves it.

**Why this priority**: A simple way back to passages that mattered, separate from answering.

**Independent Test**: Save Mark 1:9–11 and 1:12–13, confirm both appear in You & settings and the
panel count reads 2, unsave one, and confirm it's gone on both.

**Acceptance Scenarios**:

1. **Given** an unsaved card, **When** the bookmark is tapped, **Then** it fills, the section's
   progress records `saved`, and the section row shows the bookmark.
2. **Given** saved passages, **When** You & settings or the panel's "Saved passages" row is opened,
   **Then** they are listed with reference and title, and each opens the feed at that card.

---

### User Story 4 - My reflections follow me to a new phone (Priority: P1)

The reader signs into the same Apple ID on a new iPhone and installs ThinkBible. Their reflections,
progress, levels, unlock times, saved passages and streak appear without any ThinkBible account.

**Why this priority**: Losing reflections would break trust. No accounts is a privacy principle.

**Independent Test**: With iCloud on, create reflections on device A. Install on device B with the
same Apple ID and confirm they appear, and that a change on B appears on A.

**Acceptance Scenarios**:

1. **Given** iCloud is available, **When** reflections and progress change, **Then** they sync to
   the reader's other devices on the same Apple ID.
2. **Given** iCloud is off or unavailable, **When** the reader uses the app, **Then** everything
   works and is saved on the device, and You & settings shows the sync status.
3. **Given** the same section was answered on two devices while offline, **When** they sync,
   **Then** both reflections are kept. Neither overwrites the other.
4. **Given** the reader deletes and reinstalls the app, **When** iCloud is on, **Then** reflections
   and progress come back.

---

### User Story 5 - Streak and profile (Priority: P2)

The avatar in the header carries a small flame badge with "6". You & settings opens with a profile
card: the initial, "You", "Reading Mark since Nov 3", and three tiles: 6 day streak · 4
reflections · 9 ideas caught. Under "YOUR BOOKS", Mark shows a progress bar, "Chapter 1 of 16 · 5
of 9 sections read · 2 ready for a harder question" and "Continue · 1:21". Upcoming books show
in secondary ink, e.g. "John · Coming before Easter".

**Why this priority**: A light habit cue and a sense of progress. Useful but not core.

**Independent Test**: Read on three consecutive days, then miss a day. Confirm the streak goes 1, 2,
3, then resets. Confirm the tiles and book line match seeded progress.

**Acceptance Scenarios**:

1. **Given** the reader read or reflected on at least one section today and on each of the previous
   N−1 days, **When** the header shows, **Then** the badge reads N.
2. **Given** a day was missed, **When** the header shows, **Then** the streak starts again from
   today's activity, or the badge is hidden if there's none yet.
3. **Given** Your books, **When** Mark's row shows, **Then** it shows sections read out of the
   chapter's total, the number of sections with an unlocked question, and "Continue · <ref>", which
   opens the feed at the reading position.

---

### User Story 6 - Delete all reflections (Priority: P3)

In You & settings → Your reflections, the reader taps "Delete all reflections", confirms, and all
reflections and study progress are removed from this device and their iCloud.

**Why this priority**: A privacy right and App Store expectation. Rarely used.

**Independent Test**: Delete all, confirm, and verify no reflections remain on this device or a
second synced device.

**Acceptance Scenarios**:

1. **Given** saved reflections, **When** the reader taps "Delete all reflections", **Then** a
   confirmation dialog explains it cannot be undone and removes them from all their devices.
   Pending unlock notifications are cancelled.
2. **Given** the confirmation, **When** the reader cancels, **Then** nothing is deleted.

### Edge Cases

- A pack update changes section boundaries: this should not happen, since packs are additive.
  Reflections still resolve by their saved snapshot and section ID.
- A reader who keeps Show questions off: rows show "Read" and the streak still counts.
- A reflection pending a live check (offline) shows "✓ 0/M" from the fallback, then updates when
  checked.
- A pack update changes a section's number of key ideas: the pill's total uses the current pack;
  caught IDs no longer in the pack are not counted.
- The iCloud account changes on the device: data from the previous account is not mixed into the
  new account's store.
- iCloud storage is full: the app keeps working locally and shows the status in You & settings.
- Very long reading history: the panel and You & settings stay responsive with every section of
  every chapter reflected.
- Delete all reflections: saved passages are kept unless the reader also unsaves them. [Assumption;
  the bookmark isn't a reflection.]

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST keep one progress record per section: `sectionId`, `state` (none, read,
  reflected), `ideasCaught` (union across levels) and `ideasTotal`, `level` (highest answered),
  `unlocksAt`, `saved`, `updatedAt`.
- **FR-002**: `reflected` MUST be set when an answer is evaluated (live or fallback), even with 0
  ideas caught. `read` MUST be set when a card's last page has been on screen and the card has
  scrolled past without an answer. Read never downgrades reflected.
- **FR-003**: Chapter panel section rows MUST show exactly one trailing state: "✓ c/t" (reflected),
  "Read", "Reading" (current, unanswered) or none, preceded by a bookmark when saved and "New" when
  a level is unlocked. Counts MUST appear nowhere else in the panel.
- **FR-004**: Every row, saved passage and "Continue" MUST open the feed at that section.
- **FR-005**: The Save bookmark in each card's action row MUST toggle `saved`. Saved passages MUST
  be listed newest first in You & settings and counted on the panel's "Saved passages" row.
- **FR-006**: Saved reflections MUST display from their snapshot and remain viewable regardless of
  entitlement, pack changes or translation.
- **FR-007**: Reflections, section progress, question history, reading position, saved passages and
  streak MUST be stored on the device (SwiftData) and synced through the user's own iCloud
  (CloudKit) when available, with no app account.
- **FR-008**: Sync conflicts MUST never lose a reflection. Concurrent reflections are all kept, and
  progress merges by taking the highest level, the furthest state (reflected > read > none), the
  union of caught ideas, and the latest `unlocksAt` for the merged level.
- **FR-009**: The streak MUST count consecutive local calendar days with at least one section read
  or reflected, shown as a flame badge on the header avatar.
- **FR-010**: You & settings MUST open with the profile card (start date, streak, reflections,
  ideas caught), Your books (per-book progress, sections read, sections ready for a harder question,
  "Continue · <ref>", and upcoming books), and Saved passages. Published and upcoming books come from
  the content catalog.
- **FR-011**: You & settings MUST show iCloud sync status and offer "Delete all reflections" with a
  confirmation. Deletion removes reflections and study progress from the device and the user's
  iCloud, and cancels pending unlock notifications.
- **FR-012**: No reflection or progress data is sent to ThinkBible's servers.

### Key Entities

- **Reflection**: as defined in spec 003, including the shown snapshot.
- **SectionProgress**: see FR-001 (matches `docs/design/README.md` → Progress model).
- **Reading position**: book, chapter, section ID, updated time.
- **Question history**: as defined in spec 004.
- **Derived values** (computed, not stored): streak, per-book progress, reflections count, ideas
  caught total, sections ready for a harder question.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The chapter panel with full Mark progress opens in under 300 ms on a recent iPhone.
- **SC-002**: 100% of saved reflections remain viewable and unchanged after a pack update that
  retires or rewords their question.
- **SC-003**: Reflections created on one device appear on a second device on the same Apple ID
  within 1 minute under normal connectivity.
- **SC-004**: Zero reflections are lost in a scripted test of 20 concurrent offline edits across
  two devices.
- **SC-005**: In unit tests of progress derivation, read never overrides reflected, and every
  chapter's fractions and counts match seeded data, 100% of the time.
- **SC-006**: Readers can find and open a reflection from last week in under 10 seconds.

## Assumptions

- Streak counts reading or reflecting, so readers with questions off are rewarded too.
- Export of reflections to PDF or text is V2.
- The free count lives on the server per device (spec 006) and is not part of iCloud data.
- There is no Home screen and no separate Journal tab. The chapter panel and each card's thread are
  the way back to reflections.
- "Upcoming" book lines (e.g. "John · Coming before Easter") come from catalog metadata, not code.
