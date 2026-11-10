# Feature Specification: Subscription, Paywall and You & Settings

**Feature Branch**: `006-subscription-paywall-settings`

**Created**: 2026-11-03

**Updated**: 2026-11-10 for the "book feel" design: Settings becomes **You & settings**, opened from
the avatar or the chapter panel. Scripture font, "Open in" and "Open questions automatically" are
gone. Accent color, Justify text, Show questions and Harder-question alerts are new. "Submit" is
now "Post". The paywall and entitlement rules are unchanged.

**Status**: Draft

**Input**: User description: "Subscription, paywall and settings (brief spec 7): reading is always
free. Every device gets 3 free reflections in total (counted by posted answers, enforced
server-side per device so reinstalling doesn't reset it). The composer note shows 'N of 3 free
reflections left'. On the next Post after they're used, a paywall sheet opens over the feed,
keeping the typed answer, which is checked as soon as the trial starts. Premium is monthly or
yearly (yearly preselected) with a 7-day free trial, restore, and manage subscription. You &
settings covers reading, questions, appearance, reminder, subscription, your reflections and
about."

**References**: [docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Free reflections and the
paywall, You & settings); mockup [Paywall.dc.html](../../docs/design/screens/Paywall.dc.html);
[docs/design/README.md](../../docs/design/README.md) (You & settings, Composer, Tokens); screen
[10-you-settings.png](../../docs/design/screens/10-you-settings.png); brief "Users and business
model"; constitution principles I, VI, IX, X. Depends on 003 (compare service outcomes), 004
(harder-question alerts) and 005 (profile, books, saved passages, reflections settings).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Three free reflections, clearly counted (Priority: P1)

A new reader gets 3 reflections with full personal replies. Under the composer the note reads "A
sentence or so · 2 of 3 free reflections left". Once they're used, it reads "You've used your 3
free reflections." Reinstalling the app doesn't reset the count.

**Why this priority**: The free tier is the conversion funnel, and it has to feel generous and
honest.

**Independent Test**: On a fresh device, post three answers and watch the count drop. Delete and
reinstall, and confirm the count is still used up.

**Acceptance Scenarios**:

1. **Given** a new device, **When** the first composer opens, **Then** its note reads "3 of 3 free
   reflections left" (or the equivalent wording at each count).
2. **Given** a free reflection's live check succeeds, **When** the reply shows, **Then** the count
   goes down by one. An unlocked Level 2–3 question counts the same way.
3. **Given** a re-check of a free answer, or a failed, offline or capped check, **When** it
   completes, **Then** the count is unchanged.
4. **Given** the app is deleted and reinstalled on the same device, **When** the composer opens,
   **Then** the server-side count is restored.
5. **Given** the device was offline when posting, **When** it comes back online, **Then** the count
   syncs with the server.

---

### User Story 2 - Paywall that keeps your answer (Priority: P1)

With no free reflections left, the reader types an answer and taps Post. A sheet slides up over the
feed:
- "Keep thinking it through" and the subtitle;
- a "Waiting · Mark 1:9–11" card with their pending answer;
- three benefit rows;
- the plans, Yearly (preselected, "Save 37%", "just $2.50 a month") and Monthly;
- "Start 7-day free trial", with the post-trial price and "Cancel anytime in Settings";
- Restore purchases · Terms · Privacy;
- "Not now, keep reading".

If they start the trial, the sheet closes and their answer is checked straight away.

**Why this priority**: This is the revenue path, and keeping the answer avoids punishing the reader
for hitting the limit.

**Independent Test**: In a StoreKit test environment, use up the free reflections, post a fourth
answer, start the yearly trial, and confirm the answer is checked automatically and the reply
appears.

**Acceptance Scenarios**:

1. **Given** no free reflections and no subscription, **When** Post is tapped, **Then** the paywall
   sheet opens and the typed answer is saved as a draft.
2. **Given** the sheet, **When** it shows plans, **Then** prices, trial length and per-month
   equivalents come from the App Store, not the app. Yearly is preselected, and the line under the
   button updates with the selected plan.
3. **Given** the reader starts the trial, **When** the purchase completes, **Then** the sheet
   closes and the waiting answer is posted and checked automatically.
4. **Given** "Not now, keep reading" or the close button, **When** tapped, **Then** the sheet
   closes, the draft is kept in the composer, and reading continues freely.
5. **Given** a reader who already subscribed on another device, **When** they tap Restore
   purchases, **Then** Premium is restored, and the waiting answer is checked.

---

### User Story 3 - Premium unlocks unlimited reflections (Priority: P1)

A subscriber can reflect on any section, at every level as it unlocks, subject only to the fair-use
daily cap. When a subscription lapses, reading and saved reflections remain, and new posts go back
to the paywall.

**Why this priority**: The service must deliver what was paid for, and the backend must know about
entitlement without accounts.

**Independent Test**: With an active test subscription, post more than 3 answers. Expire it, and
confirm the next Post opens the paywall while saved reflections stay viewable.

**Acceptance Scenarios**:

1. **Given** an active subscription or trial, **When** Post is tapped, **Then** a live check runs
   with no free count shown.
2. **Given** a lapsed subscription and no free reflections, **When** Post is tapped, **Then** the
   paywall opens. Reading and saved reflections are unaffected.
3. **Given** a subscriber, **When** the compare service is called, **Then** it verifies the
   entitlement itself, without any app account.

---

### User Story 4 - You & settings (Priority: P2)

The reader taps their avatar (or "You & settings" at the bottom of the chapter panel). A screen
opens with a back link to the current chapter ("‹ Mark 1"). Under the profile, books and saved
passages from spec 005, it lists:
- **Reading:** Translation (BSB / KJV); Text size, a slider with a live page preview (drop cap,
  justified text, folio); Accent color (Blue / Red, "Drop caps, verse numbers, question label");
  Justify text ("Book-style edges. Off at the largest size."); Verse numbers.
- **Questions:** Show questions ("Off for plain reading. Your reflections stay saved."),
  Harder-question alerts ("One notification when a new level unlocks, a day after you answer.").
- **Appearance:** System / Light / Dark.
- **Reminder:** Daily reading reminder and Time.
- **Subscription:** "Free · 2 of 3 free reflections left" with See plans; Restore purchases.
- **Your reflections:** iCloud sync status, Delete all reflections.
- **About:** Sources and licenses, AI disclosure, Report a problem, Privacy policy · Terms, version.

**Why this priority**: Needed for launch (restore, legal links, appearance) but not for the core
loop.

**Independent Test**: Change each setting and confirm its effect in the feed: text size and page
re-split, red accent, justify off, verse numbers off, questions hidden, dark appearance, KJV text,
and a scheduled reminder notification.

**Acceptance Scenarios**:

1. **Given** Text size, **When** the slider moves, **Then** the preview and every page in the feed
   use the new size on top of Dynamic Type, and pages re-split between verses.
2. **Given** Accent color is Red, **When** the feed shows, **Then** drop caps, verse numbers,
   heading rules, question labels and accents use the red rubric token.
3. **Given** Justify text is off, or the largest text size is chosen, **When** pages draw, **Then**
   text is left-aligned with no hyphenation.
4. **Given** Show questions is off, **When** the feed shows, **Then** every question footer and
   thread is hidden, the text is unchanged, and no reflection is deleted.
5. **Given** Translation is switched to KJV, **When** the reader returns to the feed, **Then** the
   same section is on screen in KJV.
6. **Given** Appearance is set to Dark, **When** the reader returns to any screen, **Then** the
   whole app uses dark tokens. System follows the device.
7. **Given** the reminder is switched on, **When** permission is not yet granted, **Then** the
   system permission prompt appears. Once granted, a daily local notification is scheduled at the
   chosen time (7:30 AM default), and opening it lands on the reading position. Unlocks fold into it
   (spec 004).
8. **Given** a free user, **When** the Subscription group shows, **Then** it reads "Free · N of 3
   free reflections left" with "See plans" and "Restore purchases". For Premium it shows the plan
   name and "Manage subscription", which opens the App Store's management sheet.
9. **Given** About → Sources and licenses, **When** opened, **Then** it lists BSB, KJV, Matthew
   Henry, Jamieson-Fausset-Brown and Adam Clarke with their licenses. It says the commentaries are
   Protestant (Reformed and Wesleyan), that AI summarises them into key ideas, and that Enduring
   Word is link-out only.

### Edge Cases

- A purchase is pending (Ask to Buy, SCA): the sheet shows a pending state, and the waiting answer
  stays as a draft until the purchase completes.
- A purchase fails or is cancelled: the sheet stays open with the plan still selected, and no
  answer is lost.
- Refund or revocation: Premium ends at the next entitlement check. Saved reflections remain.
- Offline at Post with no free reflections: the paywall cannot verify anything, so the answer is
  saved and the fallback reply is shown. The paywall opens when back online.
- A device without App Attest support: free reflections cannot be granted safely. Readers can
  still read, and Premium still works through a verified purchase.
- Family Sharing: whether it is enabled is decided in App Store Connect configuration, and
  entitlement follows the App Store's answer.
- Free-tier abuse across many devices: accepted risk. Each real device gets 3.
- Harder-question alerts switched on without notification permission: the system prompt is shown
  (or, if denied before, a line explains how to allow it in iOS Settings).

## Requirements *(mandatory)*

### Functional Requirements

**Free reflections and entitlement**

- **FR-001**: Each device MUST get a fixed number of free reflections in total (default 3,
  configurable on the server without an app update), counted only by successful, first-time live
  checks of a new answer, at any level.
- **FR-002**: The free count MUST be kept on the server per attested device, so reinstalling does
  not reset it. No account and no personal data are used.
- **FR-003**: For non-subscribers, the composer note MUST show "A sentence or so · <n> of 3 free
  reflections left", or "You've used your 3 free reflections." when none are left.
- **FR-004**: The compare service MUST return the "free limit reached" outcome when a
  non-subscribed device has no free reflections left. The app MUST then open the paywall sheet and
  keep the answer as a draft.
- **FR-005**: The compare service MUST verify subscription status from a signed App Store
  transaction sent by the app, without accounts, and treat trial and active subscriptions as
  Premium.
- **FR-006**: Premium MUST grant unlimited live comparisons at every level, subject only to the
  daily fair-use cap (spec 003).

**Paywall**

- **FR-007**: The paywall MUST be a sheet over the feed with the content and order in DESIGN.md:
  grab handle and close, title, subtitle, waiting-answer card, three benefits, plan radio group
  (Yearly preselected with savings and per-month price; Monthly), "Start 7-day free trial" with
  post-trial price and "Cancel anytime in Settings", Restore · Terms · Privacy, and "Not now, keep
  reading".
- **FR-008**: All prices, savings percentages, per-month equivalents and trial lengths MUST come
  from the App Store product data, never from app code.
- **FR-009**: Offer two auto-renewing subscriptions (monthly and yearly) in one group, each with a
  7-day introductory free trial.
- **FR-010**: After a successful purchase or restore, the waiting answer MUST be posted
  automatically.
- **FR-011**: The paywall MUST never block reading, navigation, Show questions off, or viewing saved
  reflections.

**You & settings**

- **FR-012**: You & settings MUST open from the header avatar and from the chapter panel's "You &
  settings" row, with a back link to the current chapter, and provide the groups and rows in Story
  4 in that order, under the profile, books and saved passages (spec 005). Rows are at least 44pt.
- **FR-013**: Translation and text size MUST be controlled only here (never in the header or on
  cards). Text size MUST offer a slider with a live page preview, applied on top of Dynamic Type.
- **FR-014**: Accent color MUST offer Blue (default) and Red, switching the `rubric` token set
  app-wide. Justify text (default on) MUST be forced off at the largest text size. Verse numbers
  MUST toggle their display.
- **FR-015**: Show questions (default on) MUST hide or show every question footer and thread
  (spec 003 FR-016). Harder-question alerts (on by default once permission is granted) MUST turn
  unlock notifications on or off (spec 004).
- **FR-016**: Appearance MUST offer System, Light and Dark, applied app-wide.
- **FR-017**: The daily reminder MUST use local notifications, ask permission only when switched
  on (unless already granted), default to 7:30 AM, and open the reading position when tapped.
- **FR-018**: About MUST show sources and licenses, the AI disclosure, the commentary tradition
  disclosure, Report a problem, Privacy policy, Terms of use and the app version.

### Key Entities

- **Entitlement** (device): subscription status from the App Store, plus the free reflections
  remaining (as reported by the server).
- **Device free count** (server): attested device key → free reflections used. No personal data.
- **Subscription products** (App Store): monthly and yearly, in one group, each with a trial.
- **Preferences** (device, `@AppStorage`): translation, text size, accent color, justify text,
  verse numbers, show questions, harder-question alerts, appearance, reminder on and time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of attempts to reset the free count by reinstalling fail in testing.
- **SC-002**: 0 answers are lost across every paywall path (start trial, restore, not now, close,
  failed purchase, pending purchase).
- **SC-003**: The waiting answer's reply appears within 3 seconds of a successful trial start.
- **SC-004**: After launch, about 4–5% of new users subscribe within 30 days (business target).
- **SC-005**: No app code contains a hard-coded price or color (enforced by a lint check).
- **SC-006**: Paywall is not the top complaint in App Store reviews in the first 90 days.

## Assumptions

- The free tier is 3 reflections in total per device, after which the reader must subscribe
  (confirmed 2026-11-04). An unlocked Level 2–3 question counts as a reflection (the brief's open
  question leans yes). A/B testing 3 against 5 is later work.
- Prices ($3.99 monthly, $29.99 yearly) and the 7-day trial are App Store Connect configuration and
  can change without an app update.
- The paywall sheet's layout is unchanged from `Paywall.dc.html`. It is restyled with book-feel
  tokens where they overlap.
- The You & settings screen does not draw an AI disclosure row. It stays in About, required by spec
  003 FR-006 and the App Store.
- The text-size slider's steps are not specified by the design. Default to 5 steps (15, 16, 17
  default, 19, 21pt Scripture base) until a design value is given.
- Privacy policy and Terms are hosted on thinkbible.app.
- "Report a problem" opens a pre-addressed email with the app version and section, and no answer
  text unless the reader adds it.
- Groups and homeschool tiers are V2.
