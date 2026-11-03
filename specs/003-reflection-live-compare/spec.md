# Feature Specification: Reflection, Comparison and Live Compare API

**Feature Branch**: `003-reflection-live-compare`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Reflection, comparison and live API (brief spec 4): in Study mode
each section gets an inline question card under its verses. The reader answers in their own words
(typed or dictated) and taps Submit. A small live AI call compares the answer with the section's
stored key ideas and returns which ideas were covered, a phrase to highlight, a short warm note and
a contradicts-text flag. The same card turns into results: 'What commentators noticed', You
caught / What you missed with sources and verse chips, context, views differ and an Enduring Word
link. Works offline from stored key ideas. Skip, Edit with 2 re-checks, App Attest, server cache by
answer hash, daily cap, no answer text stored on the server."

**References**: [docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Study card states, Question
scope, Submit/edit/cost rules, States with no mockup, Copy reference); mockups
[FeedHybrid.dc.html](../../docs/design/screens/FeedHybrid.dc.html),
[ReaderResults.dc.html](../../docs/design/screens/ReaderResults.dc.html),
[ReaderFallback.dc.html](../../docs/design/screens/ReaderFallback.dc.html); brief "Live comparison"
and "Protecting live AI costs"; constitution principles III, IV, V, VI, VIII, IX. Depends on 001
and 002.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Answer a question and see what commentators noticed (Priority: P1)

Reading Mark 1:1–8 in Study mode, the reader reaches the end of the verses and the question card
opens: "YOUR TURN · VERSE 7", the question in serif, and verse 7 tinted. They type "John knew Jesus
was way more important than him…" and tap Submit. The button reads "Checking…" for a moment, then
the card becomes results:
- their answer, with "wasn't even good enough to be his servant" highlighted;
- a short personal note;
- "You caught 2 of 4" with a 4-segment bar;
- the caught ideas, checked, with their sources;
- What you missed, each idea with its sources and a verse chip;
- a footer with the Enduring Word link.

**Why this priority**: This is the product. Without the think-first, compare-second loop,
ThinkBible is just a Bible reader.

**Independent Test**: With a Mark pack and a working compare service, answer the Mark 1:1–8
question with the worked-example answer from the brief. Confirm the results show the covered ideas
as caught, the highlight, a note under 60 words, and sources taken from the pack.

**Acceptance Scenarios**:

1. **Given** Study mode and "Open questions automatically" on, **When** the reader scrolls past
   the last verse of a section, **Then** that section's question card opens by itself (asking
   state), labelled by scope ("Your turn · verse 7", "verses 7–8" or "the whole passage"). The
   scoped verses are tinted while answering.
2. **Given** an answer under 15 characters, **When** the reader looks at Submit, **Then** it is
   disabled, and the hint reads "Write a sentence or so to compare with the commentators."
3. **Given** a valid answer, **When** Submit is tapped, **Then** the button reads "Checking…" and is
   disabled until the result arrives. A success haptic plays when results appear.
4. **Given** a result with covered ideas, **When** the card shows results, **Then** it shows: the
   answer box ("Verse 7. <question>", the answer with the returned phrase highlighted, Edit);
   "What commentators noticed"; the note; "You caught N of M" with a segmented bar; YOU CAUGHT
   (checked) and WHAT YOU MISSED (empty ring) groups. Each idea shows its title, scope chip, body
   and sources ("Henry, JFB, Clarke agree" for agreed ideas). Then the context note, any views-differ
   note, and the "Enduring Word ↗" link.
5. **Given** results, **When** the reader taps an idea's scope chip ("v. 7"), **Then** those verses
   get the yellow highlight. Tapping it again clears it. "Passage" highlights the whole section.
6. **Given** results, **When** the reader taps the collapse chevron, **Then** the card folds to
   "Your reflection on 1:1–8 · 2 of 4 key ideas · tap to review". Tapping the row reopens results.
7. **Given** the reader's very first submission, **When** they tap Submit, **Then** before anything
   is sent they are told plainly that answers are processed by a third-party AI model, and they
   must agree. If they decline, the answer is saved and they see the commentators-only results.

---

### User Story 2 - Always get results, even without a personal match (Priority: P1)

If the reader skips, says "I don't know", writes something off-topic, is offline, hits an error,
or reaches the daily cap, they still get the section's key ideas right away. The card is headed
"What commentators noticed" and lists every idea under KEY IDEAS, with a one-line explanation of
why there's no personal note.

**Why this priority**: Offline-first and "never judge" are constitutional. The fallback is also
what keeps cost bounded.

**Independent Test**: Submit with airplane mode on, with the service returning 5xx, with a 429,
and with "I don't know". Each shows the full key-idea list instantly with the correct one-line
message, and none uses a re-check.

**Acceptance Scenarios**:

1. **Given** the result covers no ideas (own angle, "I don't know", off-topic), **When** results
   show, **Then** there is no bar and no "You caught" group. The line reads "Your answer took its
   own angle. Here are the key ideas the commentators focused on.", followed by every idea under
   KEY IDEAS.
2. **Given** the device is offline, **When** Submit is tapped, **Then** the answer is saved, the
   fallback results show immediately with "You're offline. We'll check your answer when you're
   back.", and when the connection returns the personal result replaces the fallback.
3. **Given** the service errors or takes more than 10 seconds, **When** Submit is tapped, **Then**
   the fallback shows with "We couldn't check your answer just now. Here's what commentators
   noticed." The app retries once automatically in the background.
4. **Given** the device has reached today's cap, **When** Submit is tapped, **Then** the fallback
   shows with "You've reached today's limit for personal feedback. Here's what commentators
   noticed."
5. **Given** any failed or capped check, **When** it completes, **Then** no re-check and no free
   reflection is used up.

---

### User Story 3 - Gentle handling of contradiction and distress (Priority: P1)

If an answer says something the passage plainly contradicts, the note points back to the text
gently ("Take another look at verse 7, where John says…") and never says "wrong". If an answer
suggests distress or crisis, the app responds with care and shows support resources instead of a
comparison.

**Why this priority**: Safety and "guide, never judge" are non-negotiable for a faith app where
answers turn personal.

**Independent Test**: Submit a set of fixture answers: one contradicting the text, one doctrinally
divergent but consistent with the text, and one with crisis language. Confirm a gentle pointer,
normal results, and a care response with resources, respectively.

**Acceptance Scenarios**:

1. **Given** an answer that contradicts what the passage plainly says, **When** results show,
   **Then** the note gently points to the relevant verse and never uses "wrong" or similar words.
2. **Given** an answer that differs on doctrine but not on what the text says, **When** results
   show, **Then** it is treated as a normal answer, with no contradiction pointer.
3. **Given** an answer containing distress or crisis language, **When** Submit is tapped, **Then**
   no comparison card is shown. A caring message and support resources appear instead.
   [NEEDS CLARIFICATION: Which support resources, for which regions at launch? For example the
   988 Suicide & Crisis Lifeline only (US launch), or a locale-aware list.]

---

### User Story 4 - Edit an answer, within limits (Priority: P2)

After seeing results, the reader taps Edit, refines the answer and taps "Re-check · 2 left". They
get a fresh comparison. After two re-checks the button becomes "Save answer", which keeps the new
text and the existing results without another check.

**Why this priority**: Refining a thought is valuable, but each re-check costs money, so it has to
be bounded.

**Independent Test**: Submit, Edit three times with changed text, and once with unchanged text.
Confirm two live re-checks, then "Save answer" with no live call, and no call for the unchanged
text.

**Acceptance Scenarios**:

1. **Given** results, **When** Edit is tapped, **Then** the answer box reopens with the current
   text, the primary button reads "Re-check · N left", the secondary reads "Cancel", and the note
   explains that changing the answer uses 1 of 2 re-checks.
2. **Given** Edit with unchanged text, **When** the primary button is tapped, **Then** no live call
   is made, the last result is reused, and no re-check is used.
3. **Given** 0 re-checks left, **When** the reader edits and taps "Save answer", **Then** the new
   text is saved with the existing results, with no live call.
4. **Given** Edit, **When** Cancel is tapped, **Then** the card returns to results unchanged.

---

### User Story 5 - Skip a question (Priority: P2)

A reader who doesn't want to answer taps Skip. The section collapses, its header shows "Skipped",
and the folded row reads "Skipped · answer anyway".

**Why this priority**: Skip reduces reflection fatigue, and skip rates feed analytics (spec 007).

**Independent Test**: Skip the Mark 1:9–11 question. The header chip reads "Skipped", and tapping
"answer anyway" reopens the question.

**Acceptance Scenarios**:

1. **Given** the asking state, **When** Skip is tapped, **Then** the card collapses, the sticky
   header chip reads "Skipped", and the skip is recorded on the device.
2. **Given** a skipped section, **When** the reader taps "Skipped · answer anyway", **Then** the
   same question reopens in the asking state.

---

### User Story 6 - Dictate an answer (Priority: P3)

The reader taps the mic in the answer box and speaks. On-device speech recognition fills in the
text, which they can then edit before submitting.

**Why this priority**: Lowers the effort of reflecting. Not essential to the core loop.
[NEEDS CLARIFICATION: Is voice input in the MVP? The brief's MVP table includes it, but its open
questions list "Voice input in the MVP or V2".]

**Independent Test**: Tap the mic, speak a sentence, and confirm the text appears in the answer
box with nothing sent off the device for recognition.

**Acceptance Scenarios**:

1. **Given** the asking state, **When** the mic is tapped for the first time, **Then** speech
   permission is requested. Once granted, dictated text is appended to the answer.
2. **Given** permission is denied, **When** the mic is tapped, **Then** a short message explains
   how to enable it, and typing still works.

### Edge Cases

- A draft is being typed when the app is backgrounded or killed: drafts save automatically as the
  reader types, and they are restored when the section is reopened.
- The reader scrolls away during "Checking…": the result is applied to that section's card when it
  arrives. Scrolling back shows it.
- The reader submits several sections while offline: each is queued and checked in order when
  back online. Results replace fallbacks section by section.
- The returned highlight phrase is not found word for word in the answer: no highlight is shown,
  and the rest of the results show normally.
- The live note fails code checks (too long, names a commentator not attached to a matched idea):
  a template note is used ("You noticed John's humility. Here's what commentators noticed…").
- The returned covered idea IDs include an ID not in this section: it is ignored.
- Identical text resubmitted (same section and question): the server returns the cached result at
  no AI cost.
- An answer in a language other than English: the comparison is attempted, and the note is in
  English. Fallback rules apply if nothing matches.
- App Attest is unavailable (simulator, jailbroken or unsupported device): the call is refused, and
  the fallback is shown.

## Requirements *(mandatory)*

### Functional Requirements

**Question card (app)**

- **FR-001**: In Study mode, each prompted section MUST show one study element whose state is one
  of: collapsedNew, asking, checking, results, folded, skipped (per the DESIGN.md state diagram).
- **FR-002**: With "Open questions automatically" on (default), a section's card MUST open when the
  reader reaches the end of its verses. With it off, the card stays a one-line collapsed row until
  tapped.
- **FR-003**: The card MUST label the question's scope (verse, verses or whole passage), tint those
  verses while asking, and, for whole-passage questions, show "Question covers this whole passage"
  under the sticky header title.
- **FR-004**: The question shown on a first read MUST be the section's Level 1 primary question,
  in the reader's translation wording. Level selection on later reads is specified in 004.
- **FR-005**: Submit MUST be disabled below 15 characters and while a check is running.
- **FR-006**: Drafts MUST save automatically while typing and survive app termination.
- **FR-007**: On the first launch the first question card MUST be open, with one dismissible line
  above it: "Answer in your own words. There are no wrong answers. Then see what the commentators
  noticed."
- **FR-008**: Before the first submission ever, the app MUST disclose that answers are processed by
  a third-party AI model and get the reader's explicit agreement. Without agreement, no answer
  leaves the device, and results come from stored key ideas.

**Results (app)**

- **FR-009**: Results MUST be built by app code from the pack: idea titles, bodies, sources, agreed
  wording, scope chips, context, views-differ and the Enduring Word link. Only the covered idea
  IDs, highlight phrase, note and contradicts flag come from the live result.
- **FR-010**: Results MUST show the personal variant when at least one idea is covered, and the
  fallback variant ("KEY IDEAS", no bar) otherwise, with the state-specific one-line message for
  offline, error and cap.
- **FR-011**: Scope chips MUST toggle a yellow highlight on their verses. Only one range is
  highlighted at a time.
- **FR-012**: Each reflection MUST be saved on the device with: section ID, question ID, level,
  answer text, covered idea IDs, highlight, note, translation, pack version, created time, check
  status (pending, checked, fallback), and a snapshot of the question and key ideas as shown.
- **FR-013**: Pending (unchecked) reflections MUST be checked automatically when connectivity
  returns, and their results updated in place.
- **FR-014**: Edit MUST allow 2 re-checks per question. Unchanged text never triggers a call.
  After the limit, "Save answer" saves text only.
- **FR-015**: Skip MUST collapse the card, mark the section skipped, and allow "answer anyway".
- **FR-016**: If voice input is in scope, it MUST use on-device recognition only.

**Compare service**

- **FR-017**: The compare service MUST accept only: the answer text, section ID, question ID, pack
  version and translation. No other user data is sent.
- **FR-018**: The service MUST load that section's key ideas and context from the published pack
  (never raw commentary) and ask the comparison model for exactly: covered idea IDs, a highlight
  phrase quoted from the answer, a note (2–3 sentences, under 60 words), and a contradicts-text
  flag (true only when the answer contradicts what the passage plainly says, never for doctrinal
  difference).
- **FR-019**: The model instructions MUST forbid new interpretations, verses or facts, and require
  the tone rules: lead with what the person noticed, never "wrong", never preach, plain and warm.
- **FR-020**: The service MUST validate model output. It drops unknown idea IDs, and replaces the
  note with a template when it is too long or names a commentator not attached to a matched idea.
- **FR-021**: The service MUST detect distress or crisis language and return a distinct outcome so
  the app shows the care response instead of results.
- **FR-022**: The service MUST verify each request comes from a genuine app instance on a real
  device (App Attest) and refuse others.
- **FR-023**: The service MUST cache results by section, question and a hash of the answer text,
  and return cached results without a model call.
- **FR-024**: The service MUST enforce a daily per-device cap (default 30 live comparisons) and
  return a distinct "cap reached" outcome over it.
- **FR-025**: The service MUST reserve a distinct "free limit reached" outcome for the entitlement
  rules defined in spec 006.
- **FR-026**: The service MUST never write answer text to logs, traces, metrics, error reports or
  storage. It exists only in memory for the duration of the call.
- **FR-027**: Spend on the comparison model MUST be alarmed, and devices hitting the cap several
  days running MUST be alarmed.
- **FR-028**: The compare contract MUST be defined in `api/openapi.yaml` and shared by the service
  and the app's API client, with contract tests on both sides.

**Accessibility**

- **FR-029**: The question card MUST announce "Question about verse N" (or "verses A to B", "the
  whole passage"). Idea rows MUST read "Caught" or "Not yet caught" before the title. The mic,
  collapse and other icon buttons MUST have labels.

### Key Entities

- **Reflection** (device + user's iCloud): see FR-012.
- **Section progress** (device + user's iCloud): section ID, caught idea IDs, skipped flag,
  re-check counts per question, card state.
- **Compare request**: answer text, section ID, question ID, pack version, translation, device
  attestation. Never persisted.
- **Compare result**: covered idea IDs, highlight phrase, note, contradicts flag, or an outcome
  (care, cap reached, free limit reached).
- **Device usage counter** (server): device key, day, live comparisons used. No answer content.
- **Result cache entry** (server): section, question, answer hash → result. Short-lived.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of live comparisons return results within 2 seconds of Submit on a normal
  connection.
- **SC-002**: When offline or on error, fallback results appear in under 0.5 seconds, 100% of the
  time.
- **SC-003**: Average AI cost per live comparison is under $0.003, and no device can exceed about
  $0.06 of AI cost per day.
- **SC-004**: Zero occurrences of answer text in server logs, traces or storage, verified by an
  automated scan of logs produced during the test suite and a staging soak.
- **SC-005**: On a labelled set of at least 50 sample answers for Mark, covered-idea matching
  agrees with the owner's judgment at least 85% of the time.
- **SC-006**: 0% of sampled notes contain "wrong" or similar judgment words, or commentator names
  not attached to matched ideas.
- **SC-007**: In the TestFlight test, most testers still submit reflections in week 2.

## Assumptions

- The comparison model is a fast, Haiku-class model on the backend. An on-device model is a later
  option.
- The paywall, the free-reflection count and its "N of 3 free reflections left" line are specified
  in spec 006. Until then, every device is treated as entitled.
- The "Not a helpful question?" link and level progression are specified in 004. Analytics events
  (shown, skipped, not helpful) are specified in 007.
- Text checks for distress run on the server as part of the compare call. A conservative on-device
  check MAY also run so that the care response works offline.
- "Try a different question" from the brief's MVP table is replaced by levels and "Not a helpful
  question?" (per the brief's Question freshness section and DESIGN.md).
- Result cache entries expire after a short period (for example 30 days) and hold no answer text.
