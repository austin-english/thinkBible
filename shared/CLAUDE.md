# shared/: rules for agents

`thinkbible_core` is the Python view of the content pack contract, used by the pipeline (and the
backend from spec 003).

- **Schema first.** The contract is `content/schema/*.schema.json`. To change the pack format:
  1. edit the schema;
  2. update the fixtures in `content/schema/fixtures/`;
  3. update the models here;
  4. update the pipeline output and the Swift `ContentKit` models.

  All of this goes in the same change.
- Models mirror the schemas field for field (camelCase aliases, `extra="forbid"`). The contract
  tests in `tests/test_contract.py` must pass for every fixture.
- Cross-field rules that JSON Schema can't express live in `rules.py`. They are listed in
  `specs/001-content-pack-pipeline/data-model.md`.
- IDs are permanent: never change an ID format in a way that would re-key existing content.
