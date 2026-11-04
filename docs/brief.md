> Exported from the ThinkBible product & architecture brief (claude.ai/artifact/BssLySyZMQDLhZKAPMDeFf). The online doc is the source of truth; re-export when it changes.

# ThinkBible — Product & Architecture Brief

Oct 29, 2026 · @Austin

## Product overview

A Bible reader where you think first: scroll through a book one section at a time, write what you think each passage means, then compare your reflection with what trusted commentators noticed. Most AI Bible apps tell you what a verse means; this one asks you first.

- **Core loop:** read a section → answer one thoughtful question → tap Submit → see what you caught, what commentators add, where traditions differ, and quick context → keep scrolling to the next section.
- **Feel:** one continuous, scrolling chapter like a printed Bible, split into passage sections rather than single verses because meaning lives at the paragraph level. Each section's question and results sit inline under its verses, so the reader never leaves the text.
- **Grounded, not invented:** questions, key ideas and context are generated once in batch jobs from public-domain commentaries, reviewed, and shipped as content packs. The live AI only compares your answer with those stored ideas.
- **Works offline:** the stored key ideas are on the phone, so the comparison card always works; the personal note fills in when online.
- **Your reflections:** saved per section and shown in Home's contents, where each answered section offers "Read again · Level 2" for a harder question.
- **Name:** ThinkBible (App Store: "ThinkBible: Read & Reflect"; domain thinkbible.app). Tagline idea: "Think first. Then see what the commentators saw."

## Users and business model

Scripture stays free; people pay for the study experience around it. Faith apps that sell an experience rather than the text do well: Hallow made roughly $40M in 2025.

| User | Wants | Uses it |
| --- | --- | --- |
| Personal Bible reader | Understand what they read, not just get through it | Daily, 10–20 minutes |
| Newer believer | Guidance without feeling lost or judged | Several times a week |
| Small-group member | Be ready for the group discussion | Weekly, around the group |
| Homeschool parent (later) | Structured, thoughtful Bible study for kids | School days |

**Free vs Premium (prices are hypotheses to test):**

- **Free:** reading is always free (Read mode and the full text), plus **3 free reflections** with full results, counted by submitted answers. The question card shows "2 of 3 free reflections left". On the 4th Submit the paywall opens as a sheet; the typed answer is kept and checked as soon as the trial starts. The free count is stored server-side per device (App Attest), so reinstalling doesn't reset it. Earlier reflections stay viewable after the free ones run out.
- **Premium, about $3.99/month or $29.99/year:** unlimited reflections, harder questions on every re-read (Levels 2–3), every study book as it's released, seasonal series.
- **Free trial:** 7 days of Premium, offered on the paywall as "Start 7-day free trial" with the plan price and "Cancel anytime in Settings" underneath (yearly preselected, "Save 37%"). The sheet also has Restore purchases, Terms, Privacy and "Not now, keep reading".
- **Groups and homeschool tier:** V2.

**Seasonality:** downloads spike around Lent, Easter, Advent and New Year. Launch, and release new books and series, ahead of those windows.

**Lesson from Scroll The Bible:** its most common complaint is the paywall. Never lock the Bible text itself, and show clearly what's free.

## The feed

One continuous scroll per chapter, split into passage sections (roughly 5–12 verses), not single verses. Sections are shared across both translations: titled from the BSB headings and checked against Matthew Henry's divisions, so each section lines up with how the commentary groups its notes.

**Why sections, not single verses:**

- "What does this mean?" works for a story or an argument; a single verse lifted out of it often loses its meaning.
- Commentaries explain verse groups, so stored key ideas line up with each section.
- One prompt per section feels like a natural pause; one per verse would be exhausting.

**What's on screen:**

| Part | What's on it | Actions |
| --- | --- | --- |
| Sticky section header | Ref, title in serif, status chip (✓ 2/4 or Skipped); pins while the section is on screen | None |
| Verse text | Verses with superscript numbers; the verse a question is about is tinted while answering | Tap a "v. N" tag in the results to highlight that verse |
| Question card (under the verses) | "Your turn · verse N", one question for this read, answer box with mic, free-reflection count | Submit, Skip, "Not a helpful question?" (once) |
| Results (same card after Submit) | Your answer with the matched phrase highlighted, "What commentators noticed": personal note, You caught / What you missed with sources and verse tags, Enduring Word link | Edit (2 re-checks), collapse to a one-line row |

**Layout rules:**

- Very short sections merge with the next.
- A section gets a short context note instead of a question only when the commentaries give nothing to ask about (for example a bare census total). Genealogies, lists and laws still get questions wherever the commentaries discuss them, aimed at those verses.
- Drafts save automatically while typing.

**Two modes, switchable at any time:**

- **Read:** pure scrolling, no prompts. Always free.
- **Study:** a question card under each section (the default).

**Prompt frequency (Study mode setting):** "Open questions automatically" in Settings opens each section's question when you reach the end of its verses (default on); off, questions stay as a one-line row until tapped.

## User flow

Every answered section shows its results in place under the verses: personal when the answer matches and the user is online, and "Here's what commentators noticed" from stored key ideas when they skip, say they don't know, or are offline.

_(User flow diagram: see the online brief. It predates the inline reader; follow docs/design/DESIGN.md for the current flow.)_

Read mode skips the reflection step entirely and simply moves to the next section.

## Content sources and licensing

Launch with two public-domain translations, the BSB (default) and the KJV, sharing one set of study content generated from the KJV and three well-known commentaries written on it. Fewer sources means fewer chances for a wrong or slanted idea to slip in, and more trust.

| Content | Source | License | Notes |
| --- | --- | --- | --- |
| Default translation | Berean Standard Bible (BSB), via the Free Use Bible API (or berean.bible downloads) | Dedicated to the public domain (CC0) on April 30, 2023 | Modern, readable, close to the original wording; scholar-advised; section headings included |
| Second translation | King James Version, via the [Free Use Bible API](https://github.com/HelloAOLab/bible-api) | Public domain in the US | One-tap switch in Settings and on the reading card |
| Sections | One shared set of verse ranges for both translations | — | Titled from the BSB headings, checked against Matthew Henry's divisions so each card lines up with the commentary |
| Commentary 1 | Matthew Henry's Commentary, via the Free Use Bible API commentary endpoints | Public domain (CC0 mark per the [API's listing](https://learnofchrist.com/resources/free-use-bible-api)) | Reformed (Presbyterian); the best-known devotional commentary, practical and warm; written on the KJV text |
| Commentary 2 | Jamieson-Fausset-Brown, same source | Public domain (CC0 mark) | Reformed-leaning; more concise and technical, strong on background and word meanings |
| Commentary 3 | Adam Clarke's Commentary, same source | Public domain (CC0 mark) | Wesleyan (Methodist); practical and detailed; balances Reformed readings on predestination and free will, closer to Enduring Word's view |
| Enduring Word (David Guzik) | Link out only | Their [FAQ](https://enduringword.com/faqs-for-david-guzik/) says content can't be hosted on other platforms, so it can't be summarized into key ideas either | "Read David Guzik on this passage" link on each comparison card; request permission for more through their form |
| NKJV | Thomas Nelson (HarperCollins) | Copyrighted; an app needs a license | V2, only if licensed |
| WEB and others | Free Use Bible API | Public domain or free use | V2; reuse the same study content with an alignment check |

**Where the data comes from, and how it stays fixed:**

- **One source, downloaded once:** the two translations and three commentaries are pulled from the Free Use Bible API a single time by an import script, then frozen as write-once files in a private S3 bucket. Their checksums and the retrieval date are recorded in `content/sources/manifest.json` in the repo, and the pipeline works from a verified local copy in `content/sources/`. The app and pipeline never call the API live.
- **Closed world for the models:** every model call receives only the excerpts for one section from that frozen snapshot. Bedrock models have no web access, and the pipeline gives them no browsing or search tools.
- **No sprawl from coding agents:** the repo's `CLAUDE.md` and the constitution state that pipeline code may read only `content/sources/`; adding or updating a source is a deliberate, reviewed change (new snapshot, new checksums), never something an agent does on its own.
- **Provenance in every pack:** each content pack records the source names, snapshot date and checksums it was built from.
- **Spot verification:** for the launch book, compare a sample of passages in the snapshot against a printed or CCEL edition of each commentary to confirm the text is complete and unaltered.

**One study set, two translations:** questions, key ideas and context are generated once, from the KJV plus Matthew Henry, JFB and Adam Clarke, in plain modern English that doesn't quote either translation's wording. Verse references are placeholders the app fills in with the reader's translation. A cheap alignment step then adds a per-translation wording variant only where a question or idea leans on KJV-only words, and a short neutral note where a verse is present in one translation but missing or bracketed in the other. The expensive generation never runs per translation.

**Adding translations later:** a new public-domain translation needs only its verse text and the alignment check. Separate commentary sets are for traditions (for example Catholic, with Haydock), not for translations.

**Attribution:** every key idea carries the commentator it came from, and the comparison card shows those names.

## Content pipeline (batch jobs)

All the study content is produced ahead of time, one book at a time, reviewed, and published as a versioned content pack the app downloads. The live app never asks the model to interpret Scripture on its own.

1. **Import text and sections:** load the BSB and KJV texts from the frozen snapshot in content/sources/; define one shared set of sections (verse ranges) titled from the BSB headings and checked against Matthew Henry's divisions; split long sections and merge very short ones by rule.
2. **Gather commentary:** for each section, pull the matching excerpts from the frozen snapshot of Matthew Henry, Jamieson-Fausset-Brown and Adam Clarke only; nothing is fetched from the web.
3. **Extract key ideas:** a Sonnet-class model condenses the excerpts into 3–5 key ideas in plain modern English, each tagged with its source commentators; ideas that two or three commentators share are marked as agreed, and the best-supported ideas are chosen first. Ideas only commentators state are allowed; no new interpretations. No quoted translation wording; verse references are placeholders.
4. **Write questions:** from the key ideas, a pool of 3–5 questions per section, mixed by type (noticing, meaning, application), each aimed at a key idea without giving it away, and phrased to work in either translation.
5. **Context and differences:** a two-line context note (who wrote it, to whom, why) and, where commentators or traditions disagree, a short neutral "views differ" note.
6. **Verse notes:** one short note for verses worth explaining on their own (names, places, customs).
7. **Translation alignment (cheap, mostly code):** check every question and key idea against the BSB wording; anything that leans on KJV-only words gets a per-translation wording variant from a small model call; verses present in one translation but missing or bracketed in the other get a short, neutral manuscript note. Steps 3–6 run once, never per translation.
8. **Automatic checks:** length limits; questions end with "?"; no key idea repeated word for word in a question; every key idea has at least one source; every verse placeholder resolves in both translations; JSON schema valid.
9. **Model review:** a second model pass grades each question and key idea against the quality rules and flags weak ones.
10. **Human review:** you review flagged items, the translation variants and manuscript notes, and read through the launch book in full; later books get spot checks.
11. **Publish:** one study-content file per book, shared by both translations, plus one verse-text file per translation, versioned in S3 behind CloudFront; the app downloads them per book and keeps them for offline use.

**Question quality rules:** open-ended (no yes/no); short, one question at a time; answerable from the passage itself; not leading; no assumptions about one tradition's doctrine.

**How questions are shaped:** the commentary decides what is worth asking about; the passage is what the user answers from. Each question must target at least one key idea without giving it away, and be answerable from the passage alone. Each question is also ranked by difficulty: **Level 1** notices what the text says, **Level 2** interprets what it means, **Level 3** connects it to the rest of Scripture or to life. Every section gets at least one question per level (two or three levels depending on the section), and each question records which key ideas it targets.

- **Inputs per section:** the passage in both translations; the ranked key ideas (agreed ideas first); any "views differ" note; a one-line summary of the previous section; existing questions for that section (on refreshes, to avoid repeats); and the question guide.
- **Question guide:** a file in the repo with the quality rules and 10–20 example questions you write or approve. It sets the app's voice, and its version is recorded with every question.
- **By kind of passage:** stories ask what happens and why people act as they do; letters follow the argument; poetry asks about images and feelings; prophecy asks who was addressed and their situation; laws and genealogies ask about the verses the commentaries single out (for example Enoch in Genesis 5), and get a context note instead only when there is nothing to ask about.
- **Contested passages:** questions stay open ("What does this passage say about God's choosing?"), and the comparison card shows both readings.

**Example stored section:**

Shape follows `docs/design/DESIGN.md` ("Data the UI reads"); `content/schema/section.schema.json` is the binding contract.

```json
{
  "id": "mrk-1-1",
  "ref": "Mark 1:1-8",
  "title": "The Mission of John the Baptist",
  "noPrompt": false,
  "keyIdeas": [
    { "id": "mrk-1-1-k1", "title": "Untying sandals was a slave's task", "body": "John places himself below even the lowest servant's job.", "sources": ["Matthew Henry", "JFB", "Clarke"], "agreed": true, "verseStart": 7, "verseEnd": 7 },
    { "id": "mrk-1-1-k2", "title": "Jesus is the greater one", "body": "John's message points away from himself to the One coming after him.", "sources": ["Matthew Henry", "JFB"], "agreed": true, "verseStart": 7, "verseEnd": 7 },
    { "id": "mrk-1-1-k3", "title": "Water and the Spirit", "body": "John can wash the outside. Only Jesus can give the Holy Spirit.", "sources": ["JFB", "Clarke"], "agreed": true, "verseStart": 7, "verseEnd": 8 },
    { "id": "mrk-1-1-k4", "title": "Where the prophets left off", "body": "John is the messenger Isaiah promised, so the good news picks up where the prophets left off.", "sources": ["Matthew Henry", "JFB"], "agreed": true, "verseStart": 1, "verseEnd": 8 }
  ],
  "questions": [
    { "id": "mrk-1-1-q1", "level": 1, "type": "meaning", "verseStart": 7, "verseEnd": 7, "text": "Why do you think John says he isn't worthy to untie the straps of Jesus's sandals?", "textByTranslation": { "kjv": "Why do you think John says he isn't worthy to unloose Jesus's shoes?" }, "targets": ["mrk-1-1-k1", "mrk-1-1-k2"], "isAlternate": false, "status": "active", "addedIn": "1.0.0" },
    { "id": "mrk-1-1-q2", "level": 1, "type": "noticing", "verseStart": 7, "verseEnd": 7, "text": "How does John describe the One who is coming after him?", "targets": ["mrk-1-1-k2"], "isAlternate": true, "status": "active", "addedIn": "1.0.0" },
    { "id": "mrk-1-1-q3", "level": 2, "type": "meaning", "verseStart": 1, "verseEnd": 8, "text": "Mark starts his gospel with John in the wilderness, not with Jesus's birth. Why do you think he begins here?", "targets": ["mrk-1-1-k4"], "isAlternate": false, "status": "active", "addedIn": "1.0.0" },
    { "id": "mrk-1-1-q4", "level": 3, "type": "application", "verseStart": 7, "verseEnd": 8, "text": "John baptizes with water, but says Jesus will baptize with the Holy Spirit. What difference is he pointing to?", "textByTranslation": { "kjv": "John baptizes with water, but says Jesus will baptize with the Holy Ghost. What difference is he pointing to?" }, "targets": ["mrk-1-1-k3"], "isAlternate": false, "status": "active", "addedIn": "1.0.0" }
  ],
  "context": "Mark opens without a birth story; John is introduced as the messenger Isaiah foretold.",
  "viewsDiffer": null,
  "packVersion": "1.0.0"
}
```

**Running the jobs, one book at a time:** there is no single big crawl. The pipeline is a set of separate jobs, each scoped to one book, that can run in any order and be re-run on their own.

| Job | When it runs | Scope | Approx. time | Approx. cost |
| --- | --- | --- | --- | --- |
| Source snapshot | Once; again only when adding or updating a source | Whole Bible: 2 translations + 3 commentaries, chapter by chapter at a polite request rate | Under an hour | Free |
| Generate a book | Once per book release | One book: map over its sections, 10–20 in parallel | Mark (\~100 sections): about 10–20 minutes on demand, or within a day via Bedrock batch inference | Mark \~$6–10; a long book like Genesis \~$15–25 |
| Checks and model review | Right after generating a book | Same book | Minutes | Cents |
| Human review | After checks | Flagged items, plus a full read for the launch book | Mark: an evening or two; later books: spot checks | Your time |
| Publish | After you approve | Same book | Seconds | Negligible |
| Question refresh | Monthly | Only sections with thin pools or poor feedback; reuses stored key ideas | Minutes | A few dollars |
| Seasonal series | Ahead of Advent, Lent, New Year | Selected passages; new questions only | Minutes | A few dollars |
| Targeted re-run | When a prompt or model changes | Only the sections or book affected | Minutes | Proportional |

**How the split works:**

- **One workflow execution per book:** a Step Functions Standard workflow takes a book name, maps over its sections and writes results to a book-specific location. A failed section retries alone; a finished book is never touched by another book's run.
- **Idempotent by section:** each section's output is keyed by book, section and prompt version, so re-running skips sections already done unless you ask for a fresh version.
- **A human gate before publishing:** the workflow stops at "ready for review"; publishing is a separate step you trigger after approving the book.
- **On-demand vs. batch:** use on-demand calls while tuning prompts on Mark (fast feedback); switch to Bedrock batch inference for later books, which is cheaper and fine for anything not needed the same day.
- **Release rhythm:** launch with Mark, then add a book every few weeks, timed to seasons (for example John before Easter, Luke 1–2 as an Advent series). Each release is also a reason to bring readers back.

## Question freshness

Each section has a pool of questions, and new questions and series are added on a regular schedule, so rereading a book never feels like repeating a quiz.

- **Pools, not single questions:** 3–5 questions per section across types (noticing, meaning, application), all tied to the same stored key ideas, so any of them works with the comparison card.
- **Rotation per user:** the app remembers which question IDs you've answered (on the device) and picks one you haven't seen, starting with "meaning" questions on a first read and favoring "application" on later reads.
- **"Try a different question"** on the reflection card swaps in another from the pool.
- **Seasonal and themed series:** batch runs that write new questions for existing sections around a theme or season (Advent, Lent and Easter, New Year, "prayer in the Gospels"), released ahead of each season.
- **No scheduled refresh:** the three commentaries are public domain and never change, so key ideas are stable once reviewed, and re-reads already bring harder questions. New questions come only from deliberate runs: a new commentary source, replacing questions flagged "not helpful" or with odd catch rates (only those sections), topping up missing alternates, or a better model or prompt. Refreshes are additive: existing questions keep their IDs and wording, and weak ones are retired (removed from rotation but kept in the pack), never deleted. Key ideas stay the same, so refreshed questions still match the comparison card.
- **Question budget per section:** the number of levels follows the number of key ideas (1 idea = Level 1 only, 2 ideas = Levels 1–2, 3+ = all three). The pipeline never invents an idea to fill a level. Cap: 3 levels × 2 questions = 6 per section.
- **One question visible per read; alternates stay hidden.** The second question at a level is used only to (1) replace a question the reader marks "Not a helpful question?" (shown once, in place) and (2) quietly pick the one aimed at an idea the reader hasn't caught. After the last level the section shows "All levels done".
- **How levels are set:** the model records features for each question, and a fixed rule sets the level. Level 1 (notice): one verse, answer nearly stated, no outside knowledge, an idea all three commentators agree on. Level 2 (interpret): several verses or a contrast, answer must be inferred, a little context helps, usually two commentators. Level 3 (connect): needs other Scripture, history or life application, often a deeper point from one commentator.
- **Level checks:** a separate model answers each question as a typical reader with only the passage; a Level 3 it nails easily moves down, a Level 1 it struggles with is flagged. After launch, if a Level 2 question is caught more often than its section's Level 1, the next maintenance run swaps them.
- **Feedback loop:** "This question wasn't helpful" and skip rates per question feed the review queue; you see the worst performers first.
- **New books:** each new book released (the next after Mark might be John, Genesis or Philippians) brings its own fresh pool and is a natural moment to bring lapsed users back.
- **Each re-read climbs a level:** the next read of a section serves the next harder question, preferring one that targets an idea the user hasn't caught yet. This replaces "Try a different question" and the in-card "Go deeper".

## Live comparison

The only live AI step: a fast model compares the user's answer with that section's stored key ideas and writes a short, personal note. Everything factual on the card comes from the content pack.

**What is pre-built vs. live:**

| Pre-built (same for everyone) | Live (per answer) |
| --- | --- |
| Question pool | Which key ideas the user touched on |
| Key ideas with commentator sources | A highlighted phrase from the user's own words |
| Context note, views-differ note, verse notes | A 2–3 sentence encouraging note |
|  | Nothing else: every question, including later-read levels, is pre-generated |

**The call:**

1. The app sends the answer text, section ID and question ID; nothing else about the user.
2. A Lambda loads that section's key ideas and context.
3. A Haiku-class model returns structured output: `coveredIdeaIds`, `highlightPhrase`, `note`, and `contradictsText` (true only if the answer contradicts what the passage plainly says, never for doctrinal disagreement).
4. The app builds the card: "What you caught" from covered ideas and the highlight, "What commentators add" from the remaining ideas with their sources ("all three commentators note…" where they agree), then context, views-differ and the Enduring Word link. Sources always come from the content pack, so citations can't be invented.

**What the model receives and does:** it gets the user's answer, the question, that section's key ideas (with sources and "agreed" flags) and the context note; never the raw commentary text. It matches the answer to key ideas even when worded differently, picks the user's best phrase to quote back, and writes a 2–3 sentence note connecting what they said to what the commentators said, using only the stored key ideas.

**Worked example (Mark 1:1–8):**

User's answer: *"John knew Jesus was way more important than him. He felt like he wasn't even good enough to be his servant."*

```json
{
  "coveredIdeaIds": ["k1", "k2"],
  "highlightPhrase": "wasn't even good enough to be his servant",
  "note": "You picked up on John's humility, and that he saw himself as less than a servant. All three commentators point to exactly that: untying sandals was the lowliest servant's job.",
  "contradictsText": false
}
```

The card, built by code from the content pack:

- **What you caught:** John's humility (Matthew Henry, JFB, Clarke); Jesus's greater authority (JFB), with the user's phrase highlighted.
- **What commentators add:** John as the messenger Isaiah foretold (Matthew Henry); water baptism vs. baptism with the Holy Spirit (Matthew Henry).
- **Then:** the context note, any "views differ" note, and the Enduring Word link.

**Keeping the note honest:**

- The prompt allows only restating stored key ideas: no new interpretations, verses or facts.
- Cheap code checks on every note: a length limit, and no commentator names other than those attached to the matched ideas. If a check fails, a template note is used instead ("You noticed John's humility. Here's what commentators noticed…").

**On-device option (later):** on newer iPhones, Apple's on-device model could do the matching and the note, making the personal note work offline and keeping answers on the phone; the cloud call stays as the fallback for older devices.

**Defaults and fallbacks:**

- **Short or "I don't know" answers:** no critique; the card opens with **"Here's what commentators noticed"** and shows all key ideas warmly.
- **Offline or the call fails:** the answer is saved and the card appears immediately from the stored key ideas under "Here's what commentators noticed"; the personal note fills in when back online.
- **Answer contradicts the text:** a gentle pointer back to the passage ("Take another look at verse 7, where John says…"), never "wrong".
- **Off-topic or empty:** treated like "I don't know".
- **Distress or crisis language:** the app responds with care and shows support resources instead of a comparison.

**Harder questions on later reads:** one question per section per read, no in-card "Go deeper" button. The first read of a section asks its Level 1 question. Reading that section again on a later day asks the next level, picked from the reviewed batch pool to target a key idea the user hasn't caught yet. The answer goes through the same live comparison; "You caught" counts ideas across all reads, and ideas caught this time get a "New" tag. Earlier answers sit behind a one-line "Your first-read reflection" row. A quiet line under the results says "Next time you read this section: a harder Level 2 question." No questions are generated live. With only Mark at launch, this gives about three reads' worth of fresh questions.

**Tone rules in every prompt:** lead with what the person noticed; never say "wrong"; never preach; plain, warm language; under 60 words.

**Targets:** about 1–2 seconds per comparison; a fraction of a cent each.

## System architecture

Two separate paths: a batch pipeline that produces and reviews all study content, and a small live API that only compares answers with it.

_(System architecture diagram: see the online brief. iPhone app → API Gateway + compare Lambda → Bedrock; batch pipeline (Step Functions + Bedrock batch) → S3 + CloudFront content packs.)_

The live path is a single Lambda behind API Gateway (no workflow needed); the batch path runs per book on a Step Functions Standard workflow, using Bedrock batch inference where possible.

## Data model

Published study content (questions, key ideas, context) lives in versioned content packs: JSON files in S3 behind CloudFront, downloaded and cached on the phone so everything works offline. DynamoDB holds only operational data: pipeline progress and anonymous question stats. Everything personal stays on the device and in the user's iCloud, and a user's answers never disappear.

| Entity | Key fields | Lives in |
| --- | --- | --- |
| ContentPack | book, packVersion, sections\[\] (study content shared by both translations), plus one verse-text file per translation, source provenance | S3 + CloudFront; cached on device |
| Section | id, ref (shared verse range), title, questions\[\], keyIdeas\[\], context, viewsDiffer, verseNotes\[\] (V2), noPrompt flag | Inside the content pack |
| Question | id (permanent, never reused), level (1–3), type (noticing, meaning, application, seasonal), verseStart, verseEnd, text, optional per-translation wording, target key idea IDs, isAlternate, series, status (active or retired), added in pack version | Inside the content pack |
| KeyIdea | id, title, body, sources\[\], agreed (shared by 2+ commentators), verseStart, verseEnd | Inside the content pack |
| Reflection | section ID, question ID, answer text, covered idea IDs, note, highlight, created, synced status, plus a snapshot of what was shown: question text, key ideas, translation, pack version | SwiftData + iCloud |
| Progress | book, last section, sections read, sections reflected, streak | SwiftData + iCloud |
| QuestionHistory | question IDs answered or skipped | SwiftData + iCloud |
| PipelineState | book, section, prompt version, stage (generated, checked, flagged, approved, published) | DynamoDB |
| QuestionStats | question ID, times shown, answered, skipped, not helpful (anonymous counts) | DynamoDB |
| Entitlement | free reflections used (3 in total per device, then subscribe), subscription status | StoreKit 2 + backend check |

**Why answers never disappear:**

- Each reflection saves a snapshot of the question and key ideas exactly as the user saw them, so the saved reflection stays complete even if that question is later retired or reworded, or the user switches translation.
- Question IDs are permanent and never reused; retired questions stay in the pack (hidden from rotation), so older reflections always resolve.
- Pack updates are additive and versioned; an update never deletes study content a user has answered.
- Saved reflections live in SwiftData and sync through the user's own iCloud, so it survives a new phone or a reinstall. Export to PDF or text is a V2 option.

## Cost estimates

Most cost is one-time content generation; each live reflection costs a fraction of a cent, so a subscriber costs cents a month to serve. Estimates assume roughly $3/$15 per million input/output tokens for a Sonnet-class model and $1/$5 for a Haiku-class model; confirm current Bedrock pricing.

| Item | Assumption | Approx. cost |
| --- | --- | --- |
| Batch, per section | \~12k tokens of commentary in (three commentaries), \~1.5k out (key ideas, question pool, context, verse notes) + review pass | \~$0.06–0.10 |
| Batch, launch book (Mark) | roughly 100 sections | \~$6–10 |
| Batch, whole Bible | roughly 2,500–3,000 sections | \~$180–300, less with batch-inference discounts |
| Seasonal or refresh batch | new questions only, reusing stored key ideas | a few dollars per series |
| Live comparison | \~1k tokens in, \~200 out, Haiku-class | \~$0.002 |
| Re-check after Edit | similar size | \~$0.002 |
| Content delivery | packs of a few hundred KB per book via CloudFront | negligible |

**Per user:** a daily Premium user (about 3 reflections and 1 re-check a day) costs roughly $0.25 a month in AI, against about $2.10 net a month on the yearly plan after Apple's 15% commission. A free user costs under 1 cent in total (3 reflections plus any re-checks).

**The real investment is review time:** reading the launch book's content in full, then spot checks.

## Theology, safety and privacy guardrails

Faith is personal, so the app guides without judging and never claims to speak with authority.

**Theology:**

- Key ideas come only from named commentators, and the card shows who said what.
- Where traditions or commentators disagree, present the main views neutrally in a "views differ" note.
- Never tell someone their understanding is wrong; the comparison is "what you noticed" and "what others noticed".
- Launch with three Protestant commentaries from two traditions (Reformed: Matthew Henry and JFB; Wesleyan: Adam Clarke) and say so plainly; a tradition setting (adding Haydock for Catholic readers) comes later.
- An About page explains the sources and that AI summarizes them, so users know where content comes from.

**Safety:**

- Reflections can turn personal. If an answer suggests distress or crisis, respond with care and show support resources instead of a comparison card.
- The live model has no free-chat surface: it only compares answers (every question is pre-written and reviewed in the batch pipeline), which limits misuse.

**Privacy:**

- Saved reflections live on the device and in the user's iCloud; the backend sees answer text only long enough to compare it and does not store or log it.
- No accounts are required; StoreKit's app account token handles entitlements.
- Tell users before their first submission that answers are processed by a third-party AI model.
- Never sell or share reflection data.

### Protecting live AI costs

- **Submit needs a real answer:** about a sentence (15+ characters) before it enables; the button locks while a check is running.
- **Edit gets 2 re-checks per question.** After that, Save keeps the new text and the existing results with no AI call. Cancel returns to the results.
- **No call for an unchanged answer:** the server caches results by section, question and a hash of the answer text, so resubmitting identical text costs nothing.
- **Daily cap per device:** about 30 live comparisons a day for Premium, enforced server-side with App Attest and a DynamoDB counter; free users are limited to 3 reflections in total. Over the cap, the card shows the stored key ideas as "Here's what commentators noticed" at zero AI cost.
- **Worst case:** 30 checks × about $0.002 = about $0.06 per user per day, even for someone hammering the button.
- **Alarms:** a CloudWatch alarm on Bedrock spend and on any device that hits the cap several days running.

## Competition, risks and validation

No app found asks you to interpret first and then compares your answer with commentators; the risks are content quality and keeping reflection from feeling like homework.

**Competition:**

| Competitor | What it does | What it doesn't do |
| --- | --- | --- |
| [Scroll The Bible](https://faith.tools/app/scroll-the-bible) (Dec 2025) | One verse per swipe; AI study tools (deep study, original language, explain it easier) behind a subscription | Doesn't ask the user to interpret first; paywall is its top complaint |
| [Examine: Scripture](https://apps.apple.com/us/app/examine-scripture/id6787314826) | Close-reading Bible app; AI tools grounded in the text (Ask, Weigh, Trace); a commentary lens showing Matthew Henry or JFB when you tap a verse; free, data on device | Doesn't ask the user to write an interpretation first or compare it; uses some of the same public-domain sources, so the interpret-then-compare loop is the difference |
| AI Bible chat apps, e.g. [Manna / Lampstand](https://mwm.ai/apps/manna-ai-bible-study/6760036886) ($14.99/year), Bible Chat, [ScriptaVerse](https://apps.apple.com/app/id6742846288) | Answer questions or generate commentary on verses | Tell rather than ask; no reflection loop |
| [Enduring Word Commentary app](https://apps.apple.com/app/id1436262209) | David Guzik's verse-by-verse commentary | Reading commentary, not reflecting first |
| YouVersion | Free Bible, plans, community | No interpret-then-compare study |
| Hallow | Guided prayer and audio, \~$40M revenue in 2025 | Prayer and meditation focus, not Bible study |

**Risks:**

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| Content quality | A shallow or slanted key idea undermines trust | Commentary-only sourcing, model review, full human review of the launch book |
| Reflection fatigue | Typing after every section can feel like homework | Read mode, prompt frequency setting, Skip, voice input |
| Feeling judged | People may feel graded on their faith | "What you noticed" framing, no right or wrong, warm tone rules |
| Old commentary language | 1700s–1800s texts can feel dated | Key ideas restated in modern English |
| Seasonal swings | Faith app downloads spike around Lent and Advent and fall after | Seasonal series, new book releases, yearly plan emphasis |
| AI theology concerns | Some users distrust AI near Scripture | Clear sourcing, AI only compares against named commentators |

**Validation:**

1. **Content spike (1–2 weekends):** run the pipeline on Mark; read every section yourself. Are the key ideas sound and the questions worth answering?
2. **Prototype test:** 5–10 people (including you) do 2 weeks of Mark using a TestFlight build. Measure reflections per session, skip rate and "not helpful" rate per question.
3. **Continue if:** most testers are still reflecting in week 2, and fewer than about 1 in 10 questions is marked not helpful.
4. **After launch:** about 4–5% of new users subscribing within 30 days.

## MVP scope and V2 backlog

The MVP is one book (Mark) done very well in one translation, with the full read, reflect and compare loop, offline support, harder questions on re-reads, and saved reflections in Home's contents.

| MVP feature | Spec | Notes |
| --- | --- | --- |
| Content pack format and pipeline | 2 | Batch jobs, checks, review queue, publish to S3 + CloudFront |
| Feed: reading cards and Read mode | 3 | Sections, verse notes, progress, offline packs; BSB (default) and KJV switch |
| Reflection and comparison cards (Study mode) | 4 | Question rotation, Submit, Skip, try a different question, "Here's what commentators noticed" default |
| Live comparison API | 4 | One Lambda + Bedrock, App Attest, offline fallback |
| Question levels and re-reads | 5 | Levels 1–3 per section, served one per read |
| Contents, saved reflections and progress | 6 | Reflections by book and chapter, streak |
| Subscription and paywall | 7 | 3 free reflections, then the paywall sheet on Submit; Premium monthly and yearly with a 7-day trial |
| Feedback and question analytics | 8 | Not helpful, skip rates, review queue |
| Voice input | 4 | On-device speech recognition for answers |

**V2 backlog (not specced):**

| Feature | Notes |
| --- | --- |
| More books | Next candidates: John, Genesis, Philippians, Psalms; release ahead of seasons |
| Seasonal series | Advent, Lent and Easter, New Year question sets |
| Family mode | Kids answer first, then compare together; connects to the family table devotions idea |
| Groups and homeschool tier | Leader assigns passages, sees and discusses reflections |
| Tradition setting | Catholic (Haydock) and other commentary sets |
| More translations | WEB and other public-domain translations via the alignment step; NKJV if licensed |
| Journal insights | Themes you return to, growth over a book |
| Audio | Listen to each section before reflecting |
| Home Screen widget | Today's section on the Home Screen |

## Engineering principles, repo and Spec Kit plan

Same stack as the grocery app: Swift app, Python backend and pipeline, Terraform, one monorepo, Spec Kit with Claude Code at the repo root.

**Principles (constitution input):**

1. Swift 6, SwiftUI + Observation, SwiftData with CloudKit, Swift Testing.
2. Scripture text is never paywalled.
3. The live model only compares answers with stored key ideas; it never generates questions or interpretation on its own. Follow-up questions are the harder, pre-generated questions served when the reader re-reads a section (one level up per later read).
4. Every key idea shown has a named commentator source from the content pack.
5. The comparison card always works offline from the content pack.
6. Reflections stay on the device and in iCloud; the backend never stores answer text.
7. Content packs are versioned; no content change ships without passing automatic checks and review. The pipeline reads only the frozen source snapshot; no step fetches from the web, and models are given no browsing or search tools.
8. Backend: Python Lambdas, Terraform, least-privilege IAM, Powertools for logging and validation.
9. Accessibility: Dynamic Type, VoiceOver labels on every card, voice input.

**Repo layout:**

```
thinkbible/
├─ CLAUDE.md                  # repo map + rules for every agent
├─ Makefile                   # bootstrap, lint, test, pipeline, deploy
├─ pyproject.toml             # uv workspace: shared, backend, pipeline
├─ thinkbible.code-workspace  # VS Code: everything except ios/
├─ docs/
│  ├─ brief.md                # this brief, exported
│  └─ design/                 # DESIGN.md + screen mockups
├─ api/openapi.yaml           # compare endpoint (the only live API)
├─ content/
│  ├─ schema/                 # section pack JSON Schema (shared contract)
│  ├─ sources/manifest.json   # checksums of the frozen snapshot (text in S3, local cache gitignored)
│  └─ drafts/                 # reviewed drafts per book (published packs live in S3)
├─ shared/                    # Python: pack models used by backend + pipeline
├─ backend/                   # Lambdas: compare, authorizer (App Attest)
├─ pipeline/                  # batch jobs: import_text, commentary, generate, checks, review, publish
│  └─ prompts/                # versioned prompts
├─ infra/                     # Terraform: modules (api, pipeline, storage, cdn) + envs (dev, prod)
├─ ios/                       # open in Xcode
│  ├─ ThinkBible.xcodeproj    # app target (Home, Reader, Paywall, Settings)
│  └─ Packages/               # DesignSystem, ContentKit, ReflectionKit, APIClient
├─ specs/ and .specify/       # Spec Kit (created by specify init)
└─ .github/workflows/         # backend CI, iOS CI
```

**Step zero:** the content spike on Mark (see Validation) before any Spec Kit spec.

**Spec order:** 1 constitution → 2 content pack format and pipeline → 3 feed and Read mode → 4 reflection, comparison and live API → 5 question levels and re-reads → 6 contents, saved reflections and progress → 7 subscription, paywall and Settings → 8 feedback and question analytics.

## Screens

Four MVP screens: Home, the chapter reader, the Paywall sheet and Settings (reading, study, appearance with light and dark, reminder, subscription, your reflections, about). Dark mode is a set of light/dark color pairs in the asset catalog, not separate screens. Past reflections live in Home's contents list rather than a separate Journal tab. The chapter reader is one continuous scroll, built so the reader always knows which section and verse a question belongs to: (1) each section's heading sticks to the top while you're in it and shows a ✓ 2/4 tag once answered; (2) the current section's question opens under its verses, labelled with its verse, which is tinted in the text while you answer; (3) Submit turns that card into your answer, with the matched phrase highlighted, plus the results, and each key idea carries a verse tag that highlights that verse in yellow; (4) answered sections fold to a one-line "Your reflection" row, tap to review; (5) a Study / Read switch (Study by default) hides or shows all question rows. Mockups of Home, the reader while answering, the results, and the commentators-only fallback are on the [ThinkBible Screens canvas](https://claude.ai/artifact/PjnBTToNP6MMerBNq6DzEn), along with the Paywall and Settings in light and dark.

| Screen | Purpose | Key elements |
| --- | --- | --- |
| Home | Pick up where you left off, or revisit any section and your past reflections | Continue reading, streak, settings, book picker, chapter grid, and each section of the chapter with its status: reflected (ideas caught, tap to see your answer and the comparison), read only, up next, or not yet read |
| Chapter reader: text | Read a section | Title, verses, progress bar, tap a verse for a note, Study / Read toggle (Study by default), BSB / KJV switch |
| Chapter reader: inline question card | Think first | Section question, text and voice input, Submit, Skip, try a different question |
| Chapter reader: results (same card after Submit, folds to one line) | Compare | One "What commentators noticed" list: a short personal note and "You caught 2 of 4", then the ideas you caught (checked), then "What you missed" (unchecked), each with its sources and a verse tag; views differ, context, Enduring Word link, Go deeper |
| Paywall | Subscribe | Free vs Premium, monthly and yearly, 7-day trial, restore |

## Open questions

- [ ] Name: ThinkBible. App Store name "ThinkBible: Read & Reflect" reserved in App Store Connect (plain "ThinkBible" is held by another developer). Next: buy thinkbible.app, consider thinkbible.com, reserve @thinkbible social handles, check USPTO for "ThinkBible" and "BibleThinker", consider a trademark filing near launch, and upload a TestFlight build within a few months to keep the reservation.
- [ ] Launch book: Mark, or another first book? And confirm BSB as the default with KJV as the alternate.
- [ ] Commentary set at launch, and whether to show "Protestant commentaries" explicitly or offer a tradition choice from day one.
- [ ] Is 3 free reflections the right number? Test 3 against 5 once there's traffic.
- [ ] Prices and trial length; test before launch.
- [ ] Voice input in the MVP or V2.
- [ ] Whether later-read questions (Levels 2–3) are Premium-only. With 3 free reflections in total, this mostly settles itself.
- [ ] Request permission from Enduring Word (their permissions form) for anything beyond linking.
