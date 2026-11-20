# Eval candidates

Each file is a settings overlay (TOML) laid over `pipeline/config/settings.toml`: name only what
the candidate changes. For example, a new questions prompt (add `prompts/questions/v19.md` and
`prompts/extract/v19.md` first, since the generate stage's prompts share a version):

```toml
[stages.generate]
prompt = "v19"
```

or a new question guide:

```toml
[prompts]
question_guide = "v6"
```

`eval` grades every arm with the current, calibrated grader, so a candidate may not change the
`review` stage: a grader change is checked with `calibrate` instead. A candidate may change the
shared context (`[prompts] shared_context`): in `eval` only the writer reads the new one, but the
grader reads it too once adopted, so run `calibrate` before adopting it.

`control.toml` changes nothing. Run it once to see how far two runs of the same prompts differ
on the sample: a candidate's gain smaller than that is chance.

```bash
uv run --package thinkbible-pipeline thinkbible-pipeline eval --sample mark-sample --candidate control
uv run --package thinkbible-pipeline thinkbible-pipeline eval --sample mark-sample --candidate my-idea --repeats 2
```

Each run shows its estimate and asks first (about $0.25 per section per generated arm). The
scratch drafts and `eval.html` go to `pipeline/out/evals/` (gitignored); the real drafts are only
read.
