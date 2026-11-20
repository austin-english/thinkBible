# Feature Specification: Question Sequence and Weekly Unlocks

**Feature Branch**: `004-question-levels-rereads` (folder name kept from the earlier "Question
levels and re-reads" draft)

**Created**: 2026-11-03

**Updated**:
- 2026-11-10: rewritten for the "book feel" design. The next question unlocks a set time after the
  previous answer, not on a re-read, and a local notification brings the reader back.
- 2026-11-17 (constitution v1.3.0): **no levels.** A section has up to three questions in a fixed
  order, aimed at the passage's main ideas. The next one unlocks **a week** after the previous
  answer, not 24 hours. Hidden alternates are gone: "Not a helpful question?" moves on to the next
  question.

**Status**: Draft

**Input**: User description: "Question sequence and unlocks (brief spec 5): each section has up to
three questions in a fixed order, shown one at a time. A section starts with its first question. A
week after a question is answered, the next one unlocks. The new question sits at the top of the
card's comments with a 'New' tag, and the earlier thread folds behind 'Show more'. One local
notification per chapter brings the reader back, folded into the daily reminder when that's on.
Permission is asked once, in the card, after the first answer. Everything runs on the device.
'Not a helpful question?' in the card's … menu moves on to the next question."

**References**: [docs/design/README.md](../../docs/design/README.md) (Next-question unlock, `…`
menu, Answered thread → footer note, Progress model); screens
[04-answered.png](../../docs/design/screens/04-answered.png),
[11-notify-prompt.png](../../docs/design/screens/11-notify-prompt.png),
[12-notification.png](../../docs/design/screens/12-notification.png),
[13-level-2-unlocked.png](../../docs/design/screens/13-level-2-unlocked.png),
[14-level-1-opened.png](../../docs/design/screens/14-level-1-opened.png),
[15-panel-new.png](../../docs/design/screens/15-panel-new.png) (screens 11, 13 and 14 still show
the older "level" and "tomorrow" copy; the README's text wins);
[docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Question sequence); brief "Question
freshness" and "Next-question unlock (one week)"; constitution principles III, VII. Depends on 001
(ordered questions in the pack), 002 (feed and panel) and 003 (question footer and compare).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The next question unlocks a week later (Priority: P1)

A reader answers Mark 1:1–8's first question on a Monday at 8:10 pm. The reply's footer line reads
"Next question unlocks in a week · Enduring Word". Opening the section again that week shows the
same thread and no new question. The next Monday at 8:10 pm, the second question unlocks. The
card's comments now read newest first: the second question from ThinkBible with a "New" tag
("· question on verses 7–8"), "Add your answer…", then a plain "—— Show more" link. Tapping it
opens the earlier question, answer and reply underneath, and the link reads "Show less". The meta
line reads "MARK 1 · SECTION 1 OF 9 · QUESTION 2".

**Why this priority**: Spacing the questions out gives readers a reason to come back and matches
how people read the Bible: they rarely return to the same passage within days. It is a core
Premium benefit.

**Independent Test**: With an injected clock, answer the first question at T. At T+6d23h59m
confirm no second question. At T+7d confirm it shows with "New" at the top and the first thread
behind "Show more". Answer it and confirm its thread stacks above "Show more" and, if a third
question exists, the footer reads "Next question unlocks in a week".

**Acceptance Scenarios**:

1. **Given** a section never answered, **When** its card shows, **Then** it asks the section's
   first active question.
2. **Given** question N was answered at time T, **When** the reader opens the section before
   T+7 days, **Then** no new question is shown. Leaving and reopening the section never advances it.
3. **Given** question N was answered at T and the section has another active question, **When** the
   app is launched or returns to the foreground at or after T+7 days, **Then** the next question is
   unlocked: it shows at the top of the card's comments with a "New" tag and "Add your answer…",
   and the earlier threads fold behind "Show more".
4. **Given** "Show more", **When** tapped, **Then** each earlier question (labelled "· verse 7"),
   answer with its highlight, and reply show underneath, newest first, and the link reads
   "Show less".
5. **Given** a reply on a question that isn't the section's last, **When** its footer line shows,
   **Then** it reads "Next question unlocks in a week", followed by the Enduring Word link.
6. **Given** an unlocked question, **When** the reply shows, **Then** "You caught N of M" counts
   ideas caught on any of the section's questions.

---

### User Story 2 - One notification per chapter brings me back (Priority: P1)

The reader answered three sections of Mark 1 last week. Today, at the earliest unlock time among
them, one notification arrives: "3 new questions are ready in Mark 1 / You answered these last
week. Each one opens another side of the passage." Tapping it opens the feed at the first unlocked
section.

**Why this priority**: A week is long enough to forget. Without the nudge, most readers never see
the follow-up questions.

**Independent Test**: With an injected clock and a fake notification center, answer three sections
of Mark 1 and one of Mark 2. Confirm exactly one pending notification per chapter, that each new
answer in a chapter replaces that chapter's pending one with an updated count, and that tapping
opens the first unlocked section.

**Acceptance Scenarios**:

1. **Given** a checked answer with a next question, **When** it is saved, **Then** the app sets
   `unlocksAt = answeredAt + 7 days` for that section and cancels and reschedules that chapter's
   single pending notification (identifier `unlock.<book>.<chapter>`) at the earliest `unlocksAt` in
   the chapter, with the current count.
2. **Given** one unlocking section in the chapter, **When** the notification is built, **Then** it
   reads "A new question is ready for Mark 1:1–8" with the question as a teaser. With several, it
   reads "N new questions are ready in Mark 1".
3. **Given** the daily reading reminder (spec 006) is on, **When** an unlock falls on a day the
   reminder fires, **Then** the unlock is folded into the reminder's text instead of a second
   notification. At most one ThinkBible notification fires per day.
4. **Given** a free user with no free reflections left, **When** the notification is built, **Then**
   it reads "Your next question is ready · Premium / Mark 1:1–8 is waiting. You've used your 3 free
   reflections."
5. **Given** the reader taps a notification, **When** the app opens, **Then** the feed opens at the
   first unlocked section in that chapter.
6. **Given** notifications are not allowed or New-question alerts is off, **When** a question
   unlocks, **Then** nothing is scheduled, and the unlocked question still shows the next time the
   app opens.
7. **Given** the section's last question is answered, **When** it is saved, **Then** nothing more
   is scheduled for that section.

---

### User Story 3 - Ask for notification permission once, in context (Priority: P2)

Under the reader's first answer ever, below the reply, a card asks "Want a nudge when it's ready?
One notification when your next question unlocks. Not a daily ping." with Not now and Notify me.

**Why this priority**: Asking at launch gets refused. Asking right after the first answer explains
why.

**Independent Test**: On a fresh install, post the first answer and confirm the prompt shows once.
Tap either button, post another answer, relaunch, and confirm it never appears again.

**Acceptance Scenarios**:

1. **Given** the reader's first answer ever, **When** the reply shows, **Then** the notify prompt
   appears under it.
2. **Given** the reader taps Notify me, **When** the system prompt is answered, **Then** the card
   shows "✓ We'll let you know when it's ready." for the rest of that session only.
3. **Given** the reader taps either button, **When** any later answer shows, **Then** the prompt
   never returns (a stored `notifyPromptShown` flag), and only the small unlock line shows. The
   switch lives in Settings (New-question alerts, spec 006).

---

### User Story 4 - "Not a helpful question?" (Priority: P2)

In the card's `…` menu, if the section has another active question after the current one, "Not a
helpful question?" is shown. Choosing it replaces the current question in place with the next one,
without waiting a week, and shows "Thanks for the feedback. Here's another question on this
passage."

**Why this priority**: Gives readers an escape from a weak question and feeds the review queue
(spec 007).

**Independent Test**: On a section with two or more questions, choose "Not a helpful question?" on
the first. The second appears, the skip persists after relaunch, and the skipped question is
recorded as not helpful.

**Acceptance Scenarios**:

1. **Given** an unanswered current question with another active question after it, **When** the
   `…` menu opens, **Then** "Not a helpful question?" is shown.
2. **Given** it is chosen, **When** the swap happens, **Then** the next question replaces the
   current one in place, with the thank-you line, and any typed draft is kept. The skipped question
   is never offered again in that section.
3. **Given** the current question is the section's last, or it is already answered, **When** the
   menu opens, **Then** the item is not shown; Report a problem is still there.

---

### User Story 5 - See unlocked questions in the chapter panel (Priority: P2)

In the chapter panel, a section with an unlocked, unanswered question shows a "New" pill before its
✓ fraction, and its chapter tile has a small dot. Both clear once that question is answered.

**Why this priority**: Lets a reader find waiting questions without scrolling the whole book.

**Acceptance Scenarios**:

1. **Given** a section with an unlocked, unanswered question, **When** the panel shows its chapter,
   **Then** the row shows "New" and the chapter tile shows the dot. VoiceOver reads "new question".
2. **Given** that question is answered, **When** the panel opens, **Then** the pill and the dot are
   gone (unless another section in the chapter still has one).

---

### User Story 6 - Finishing a section's questions (Priority: P3)

After the reader answers the last question of a section, the reply footer reads "All questions
done", and nothing more unlocks.

**Acceptance Scenarios**:

1. **Given** a section with Q active questions, **When** the last is answered, **Then** the footer
   reads "All questions done", no `unlocksAt` is set, and no notification is scheduled.
2. **Given** all questions are done, **When** the reader returns, **Then** the newest thread shows
   with earlier ones behind "Show more", and no new question is offered.

### Edge Cases

- A section with only one question (one key idea): after answering, it is immediately "All
  questions done".
- An answer fell back (offline, error) and was checked later: the week starts when the answer was
  posted, not when it was checked.
- The reader caught every idea on the first question: later questions still unlock, since they open
  other sides of the passage.
- The device clock is changed forward: a question can unlock early. This is accepted for a reading
  app.
- Two devices on the same iCloud: `unlocksAt` syncs, so both show the unlock. Each device may
  schedule its own notification. Accepted for v1; a server could dedupe later.
- A pack update adds a question to a finished section: it is no longer "All questions done", and the
  new question unlocks a week after the last answer (immediately if that's already past).
- A pack update retires the question the reader is on before they answer it: the next active
  question takes its place at once. A reflection on a retired question stays intact from its
  snapshot.
- Show questions is off: unlocks still happen and notifications still fire if alerts are on.
  Tapping one opens the section with its question hidden. [Assumption: the alert switch, not Show
  questions, controls notifications.]
- Many sections answered at different times in one chapter: the notification fires at the earliest
  `unlocksAt`. Sections unlocking later that day are counted in the next notification, at most one
  per day.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST show exactly one open question per section at a time.
- **FR-002**: The next question MUST unlock only when both gates pass: the previous question was
  answered, AND the current time is at or after `unlocksAt = previous answeredAt + 7 days`.
  Opening, scrolling past or re-reading a section MUST NOT advance it.
- **FR-003**: Unlocks MUST be evaluated on launch and on return to the foreground, from the stored
  `unlocksAt`, with an injectable clock for tests.
- **FR-004**: The app MUST serve a section's active questions in pack order (`questions[]`),
  skipping questions already answered or skipped. There is no per-reader choice between questions.
- **FR-005**: The app MUST record, per section, the question IDs answered and skipped, the number
  answered, `answeredAt` per question, and `unlocksAt`.
- **FR-006**: An unlocked question MUST show at the top of the card's comments with a "New" tag,
  then "Add your answer…", then "Show more" / "Show less" for earlier threads. Answered questions
  stack above "Show more", newest first. The meta line adds "· QUESTION N".
- **FR-007**: Reply footer lines MUST read "Next question unlocks in a week" or "All questions
  done", followed by the Enduring Word link.
- **FR-008**: The app MUST keep at most one pending local notification per chapter (identifier
  `unlock.<book>.<chapter>`), cancelled and rescheduled on every answer in that chapter at the
  earliest `unlocksAt` with the current count, and fire at most one ThinkBible notification per
  day. When the daily reminder is on, unlocks fold into the reminder instead.
- **FR-009**: Notification copy MUST follow `docs/design/README.md`: several sections, one section
  (with the question as teaser), and the honest free-user variant.
- **FR-010**: Tapping an unlock notification MUST open the feed at the first unlocked section in
  that chapter (spec 002 FR-016).
- **FR-011**: The in-card notify prompt MUST appear once ever, under the first answer, and never
  again after either button. Notify me requests system permission. New-question alerts in Settings
  turns scheduling on and off.
- **FR-012**: The app MUST offer "Not a helpful question?" in the `…` menu only when the current
  question is unanswered and another active question follows it. Choosing it serves that next
  question at once, in place, keeping the draft, and records the skip (spec 007).
- **FR-013**: The chapter panel MUST show a "New" pill on sections with an unlocked, unanswered
  question and a dot on their chapter tile, both cleared once answered.
- **FR-014**: Retired questions MUST never be served as new questions. Reflections that used them
  stay complete from their snapshot.
- **FR-015**: Question progress and `unlocksAt` MUST sync with the reader's other progress
  (spec 005).
- **FR-016**: No question is generated live. Unlocked questions are the app's follow-up questions,
  and every one comes from the pack already on the phone. No server, push service or cron job is
  involved.

### Key Entities

- **Section progress** (device + iCloud, spec 005): `answered` (count), `answeredAt` per question,
  `unlocksAt`, skipped question IDs, caught idea IDs.
- **Question history** (device + iCloud): question IDs answered and skipped, with time.
- **Pending unlock notification** (device): chapter, fire date, count, first unlocked section.
- **Notify prompt flag** (device): `notifyPromptShown`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of unit tests with an injected clock, question N+1 is unavailable before
  answeredAt + 7 days and available at or after it, and reopening a section never advances it.
- **SC-002**: In 100% of tests, there is never more than one pending unlock notification per
  chapter, never more than one ThinkBible notification fires per day, and nothing is scheduled after
  a section's last question.
- **SC-003**: Questions are served in pack order 100% of the time, never repeating an answered or
  skipped question.
- **SC-004**: Mark at launch provides at least two questions for at least 80% of prompted sections.
- **SC-005**: In the TestFlight test, at least a third of unlocked questions are answered within a
  week of unlocking.

## Assumptions

- The one-week rule (2026-11-17) replaces the 24-hour rule, which replaced the earlier "a later
  read on a later calendar day" rule. Spacing is a fixed 7 days from the answer, not midnight.
- Difficulty levels were dropped (2026-11-17): difficulty depends on the reader and couldn't be
  measured reliably in the pipeline (spec 001 R11). Questions are ordered by the pipeline instead:
  the first opens the passage's main idea, later ones take up other ideas.
- Follow-up questions are not separately paywalled, but each unlocked question counts as a
  reflection for free users (3 in total, spec 006). With none left, Post opens the paywall.
- Local notifications only (`UNUserNotificationCenter`). Server push is later work and only for
  things the phone can't know.
- Copy variants for notifications live in the design source `UnlockNotification.dc.html`, which is
  not in the repo yet. The README's copy is the source until it is added.
- Constitution v1.3.0 principle III matches this spec: follow-ups are the section's next questions
  in order, unlocking a week after the previous answer, and re-reading never advances them.
