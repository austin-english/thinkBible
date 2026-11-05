# Content pack contract fixtures

These are shared test data for every implementation of the pack contract: the Python models in
`shared/` (contract tests in `shared/tests/test_contract.py`) and, from spec 002, the Swift
`ContentKit` models.

- **`valid/`**: each file must validate against its JSON Schema and parse with the models. The
  schema is chosen by file-name prefix: `study-pack-*`, `verses-*`, `index-*`.
  - `study-pack-mark-sample.json` holds Mark 1:1–8 and 1:9–11 at pack version 1.1.0, including a
    retired question (`mrk-1-9-q5`) and its replacement (`mrk-1-9-q3`, `replaces`).
- **`invalid/`**: each file is the valid study pack with **exactly one** defect, named after it
  (`study-pack--<defect>.json`). Each must fail both the JSON Schema and the models.

Text comes from the public-domain BSB and from the brief and mockup sample content. To add a
defect case, copy the valid pack, change one thing, and name the file after the defect.
