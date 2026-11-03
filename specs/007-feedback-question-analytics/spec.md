# Feature Specification: Feedback and Question Analytics

**Feature Branch**: `007-feedback-question-analytics`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Feedback and question analytics (brief spec 8): anonymous per-question
counts (shown, answered, skipped, 'not helpful', and how often each targeted idea was caught) feed
a review queue for the content owner. The worst performers come first, and a maintenance run can
retire or replace weak questions and swap levels whose difficulty is inverted. No answer text and
no personal data."

**References**: brief "Question freshness → Feedback loop", "Level checks", "Validation", data
model rows QuestionStats and PipelineState; constitution principles III, VI, VII. Depends on 003
(compare), 004 ("Not a helpful question?") and 001 (refresh runs).

## User Scenarios & Testing *(mandatory)*

The primary actor is the **content owner**. Readers produce the signals without doing anything
extra.

### User Story 1 - Anonymous question signals are collected (Priority: P1)

As readers use Study mode, the system counts, per question: times shown, answered, skipped, marked
"not helpful", and, for answered questions, how often each targeted key idea was caught. Nothing
identifies the reader, and no answer text is involved.

**Why this priority**: Without signals there is nothing to review. The TestFlight validation
("fewer than about 1 in 10 questions marked not helpful") depends on them.

**Independent Test**: In a test build, show, answer, skip and mark not helpful a known set of
questions. Confirm the aggregate counts match, and that the stored records contain no device ID,
answer text or timestamp finer than a day.

**Acceptance Scenarios**:

1. **Given** a question card opens in the asking state, **When** it is the first time that
   question is shown on this device, **Then** "shown" is counted once for that question.
2. **Given** a reader submits an answer that is checked live, **When** the result is returned,
   **Then** "answered" and each covered target idea's "caught" count go up.
3. **Given** a reader taps Skip or "Not a helpful question?", **When** the action completes,
   **Then** "skipped" or "not helpful" is counted for that question.
4. **Given** the device is offline, **When** events happen, **Then** they are queued on the device
   and sent later, at most once each.
5. **Given** any signal, **When** it is stored, **Then** it holds only the question ID, pack
   version, event type and day, plus covered idea IDs for "answered".

---

### User Story 2 - Review queue, worst first (Priority: P1)

The content owner opens a review report for a book and sees questions ranked worst first, by
not-helpful rate, skip rate and catch-rate anomalies, each with its counts, section, level and
text. They can choose to retire it, request a replacement, or swap levels.

**Why this priority**: Turns signals into better content. This is the brief's "feedback loop".

**Independent Test**: Seed stats where one question has a 30% not-helpful rate and another has a
Level 2 caught more often than its section's Level 1. Confirm both appear at the top with the right
reasons.

**Acceptance Scenarios**:

1. **Given** stats for a book, **When** the owner generates the review report, **Then** questions
   are ranked by a combined weakness score, with the reason shown (high not-helpful, high skip,
   inverted level difficulty, low sample size flagged as such).
2. **Given** a question with too few shows (below a minimum sample), **When** ranked, **Then** it
   is listed separately as "not enough data", not ranked as weak.
3. **Given** a section where Level 2 is caught more often than Level 1, **When** the report is
   generated, **Then** that section is flagged "levels inverted" with both rates.

---

### User Story 3 - Maintenance run fixes weak questions (Priority: P2)

From the review queue, the owner marks questions to retire and sections that need a replacement or
level swap. A targeted refresh run produces new questions for only those sections, reusing the
stored key ideas. It goes through the normal checks and human review, and publishes an additive
pack version.

**Why this priority**: Closes the loop. It reuses the pipeline from spec 001, so the effort is
mostly plumbing.

**Independent Test**: Retire one question and request one replacement in Mark. Run the refresh,
approve and publish. Confirm the new pack keeps every old ID, marks the retired one, adds one new
question, and changes no key ideas.

**Acceptance Scenarios**:

1. **Given** a question marked for retirement, **When** the next version is published, **Then** it
   is present with status retired and is never served as a new question.
2. **Given** a section marked for replacement, **When** the refresh runs, **Then** only that
   section's questions are generated, against its existing key ideas, with new IDs.
3. **Given** a level swap, **When** it is approved, **Then** the two questions' levels change in the
   next pack version, their IDs are unchanged, and saved reflections are unaffected.

### Edge Cases

- A reader marks the same question "not helpful" on two devices: counted twice. This is acceptable
  for aggregate signals.
- A malicious client floods events: events require the same device attestation as compare, and
  they are rate-limited per device per day.
- Pack version changes mid-collection: stats are kept per question ID across versions, and can
  be filtered by version.
- A question that is shown but never answered or skipped (the reader scrolled past): it counts as
  shown only. The skip rate uses explicit skips.
- Analytics collection fails: the reader experience is never affected. Events are best-effort.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST collect per-question counts of: shown (first time per device), answered
  (live-checked), skipped, not helpful, and per-target-idea caught counts.
- **FR-002**: Signals MUST be anonymous: no device identifier, account, IP address, answer text or
  sub-day timestamp is stored with them.
- **FR-003**: "Answered" and "caught" counts MUST be recorded by the compare service from the
  result, never from answer text.
- **FR-004**: Shown, skipped and not-helpful events MUST be sent from the app, queued while offline,
  sent at most once, and rate-limited per attested device.
  [NEEDS CLARIFICATION: How do app-side events reach the server? (a) a small anonymous events
  endpoint added to `api/openapi.yaml`, which amends the "compare is the only live API" rule in
  CLAUDE.md; (b) piggyback queued events on the next compare call, which loses data from Read-mode
  or free-limit users; (c) use Apple's App Analytics / TelemetryDeck-style third-party analytics.]
- **FR-005**: The owner MUST be able to produce a review report per book that ranks questions by
  weakness (not-helpful rate, skip rate, inverted level difficulty) with a minimum sample size, and
  lists low-data questions separately.
- **FR-006**: The owner MUST be able to mark questions for retirement, replacement or a level swap,
  and run a targeted refresh limited to those sections that reuses stored key ideas.
- **FR-007**: Refresh output MUST go through the same checks, model review, human approval and
  additive publishing as spec 001, and never change or reuse IDs or key ideas.
- **FR-008**: The app's privacy disclosures MUST describe the anonymous usage counts.

### Key Entities

- **Question stats**: question ID, pack version, day, and counts of shown, answered, skipped and not
  helpful, plus caught counts per target idea ID.
- **Review item**: question ID, section, level, weakness reasons, counts, owner decision (retire,
  replace, swap, keep).
- **Refresh run**: book, sections, prompt version, resulting pack version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: During the TestFlight test, the owner can tell for each Mark question whether fewer
  than 1 in 10 readers marked it not helpful.
- **SC-002**: The review report for Mark generates in under 1 minute and lists the 10 worst
  questions with reasons.
- **SC-003**: A targeted refresh of up to 10 sections, from decision to published pack, takes under
  one evening of owner time.
- **SC-004**: An audit of stored analytics finds zero personal data or answer text.
- **SC-005**: After the first refresh cycle, the not-helpful rate of replaced sections drops by at
  least half.

## Assumptions

- Minimum sample before a question is ranked: 20 shows (tunable).
- The review report is produced by the pipeline tooling, in the same review surface chosen in
  spec 001.
- Retire/replace decisions are always made by the owner. The system never retires or swaps on its
  own.
- A seasonal series uses the same refresh machinery, but its content and schedule are V2.
