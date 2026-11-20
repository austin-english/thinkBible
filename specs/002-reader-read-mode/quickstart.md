# Quickstart: validate the reader (spec 002)

How to build the app and prove the feature works. Contracts:
[cdn-consumption.md](contracts/cdn-consumption.md), [app-interfaces.md](contracts/app-interfaces.md);
models: [data-model.md](data-model.md).

## Prerequisites

- Xcode 27 or later with an iPhone 16 Pro simulator, and a physical iPhone (iOS 17 or later) for
  the smoothness check.
- `brew install xcodegen`, only for the one-time project bootstrap.
- `uv` (already used by the pipeline), for `make ios-packs`.
- Mark and Philippians published on the draft channel (spec 001; Mark 1.2.1 today).

## 0. Package tests (no simulator, no network)

```bash
cd ios/Packages/ContentKit && swift test
cd ios/Packages/DesignSystem && swift test
```

**Expected**: everything passes, including:
- every `content/schema/fixtures/valid/*` decodes and validates, and every `fixtures/invalid/*` is
  rejected;
- pagination never splits, drops or repeats a verse (fake measurer);
- the pack store only uses verified packs and activates them at launch;
- the feed lists books, chapters and sections in order, skips unpublished books, and ends with
  the book list when nothing comes next;
- the 66-book table (1,189 chapters) and every token's light and dark contrast.

## 1. Bundle the packs and build

```bash
make ios-packs CHANNEL=draft   # downloads and verifies the draft channel into Resources/Packs
make ios-test                  # package tests, then the app tests on the iPhone 16 Pro simulator
```

**Expected**: `ios-packs` lists Mark 1.2.1 and Philippians 1.0.0 with their checksums verified.
Building without running it first fails with "run make ios-packs CHANNEL=draft". The app tests
pass, including pagination of every Mark section at every text size with the real text layout
(SC-004).

Open `ios/ThinkBible.xcodeproj` and run the `ThinkBible` scheme (Debug, draft channel).

## 2. Read (US1)

- First launch opens at the "About Mark" post (FR-016), with Mark 1:1–8 right below it.
  Compare with `screens/01-feed.png`:
  wordmark, "Mark 1 ▾" pill, avatar; the card's header row, italic heading with rubric rule, drop
  cap, justified serif text, rubric verse numbers, folio, "1/2" counter and dots.
- Swipe the first card sideways: page 2 has no heading or drop cap (`02-page-2.png`). No verse is
  cut between pages.
- The footer shows "ThinkBible · question on …" and the question, read-only.
- Scroll to the end of Mark 1: "End of Mark 1 · Keep scrolling for Mark 2", then Mark 2. The pill
  follows the chapter on screen.
- Scroll to the end of Mark 16: "End of Mark · Keep scrolling for Philippians", then "About
  Philippians".

## 3. Navigate (US2)

- Tap "Mark 1 ▾": the panel drops down over a dimmed feed (`07-chapter-picker.png`). Tap chapter
  4, then its third section: the panel closes with that card at the top. That's three taps
  (SC-006).
- Tap the book button: all 66 books under sticky testament headers, opened at Mark, with "Ready"
  on Mark and Philippians (`08-book-list.png`). Pick Genesis: its chapter grid and "Genesis is
  coming soon" (`09-genesis.png`, without "Notify me", which is deferred).
- Tap the dimmed backdrop: the panel closes.

## 4. Resume (US3)

- Scroll to Mark 2:13–17, quit the app from the app switcher and relaunch: the feed opens with that
  card at the top, in under 2 seconds (SC-001).
- Delete and reinstall: it opens at the "About Mark" post.
- Run `xcrun simctl openurl booted thinkbible://section/mrk-1-21`: the feed opens at Mark 1:21–28.

## 5. Offline (US4)

- Delete the app, turn on airplane mode (on the simulator: run the app with the network link
  conditioner at 100% loss), install and launch: Mark and Philippians read in full in both
  translations (SC-003; KJV via the `-translation kjv` launch argument in Debug builds).
- Mark 7:14–23 in the BSB shows the manuscript note where 7:16 is missing; the KJV shows the verse.
- With a newer pack on the channel (republish a test book to draft), the app downloads it while
  running but keeps the open feed unchanged; the next launch uses it at the same position.

## 6. Share (US5)

- Tap Send on Mark 1:1–8: the share sheet holds the passage, "Mark 1:1–8 (BSB)" and a
  `thinkbible.app` link.

## 7. Accessibility and dark mode

- Turn on VoiceOver: chapter tiles read "Mark chapter 1", section rows read range and title, the
  drop cap reads as part of the first word, the counter reads "Page 1 of 2".
- Set the largest accessibility text size: nothing is clipped, justification turns off, and pages
  re-split with no verse cut.
- Switch to dark mode: every surface uses the dark tokens, and text stays readable.

## 8. Smoothness (SC-002)

On a physical iPhone 16 or older, record Instruments' "Hitches" template while flinging through Mark
1 and paging its cards. **Expected**: hitch-time ratio under 5 ms/s.

## 9. Channels

- A Release build (`make ios-packs CHANNEL=live` first) reads only the live channel. Until a book
  is promoted, the live catalog returns 403 and the build has no bundled books; the build step
  warns about it.
- The Release configuration's `CONTENT_CHANNEL` is `live` (a test checks it).
