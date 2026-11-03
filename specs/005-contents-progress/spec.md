# Feature Specification: Contents, Saved Reflections and Progress

**Feature Branch**: `005-contents-progress`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Contents, saved reflections and progress (brief spec 6): Home's
contents list shows every section of the selected chapter with its status (reflected with ideas
caught and a 'Read again · Level N' pill, read only, current, not yet read), the chapter summary
('5 of 9 read · 4 reflections'), a reading streak, and tapping any row opens the reader at that
section to review past reflections. Reflections and progress are saved on the device and synced
through the user's own iCloud, so they survive a new phone or reinstall, and never disappear."

**References**: [docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Home, Settings → Your
reflections, Suggested state); mockup [Main.dc.html](../../docs/design/screens/Main.dc.html);
brief "Data model → Why answers never disappear"; constitution principles I, VI, VII. Depends on
002, 003 and 004.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See where I am in a chapter (Priority: P1)

On Home, the reader selects Mark 1 in the chapter grid and sees "5 of 9 read · 4 reflections",
then every section as a row:
- **Reflected** rows show the ref and title, a "YOUR OBSERVATIONS" strip with idea dots and
  "2 of 4 ideas", and a "↻ Read again · Level 2" pill (or a grey "All levels done").
- **Read-only** rows say "Read only · reflect anytime".
- The **current** section shows its title only.
- **Not-yet-read** rows are dimmed.

**Why this priority**: The contents list replaces a separate journal. It is how readers find their
past thinking and see progress.

**Independent Test**: Seed progress for Mark 1 (some reflected, some read, some skipped) and
confirm each row's status, the counts, and that tapping a row opens the reader at that section.

**Acceptance Scenarios**:

1. **Given** a chapter with mixed progress, **When** it is selected on Home, **Then** the header
   shows "<read> of <total> read · <n> reflections", and each section row shows exactly one of:
   reflected, read only, skipped, current or not yet read.
2. **Given** a reflected section with remaining levels, **When** its row shows, **Then** the pill
   reads "↻ Read again · Level N". Tapping it opens the reader at that section ready for the next
   read.
3. **Given** a section with all levels done, **When** its row shows, **Then** a grey "All levels
   done" replaces the pill.
4. **Given** a skipped section, **When** its row shows, **Then** it reads "Skipped · answer
   anyway".
5. **Given** a chapter the reader hasn't started, **When** it is selected, **Then** it shows "You
   haven't started this chapter yet…" with a "Start Mark N" link.

---

### User Story 2 - Review a past reflection (Priority: P1)

The reader taps a reflected section on Home. The reader opens at that section with its folded
reflection row, and tapping it shows the saved answer, highlight, note and the ideas caught and
missed, exactly as they were shown, even if the pack has since changed or the translation was
switched.

**Why this priority**: "Your answers never disappear" is a core promise and a privacy-respecting
alternative to a server-side journal.

**Independent Test**: Save a reflection, then install a pack update that retires that question and
rewords an idea's body. Switch translation. Confirm the saved reflection still shows the original
question and ideas from its snapshot.

**Acceptance Scenarios**:

1. **Given** a saved reflection, **When** the reader opens it, **Then** it shows the question,
   answer, highlight, note and idea list from its saved snapshot.
2. **Given** the reader's free reflections are used up and they are not subscribed, **When** they
   open a saved reflection, **Then** it is fully viewable.
3. **Given** a section with reflections on several reads, **When** reviewed, **Then** each read's
   reflection can be opened, newest first.

---

### User Story 3 - My reflections follow me to a new phone (Priority: P1)

The reader signs into the same Apple ID on a new iPhone and installs ThinkBible. Their reflections,
progress, levels and streak appear without any ThinkBible account.

**Why this priority**: Losing reflections would break trust. No accounts is a privacy principle.

**Independent Test**: With iCloud on, create reflections on device A. Install on device B with the
same Apple ID and confirm they appear, and that a change on B appears on A.

**Acceptance Scenarios**:

1. **Given** iCloud is available, **When** reflections and progress change, **Then** they sync to
   the reader's other devices on the same Apple ID.
2. **Given** iCloud is off or unavailable, **When** the reader uses the app, **Then** everything
   works and is saved on the device, and Settings shows the sync status.
3. **Given** the same section was answered on two devices while offline, **When** they sync,
   **Then** both reflections are kept. Neither overwrites the other.
4. **Given** the reader deletes and reinstalls the app, **When** iCloud is on, **Then** reflections
   and progress come back.

---

### User Story 4 - Reading streak (Priority: P2)

Home's header shows a flame and "6 days", the reader's current streak of days with reading.

**Why this priority**: A light habit cue. Useful but not core.

**Independent Test**: Read on three consecutive days, then skip a day. Confirm the streak goes
1, 2, 3, then resets.

**Acceptance Scenarios**:

1. **Given** the reader read at least one section to its end today and on each of the previous
   N−1 days, **When** Home opens, **Then** the pill reads "N days".
2. **Given** a day was missed, **When** Home opens, **Then** the streak starts again from today's
   activity, or the pill is hidden if there's none yet.

---

### User Story 5 - Delete all reflections (Priority: P3)

In Settings → Your reflections, the reader taps "Delete all reflections", confirms, and all
reflections and study progress are removed from this device and their iCloud.

**Why this priority**: A privacy right and App Store expectation. Rarely used.

**Independent Test**: Delete all, confirm, and verify no reflections remain on this device or a
second synced device.

**Acceptance Scenarios**:

1. **Given** saved reflections, **When** the reader taps "Delete all reflections", **Then** a
   confirmation dialog explains it cannot be undone and removes them from all their devices.
2. **Given** the confirmation, **When** the reader cancels, **Then** nothing is deleted.

### Edge Cases

- A pack update changes section boundaries: this should not happen, since packs are additive.
  Reflections still resolve by their saved snapshot and section ID.
- A reader who uses only Read mode: rows show "Read only · reflect anytime". The streak still
  counts.
- A reflection pending a live check (offline) is shown with fallback results, then updated in
  place.
- The iCloud account changes on the device: data from the previous account is not mixed into the
  new account's store.
- iCloud storage is full: the app keeps working locally and shows the status in Settings.
- Very long reading history: Home stays responsive with every section of every chapter reflected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Home MUST show, for the selected chapter, a summary line ("<read> of <total> read ·
  <n> reflections") and one row per section with status: reflected, read only, skipped, current or
  not yet read, styled per DESIGN.md.
- **FR-002**: A section counts as "read" when the reader has scrolled to the end of its verses in
  either mode.
- **FR-003**: Reflected rows MUST show idea dots and "<caught> of <total> ideas" (caught across all
  reads), plus the "↻ Read again · Level N" pill or "All levels done".
- **FR-004**: Every row MUST open the reader scrolled to that section.
- **FR-005**: The chapter grid MUST mark the selected chapter (filled), started chapters
  (outlined) and others (neutral).
- **FR-006**: Saved reflections MUST display from their snapshot and remain viewable regardless of
  entitlement, pack changes or translation.
- **FR-007**: Reflections, section progress, question history, reading position and streak MUST be
  stored on the device and synced through the user's own iCloud when available, with no app
  account.
- **FR-008**: Sync conflicts MUST never lose a reflection. Concurrent reflections are all kept, and
  progress merges by taking the furthest level and the union of caught ideas.
- **FR-009**: The streak MUST count consecutive local calendar days on which the reader read at
  least one section to its end. It is shown in Home's header as a flame and "N days".
- **FR-010**: Settings MUST show iCloud sync status and offer "Delete all reflections" with a
  confirmation. Deletion removes reflections and study progress from the device and the user's
  iCloud.
- **FR-011**: No reflection or progress data is sent to ThinkBible's servers.

### Key Entities

- **Reflection**: as defined in spec 003, including the shown snapshot.
- **Section progress**: section ID, read flag, skipped flag, current level, caught idea IDs, last
  read day, all-levels-done flag.
- **Progress**: book, last section (reading position), sections read, sections reflected, streak
  days.
- **Question history**: as defined in spec 004.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Home with full Mark progress appears in under 1 second after launch on a recent
  iPhone.
- **SC-002**: 100% of saved reflections remain viewable and unchanged after a pack update that
  retires or rewords their question.
- **SC-003**: Reflections created on one device appear on a second device on the same Apple ID
  within 1 minute under normal connectivity.
- **SC-004**: Zero reflections are lost in a scripted test of 20 concurrent offline edits across
  two devices.
- **SC-005**: Readers can find and open a reflection from last week in under 10 seconds.

## Assumptions

- Streak counts reading, not reflecting, so Read-mode users are rewarded too.
- Export of reflections to PDF or text is V2.
- The free count lives on the server per device (spec 006) and is not part of iCloud data.
- There is no separate Journal tab. Home's contents list is the way back to reflections.
