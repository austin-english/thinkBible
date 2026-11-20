# pipeline/: rules for agents

The batch content pipeline (spec 001). The root `CLAUDE.md` and the constitution
(`.specify/memory/constitution.md`) still apply. These rules add to them.

- **Only `src/thinkbible_pipeline/sources/importer.py` may fetch text over the network.** No other
  module imports `urllib`, `http.client`, `httpx`, `requests` or `socket`
  (`tests/unit/test_network_guard.py` enforces this). Model calls go through the Anthropic SDK in
  `llm/`, and AWS calls go through boto3.
- **Never pass `tools` to a model call.** Models get only the current section's excerpts
  (`tests/unit/test_no_tools.py` enforces this).
- **Prompts are versioned files** in `prompts/{stage}/vN.md`. Never edit a version that has been
  used for a run. Add `vN+1.md` instead.
- **Drafts are pipeline state in S3, not hand-edited** (2026-11-10). Quality comes from the
  automatic gate (checks, evidence check, the calibrated Opus grader), which drops
  weak items and records why in the scorecard. To change content, add a prompt version and
  regenerate; after a promotion to live, retire and replace.
- **Live content is frozen.** Never change the text of a promoted question or key idea.
  Retire and replace it instead (FR-024). The draft channel may be republished from scratch; IDs are never
  reused anywhere.
- **No source text in git.** Only `content/sources/manifest.json` is committed.
- Every model-calling run shows an estimate and respects the spend cap. Tests use `FakeRunner` and
  never call models.
- **Change prompts through `eval`, not by eye** (FR-029). One run can't separate a prompt's effect
  from chance: put the change in a candidate overlay (`pipeline/evals/candidates/`), run `eval`,
  and adopt it only if it does at least as well on every measure. A grader change is checked with
  `calibrate`. Both cost money: ask the owner before running them.

Design docs: `specs/001-content-pack-pipeline/` (plan, research, data-model, contracts/cli.md).

## Stage order

`sections` → `intro` → `summaries` → `generate` → `align` → `check` → `review` → `report`
(`--stage all`). Each stage needs the one before it finished for the whole book. What each does,
the state machine and costs: [`src/thinkbible_pipeline/README.md`](src/thinkbible_pipeline/README.md).

## Commands

`…` is `uv run --package thinkbible-pipeline thinkbible-pipeline`. Full list:
`specs/001-content-pack-pipeline/contracts/cli.md`.

```bash
make test && make lint                       # offline: FakeRunner, moto; no cost
… run --book mark --stage generate --local --sections mrk-1-1,mrk-1-9   # a few sections in-process
make pipeline BOOK=mark STAGE=all            # a cloud run: estimate, confirm, start, wait
make status BOOK=mark                        # runs, spend, the scorecard (review.html)
… eval --sample mark-sample --candidate NAME # a prompt change vs the current prompts
… calibrate                                  # the grader vs the owner's grades
make publish BOOK=mark / make promote BOOK=mark
make deploy                                  # after any code, config or prompt change (owner's OK)
```

Cloud runs, `eval`, `calibrate`, `promote` and `make deploy` spend money or change what's
published: the owner runs them or approves them first. Tests and `--local` runs with
`FakeRunner` are free.
