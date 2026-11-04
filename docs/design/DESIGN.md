# ThinkBible: UI design spec (MVP)

Source of truth for the iOS UI. Build in SwiftUI (iOS 17+, Swift 6, Observation, SwiftData).
The mockups in `screens/` are HTML prototypes: read them for exact copy, colors, spacing and
state logic (the `renderVals()` script at the bottom of each file). They need the design-canvas
runtime to run, so treat them as reference, not code to port line by line.

Sample Scripture, questions and commentator ideas in the mockups are placeholders. Real content
comes from the content packs (see "Data the UI reads").

## Screens

| File | Screen | What it shows |
|---|---|---|
| `screens/Main.dc.html` | Home + contents | Continue card, chapter grid, section list with progress |
| `screens/FeedHybrid.dc.html` | Chapter reader | The whole reader. `scene` prop: Answering, Results, Second read, Commentators only |
| `screens/ReaderResults.dc.html` | Reader, results state | Imports FeedHybrid with scene = Results |
| `screens/ReaderDeeper.dc.html` | Reader, second read | Imports FeedHybrid with scene = Second read |
| `screens/ReaderFallback.dc.html` | Reader, no personal match | Imports FeedHybrid with scene = Commentators only |
| `screens/Paywall.dc.html` | Paywall sheet | Over the reader (scene = Free limit) after the 3 free reflections |
| `screens/Settings.dc.html` | Settings | Reading, Study, Appearance, Reminder, Subscription, Your reflections, About. The Appearance switch flips the screen between light and dark |
| `screens/SettingsDark.dc.html` | Settings, dark | Imports Settings with appearance = Dark |

There is no tab bar. Home is the root; Settings is a gear button in Home's header (push navigation).

## Design tokens

### Color

Every token is a named color in the asset catalog with an Any (light) and a Dark appearance.
Never hard-code hex in views. Dark mode is this table, not separate screens. `Settings.dc.html`
(Appearance switch) and `SettingsDark.dc.html` show the dark values on a real screen.

| Token | Light | Dark | Use |
|---|---|---|---|
| `accentText` | #2B4C7E | #8FB0E0 | Links, section refs, labels, checks, progress, scope chip text ("v. 7", "vv. 7–8", "Passage") |
| `accentFill` | #2B4C7E | #3D64A0 | Filled buttons, selected chips, filled checks, switch on (white text on top) |
| `accentPressed` | #1F3A62 | #335588 | Pressed state of filled buttons |
| `accentTint` | #E7EDF6 | #22314A | Tinted chips, "?" badge, mic button, verse tint while answering |
| `background` | #FFFFFF | #121211 | Reader background |
| `paper` | #F6F5F1 | #1C1B19 | Home and Settings background, study card, folded rows |
| `surface` | #FFFFFF | #262522 | Boxes on paper: your answer, answer box, Home cards, grouped rows |
| `fill` | #EFEEE9 | #34332F | Segmented-control track, neutral pills |
| `ink` | #1C1C1E | #F2F1EC | Primary text |
| `inkSecondary` | #5E5E63 | #A3A29B | Labels, captions, meta |
| `inkTertiary` | #8A8A90 | #7C7B75 | Verse numbers, chevrons |
| `bodyMuted` | #3A3A3F | #CFCEC8 | Idea body text |
| `hairline` | #E6E4DD | #3A3935 | Borders, dividers in cards |
| `hairlineLight` | #EFEEE9 | #2E2D2A | Row dividers |
| `highlight` | #FFF1B8 | #5C4B10 | Matched phrase in your answer; verse focused from a v. chip; "New" tag background |
| `highlightInk` | #5C4A00 | #FFE58A | Text on the "New" tag (highlighted answer text stays `ink`) |
| `barEmpty` | #DCDAD2 | #3A3935 | Unfilled progress segments |
| `ringEmpty` | #C9C6BC | #5A5953 | Unchecked idea circle |
| `switchOff` | #DCDAD2 | #4A4945 | Switch track when off |
| `disabled` | #8E9DB4 | #4A5A73 | Submit while disabled or checking (dark: text #C9D3E3) |
| `danger` | #B3261E | #F2B8B5 | "Delete all reflections" |
| `streak` | #B45309 | #F0A04B | Flame icon |
| `scrim` | rgba(20,20,19,0.42) | rgba(0,0,0,0.6) | Behind the paywall sheet |

Dark-mode rules:
- The mockups use one `accent` for both text and fills. In code, use `accentText` for text, icons and outlines, and `accentFill` for filled shapes.
- In dark mode, the study card (`paper`) sits on the reader `background`. Keep that step in lightness so cards still read as cards.
- Check contrast of text on `highlight` in dark mode (`ink` on #5C4B10 passes).

### Type

- **Scripture and headings:** New York (`.fontDesign(.serif)`).
  - Verse text 17pt, line height ~1.6.
  - Section title 19pt semibold.
  - Chapter title 32pt bold.
  - Question 20pt semibold.
  - "What commentators noticed" 19pt semibold.
- **UI:** SF Pro.
  - Uppercase labels 12pt semibold, tracking ~0.5.
  - Body 15–16pt.
  - Meta and captions 12–13pt.
- **Verse numbers:** 11pt semibold SF, superscript, `inkTertiary`.
- Support Dynamic Type; the sizes above are the defaults.

### Shape and spacing

- **Radii:**
  - Study card: 20.
  - Folded rows and Home cards: 16–18.
  - Inner boxes (answer, your answer): 14.
  - Strips: 12.
  - Verse chips: 8.
  - Pills: capsule.
- **Spacing:**
  - Reader text gutter 20, card gutter 16, Home gutter 16.
  - Card padding 16.
  - Stack gaps 10–14.
- **Touch targets:** at least 44pt.
- **Icons:** SF Symbols. Mockup equivalents:
  - `chevron.left`, `chevron.down` / `chevron.up`
  - `mic`, `checkmark`, `arrow.clockwise`, `arrow.up.right.square`
  - `flame`, `gearshape`, `play.fill`

## Home (`Main.dc.html`)

1. **Header:**
   - "ThinkBible" wordmark in serif, with "Bible" in accent.
   - Streak pill: flame and "6 days".
   - Settings gear button.
2. **Continue card** (accent background):
   - "Continue · Mark 1:21–28", the section title in serif, and "About 3 min · 1 question".
   - A white play button.
   - Tap opens the reader at that section.
3. **Contents:**
   - "Contents" heading and a book picker pill ("Mark ▾").
   - Chapter grid: 8 columns, rounded squares. Selected is filled accent, started is outlined accent, the rest are neutral.
4. **Section list** for the selected chapter:
   - Header: "5 of 9 read · 4 reflections".
   - Rows of four kinds:
     - **Reflected:** ref and title, then a paper-colored strip. Left side: "YOUR OBSERVATIONS" label, idea dots and "2 of 4 ideas". Right side: a pill, "↻ Read again · Level 2", or a grey "All levels done".
     - **Read only:** title plus "Read only · reflect anytime".
     - **Current:** title only. The Continue card already points at it, so there's no badge.
     - **Not yet read:** title in `inkSecondary`.
   - Every row opens the reader scrolled to that section.
5. **Unstarted chapter:** "You haven't started this chapter yet…" with a "Start Mark N" link.

## Chapter reader (`FeedHybrid.dc.html`)

One continuous scroll per chapter. The reader must always know which section and verse a
question belongs to.

### Layout

- **Fixed top bar:**
  - Back button.
  - Study / Read segmented control (Study is the default).
  - Translation pill: "BSB ▾", toggling to KJV.
- **Chapter title**, then one block per section:
  1. **Sticky section header:** pins while the section is on screen and is replaced by the next one. It shows the ref in uppercase accent, the title in serif, and a status chip on the right ("✓ 2/4", or "Skipped").
  2. **Verse text** with inline superscript verse numbers.
  3. **The section's study element**, one of the card states below.
- **Read mode** hides every study element, leaving only the headers and the text.

### Verse highlighting

- **Answering:** the verse the current question is about gets an `accentTint` background.
- **Results:** tapping an idea's scope chip ("v. 7", "vv. 7–8" or "Passage") gives those verses a `highlight` (yellow) background; "Passage" highlights the whole section. Tapping it again clears it.

### Study card states (per section)

```
collapsedNew ──tap──▶ asking ──Submit──▶ checking ──▶ results ──collapse──▶ folded
     ▲                  │  ▲                                  │                │
     └──── Skip ────────┘  └──────────── Edit ────────────────┘◀──── tap ──────┘
```

- **collapsedNew:** a paper-colored row with a "?" badge, "Question on verse 12" (or "on verses 12–13", "on the whole passage") and the question on one line. On a later read the label is "Second read · a harder question on the whole passage".
- **asking:**
  - Label: "YOUR TURN · VERSE 11", or "SECOND READ · A HARDER QUESTION · VERSE 8".
  - The question in serif.
  - A "Not a helpful question?" link, shown only if this level has a hidden alternate and it hasn't been used.
  - The answer box with the mic button.
  - Skip / Submit buttons.
- **checking:** the Submit label becomes "Checking…" and the button is disabled. On the device this is the live compare call.
- **results** (same card, in place):
  1. The label row and a collapse chevron.
  2. "Your first-read reflection", a disclosure row shown only on later reads. It expands to show earlier answers.
  3. Your answer box: "Verse 7. <question>", the answer with the matched phrase in `highlight`, and an Edit link.
  4. "What commentators noticed". When there's a personal match:
     - A short personal note.
     - A 4-segment bar with "You caught 2 of 4".
     - **YOU CAUGHT** (accent): ideas with a filled check.
     - **WHAT YOU MISSED** (grey): ideas with an empty ring.
     - Each idea row shows a title, an optional "New" tag, a scope chip ("v. N", "vv. A–B" or "Passage"), the body text, and its sources (e.g. "Henry, JFB, Clarke agree").
  5. **Fallback** (no personal match): no bar and no "You caught" group. The line reads "Your answer took its own angle. Here are the key ideas the commentators focused on." All ideas are listed under **KEY IDEAS**.
  6. **Footer:** "Next time you read this section: a harder Level 2 question." (or "You've answered every level for this section.") and an "Enduring Word ↗" link that opens in Safari.
- **folded:** a paper-colored row with an accent check badge, "Your reflection on 1:1–8" and "2 of 4 key ideas · tap to review".
- **On device:** a new section's card should open by itself once the reader scrolls to the end of its verses, so people read first and still get the question without a tap.

### Question scope

Questions and key ideas each have a scope: `verseStart`–`verseEnd`. A scope covering the
section's first to last verse means **the whole passage**.

| Scope | Card label | Verse tint while answering | Idea chip |
|---|---|---|---|
| One verse | "Your turn · verse 7" | That verse | "v. 7" |
| A few verses | "Your turn · verses 7–8" | Those verses | "vv. 7–8" |
| Whole passage | "Your turn · the whole passage" | None; the sticky header shows "Question covers this whole passage" under the title | "Passage" |

Every section with 2 or more levels has at least one whole-passage question, usually Level 2 or 3.
Level 1 is often a single verse.

### Levels (one question per section per read)

- A first read asks Level 1. A later read of that section, on a later day, asks the next level.
- When a level has two questions, the app picks the one that targets a key idea the user hasn't caught yet. The other is a hidden alternate, shown only through "Not a helpful question?" (once).
- "You caught" counts ideas across all reads. Ideas caught on this read get the "New" tag.
- After the last level the section shows "All levels done" (Home pill) and the completion footer.

### Submit, edit and cost rules

- Submit is disabled until the answer is at least 15 characters. Below the buttons the hint reads "Write a sentence or so to compare with the commentators."
- Submit is also disabled while checking.
- **Edit** reopens the answer box with the current text:
  - The button reads "Re-check · 2 left" and the secondary button becomes "Cancel".
  - The note reads "Changing your answer uses 1 of 2 re-checks for this question. If you don't change it, your last result is reused."
  - An unchanged answer makes no API call.
  - After 2 re-checks the button becomes "Save answer": it keeps the new text and the existing results, with no API call.
- **Skip** on the first question collapses the section and marks it "Skipped". Its row then reads "Skipped · answer anyway".
- **Server side:** results are cached by hash(section, question, answer); there's a daily cap per device (about 30) for Premium; the free tier is 3 reflections in total, after which the user must subscribe (see the paywall section). Over the daily cap, show the fallback results from the stored key ideas.

## Free reflections and the paywall (`Paywall.dc.html`)

- **Reading is always free.** Read mode and the full text are never locked.
- **Free reflections:**
  - 3 in total, counted by submitted answers.
  - Re-checks of a free answer don't count.
  - The count is enforced on the server per device (App Attest), so reinstalling doesn't reset it.
- **Under the question card's buttons**, a small note reads "2 of 3 free reflections left". When they're used up, it reads "You've used your 3 free reflections."
- **When no free reflections are left,** Submit opens the paywall as a sheet. The typed answer is kept, and if the user starts the trial, it's checked straight away.
- **Sheet content, top to bottom:**
  1. A grab handle and a close (X) button.
  2. "Keep thinking it through" in serif.
  3. The subtitle.
  4. A "Waiting · <ref>" card with the user's pending answer.
  5. Three benefit rows.
  6. The plan radio group: Yearly preselected ($29.99, "Save 37%", "just $2.50 a month") and Monthly ($3.99).
  7. A "Start 7-day free trial" button, with the post-trial price and "Cancel anytime in Settings" underneath. This line updates with the selected plan.
  8. Restore purchases · Terms · Privacy.
  9. "Not now, keep reading".
- **StoreKit 2:** two auto-renewable subscriptions in one group, each with a 7-day introductory free trial. Read prices from `Product.displayPrice`, never hard-code them. Use `SubscriptionStoreView` only if it can match this layout; otherwise build a custom view on `Product.purchase()`.

## Settings (`Settings.dc.html`)

Grouped list on `paper`. Every row is at least 52pt tall, with segmented controls and switches on the right.

1. **Reading:**
   - Translation (BSB / KJV).
   - Text size: a 5-step slider with a live serif preview of Mark 1:1. Scale Scripture text by these steps (15, 16, 17 default, 19, 21pt) on top of Dynamic Type.
   - Scripture font (Serif / Sans).
   - Verse numbers (switch).
2. **Study:**
   - Open in (Study / Read).
   - Open questions automatically (switch, on), subtitled "When you reach the end of a section".
3. **Appearance:** System / Light / Dark. Map it to `.preferredColorScheme(nil / .light / .dark)` at the app root and store it in `@AppStorage`.
4. **Reminder:** daily reading reminder (switch) and a time row (7:30 AM default). Use local notifications and ask for permission when the user turns it on.
5. **Subscription:** a status row ("Free · 2 of 3 free reflections left", or the plan name for Premium) with a "See plans" button, and Restore purchases. For Premium, show "Manage subscription", which opens the App Store management sheet (`manageSubscriptionsSheet`).
6. **Your reflections:** iCloud sync status, then "Delete all reflections" in `danger`, with a confirmation dialog.
7. **About:** Sources and licenses (BSB, KJV, Matthew Henry, Jamieson-Fausset-Brown, Adam Clarke; Enduring Word is link-out only), Report a problem, Privacy policy, Terms of use, and the version line.

Store all settings in `@AppStorage` (they're device preferences). Reflections stay in SwiftData with CloudKit.

## States with no mockup (build to these rules)

- **First launch:**
  - Open Home with Mark 1:1–8 as the Continue card.
  - In the reader, show the first question card already open, with one dismissible line above it: "Answer in your own words. There are no wrong answers. Then see what the commentators noticed."
  - No onboarding carousel.
- **Loading a content pack:** Packs are cached after the first download.
  - Show the section headers and text as soon as they're available.
  - Load the study elements in place: a small inline spinner in the card, never a full-screen loader.
- **Offline:**
  - Reading and Read mode work fully.
  - Submit saves the answer and immediately shows the fallback results from the stored key ideas, with one line: "You're offline. We'll check your answer when you're back." When the connection returns, the personal results replace the fallback, with the "New" tags.
  - Free-reflection counts sync when back online.
- **Compare error (5xx or timeout after 10s):**
  - Same as offline, with the line "We couldn't check your answer just now. Here's what commentators noticed."
  - Retry automatically once in the background. A failed check never uses up a re-check or a free reflection.
- **Daily cap reached (429):** fallback results, with the line "You've reached today's limit for personal feedback. Here's what commentators noticed."
- **Free limit reached (402):** open the paywall sheet, keeping the answer as a draft.
- **Sections with no question** (`noPrompt` in the pack, set only when the commentaries give nothing to ask about, such as a bare census list; genealogies the commentaries discuss still get questions): no study element; show a one-line context note under the verses instead.
- **Empty Home** (nothing read yet): the Continue card says "Start · Mark 1:1–8". The contents list shows every section as not yet read.
- **Verse notes** (tap a dotted word for a short note) were in the earlier card design. They're **not in the MVP reader**; they're planned for V2.
- **Accessibility:**
  - VoiceOver reads each section header as a heading.
  - The question card announces "Question about verse N" (or "verses A to B", "the whole passage").
  - Idea rows read "Caught" or "Not yet caught" before the title.
  - Every icon-only button has a label (Settings, Dictate your answer, Collapse, Close).
  - All tap targets are at least 44pt.

## SwiftUI mapping

| Element | Suggested implementation |
|---|---|
| Reader scroll + sticky headers | `ScrollView { LazyVStack(pinnedViews: [.sectionHeaders]) { Section(header:) … } }` |
| Jump to section from Home | `ScrollViewReader` / `.scrollPosition(id:)` with section IDs |
| Auto-open card at end of verses | `onScrollVisibilityChange` or `.onAppear` on an end-of-verses marker |
| Verse text with numbers and highlights | One `Text` built from an `AttributedString`: superscript runs (`baselineOffset`, smaller font) for verse numbers, `backgroundColor` runs for the tint and yellow highlight |
| Study / Read switch | `Picker(.segmented)` or a small custom capsule control |
| Answer box | `TextField(…, axis: .vertical).lineLimit(3...8)` plus a mic button (`SFSpeechRecognizer`, on device) |
| Card state changes | One `enum CardState` per section; animate with `.animation(.snappy, value:)` |
| Fold / expand rows | `DisclosureGroup`-like custom view; chevron rotates 180° |
| Idea row scope chip | `Button` that sets `focusedRange: ClosedRange<Int>?` in the reader model |
| Haptics | `.sensoryFeedback(.success, trigger:)` when results arrive |

### Suggested state

- `@Observable final class ReaderModel`: chapter, translation, `mode` (study/read), per-section `CardState`, `focusedRange`, and the in-flight compare task.
- **SwiftData:**
  - `Reflection`: `sectionId`, `level`, `questionId`, `answer`, `coveredIdeaIds`, `highlightPhrase`, `note`, a snapshot of the question and ideas, `createdAt`.
  - `SectionProgress`: `sectionId`, `currentLevel`, `lastReadDay`, `caughtIdeaIds`, `skipped`, `recheckCounts`, `swappedQuestionIds`.

## Data the UI reads

The content pack for each section (from the batch pipeline, cached offline) includes:

- `id`, `ref`, `title`
- `verses` (BSB and KJV)
- `keyIdeas[]`: `id`, `title`, `body`, `sources[]`, `verseStart`, `verseEnd`, `agreed`
- `questions[]`: `id`, `level` (1–3), `verseStart`, `verseEnd`, `text` (BSB and KJV variants), `targets[]` (key idea IDs), `isAlternate`

The compare API returns `coveredIdeaIds`, `highlightPhrase`, `note`, `contradictsText`.

## Copy reference

These strings come from the mockups. Keep the wording unless a spec changes it.

- "Your turn · verse N" / "Your turn · verses A–B" / "Your turn · the whole passage"
- "Question covers this whole passage"
- "Second read · a harder question"
- "Not a helpful question?"
- "Thanks for the feedback. Here's another question at this level."
- "What commentators noticed"
- "You caught N of M"
- "You caught"
- "What you missed"
- "Key ideas"
- "Your answer took its own angle. Here are the key ideas the commentators focused on."
- "Next time you read this section: a harder Level N question."
- "Your reflection on 1:1–8"
- "Read again · Level N"
- "All levels done"
- "Read only · reflect anytime"
- "Skipped · answer anyway"
- "Checking…"
- "Re-check · N left"
- "Save answer"
- "Write a sentence or so to compare with the commentators."
- "2 of 3 free reflections left"
- "You've used your 3 free reflections."
- "Keep thinking it through"
- "Start 7-day free trial"
- "Not now, keep reading"
