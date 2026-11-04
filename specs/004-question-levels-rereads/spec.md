# Feature Specification: Question Levels and Re-reads

**Feature Branch**: `004-question-levels-rereads`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Question levels and re-reads (brief spec 5): each section has up to
three levels (1 notice, 2 interpret, 3 connect). One question per section per read. The first read
asks Level 1, and each later read on a later day asks the next level, preferring a question that
targets an idea the reader hasn't caught yet. 'You caught' counts ideas across all reads, ideas
caught this time get a 'New' tag, earlier answers sit behind a 'Your first-read reflection' row,
and the footer says what's next or 'All levels done'. 'Not a helpful question?' swaps in the hidden
alternate once."

**References**: [docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Levels, Study card states,
Home section rows); mockup
[ReaderDeeper.dc.html](../../docs/design/screens/ReaderDeeper.dc.html) (scene "Second read");
brief "Question freshness" and "Harder questions on later reads"; constitution principles III, VII.
Depends on 001 (levels and alternates in the pack) and 003 (question card and compare).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A harder question on the next read (Priority: P1)

A reader answered Mark 1:1–8's Level 1 question yesterday. Today they read that section again,
and the card offers "Second read · a harder question on the whole passage". They answer, and the
results count what they caught across both reads. Ideas caught today carry a "New" tag. Yesterday's
answer sits behind a "Your first-read reflection" row.

**Why this priority**: This is what makes re-reading fresh instead of a repeat quiz, and it is a
core Premium benefit.

**Independent Test**: With a device clock you can control, answer Level 1 on day 1. On day 2,
reopen the section, confirm the Level 2 question is offered, answer it, and confirm cumulative
counts and "New" tags.

**Acceptance Scenarios**:

1. **Given** a section never answered, **When** its card opens, **Then** it asks a Level 1 question.
2. **Given** Level 1 was answered on an earlier day, **When** the reader returns to the section,
   **Then** the collapsed row reads "Second read · a harder question on <scope>", and the asking
   label reads "SECOND READ · A HARDER QUESTION · <SCOPE>" with a Level 2 question.
3. **Given** Level 1 was answered earlier today, **When** the reader returns today, **Then** the
   section shows its folded reflection, not a new question.
4. **Given** a second-read result, **When** it shows, **Then** "You caught N of M" counts ideas
   caught on any read, ideas first caught on this read show a "New" tag, and a "Your first-read
   reflection" disclosure row expands to the earlier answer and its results.
5. **Given** results on a read that isn't the last level, **When** the footer shows, **Then** it
   reads "Next time you read this section: a harder Level N question."

---

### User Story 2 - Prefer questions aimed at what you missed (Priority: P1)

When a level has two questions, the app picks the one that targets a key idea the reader hasn't
caught yet. The other stays hidden as the alternate.

**Why this priority**: Targeting missed ideas is what makes later reads teach something new.

**Independent Test**: For a section whose Level 2 has two questions targeting different ideas,
catch one of those ideas at Level 1 and confirm Level 2 serves the question targeting the other.

**Acceptance Scenarios**:

1. **Given** a level with two active questions, **When** choosing which to show, **Then** the app
   shows the one whose targets include the most not-yet-caught ideas. Ties go to the pack's
   primary question.
2. **Given** a level with one active question, **When** choosing, **Then** that question is shown.
3. **Given** a question retired in a newer pack, **When** choosing, **Then** it is never shown as a
   new question. Saved reflections that used it still display from their snapshot.

---

### User Story 3 - "Not a helpful question?" (Priority: P2)

On the asking card, if the current level has a hidden alternate that hasn't been used, a "Not a
helpful question?" link is shown. Tapping it replaces the question in place with the alternate and
shows "Thanks for the feedback. Here's another question at this level."

**Why this priority**: Gives readers an escape from a weak question and feeds the review queue
(spec 007).

**Independent Test**: On a level with an alternate, tap "Not a helpful question?". The alternate
appears, the link disappears, and the swap persists after relaunch.

**Acceptance Scenarios**:

1. **Given** a level with an unused alternate, **When** the card is asking, **Then** "Not a helpful
   question?" is shown.
2. **Given** the link is tapped, **When** the swap happens, **Then** the alternate replaces the
   question in place, with the thank-you line, and any typed draft is kept.
3. **Given** the swap was used for this level, **When** the card shows again, **Then** the link is
   not shown again for that level.
4. **Given** a level with no alternate, **When** the card is asking, **Then** no link is shown.

---

### User Story 4 - Finishing every level (Priority: P2)

After the reader answers the last available level of a section, the results footer reads "You've
answered every level for this section.", and Home shows "All levels done" for that section.

**Why this priority**: A clear end state avoids confusion and gives a sense of completion.

**Independent Test**: Answer all levels of a two-level section on two different days. Confirm the
completion footer, and that later visits show the folded reflection with no new question.

**Acceptance Scenarios**:

1. **Given** a section with L levels, **When** level L is answered, **Then** the footer reads
   "You've answered every level for this section." and the section is marked all levels done.
2. **Given** all levels are done, **When** the reader returns on a later day, **Then** no new
   question is offered. The folded reflection is shown, and each earlier read's reflection can be
   reviewed.

### Edge Cases

- The reader skipped Level 1: skipping does not advance the level. The next read offers Level 1
  again.
- A Level 1 answer fell back (offline, error) and was later checked: it counts as answered at
  Level 1 when submitted, not when checked.
- A section with only Level 1 (one key idea): after answering, it is immediately "all levels done".
- The device clock or time zone changes: "a later day" uses the device's local calendar day at the
  time of the read.
- Pack update adds a level to a section the reader already finished: the section is no longer
  "all levels done", and the next read offers the new level.
- The reader caught every idea at Level 1: later levels are still offered, since they ask
  different kinds of questions. Questions are chosen by the primary rule.
- The alternate is used and then the pack retires the alternate: the reflection stays intact from
  its snapshot.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST serve exactly one question per section per read.
- **FR-002**: The level served MUST be the lowest level not yet answered. A level advances only
  after a submitted answer at the current level, and only on a later local calendar day than the
  previous answer for that section.
- **FR-003**: Within a level, the app MUST choose the active question whose targets include the
  most not-yet-caught key ideas, falling back to the pack's primary question.
- **FR-004**: The app MUST record, per section, the question IDs answered, skipped and swapped,
  and the level and day of each answer.
- **FR-005**: The app MUST offer "Not a helpful question?" only when the current level has an
  active, unused alternate, at most once per level, and swap in place while keeping the draft.
- **FR-006**: Results MUST count caught ideas across all reads of the section, tag ideas first
  caught on this read as "New", and show earlier reads behind a "Your first-read reflection"
  disclosure (or one row per earlier read).
- **FR-007**: The results footer MUST read "Next time you read this section: a harder Level N
  question." or "You've answered every level for this section."
- **FR-008**: The collapsed and asking labels on later reads MUST use the "Second read · a harder
  question" wording (and "Third read" for Level 3), with the scope.
- **FR-009**: Retired questions MUST never be served as new questions. Reflections that used them
  stay complete from their snapshot.
- **FR-010**: Level progress MUST sync with the reader's other progress (spec 005).
- **FR-011**: No question is generated live. These later-read questions are the app's follow-up
  questions, and every question served comes from the pack.

### Key Entities

- **Question history** (device + iCloud): question IDs answered, skipped, swapped, with day and
  level.
- **Section progress** (device + iCloud): current level, last answered day, caught idea IDs,
  swapped levels, all-levels-done flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tests, a section answered on day N offers the next level on day N+1 and
  never the same day.
- **SC-002**: When a level has two questions, the served question targets at least one uncaught
  idea whenever such a question exists, 100% of the time.
- **SC-003**: Mark at launch provides at least two reads' worth of fresh questions for at least 80%
  of prompted sections.
- **SC-004**: Testers who re-read a section answer the later-read question at a rate within 10
  percentage points of their first-read answer rate.

## Assumptions

- "A later day" means a later local calendar day. This prevents level-farming in one session and
  matches "on a later day" in DESIGN.md.
- Later levels are not separately paywalled. The free allowance (3 reflections in total, spec 006)
  applies to every level equally, which settles the brief's open question in practice.
- Skipping does not advance the level and does not count as a read for leveling.
- Reading a section in Read mode does not advance its level.
- The brief's earlier rotation by question type ("meaning first, application later") is
  superseded by levels.
