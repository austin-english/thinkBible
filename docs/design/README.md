# Book-feel reader: design spec

**Status:** chosen direction (Nov 2026). This replaces the **Home + contents** and **Reader** screens in `docs/design/DESIGN.md` (sticky-header reader, results card, swipe-up answer sheet). Paywall, fallback rules, question levels, scope chips, re-check limits and the content/API contracts are unchanged.

**What it is:** a single vertical feed of "pages," one card per passage section. Long passages swipe sideways inside their card. The question sits in the card footer as a comment from ThinkBible. You answer inline, and the commentators' reply appears as a threaded comment. One scroll, no sheets.

## Screens (`screens/`)

| File | Shows |
|---|---|
| `01-feed.png` | Feed, first card (page 1 of 2, drop cap, question footer, "Add your answer…") |
| `02-page-2.png` | Same card swiped to page 2 |
| `03-typing.png` | Composer open, Post enabled, free-reflection count |
| `04-answered.png` | Answer posted: "You caught 2 of 4 key ideas", matched phrase highlighted, ThinkBible reply |
| `05-expanded.png` | Reply expanded: every key idea with body + sources |
| `06-no-match.png` | Answer that took its own angle: "✓ Answered", "See 4 key ideas" |
| `07-chapter-picker.png` | "Mark 1 ▾" panel: chapters, then sections with their reflection counts |
| `08-book-list.png` | Book button tapped: the panel becomes the whole-Bible book list |
| `09-genesis.png` | Unpublished book picked: chapter grid + "coming soon · Notify me" |
| `10-you-settings.png` | You & settings (avatar in the header) |
| `11-notify-prompt.png` | After the first answer: "Harder question unlocks tomorrow" + the notify prompt |
| `12-notification.png` | The next day: one notification per chapter (copy variants in the source) |
| `13-level-2-unlocked.png` | Level 2 unlocked: new question at the top of the comments, "Show more" below |
| `14-level-1-opened.png` | "Show more" tapped: the earlier thread opens under the new one |
| `15-panel-new.png` | Chapter panel: "New" on the unlocked section, dot on the chapter tile |

`source/PostBook.dc.html`, `source/YouBook.dc.html` and `source/UnlockNotification.dc.html` are the design-tool sources. They hold the exact values, copy and state logic. **Read them for values; do not port the markup or JS.** They need the design tool's runtime to run.

## Tokens (light)

| Token | Value | Use |
|---|---|---|
| `desk` | `#F3EEE3` | Screen background behind the pages, header |
| `page` | `#FDFBF6` | Card (page) surface |
| `panel` | `#FBF8F1` | Chapter panel surface |
| `surface` | `#FFFFFF` | Lists inside the panel, composer field |
| `ink` | `#1C1C1E` | UI text, icons, dark pills |
| `ink.page` | `#2A2620` | Scripture, questions, headings on pages |
| `ink.secondary` | `#5E5E63` | Subtitles |
| `ink.tertiary` | `#8A8A90` | Placeholders, meta, notes |
| `folio` | `#9A8E78` | Verse-range folio under text |
| `rule` | `#E2D9C6` | Header border, panel borders, unread bar segment |
| `rule.page` | `#EFE7D6` | Hairlines inside a card |
| `rubric` | `#2B4C7E` (default "Blue") / `#8B2F25` ("Red") | Drop cap, verse numbers, heading rule, question label, accents. User setting **Accent color**. |
| `rubric.tint` | `#E7EDF6` | Book avatar, "Reading"/"Ready" tags |
| `rubric.read` | `#B9C6DA` | "Read" bar segment |
| `highlight` | `#FFF1B8` | Matched phrase in the user's answer |
| `streak` | `#B45309` | Flame badge |
| Page shadow | `0 1 1 rgba(70,52,24,.10)` + `0 8 22 rgba(70,52,24,.08)` | Card |

**Dark mode was not drawn for this layout.** Proposed starting point (check contrast before shipping): desk `#151311`, page `#1F1C18`, panel `#1A1815`, ink.page `#E9E3D6`, ink `#F2F2F4`, rule `#3A342B`, rubric blue `#8FB0E0`, red `#D98A7E`, highlight `rgba(255,214,102,.28)`.

**Type:** serif = `Font.system(design: .serif)` (New York), so no font bundle. UI = SF Pro.
- Wordmark: serif 22 bold, "Think" ink + "Bible" rubric
- Scripture: serif 17, line height 1.6, **justified with hyphenation**, old-style figures
- Drop cap: serif 54 semibold, rubric, 2 lines deep
- Section heading (page 1 only): serif italic 18 medium, centered, 36×1 rubric rule below
- Verse numbers: SF 10 bold superscript, rubric
- Folio: serif 12, letter-spacing 1, `folio` color, centered, 12pt under the text
- Question: serif italic 18, line height 1.45
- Question label: serif small caps 14 bold, rubric: "· question on verse 7"
- Comments: SF 14 / 1.45

All text sizes follow the **Text size** setting (Dynamic Type).

## Layout

### Header (fixed)
Height = safe area + 48. Background `desk`, bottom hairline `rule`.
- Wordmark (leading, flexible)
- Chapter pill "Mark 1 ▾": 34 tall, dark `ink` capsule, white 13 bold, chevron rotates 180° when open
- Avatar 34 circle in `rubric` with the user's initial; flame streak badge bottom-right (`page` fill, `rule` stroke, `streak` text). Opens **You & settings**.

There's no translation control in the header or on cards. Translation lives only in You & settings.

### Feed
- Chapter title row: serif 22 bold "Mark 1" + trailing "9 sections" (13, secondary). Padding 14/18.
- Cards stack vertically, 12pt side margins, 20pt between, radius 4, `page` fill, page shadow.
- After the last section: an "End of Mark 1 · Keep scrolling for Mark 2" page. Scrolling continues straight into the next chapter (endless through the book).

### Card (one section)
1. **Card header row** (padding 10/12/10/14): 36 circle book avatar (`rubric.tint`, serif "Mk"), ref "Mark 1:1–8" (14 bold), title (13 secondary, one line), `…` button 40×40.
2. **Pages** between two `rule.page` hairlines. Horizontal paging, each page = card width; padding 22/30/14; min height 300. A soft inner shadow on the trailing edge suggests a page edge.
   - Page 1: italic heading, rubric rule, drop cap on the first word of the first verse (leading quote marks are stripped before taking the cap).
   - Every page: justified scripture with superscript verse numbers (the drop-cap verse has no number), then the folio "1:1–4".
   - More than one page: dots row (6pt, rubric active / `#C9C6BC`) **inside** the pages area, below the text, and a "1/2" counter capsule top-right (`rgba(42,38,32,.55)`, white 12 semibold).
   - **Split rule:** pages break between verses only, never mid-verse. Paginate by measured height at the current text size.
3. **Action row:** Send (paper plane) leading, Save (bookmark, filled when saved) trailing. 44×44 targets. No other actions.
4. **Footer** (padding 4/16, no divider above):
   - ThinkBible comment: 28 black circle "T" + "**ThinkBible** · question on verse 7" + the question in italic serif. The question is **always visible**, regardless of passage length.
   - Status line once answered (13 bold rubric): "✓ You caught 2 of 4 key ideas", or "✓ Answered" when nothing matched.
   - Composer row ("Add your answer…" with the user avatar) → tap opens the composer.
   - Meta line: "MARK 1 · SECTION 1 OF 9" (11, uppercase, tertiary).

### Composer (inline, in the card)
- 1.5pt `rubric` stroke, radius 18, white fill. Mic (dictation) + "Post" text button inside, trailing.
- Post is disabled under **15 characters**.
- Note under the field: "A sentence or so · 2 of 3 free reflections left" → "Checking with the commentators…" while checking.
- While composing, the verses the question is about get a soft `rubric` 12% tint on the page. Use the question's verse scope.
- Post with 0 free reflections left → existing paywall.

### Answered thread
- **You** comment: the answer, with the phrase that matched a key idea highlighted (`highlight`). "Edit" under it (edit counts against the 2 re-checks).
- **ThinkBible** reply, indented 38: "ThinkBible · from Henry, JFB & Clarke" + a one-to-two-sentence note.
  - Collapsed: only caught ideas (filled rubric check + title + "· v. 7" scope chip). Then "— See what you missed (2)".
  - Expanded: caught first, then missed (hollow circle), each with body (13) and sources (12 tertiary). "Hide details".
  - No match: the note says "Your answer took its own angle. Here's what the commentators focused on." and the toggle reads "See 4 key ideas".
  - Footer note: clock icon + "Harder question unlocks tomorrow · Enduring Word" (link). After Level 2 it says "Level 3 unlocks tomorrow". After Level 3: "All levels done".

## Next-level unlock (24 hours)

Harder questions don't appear just because a section is opened again, since tapping out and back in isn't a re-read. Each level unlocks **24 hours after the previous level was answered**, and a notification brings the reader back. **Everything runs on the device; there's no backend or cron.**

**Rules**
- **Two gates per level:** `now >= unlocksAt` AND the previous level was answered. A skipped day just waits; there's no streak penalty.
- **Timing:** on a checked answer, set `unlocksAt = answeredAt + 24h` and recompute on launch and on return to the foreground. After Level 3: "All levels done", nothing more scheduled.
- **Which question:** the next level, preferring a question aimed at an idea the reader hasn't caught yet. The mock's Level 2 targets "Water and the Spirit", the idea missed at Level 1.
- **Free users:** an unlocked question counts as a reflection. Post with none left opens the paywall.

**Notifications** (local, `UNUserNotificationCenter`)
- At most one per chapter and one per day. Each new answer cancels and reschedules that chapter's pending notification (`identifier = "unlock.<book>.<chapter>"`) with the new count. It fires at the earliest `unlocksAt` among that chapter's sections.
- If the daily reading reminder is on, fold the unlock into it (rewrite that reminder's text) rather than sending a second notification.
- **Copy** (variants in `source/UnlockNotification.dc.html`):
  - Several sections: "3 harder questions are ready in Mark 1" / "You answered these yesterday. Each one asks a little more of the passage."
  - One section: "A harder question is ready for Mark 1:1–8" / the question as a teaser.
  - Free user with no reflections left: "Your harder question is ready · Premium" / "Mark 1:1–8 is waiting. You've used your 3 free reflections."
- Tapping a notification opens the feed scrolled to the first unlocked section in that chapter.
- **Permission:** the in-card prompt ("Want a nudge when it's ready?" / Not now / Notify me) appears **once, ever**, under the reader's first answer.
  - Notify me opens the system prompt. The card then shows a one-line "✓ We'll let you know tomorrow when it's ready." for that session only.
  - Whichever button they tap, the prompt never returns; the switch lives in Settings.
  - Every other answered card shows only the small unlock line. Store a `notifyPromptShown` flag.
- Users without notification permission still see unlocked questions when they next open the app.

**On screen**
- **Answered card:** footer note "Harder question unlocks tomorrow" (clock icon). The first time only, the notify prompt appears under the thread, indented to the reply.
- **Unlocked card:** the comments read **newest first**, like a social thread.
  1. ThinkBible's Level 2 question: label "· level 2 · verses 7–8" + "New" tag (`#FDF1E3` / `#9A4A06`).
  2. "Add your answer…"
  3. "—— Show more": the same hairline-link style as "See what you missed". Tapping it expands the earlier question ("· level 1 · verse 7"), the answer with its highlight, and the ThinkBible reply with caught ideas; it then reads "Show less".
  - Once Level 2 is answered, its thread stacks above the Show more link, the same way.
  - The meta line adds "· LEVEL 2".
- **Chapter panel:** a "New" pill on the section row (before the ✓ fraction); a 7pt `#C2410C` dot top-right on the chapter tile. Both clear once that level is answered.
- **Settings › Questions:** "Harder-question alerts" switch (on by default once permission is granted).

### `…` menu (not drawn yet)
Proposed contents: **Not a helpful question?** (hidden alternate, existing rule), Copy passage, Report a problem.

### Send
Use the system share sheet with the passage text, the reference, the translation code and a `thinkbible.app` link. Don't include the user's answer unless they choose to.

## Chapter panel ("Mark 1 ▾")

Drops down from under the header: `panel` fill, bottom radius 22, shadow, dimmed backdrop (`rgba(20,20,19,.38)`) over the feed; tap the backdrop to close. Max height ≈ screen − header − 54, **one scroll only**. It shows one list at a time:

**Chapters view (default)**
- Book button: dark capsule, 40 tall, book icon + "Mark" + chevron. Tap → Books view.
- **Reflection counts appear in one place only: the section rows.** Chapter tiles, the sections header and the book list carry no counts, to keep the panel quiet.
- "CHAPTERS" label.
- Chapter grid: 8 columns, gap 6, tiles 42 tall, just the number, one tile per chapter in the book. Current chapter = filled rubric.
- "SECTIONS IN MARK 1" label.
- Sections list (white, radius 12): range (13 bold rubric, tabular), title (serif 15, one line), then trailing state:
  - **Reflected:** rubric pill "✓ 3/3" (key ideas caught / total for that section's best attempt)
  - **Read:** outline pill "Read"
  - **Current, unanswered:** tint pill "Reading"
  - Saved: small filled bookmark before the pill
  - Tap a row → close the panel and scroll the feed to that card.
- Picking a chapter without section data (or an unpublished book): one button: "Start Mark 2 at verse 1 ›" (published), or "Genesis is coming soon · Notify me" → "✓ We'll let you know when Genesis is ready".
- Bottom rows: "Saved passages" with count; "You & settings".

**Books view**
- The same panel becomes one list of all 66 books with sticky "OLD TESTAMENT" / "NEW TESTAMENT" headers, opened scrolled to the current book.
- Each row: name, a "Ready" tag for published books, and a check on the current one. Unpublished books are in secondary ink but still tappable.
- Picking a book returns to the Chapters view for that book.

## You & settings (`10-you-settings.png`)
In order:
- **Profile card:** initial, "You", "Reading Mark since Nov 3", tiles: day streak · reflections · ideas caught
- **Your books:** progress per book; upcoming ones, e.g. "John · Coming before Easter"
- **Saved passages**
- **Reading:**
  - Translation BSB/KJV
  - Text size slider with a live page preview
  - Accent color Blue/Red
  - Justify text
  - Verse numbers
- **Questions:** Show questions, Harder-question alerts
- **Appearance**
- **Reminder:** daily reading reminder + time
- **Subscription:** Free · See plans · Restore purchases
- **Your reflections:** delete all
- **About:** sources and licenses, report a problem, privacy and terms

## Progress model (all on-device)

Keep it per user, per section, in SwiftData and synced with CloudKit:

```
SectionProgress
  sectionId        // e.g. "MRK.1.1-8"
  state            // none | read | reflected
  ideasCaught      // best attempt
  ideasTotal       // from the section's content
  level            // highest question level answered (1–3)
  unlocksAt        // answeredAt + 24h for the next level; nil after Level 3
  saved            // bookmark
  updatedAt
```

- **reflected:** set when an answer is evaluated (even with 0 ideas caught; then the pill shows "✓ 0/4").
- **read:** set when the card's last page has been on screen and the card has scrolled past without an answer. Never downgrades a reflected section.
- **Derived values:**
  - streak = consecutive days with at least one read or reflection
  - per-book progress for You & settings › Your books
- **Published books** ("Ready") come from the content catalog the app already loads, not from a hard-coded list.
- **Notify me** is local for v1: store the book id and show an in-app banner when a content update makes it available. Push needs backend work, so it's out of scope.

## Accessibility
- Every control is a real button with a label. Chapter tiles read "Mark chapter 1", plus "new question" when one unlocked there.
- Section rows read the range, title and state.
- The drop cap is decorative; VoiceOver reads the full first word.
- Dots are hidden; the counter announces "Page 1 of 2".
- Minimum 44pt targets. Text contrast ≥ 4.5:1 in both modes.
