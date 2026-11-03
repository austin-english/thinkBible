# Feature Specification: Subscription, Paywall and Settings

**Feature Branch**: `006-subscription-paywall-settings`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Subscription, paywall and Settings (brief spec 7): reading is always
free. Every device gets 3 free reflections in total (counted by submitted answers, enforced
server-side per device so reinstalling doesn't reset it). The question card shows 'N of 3 free
reflections left'. On the next Submit after they're used, a paywall sheet opens over the reader,
keeping the typed answer, which is checked as soon as the trial starts. Premium is monthly or
yearly (yearly preselected) with a 7-day free trial, restore, and manage subscription. Settings
covers reading, study, appearance, reminder, subscription, your reflections and about."

**References**: [docs/design/DESIGN.md](../../docs/design/DESIGN.md) (Free reflections and the
paywall, Settings); mockups [Paywall.dc.html](../../docs/design/screens/Paywall.dc.html),
[Settings.dc.html](../../docs/design/screens/Settings.dc.html),
[SettingsDark.dc.html](../../docs/design/screens/SettingsDark.dc.html); brief "Users and business
model"; constitution principles I, VI, IX, X. Depends on 003 (compare service outcomes) and 005
(reflections settings).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Three free reflections, clearly counted (Priority: P1)

A new reader gets 3 reflections with full personal results. Under the question card's buttons a
small note reads "2 of 3 free reflections left". Once they're used, it reads "You've used your 3
free reflections." Reinstalling the app doesn't reset the count.

**Why this priority**: The free tier is the conversion funnel, and it has to feel generous and
honest.

**Independent Test**: On a fresh device, submit three answers and watch the count drop. Delete and
reinstall, and confirm the count is still used up.

**Acceptance Scenarios**:

1. **Given** a new device, **When** the first question card shows, **Then** it reads "3 of 3 free
   reflections left" (or the equivalent wording at each count).
2. **Given** a free reflection's live check succeeds, **When** results show, **Then** the count
   goes down by one.
3. **Given** a re-check of a free answer, or a failed, offline or capped check, **When** it
   completes, **Then** the count is unchanged.
4. **Given** the app is deleted and reinstalled on the same device, **When** the card shows,
   **Then** the server-side count is restored.
5. **Given** the device was offline when submitting, **When** it comes back online, **Then** the
   count syncs with the server.

---

### User Story 2 - Paywall that keeps your answer (Priority: P1)

With no free reflections left, the reader types an answer and taps Submit. A sheet slides up over
the reader:
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

**Independent Test**: In a StoreKit test environment, use up the free reflections, submit a fourth
answer, start the yearly trial, and confirm the answer is checked automatically and results appear.

**Acceptance Scenarios**:

1. **Given** no free reflections and no subscription, **When** Submit is tapped, **Then** the
   paywall sheet opens and the typed answer is saved as a draft.
2. **Given** the sheet, **When** it shows plans, **Then** prices, trial length and per-month
   equivalents come from the App Store, not the app. Yearly is preselected, and the line under the
   button updates with the selected plan.
3. **Given** the reader starts the trial, **When** the purchase completes, **Then** the sheet
   closes and the waiting answer is submitted and checked automatically.
4. **Given** "Not now, keep reading" or the close button, **When** tapped, **Then** the sheet
   closes, the draft is kept in the card, and reading continues freely.
5. **Given** a reader who already subscribed on another device, **When** they tap Restore
   purchases, **Then** Premium is restored, and the waiting answer is checked.

---

### User Story 3 - Premium unlocks unlimited reflections (Priority: P1)

A subscriber can reflect on any section, at every level, subject only to the fair-use daily cap.
When a subscription lapses, reading and saved reflections remain, and new submissions go back to
the paywall.

**Why this priority**: The service must deliver what was paid for, and the backend must know about
entitlement without accounts.

**Independent Test**: With an active test subscription, submit more than 3 answers. Expire it, and
confirm the next Submit opens the paywall while saved reflections stay viewable.

**Acceptance Scenarios**:

1. **Given** an active subscription or trial, **When** Submit is tapped, **Then** a live check runs
   with no free count shown.
2. **Given** a lapsed subscription and no free reflections, **When** Submit is tapped, **Then** the
   paywall opens. Read mode and saved reflections are unaffected.
3. **Given** a subscriber, **When** the compare service is called, **Then** it verifies the
   entitlement itself, without any app account.

---

### User Story 4 - Settings (Priority: P2)

From Home's gear, the reader opens Settings, a grouped list:
- **Reading:** Translation; Text size (5 steps with a live Mark 1:1 preview); Scripture font
  (Serif / Sans); Verse numbers.
- **Study:** Open in (Study / Read); Open questions automatically.
- **Appearance:** System / Light / Dark.
- **Reminder:** daily reading reminder and time.
- **Subscription:** status, See plans, Restore, Manage subscription.
- **Your reflections:** iCloud status, Delete all.
- **About:** sources and licenses, AI disclosure, Report a problem, Privacy, Terms, version.

**Why this priority**: Needed for launch (restore, legal links, appearance) but not for the core
loop.

**Independent Test**: Change each setting and confirm its effect: text size in the reader, Read as
default mode, dark appearance, and a scheduled reminder notification.

**Acceptance Scenarios**:

1. **Given** Text size, **When** the slider moves, **Then** the serif preview and the reader's
   Scripture text use 15, 16, 17 (default), 19 or 21pt as the base, on top of Dynamic Type.
2. **Given** Appearance is set to Dark, **When** the reader returns to any screen, **Then** the
   whole app uses dark tokens. System follows the device.
3. **Given** the reminder is switched on, **When** permission is not yet granted, **Then** the
   system permission prompt appears. Once granted, a daily local notification is scheduled at the
   chosen time (7:30 AM default), and opening it lands on the Continue section.
4. **Given** a free user, **When** the Subscription group shows, **Then** it reads "Free · N of 3
   free reflections left" with "See plans" and "Restore purchases". For Premium it shows the plan
   name and "Manage subscription", which opens the App Store's management sheet.
5. **Given** About → Sources and licenses, **When** opened, **Then** it lists BSB, KJV, Matthew
   Henry, Jamieson-Fausset-Brown and Adam Clarke with their licenses. It says the commentaries are
   Protestant (Reformed and Wesleyan), that AI summarises them into key ideas, and that Enduring
   Word is link-out only.

### Edge Cases

- A purchase is pending (Ask to Buy, SCA): the sheet shows a pending state, and the waiting answer
  stays as a draft until the purchase completes.
- A purchase fails or is cancelled: the sheet stays open with the plan still selected, and no
  answer is lost.
- Refund or revocation: Premium ends at the next entitlement check. Saved reflections remain.
- Offline at Submit with no free reflections: the paywall cannot verify anything, so the answer is
  saved and the fallback results are shown. The paywall opens when back online.
- A device without App Attest support: free reflections cannot be granted safely. Readers can
  still read, and Premium still works through a verified purchase.
- Family Sharing: whether it is enabled is decided in App Store Connect configuration, and
  entitlement follows the App Store's answer.
- Free-tier abuse across many devices: accepted risk. Each real device gets 3.

## Requirements *(mandatory)*

### Functional Requirements

**Free reflections and entitlement**

- **FR-001**: Each device MUST get a fixed number of free reflections in total (default 3,
  configurable on the server without an app update), counted only by successful, first-time live
  checks of a new answer.
- **FR-002**: The free count MUST be kept on the server per attested device, so reinstalling does
  not reset it. No account and no personal data are used.
- **FR-003**: The question card MUST show "<n> of 3 free reflections left", or "You've used your 3
  free reflections." when none are left, for non-subscribers.
- **FR-004**: The compare service MUST return the "free limit reached" outcome when a
  non-subscribed device has no free reflections left. The app MUST then open the paywall sheet and
  keep the answer as a draft.
- **FR-005**: The compare service MUST verify subscription status from a signed App Store
  transaction sent by the app, without accounts, and treat trial and active subscriptions as
  Premium.
- **FR-006**: Premium MUST grant unlimited live comparisons at every level, subject only to the
  daily fair-use cap (spec 003).

**Paywall**

- **FR-007**: The paywall MUST be a sheet over the reader with the content and order in DESIGN.md:
  grab handle and close, title, subtitle, waiting-answer card, three benefits, plan radio group
  (Yearly preselected with savings and per-month price; Monthly), "Start 7-day free trial" with
  post-trial price and "Cancel anytime in Settings", Restore · Terms · Privacy, and "Not now, keep
  reading".
- **FR-008**: All prices, savings percentages, per-month equivalents and trial lengths MUST come
  from the App Store product data, never from app code.
- **FR-009**: Offer two auto-renewing subscriptions (monthly and yearly) in one group, each with a
  7-day introductory free trial.
- **FR-010**: After a successful purchase or restore, the waiting answer MUST be submitted
  automatically.
- **FR-011**: The paywall MUST never block reading, Read mode or viewing saved reflections.

**Settings**

- **FR-012**: Settings MUST provide the groups and rows listed in Story 4, each row at least 52pt
  tall, stored as device preferences.
- **FR-013**: Text size MUST offer 5 steps (15, 16, 17, 19, 21pt base for Scripture) with a live
  serif preview of Mark 1:1. Scripture font MUST offer Serif and Sans, and Verse numbers MUST
  toggle their display.
- **FR-014**: "Open in" MUST set the reader's default mode, and "Open questions automatically"
  (on by default, subtitled "When you reach the end of a section") MUST control card auto-open.
- **FR-015**: Appearance MUST offer System, Light and Dark, applied app-wide.
- **FR-016**: The daily reminder MUST use local notifications, ask permission only when switched
  on, default to 7:30 AM, and open the Continue section when tapped.
- **FR-017**: About MUST show sources and licenses, the AI disclosure, the commentary tradition
  disclosure, Report a problem, Privacy policy, Terms of use and the app version.

### Key Entities

- **Entitlement** (device): subscription status from the App Store, plus the free reflections
  remaining (as reported by the server).
- **Device free count** (server): attested device key → free reflections used. No personal data.
- **Subscription products** (App Store): monthly and yearly, in one group, each with a trial.
- **Preferences** (device): translation, text size, font, verse numbers, open-in mode, auto-open,
  appearance, reminder on and time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of attempts to reset the free count by reinstalling fail in testing.
- **SC-002**: 0 answers are lost across every paywall path (start trial, restore, not now, close,
  failed purchase, pending purchase).
- **SC-003**: The waiting answer's results appear within 3 seconds of a successful trial start.
- **SC-004**: After launch, about 4–5% of new users subscribe within 30 days (business target).
- **SC-005**: No app code contains a hard-coded price or color (enforced by a lint check).
- **SC-006**: Paywall is not the top complaint in App Store reviews in the first 90 days.

## Assumptions

- The free tier is 3 reflections in total, per the brief and the paywall spec. DESIGN.md's line
  "free tier is 1 reflection a day" is stale. A/B testing 3 against 5 is later work.
- Prices ($3.99 monthly, $29.99 yearly) and the 7-day trial are App Store Connect configuration and
  can change without an app update.
- Privacy policy and Terms are hosted on thinkbible.app.
- "Report a problem" opens a pre-addressed email with the app version and section, and no answer
  text unless the reader adds it.
- Groups and homeschool tiers are V2.
