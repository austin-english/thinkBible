# Feature Specification: Question Levels and 24-Hour Unlocks

**Feature Branch**: `004-question-levels-rereads` (folder name kept from the earlier "Question
levels and re-reads" draft)

**Created**: 2026-11-03

**Updated**: 2026-11-10, rewritten for the "book feel" design: the next level now **unlocks 24
hours after the previous level is answered**, not on a re-read on a later day, and a local
notification brings the reader back.

**Status**: Draft

**Input**: User description: "Question levels and unlocks (brief spec 5): each section has up to
three levels (1 notice, 2 interpret, 3 connect), shown one at a time. A section starts at Level 1.
24 hours after a level is answered, the next level unlocks, preferring a question that targets an
idea the reader hasn't caught yet. The new question sits at the top of the card's comments with a
'New' tag, and the earlier thread folds behind 'Show more'. One local notification per chapter
brings the reader back, folded into the daily reminder when that's on. Permission is asked once,
in the card, after the first answer. Everything runs on the device. 'Not a helpful question?' in
the card's … menu swaps in the hidden alternate once."

**References**: [docs/design/README.md](../../docs/design/README.md) (Next-level unlock, `…` menu,
Answered thread → footer note, Progress model); screens
[04-answered.png](../../docs/design/screens/04-answered.png),
[11-notify-prompt.png](../../docs/design/screens/11-notify-prompt.png),
[12-notification.png](../../docs/design/screens/12-notification.png),
[13-level-2-unlocked.png](../../docs/design/screens/13-level-2-unlocked.png),
[14-level-1-opened.png](../../docs/design/screens/14-level-1-opened.png),
[15-panel-new.png](../../docs/design/screens/15-panel-new.png);
[docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Levels); brief "Question freshness" and
"Next-level unlock (24 hours)"; constitution principles III, VII. Depends on 001 (levels and
alternates in the pack), 002 (feed and panel) and 003 (question footer and compare).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The next, harder question unlocks a day later (Priority: P1)

A reader answers Mark 1:1–8's Level 1 question at 8:10 pm. The reply's footer line reads "Harder
question unlocks tomorrow · Enduring Word". Opening the section again that evening shows the same
thread and no new question. At 8:10 pm the next day, Level 2 unlocks. The card's comments now read
newest first: the Level 2 question from ThinkBible with a "New" tag ("· question on verses 7–8"),
"Add your answer…", then a plain "—— Show more" link. Tapping it opens the earlier Level 1
question, answer and reply underneath, and the link reads "Show less". The meta line reads "MARK 1
· SECTION 1 OF 9 · LEVEL 2".

**Why this priority**: Spacing the questions out helps readers remember what they read and gives
them a reason to come back. It is a core Premium benefit.

**Independent Test**: With an injected clock, answer Level 1 at T. At T+23h59m confirm no Level 2.
At T+24h confirm Level 2 shows with "New" at the top and Level 1 behind "Show more". Answer Level 2
and confirm its thread stacks above "Show more" and the footer reads "Level 3 unlocks tomorrow".

**Acceptance Scenarios**:

1. **Given** a section never answered, **When** its card shows, **Then** it asks a Level 1 question.
2. **Given** Level N was answered at time T, **When** the reader opens the section before T+24h,
   **Then** no new question is shown. Leaving and reopening the section never advances the level.
3. **Given** Level N was answered at T and the section has Level N+1, **When** the app is launched
   or returns to the foreground at or after T+24h, **Then** Level N+1 is unlocked: its question
   shows at the top of the card's comments with a "New" tag and "Add your answer…", and the earlier
   threads fold behind "Show more".
4. **Given** "Show more", **When** tapped, **Then** each earlier level's question (labelled "· level
   1 · verse 7"), answer with its highlight, and reply show underneath, newest first, and the link
   reads "Show less".
5. **Given** a reply on a level that isn't the last, **When** its footer line shows, **Then** it
   reads "Harder question unlocks tomorrow" after Level 1 and "Level 3 unlocks tomorrow" after
   Level 2, followed by the Enduring Word link.
6. **Given** an unlocked level, **When** the reply shows, **Then** "You caught N of M" counts ideas
   caught at any level of the section.

---

### User Story 2 - Prefer questions aimed at what you missed (Priority: P1)

When a level has two questions, the app picks the one that targets a key idea the reader hasn't
caught yet. The other stays hidden as the alternate.

**Why this priority**: Targeting missed ideas is what makes later levels teach something new.

**Independent Test**: For a section whose Level 2 has two questions targeting different ideas,
catch one of those ideas at Level 1 and confirm Level 2 serves the question targeting the other.
In the Mark 1:1–8 mock, missing "Water and the Spirit" at Level 1 leads to the Level 2 question
aimed at it.

**Acceptance Scenarios**:

1. **Given** a level with two active questions, **When** choosing which to show, **Then** the app
   shows the one whose targets include the most not-yet-caught ideas. Ties go to the pack's
   primary question.
2. **Given** a level with one active question, **When** choosing, **Then** that question is shown.
3. **Given** a question retired in a newer pack, **When** choosing, **Then** it is never shown as a
   new question. Saved reflections that used it still display from their snapshot.

---

### User Story 3 - One notification per chapter brings me back (Priority: P1)

The reader answered three sections of Mark 1 yesterday. Today, at the earliest unlock time among
them, one notification arrives: "3 harder questions are ready in Mark 1 / You answered these
yesterday. Each one asks a little more of the passage." Tapping it opens the feed at the first
unlocked section.

**Why this priority**: Without the nudge, most readers never see the harder questions.

**Independent Test**: With an injected clock and a fake notification center, answer three sections
of Mark 1 and one of Mark 2. Confirm exactly one pending notification per chapter, that each new
answer in a chapter replaces that chapter's pending one with an updated count, and that tapping
opens the first unlocked section.

**Acceptance Scenarios**:

1. **Given** a checked answer with a next level, **When** it is saved, **Then** the app sets
   `unlocksAt = answeredAt + 24h` for that section and cancels and reschedules that chapter's single
   pending notification (identifier `unlock.<book>.<chapter>`) at the earliest `unlocksAt` in the
   chapter, with the current count.
2. **Given** one unlocking section in the chapter, **When** the notification is built, **Then** it
   reads "A harder question is ready for Mark 1:1–8" with the question as a teaser. With several,
   it reads "N harder questions are ready in Mark 1".
3. **Given** the daily reading reminder (spec 006) is on, **When** an unlock falls on a day the
   reminder fires, **Then** the unlock is folded into the reminder's text instead of a second
   notification. At most one ThinkBible notification fires per day.
4. **Given** a free user with no free reflections left, **When** the notification is built, **Then**
   it reads "Your harder question is ready · Premium / Mark 1:1–8 is waiting. You've used your 3 free
   reflections."
5. **Given** the reader taps a notification, **When** the app opens, **Then** the feed opens at the
   first unlocked section in that chapter.
6. **Given** notifications are not allowed or Harder-question alerts is off, **When** a level
   unlocks, **Then** nothing is scheduled, and the unlocked question still shows the next time the
   app opens.
7. **Given** Level 3 (or the section's last level) is answered, **When** it is saved, **Then**
   nothing more is scheduled for that section.

---

### User Story 4 - Ask for notification permission once, in context (Priority: P2)

Under the reader's first answer ever, below the reply, a card asks "Want a nudge when it's ready?
One notification when your harder question unlocks. Not a daily ping." with Not now and Notify me.

**Why this priority**: Asking at launch gets refused. Asking right after the first answer explains
why.

**Independent Test**: On a fresh install, post the first answer and confirm the prompt shows once.
Tap either button, post another answer, relaunch, and confirm it never appears again.

**Acceptance Scenarios**:

1. **Given** the reader's first answer ever, **When** the reply shows, **Then** the notify prompt
   appears under it.
2. **Given** the reader taps Notify me, **When** the system prompt is answered, **Then** the card
   shows "✓ We'll let you know tomorrow when it's ready." for the rest of that session only.
3. **Given** the reader taps either button, **When** any later answer shows, **Then** the prompt
   never returns (a stored `notifyPromptShown` flag), and only the small unlock line shows. The
   switch lives in Settings (Harder-question alerts, spec 006).

---

### User Story 5 - "Not a helpful question?" (Priority: P2)

In the card's `…` menu, if the current level has a hidden alternate that hasn't been used, "Not a
helpful question?" is shown. Choosing it replaces the question in place with the alternate and
shows "Thanks for the feedback. Here's another question at this level."

**Why this priority**: Gives readers an escape from a weak question and feeds the review queue
(spec 007).

**Independent Test**: On a level with an alternate, choose "Not a helpful question?". The alternate
appears, the menu item disappears, and the swap persists after relaunch.

**Acceptance Scenarios**:

1. **Given** an unanswered current level with an unused alternate, **When** the `…` menu opens,
   **Then** "Not a helpful question?" is shown.
2. **Given** it is chosen, **When** the swap happens, **Then** the alternate replaces the question in
   place, with the thank-you line, and any typed draft is kept.
3. **Given** the swap was used for this level, or the level has no alternate, or it is already
   answered, **When** the menu opens, **Then** the item is not shown.

---

### User Story 6 - See unlocked questions in the chapter panel (Priority: P2)

In the chapter panel, a section with an unlocked, unanswered level shows a "New" pill before its
✓ fraction, and its chapter tile has a small dot. Both clear once that level is answered.

**Why this priority**: Lets a reader find waiting questions without scrolling the whole book.

**Acceptance Scenarios**:

1. **Given** a section with an unlocked, unanswered level, **When** the panel shows its chapter,
   **Then** the row shows "New" and the chapter tile shows the dot. VoiceOver reads "new question".
2. **Given** that level is answered, **When** the panel opens, **Then** the pill and the dot are
   gone (unless another section in the chapter still has one).

---

### User Story 7 - Finishing every level (Priority: P3)

After the reader answers the last available level of a section, the reply footer reads "All levels
done", and nothing more unlocks.

**Acceptance Scenarios**:

1. **Given** a section with L levels, **When** level L is answered, **Then** the footer reads "All
   levels done", no `unlocksAt` is set, and no notification is scheduled.
2. **Given** all levels are done, **When** the reader returns, **Then** the newest thread shows with
   earlier ones behind "Show more", and no new question is offered.

### Edge Cases

- A section with only Level 1 (one key idea): after answering, it is immediately "All levels done".
- A Level 1 answer fell back (offline, error) and was checked later: the 24 hours start when the
  answer was posted, not when it was checked.
- The reader caught every idea at Level 1: later levels still unlock, since they ask different kinds
  of questions. Questions are chosen by the primary rule.
- The device clock is changed forward: a level can unlock early. This is accepted for a reading app.
- Two devices on the same iCloud: `unlocksAt` syncs, so both show the unlock. Each device may
  schedule its own notification. Accepted for v1; a server could dedupe later.
- A pack update adds a level to a finished section: it is no longer "All levels done", and the new
  level unlocks 24 hours after the last answer (immediately if that's already past).
- The alternate is used and then the pack retires it: the reflection stays intact from its snapshot.
- Show questions is off: unlocks still happen and notifications still fire if alerts are on.
  Tapping one opens the section with its question hidden. [Assumption: the alert switch, not Show
  questions, controls notifications.]
- Many sections answered at different times in one chapter: the notification fires at the earliest
  `unlocksAt`. Sections unlocking later that day are counted in the next notification, at most one
  per day.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST show exactly one open question per section at a time.
- **FR-002**: A level MUST unlock only when both gates pass: the previous level was answered, AND
  the current time is at or after `unlocksAt = previous answeredAt + 24h`. Opening, scrolling past
  or re-reading a section MUST NOT advance the level.
- **FR-003**: Unlocks MUST be evaluated on launch and on return to the foreground, from the stored
  `unlocksAt`, with an injectable clock for tests.
- **FR-004**: Within a level, the app MUST choose the active question whose targets include the
  most not-yet-caught key ideas, falling back to the pack's primary question.
- **FR-005**: The app MUST record, per section, the question IDs answered and swapped, the level
  reached, `answeredAt` per level, and `unlocksAt`.
- **FR-006**: An unlocked level MUST show at the top of the card's comments with a "New" tag, then
  "Add your answer…", then "Show more" / "Show less" for earlier threads. Answered levels stack
  above "Show more", newest first. The meta line adds "· LEVEL N".
- **FR-007**: Reply footer lines MUST read "Harder question unlocks tomorrow", "Level 3 unlocks
  tomorrow" or "All levels done", followed by the Enduring Word link.
- **FR-008**: The app MUST keep at most one pending local notification per chapter (identifier
  `unlock.<book>.<chapter>`), cancelled and rescheduled on every answer in that chapter at the
  earliest `unlocksAt` with the current count, and fire at most one ThinkBible notification per
  day. When the daily reminder is on, unlocks fold into the reminder instead.
- **FR-009**: Notification copy MUST follow `docs/design/README.md`: several sections, one section
  (with the question as teaser), and the honest free-user variant.
- **FR-010**: Tapping an unlock notification MUST open the feed at the first unlocked section in
  that chapter (spec 002 FR-016).
- **FR-011**: The in-card notify prompt MUST appear once ever, under the first answer, and never
  again after either button. Notify me requests system permission. Harder-question alerts in
  Settings turns scheduling on and off.
- **FR-012**: The app MUST offer "Not a helpful question?" in the `…` menu only when the current,
  unanswered level has an active, unused alternate, at most once per level, and swap in place while
  keeping the draft.
- **FR-013**: The chapter panel MUST show a "New" pill on sections with an unlocked, unanswered
  level and a dot on their chapter tile, both cleared once answered.
- **FR-014**: Retired questions MUST never be served as new questions. Reflections that used them
  stay complete from their snapshot.
- **FR-015**: Level progress and `unlocksAt` MUST sync with the reader's other progress (spec 005).
- **FR-016**: No question is generated live. Unlocked questions are the app's follow-up questions,
  and every one comes from the pack already on the phone. No server, push service or cron job is
  involved.

### Key Entities

- **Section progress** (device + iCloud, spec 005): `level` (highest answered), `answeredAt` per
  level, `unlocksAt`, swapped levels, caught idea IDs.
- **Question history** (device + iCloud): question IDs answered and swapped, with level and time.
- **Pending unlock notification** (device): chapter, fire date, count, first unlocked section.
- **Notify prompt flag** (device): `notifyPromptShown`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of unit tests with an injected clock, Level N+1 is unavailable before
  answeredAt + 24h and available at or after it, and reopening a section never advances it.
- **SC-002**: In 100% of tests, there is never more than one pending unlock notification per
  chapter, never more than one ThinkBible notification fires per day, and nothing is scheduled after
  a section's last level.
- **SC-003**: When a level has two questions, the served question targets at least one uncaught
  idea whenever such a question exists, 100% of the time.
- **SC-004**: Mark at launch provides at least two levels of questions for at least 80% of prompted
  sections.
- **SC-005**: In the TestFlight test, at least a third of unlocked questions are answered within 3
  days of unlocking.

## Assumptions

- The 24-hour rule replaces the earlier "a later read on a later calendar day" rule. Spacing is a
  fixed 24 hours from the answer, not midnight.
- Later levels are not separately paywalled, but each unlocked question counts as a reflection for
  free users (3 in total, spec 006). With none left, Post opens the paywall.
- Local notifications only (`UNUserNotificationCenter`). Server push is later work and only for
  things the phone can't know.
- Copy variants for notifications live in the design source `UnlockNotification.dc.html`, which is
  not in the repo yet. The README's copy is the source until it is added.
- The brief's earlier rotation by question type ("meaning first, application later") is
  superseded by levels.
- Constitution v1.1.0 principle III matches this spec: follow-ups unlock 24 hours after the
  previous level is answered, and re-reading never advances a level.
