# Content spike notes (spec 001)

The brief's "step zero": run the pipeline on Mark, read the output, and decide whether the key
ideas are sound and the questions are worth answering. These notes record the results of T057
(first impression), the SC-004 judgement of T064, and later the quickstart run of T085.

Written 2026-11-20. The numbers come from the run records and scorecards in the drafts bucket
(`make status BOOK=mark`, `make status BOOK=php`) and from `pipeline/evals/calibration.json`.

## 1. Where things stand

| Book | Sections | Prompts | Channel | Scorecard |
|---|---|---|---|---|
| Mark | 100 | questions v18, extract v18, guide v5, review v14 | draft, 1.2.0 | promotable |
| Philippians | 14 | the same | draft | promotable |
| 2 John | 3 | the same | none (local batch test) | 1 passed; 2 failed neutrality, correctly |

Mark is not promoted to live. Live content is frozen word for word, and retire-and-replace
(T079–T082) is the only way to change it afterwards, so promotion waits for the owner's read of
Mark in the app (spec 002).

## 2. The runs

**Mark, Claude API (standard), 2026-11-19**

| Run | What | Sections | Time | Cost |
|---|---|---|---|---|
| `906b0f` | everything, first 5 sections | 5 | | $1.10 |
| `b2b8cb` | everything, the rest | 90 | 30 min | $14.10 |
| `ed68a5` | review only: 34 sections left ungraded when the API credit ran out | 34 | 8 min | $4.05 |
| `e77297` | re-select questions from stored grades (big-picture rule, 1.2.0) | 100 | 1.5 min | $0.00 |
| `df1ddf` | align (translation variants) | 100 | | $0.003 |

Mark cost about **$19** at standard prices, about $0.20 a section.

**Philippians, Message Batches, 2026-11-20** (run `a37873`): 14 sections, every stage 14/0
failed, 38 minutes, **$1.67** ($0.12 a section) of a $3.77 cap. `generate` took 3 batch rounds
(one section's questions were retried in round 3) and `review` took 1.

## 3. Scorecards

| Measure | Bar | Mark | Philippians |
|---|---|---|---|
| Key ideas passing the grader | 90% | **95%** | **99%** |
| First question graded 4–5 | 90% | **99%** | **100%** |
| Sections with a full set of questions | 95% | **99%** | **100%** |
| Candidate questions passing (information) | | 83% | 86% |
| Grader agreement with the owner (36 held-out items) | 85% | **89%** | 89% (Mark set) |
| Key ideas kept | | 533 | 78 |
| Questions kept | | 296 | 42 |
| Dropped by check / generate / review | | 30 / 5 / 556 | 14 / 3 / 80 |
| Sections failed / with no question | | 0 / 0 | 0 / 0 |

Review drops most candidates on purpose: the writer offers up to 10 per section and the grader
keeps the best 3 (R11, "Up to 10 candidates").

## 4. SC-004 judgement (T064)

SC-004 asks for four things. Three are measured, and Mark passes all three:

- **Key ideas:** the calibrated grader passes 95% of Mark's key ideas (bar 90%).
- **First questions:** 99% of sections lead with a question graded 4 or 5 (bar 90%).
- **Full sets:** 99% have as many questions as their key ideas allow (bar 95%).

The grader they rest on agrees with the owner on 89% of the held-out ratings (SC-009, bar 85%).

The fourth, **"the owner's in-app read agrees"**, can't be done yet. The app is spec 002, so it
stays open until the owner reads Mark 1.2.0 on the draft channel.

**Owner's judgement so far** (from the rating rounds and reads during the spike; owner to confirm
or edit):

> The key ideas are sound and the questions are worth answering. The balance of detail and
> big-picture questions is good as it is. Philippians, the first letter, reads well too.
> Final sign-off after reading Mark in the app.

## 5. What the spike changed

The prompts went through 18 versions. Full reasoning is in research.md R6 and R11; the turns that
mattered:

1. **Levels went** (2026-11-17). Fixed difficulty levels (detail, passage, beyond) emptied
   Level 3 in 5 of 10 sections and threw away good big-picture questions. Questions are now an
   ordered list of up to 3.
2. **Deeper meaning is the point** (2026-11-17, after the owner rated 51 Mark 1 questions). Key
   ideas are what the commentators say lies beneath the passage, and facts that aren't meanings
   are "background". Questions start from one concrete detail and ask what it reveals.
3. **Purpose first, fewer rules** (2026-11-18). Each wording rule added made the writer contort
   its sentences, and one favorite form became a template. Rewriting the prompt and rubric
   around what a question is for fixed both.
4. **The grader learns from the owner's verdicts.** Agreement went 70% → 60% (rubric over-strict)
   → 83% (owner's round 1 as worked examples, round 2 held out) → 92% on Opus 5.5 → 89% today
   (review v14 adds the big-picture mark).
5. **Claude 5.5 on the Claude API.** Bedrock's quota for this account stayed at 0. On the same
   10 sections Sonnet 5.5 wrote more natural questions, and Opus 5.5 graded closer to the owner
   than Opus 4.6 did. Sonnet stays the writer: Opus wrote a little better and cost twice as much.
6. **The first question opens the central meaning**, and a big-picture question graded 4 or
   more leads. In 1.2.0, 81 of 100 sections lead with a big-picture question.
7. **One run can't judge a prompt change.** `questions/v17` looked like a fix and made Mark's
   first sections worse, and was reverted. A control eval (same prompts, two runs) showed four
   measures steady and "big-picture first" swinging 71% → 52%. Prompt changes now go through
   `eval`, with `--repeats 2` for that measure.

## 6. Cost and time (SC-002)

SC-002 asks for Mark end to end in under 30 minutes and under $15.

| | Time | Cost for Mark |
|---|---|---|
| Standard API (measured) | about 30 min for 90 sections, 3 at a time | about $19 |
| Batches (projected from Philippians) | about 40–60 min | about $12 |

Neither meets both bars. Standard is fast enough but over budget, mostly because of the
Opus grader at high effort, and up to 10 candidates per section to grade. Batches meet the cost
and miss the time. A book run isn't interactive, so the half price matters more than the
wait. Tuning stays on `--local` and the standard API, where the wait matters.

**Proposal:** revise SC-002 to "under $15 in model usage, and within an hour" when the spec is
next touched (owner's decision).

## 7. What else the runs showed

- **Re-runs are free (SC-005).** Run `e77297` re-selected all 100 sections from stored grades
  with no model calls, and published 1.2.0 for $0.00.
- **The cap holds (SC-008).** No run went over its cap. Running out of API credit mid-run (run
  `b2b8cb`) now stops the run at the first refusal instead of failing every remaining section,
  and a re-run picks up where it stopped.
- **Context notes sometimes get the order of events wrong.** In the control eval, two of 19
  sections failed on that ("six days later" in Mark 9:1, "the morning after" in 16:9). The
  evidence check catches it and a real run regenerates once. Worth watching on later books.
- **Neutrality holds on a letter.** In 2 John, 2 of 3 sections failed because the grader
  rightly refused key ideas that took a side. They are left failed, not regenerated, since 2
  John was only a batch test.

## 8. Before the next book

- **Calibrate for letters.** The grader's examples and held-out set are all Mark narrative.
  R11 ("Genres") asks for a short rating round on a new kind of book, and a `calibrate` re-run,
  before that book is promoted. Philippians needs that round before promotion.
- **Big-picture questions in the writer** (after this PR): a question-guide version teaching
  big-picture questions that start from a concrete detail, tested with `eval --repeats 2`,
  with batch support added to `eval`.
- **A distributed Map** before Psalms or a whole-Bible run: an inline Map keeps every
  section's steps in one execution history, which Step Functions caps at 25,000 events.
- **Bedrock.** The account's Claude 5.5 quotas are 0. The `bedrock` profile is ready if a
  support case opens them.

## 9. Quickstart run (T085)

*Not yet run.* Results of quickstart.md §0–§8 end to end go here.
