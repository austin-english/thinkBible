# ThinkBible: UI design spec (MVP)

Source of truth for the iOS UI. Build in SwiftUI (iOS 17+, Swift 6, Observation, SwiftData).

**The feed, chapter panel, next-level unlock and You & settings follow the "book feel" design in
[`README.md`](README.md)** and the PNGs in `screens/`. It replaced the earlier Home + contents
screen, the sticky-header chapter reader with its study card, and the old Settings screen (Nov 2026).
This file keeps what the book-feel design leaves unchanged: the paywall, fallback and offline rules,
question scope, re-check and cost limits, the data the UI reads, and the copy for those.

Sample Scripture, questions and commentator ideas in the mockups are placeholders. Real content
comes from the content packs (see "Data the UI reads").

## Screens

| File | Screen |
|---|---|
| [`README.md`](README.md) + `screens/01`–`15-*.png` | Feed, page cards, composer and reply thread, chapter panel and book list, You & settings, notify prompt, notification, unlocked Level 2 |
| `screens/Paywall.dc.html` | Paywall sheet, after the 3 free reflections. It was drawn over the old reader; the sheet itself is unchanged, and in the app it opens over the feed. HTML prototype that needs the design-canvas runtime: read it for copy, colors and spacing, don't port it |

There is no tab bar and no Home screen. The feed opens where the reader left off. The chapter panel
("Mark 1 ▾") is the table of contents, and the avatar opens You & settings.

## Design tokens

The feed, chapter panel and You & settings use the book-feel tokens in `README.md` (`desk`, `page`,
`panel`, `ink.page`, `rubric`, and so on), with Accent color Blue/Red as a user setting. The table
below is the earlier token set. It still covers the Paywall sheet, and it's the reference for dark
values while the book-feel dark palette (proposed in `README.md`, not drawn yet) is checked for
contrast. When both define a role, the book-feel token wins: `accentText`/`accentFill` map to
`rubric`, `highlight` stays `#FFF1B8`.

Every token is a named color in the asset catalog with an Any (light) and a Dark appearance.
Never hard-code hex in views.

| Token | Light | Dark | Use |
|---|---|---|---|
| `accentText` | #2B4C7E | #8FB0E0 | Links, labels, checks |
| `accentFill` | #2B4C7E | #3D64A0 | Filled buttons, selected plan, switch on (white text on top) |
| `accentPressed` | #1F3A62 | #335588 | Pressed state of filled buttons |
| `accentTint` | #E7EDF6 | #22314A | Tinted chips |
| `paper` | #F6F5F1 | #1C1B19 | Paywall sheet background |
| `surface` | #FFFFFF | #262522 | Boxes on paper: waiting-answer card, plan rows |
| `fill` | #EFEEE9 | #34332F | Neutral pills |
| `ink` | #1C1C1E | #F2F1EC | Primary text |
| `inkSecondary` | #5E5E63 | #A3A29B | Labels, captions, meta |
| `inkTertiary` | #8A8A90 | #7C7B75 | Chevrons, fine print |
| `bodyMuted` | #3A3A3F | #CFCEC8 | Body text on the paywall |
| `hairline` | #E6E4DD | #3A3935 | Borders, dividers in cards |
| `highlight` | #FFF1B8 | #5C4B10 | Matched phrase in your answer |
| `highlightInk` | #5C4A00 | #FFE58A | Text on a highlight-colored tag |
| `disabled` | #8E9DB4 | #4A5A73 | Post while disabled or checking (dark: text #C9D3E3) |
| `danger` | #B3261E | #F2B8B5 | "Delete all reflections" |
| `streak` | #B45309 | #F0A04B | Flame badge |
| `scrim` | rgba(20,20,19,0.42) | rgba(0,0,0,0.6) | Behind the paywall sheet |

Dark-mode rules:
- Use `accentText` (or `rubric`) for text, icons and outlines, and `accentFill` for filled shapes.
- Check contrast of text on `highlight` in dark mode (`ink` on #5C4B10 passes).

### Type, shape and icons

- Type for the feed, panel and You & settings: see `README.md` (serif = New York via
  `Font.system(design: .serif)`, UI = SF Pro, all sizes follow Dynamic Type and the Text size setting).
- Paywall: title serif 30 bold, body 16, plan rows 15–17, fine print 12–13.
- Touch targets: at least 44pt. Icons: SF Symbols.

## Question scope

Questions and key ideas each have a scope: `verseStart`–`verseEnd`. A scope covering the
section's first to last verse means **the whole passage**.

| Scope | Question label (footer) | Verse tint while composing | Idea chip |
|---|---|---|---|
| One verse | "· question on verse 7" | That verse | "v. 7" |
| A few verses | "· question on verses 7–8" | Those verses | "vv. 7–8" |
| Whole passage | "· question on the whole passage" | None | "Passage" |

Every section with 2 or more levels has at least one whole-passage question, usually Level 2 or 3.
Level 1 is often a single verse.

## Levels

- A section starts with its Level 1 question. The next level **unlocks 24 hours after the previous
  level is answered** (two gates: time and the previous answer). Opening a section again is not a
  re-read and never advances the level. Details, notifications and on-screen states: `README.md` →
  "Next-level unlock".
- When a level has two questions, the app picks the one that targets a key idea the reader hasn't
  caught yet. The other is a hidden alternate, shown only through "Not a helpful question?" in the
  card's `…` menu (once per level).
- "You caught" counts ideas across all levels. After the last level the reply footer reads "All
  levels done".

## Post, edit and cost rules

- Post is disabled until the answer is at least 15 characters, and while checking.
- **Edit** (under the posted answer) reopens the composer with the current text:
  - The button reads "Re-check · 2 left" and a secondary "Cancel" returns to the thread.
  - The note reads "Changing your answer uses 1 of 2 re-checks for this question. If you don't change it, your last result is reused."
  - An unchanged answer makes no API call.
  - After 2 re-checks the button becomes "Save answer": it keeps the new text and the existing results, with no API call.
- There is no Skip button. Scrolling past an unanswered card marks the section Read.
- **Server side:** results are cached by hash(section, question, answer); there's a daily cap per device (about 30) for Premium; the free tier is 3 reflections in total, after which the user must subscribe. Over the daily cap, show the fallback results from the stored key ideas.

## Free reflections and the paywall (`Paywall.dc.html`)

- **Reading is always free.** The full text, navigation and the feed with Show questions off are never locked.
- **Free reflections:**
  - 3 in total, counted by posted answers. An unlocked Level 2–3 question counts the same way.
  - Re-checks of a free answer don't count.
  - The count is enforced on the server per device (App Attest), so reinstalling doesn't reset it.
- **Under the composer**, the note reads "A sentence or so · 2 of 3 free reflections left". When they're used up, it reads "You've used your 3 free reflections."
- **When no free reflections are left,** Post opens the paywall as a sheet. The typed answer is kept, and if the user starts the trial, it's checked straight away.
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

## You & settings

See `README.md` → "You & settings" and `screens/10-you-settings.png`. Rules kept from the earlier
Settings screen:
- **Appearance:** System / Light / Dark. Map it to `.preferredColorScheme(nil / .light / .dark)` at the app root and store it in `@AppStorage`.
- **Reminder:** daily reading reminder (switch) and a time row (7:30 AM default). Local notifications; ask for permission when the user turns it on (or reuse the permission from the notify prompt).
- **Subscription:** a status row ("Free · 2 of 3 free reflections left", or the plan name for Premium) with "See plans", and Restore purchases. For Premium, "Manage subscription" opens the App Store management sheet (`manageSubscriptionsSheet`).
- **Your reflections:** iCloud sync status, then "Delete all reflections" in `danger`, with a confirmation dialog.
- **About:** Sources and licenses (BSB, KJV, Matthew Henry, Jamieson-Fausset-Brown, Adam Clarke; Enduring Word is link-out only), the AI disclosure, Report a problem, Privacy policy, Terms of use, and the version line.

Store settings in `@AppStorage` (they're device preferences). Reflections and section progress stay in SwiftData with CloudKit.

## States with no mockup (build to these rules)

- **First launch:**
  - Open the feed at Mark 1:1–8, with its question footer showing.
  - One dismissible line above the first composer: "Answer in your own words. There are no wrong answers. Then see what the commentators noticed."
  - No onboarding carousel.
- **Loading a content pack:** Packs are cached after the first download.
  - Show the page cards (text) as soon as they're available.
  - Load the question footers in place: a small inline spinner in the footer, never a full-screen loader.
- **Offline:**
  - Reading works fully.
  - Post saves the answer and immediately shows the fallback reply from the stored key ideas, with one line: "You're offline. We'll check your answer when you're back." When the connection returns, the personal reply replaces the fallback.
  - Free-reflection counts sync when back online.
- **Compare error (5xx or timeout after 10s):**
  - Same as offline, with the line "We couldn't check your answer just now. Here's what commentators noticed."
  - Retry automatically once in the background. A failed check never uses up a re-check or a free reflection.
- **Daily cap reached (429):** fallback reply, with the line "You've reached today's limit for personal feedback. Here's what commentators noticed."
- **Free limit reached (402):** open the paywall sheet, keeping the answer as a draft.
- **No personal match:** the reply note reads "Your answer took its own angle. Here's what the commentators focused on.", the status line reads "✓ Answered", and the toggle reads "See N key ideas" (`06-no-match.png`).
- **Sections with no question** (`noPrompt` in the pack, set only when the commentaries give nothing to ask about, such as a bare census list; genealogies the commentaries discuss still get questions): no question footer; show the section's one-line context note in the footer instead.
- **Verse notes** (tap a dotted word for a short note) are **not in the MVP**; they're planned for V2.
- **Accessibility:** see `README.md` → "Accessibility". Also: the question footer announces "Question about verse N" (or "verses A to B", "the whole passage"); idea rows read "Caught" or "Not yet caught" before the title.

## Suggested state

- `SectionProgress`: see `README.md` → "Progress model".
- `Reflection` (SwiftData): `sectionId`, `level`, `questionId`, `answer`, `coveredIdeaIds`, `highlightPhrase`, `note`, a snapshot of the question and ideas, `createdAt`.

## Data the UI reads

The content pack for each section (from the batch pipeline, cached offline) includes:

- `id`, `ref`, `title`
- `verses` (BSB and KJV)
- `keyIdeas[]`: `id`, `title`, `body`, `sources[]`, `verseStart`, `verseEnd`, `agreed`
- `questions[]`: `id`, `level` (1–3), `verseStart`, `verseEnd`, `text` (BSB and KJV variants), `targets[]` (key idea IDs), `isAlternate`

The compare API returns `coveredIdeaIds`, `highlightPhrase`, `note`, `contradictsText`.
`content/schema/section.schema.json` and `api/openapi.yaml` are the binding contracts.

## Copy reference

Feed, panel, unlock and You & settings copy is in `README.md` and the PNGs. These strings cover the
rules above. Keep the wording unless a spec changes it.

- "· question on verse N" / "· question on verses A–B" / "· question on the whole passage"
- "Not a helpful question?"
- "Thanks for the feedback. Here's another question at this level."
- "Your answer took its own angle. Here's what the commentators focused on."
- "Checking with the commentators…"
- "Re-check · N left"
- "Save answer"
- "A sentence or so · 2 of 3 free reflections left"
- "You've used your 3 free reflections."
- "Keep thinking it through"
- "Start 7-day free trial"
- "Not now, keep reading"
