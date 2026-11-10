# Feature Specification: Question Footer, Reply Thread and Live Compare API

**Feature Branch**: `003-reflection-live-compare`

**Created**: 2026-11-03

**Updated**: 2026-11-10, app side rewritten for the "book feel" design: the study card, Submit,
Skip, results card and folded row are replaced by an inline question footer, composer and reply
thread. The compare service is unchanged.

**Status**: Draft

**Input**: User description: "Question footer, reply thread and live API (brief spec 4): each page
card's footer holds the section's question as a comment from ThinkBible. The reader taps 'Add your
answer…', answers in their own words (typed or dictated) and taps Post. A small live AI call
compares the answer with the section's stored key ideas and returns which ideas were covered, a
phrase to highlight, a short warm note and a contradicts-text flag. The answer appears as the
reader's comment with the phrase highlighted, and ThinkBible replies under it: the note, the ideas
caught with verse tags, 'See what you missed' with sources. Works offline from stored key ideas.
Edit with 2 re-checks, App Attest, server cache by answer hash, daily cap, no answer text stored on
the server."

**References**: [docs/design/README.md](../../docs/design/README.md) (Card → Footer, Composer,
Answered thread); screens [01-feed.png](../../docs/design/screens/01-feed.png),
[03-typing.png](../../docs/design/screens/03-typing.png),
[04-answered.png](../../docs/design/screens/04-answered.png),
[05-expanded.png](../../docs/design/screens/05-expanded.png),
[06-no-match.png](../../docs/design/screens/06-no-match.png);
[docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Question scope, Post/edit/cost rules, States
with no mockup, Copy reference); brief "Live comparison" and "Protecting live AI costs";
constitution principles III, IV, V, VI, VIII, IX. Depends on 001 and 002.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Answer a question and see what commentators noticed (Priority: P1)

Under the pages of Mark 1:1–8, the card's footer shows a comment from ThinkBible: "ThinkBible ·
QUESTION ON VERSE 7" and, in italic serif, "Why do you think John says he isn't worthy to untie the
straps of Jesus's sandals?" The reader taps "Add your answer…". An inline composer opens with a mic
and a Post button, verse 7 gets a soft tint on the page, and the note under the field reads "A
sentence or so · 2 of 3 free reflections left". They type "John knew Jesus was way more important
than him…" and tap Post. The note reads "Checking with the commentators…", then the thread appears:
- a status line, "✓ You caught 2 of 4 key ideas";
- their answer as a "You" comment with "wasn't even good enough to be his servant" highlighted, and
  Edit under it;
- an indented ThinkBible reply "· from Henry, JFB & Clarke": a short note, then the two caught
  ideas, each with a filled check and a "· v. 7" tag;
- "— See what you missed (2)";
- a footer line from spec 004 ("Harder question unlocks tomorrow") and the Enduring Word link.

Tapping "See what you missed (2)" expands every idea, caught first and then missed (hollow circle),
each with its body and sources, and the toggle reads "Hide details".

**Why this priority**: This is the product. Without the think-first, compare-second loop,
ThinkBible is just a Bible reader.

**Independent Test**: With a Mark pack and a working compare service, answer the Mark 1:1–8
question with the worked-example answer from the brief. Confirm the thread shows the covered ideas
as caught, the highlight, a note under 60 words, and sources taken from the pack.

**Acceptance Scenarios**:

1. **Given** Show questions is on and a prompted section, **When** its card is on screen, **Then**
   the footer shows the ThinkBible question comment, labelled by scope ("· question on verse 7",
   "on verses 7–8" or "on the whole passage"), the question in full whatever the passage length,
   an "Add your answer…" row, and the meta line "MARK 1 · SECTION 1 OF 9".
2. **Given** the reader taps "Add your answer…", **When** the composer opens, **Then** it is inline
   in the card (no sheet), with a mic and Post, and the question's verses are tinted on the page
   (none for a whole-passage question).
3. **Given** an answer under 15 characters, **When** the reader looks at Post, **Then** it is
   disabled, and the note reads "A sentence or so" (plus the free count from spec 006).
4. **Given** a valid answer, **When** Post is tapped, **Then** Post is disabled and the note reads
   "Checking with the commentators…" until the result arrives. A success haptic plays when the
   reply appears.
5. **Given** a result with covered ideas, **When** the thread shows, **Then** it shows the status
   line "✓ You caught N of M key ideas", the "You" comment with the returned phrase highlighted and
   Edit, and the ThinkBible reply with the note and the caught ideas (filled check, title, scope
   tag), then "See what you missed (n)" and the footer line.
6. **Given** the collapsed reply, **When** the reader taps "See what you missed (n)", **Then** it
   expands to every key idea, caught first then missed, each with body and sources ("Henry, JFB,
   Clarke agree" for agreed ideas), then the context note and any views-differ note, and the toggle
   reads "Hide details".
7. **Given** the reader's very first Post, **When** they tap it, **Then** before anything is sent
   they are told plainly that answers are processed by a third-party AI model, and they must agree.
   If they decline, the answer is saved and they see the commentators-only reply.

---

### User Story 2 - Always get a reply, even without a personal match (Priority: P1)

If the reader says "I don't know", writes something off-topic, is offline, hits an error, or
reaches the daily cap, they still get the section's key ideas right away. The status line reads
"✓ Answered", and the reply has a one-line explanation of why there's no personal note.

**Why this priority**: Offline-first and "never judge" are constitutional. The fallback is also
what keeps cost bounded.

**Independent Test**: Post with airplane mode on, with the service returning 5xx, with a 429, and
with "I don't know". Each shows the reply instantly with the correct one-line message, and none
uses a re-check.

**Acceptance Scenarios**:

1. **Given** the result covers no ideas (own angle, "I don't know", off-topic), **When** the thread
   shows, **Then** the status line reads "✓ Answered", the note reads "Your answer took its own
   angle. Here's what the commentators focused on.", no ideas are listed as caught, and the toggle
   reads "See N key ideas".
2. **Given** the device is offline, **When** Post is tapped, **Then** the answer is saved, the
   fallback reply shows immediately with "You're offline. We'll check your answer when you're
   back.", and when the connection returns the personal reply replaces it.
3. **Given** the service errors or takes more than 10 seconds, **When** Post is tapped, **Then** the
   fallback shows with "We couldn't check your answer just now. Here's what commentators noticed."
   The app retries once automatically in the background.
4. **Given** the device has reached today's cap, **When** Post is tapped, **Then** the fallback
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

**Independent Test**: Post a set of fixture answers: one contradicting the text, one doctrinally
divergent but consistent with the text, and one with crisis language. Confirm a gentle pointer,
a normal reply, and a care response with resources, respectively.

**Acceptance Scenarios**:

1. **Given** an answer that contradicts what the passage plainly says, **When** the reply shows,
   **Then** the note gently points to the relevant verse and never uses "wrong" or similar words.
2. **Given** an answer that differs on doctrine but not on what the text says, **When** the reply
   shows, **Then** it is treated as a normal answer, with no contradiction pointer.
3. **Given** an answer containing distress or crisis language, **When** Post is tapped, **Then** no
   comparison is shown. A caring message and support resources appear in the reply's place instead.
   [NEEDS CLARIFICATION: Which support resources, for which regions at launch? For example the
   988 Suicide & Crisis Lifeline only (US launch), or a locale-aware list.]

---

### User Story 4 - Edit an answer, within limits (Priority: P2)

Under their posted answer the reader taps Edit, refines it and taps "Re-check · 2 left". They get
a fresh reply. After two re-checks the button becomes "Save answer", which keeps the new text and
the existing reply without another check.

**Why this priority**: Refining a thought is valuable, but each re-check costs money, so it has to
be bounded.

**Independent Test**: Post, Edit three times with changed text, and once with unchanged text.
Confirm two live re-checks, then "Save answer" with no live call, and no call for the unchanged
text.

**Acceptance Scenarios**:

1. **Given** a posted answer, **When** Edit is tapped, **Then** the composer reopens inline with the
   current text, the primary button reads "Re-check · N left", a secondary "Cancel" is shown, and the
   note explains that changing the answer uses 1 of 2 re-checks.
2. **Given** Edit with unchanged text, **When** the primary button is tapped, **Then** no live call
   is made, the last result is reused, and no re-check is used.
3. **Given** 0 re-checks left, **When** the reader edits and taps "Save answer", **Then** the new
   text is saved with the existing reply, with no live call. The highlight is dropped if the phrase
   is no longer in the text.
4. **Given** Edit, **When** Cancel is tapped, **Then** the thread returns unchanged.

---

### User Story 5 - Pass on a question by scrolling (Priority: P2)

There is no Skip button. A reader who doesn't want to answer simply keeps scrolling. The question
stays in the footer, ready to answer later, and the section counts as Read (spec 005).

**Why this priority**: Answering is optional, which is the main answer to reflection fatigue. Pass
rates feed analytics (spec 007).

**Independent Test**: Scroll past Mark 1:9–11 without answering. Confirm no prompt or interruption,
the section shows "Read" in the chapter panel, and scrolling back shows the same question with
"Add your answer…".

**Acceptance Scenarios**:

1. **Given** an unanswered card, **When** its last page has been on screen and the card scrolls
   past, **Then** nothing interrupts the reader, the question stays answerable, and a "passed"
   event is recorded on the device for spec 007.
2. **Given** a passed section, **When** the reader returns to it, **Then** the same question and
   "Add your answer…" are shown.

---

### User Story 6 - Dictate an answer (Priority: P3)

The reader taps the mic in the composer and speaks. On-device speech recognition fills in the
text, which they can then edit before posting.

**Why this priority**: Lowers the effort of reflecting. Not essential to the core loop.
[NEEDS CLARIFICATION: Is voice input in the MVP? The brief's MVP table includes it, but its open
questions list "Voice input in the MVP or V2".]

**Independent Test**: Tap the mic, speak a sentence, and confirm the text appears in the composer
with nothing sent off the device for recognition.

**Acceptance Scenarios**:

1. **Given** the composer, **When** the mic is tapped for the first time, **Then** speech
   permission is requested. Once granted, dictated text is appended to the answer.
2. **Given** permission is denied, **When** the mic is tapped, **Then** a short message explains
   how to enable it, and typing still works.

### Edge Cases

- A draft is being typed when the app is backgrounded or killed: drafts save automatically as the
  reader types, and they are restored when the card is shown again.
- The reader scrolls away during "Checking…": the reply is applied to that card when it arrives.
  Scrolling back shows it.
- The reader posts on several sections while offline: each is queued and checked in order when
  back online. Replies replace fallbacks card by card.
- The returned highlight phrase is not found word for word in the answer: no highlight is shown,
  and the rest of the reply shows normally.
- No note is returned or it fails code checks (too long, names a commentator not attached to a
  matched idea): a template note is used ("You noticed John's humility. Here's what commentators
  noticed…").
- The returned covered idea IDs include an ID not in this section: it is ignored.
- Identical text reposted (same section and question): the server returns the cached result at
  no AI cost.
- An answer in a language other than English: the comparison is attempted, and the note is in
  English. Fallback rules apply if nothing matches.
- App Attest is unavailable (simulator, jailbroken or unsupported device): the call is refused, and
  the fallback is shown.
- The composer is open on a multi-page card: the verse tint applies on whichever page holds the
  question's verses, and the pager stays where the reader left it.

## Requirements *(mandatory)*

### Functional Requirements

**Question footer and composer (app)**

- **FR-001**: With Show questions on, each prompted section's card MUST show the question footer:
  a ThinkBible comment with the scope label ("· question on verse N", "verses A–B", "the whole
  passage") in rubric small caps, the question in italic serif, always fully visible; an "Add your
  answer…" row with the user's avatar; and the meta line "<BOOK> <CH> · SECTION n OF N".
- **FR-002**: The question shown first MUST be the section's Level 1 primary question, in the
  reader's translation wording. Later levels are specified in 004.
- **FR-003**: Tapping "Add your answer…" MUST open an inline composer in the card (rubric stroke,
  mic, Post) and tint the question's verses on the page while it is open. Post MUST be disabled
  below 15 characters and while a check is running.
- **FR-004**: Drafts MUST save automatically while typing and survive app termination.
- **FR-005**: On first launch, one dismissible line MUST appear above the first composer: "Answer
  in your own words. There are no wrong answers. Then see what the commentators noticed."
- **FR-006**: Before the first Post ever, the app MUST disclose that answers are processed by a
  third-party AI model and get the reader's explicit agreement. Without agreement, no answer
  leaves the device, and the reply comes from stored key ideas.

**Reply thread (app)**

- **FR-007**: The reply MUST be built by app code from the pack: idea titles, bodies, sources,
  agreed wording, scope tags, context, views-differ and the Enduring Word link. Only the covered
  idea IDs, highlight phrase, note and contradicts flag come from the live result.
- **FR-008**: After a Post, the footer MUST show, in order: the status line ("✓ You caught N of M
  key ideas", or "✓ Answered" when nothing matched); the "You" comment with the highlighted phrase
  and Edit; the indented ThinkBible reply ("· from <commentators of the section's ideas>") with the
  note, the caught ideas (filled check, title, scope tag), the "See what you missed (n)" toggle,
  and the footer line (spec 004) with the Enduring Word link.
- **FR-009**: The expanded reply MUST list caught ideas first, then missed ideas (hollow circle),
  each with body and sources, then the context note and any views-differ note, with "Hide details"
  to collapse.
- **FR-010**: With no covered ideas, the reply MUST use the fallback variant ("Your answer took its
  own angle…", "See N key ideas"), with the state-specific one-line message for offline, error and
  cap.
- **FR-011**: Each reflection MUST be saved on the device with: section ID, question ID, level,
  answer text, covered idea IDs, highlight, note, translation, pack version, created time, check
  status (pending, checked, fallback), and a snapshot of the question and key ideas as shown.
- **FR-012**: Pending (unchecked) reflections MUST be checked automatically when connectivity
  returns, and their replies updated in place.
- **FR-013**: Edit MUST allow 2 re-checks per question. Unchanged text never triggers a call.
  After the limit, "Save answer" saves text only.
- **FR-014**: There MUST be no Skip control. Scrolling past an unanswered card records a "passed"
  event for that question and leaves the question answerable.
- **FR-015**: If voice input is in scope, it MUST use on-device recognition only.
- **FR-016**: With Show questions off (spec 006), every question footer, composer and thread MUST
  be hidden. Nothing is deleted, and turning it back on restores them.

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

- **FR-029**: The question footer MUST announce "Question about verse N" (or "verses A to B", "the
  whole passage"). Idea rows MUST read "Caught" or "Not yet caught" before the title. The mic,
  Post, Edit and toggle buttons MUST have labels.

### Key Entities

- **Reflection** (device + user's iCloud): see FR-011.
- **Section progress** (device + user's iCloud, spec 005): caught idea IDs, re-check counts per
  question, draft.
- **Compare request**: answer text, section ID, question ID, pack version, translation, device
  attestation. Never persisted.
- **Compare result**: covered idea IDs, highlight phrase, note, contradicts flag, or an outcome
  (care, cap reached, free limit reached).
- **Device usage counter** (server): device key, day, live comparisons used. No answer content.
- **Result cache entry** (server): section, question, answer hash → result. Short-lived.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of live comparisons return a reply within 2 seconds of Post on a normal
  connection.
- **SC-002**: When offline or on error, the fallback reply appears in under 0.5 seconds, 100% of
  the time.
- **SC-003**: Average AI cost per live comparison is under $0.003, and no device can exceed about
  $0.06 of AI cost per day.
- **SC-004**: Zero occurrences of answer text in server logs, traces or storage, verified by an
  automated scan of logs produced during the test suite and a staging soak.
- **SC-005**: On a labelled set of at least 50 sample answers for Mark, covered-idea matching
  agrees with the owner's judgment at least 85% of the time.
- **SC-006**: 0% of sampled notes contain "wrong" or similar judgment words, or commentator names
  not attached to matched ideas.
- **SC-007**: In the TestFlight test, most testers still post reflections in week 2.

## Assumptions

- The comparison model is a fast, Haiku-class model on the backend. An on-device model is a later
  option.
- The paywall, the free-reflection count and its "N of 3 free reflections left" note are specified
  in spec 006. Until then, every device is treated as entitled.
- "Not a helpful question?" (in the card's `…` menu), the unlock footer line and level progression
  are specified in 004. Analytics events (shown, passed, not helpful) are specified in 007.
- Text checks for distress run on the server as part of the compare call. A conservative on-device
  check MAY also run so that the care response works offline.
- The context note and views-differ note are not drawn in the book-feel screens. They sit at the
  end of the expanded reply, since the brief's comparison card includes them.
- Scope tags ("· v. 7") are labels in the book-feel design. The old tap-to-highlight-verses
  behaviour is dropped.
- The compare API contract is unchanged by the book-feel redesign. "Submit" in the API docs and the
  old copy is "Post" in the app.
- Result cache entries expire after a short period (for example 30 days) and hold no answer text.
