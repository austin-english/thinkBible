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
  automatic gate (checks, evidence check, the calibrated Opus grader, level check), which drops
  weak items and records why in the scorecard. To change content, add a prompt version and
  regenerate; after a production promotion, retire and replace.
- **Production content is frozen.** Never change the text of a promoted question or key idea.
  Retire and replace it instead (FR-024). Dev may be republished from scratch; IDs are never
  reused anywhere.
- **No source text in git.** Only `content/sources/manifest.json` is committed.
- Every model-calling run shows an estimate and respects the spend cap. Tests use `FakeRunner` and
  never call models.

Design docs: `specs/001-content-pack-pipeline/` (plan, research, data-model, contracts/cli.md).
