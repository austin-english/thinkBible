# ThinkBible

Read a section of the Bible, answer one question in your own words, then see what the
commentators noticed. iPhone app + small live API + batch content pipeline, in one repo.

- Product and architecture: [`docs/brief.md`](docs/brief.md)
- UI spec and mockups: [`docs/design/DESIGN.md`](docs/design/DESIGN.md)
- Agent rules: [`CLAUDE.md`](CLAUDE.md) (plus one per area)

## Getting started

```bash
# Python (backend, pipeline, shared): needs uv
make bootstrap && make test

# Xcode MCP for Claude Code
claude mcp add --transport stdio xcode -- xcrun mcpbridge
```

- **Backend, pipeline, infra:** open `thinkbible.code-workspace` in VS Code (it hides `ios/`).
- **App:** follow `ios/README.md` once to create the Xcode project in `ios/`, then work in Xcode.
- **Claude Code:** run it from the repo root so it sees every `CLAUDE.md`.

## Spec Kit

Spec Kit is already initialised (Claude integration plus the git extension), and its
`/speckit-*` commands are committed in `.claude/skills/`, so there's nothing to install to use
them. The constitution is `.specify/memory/constitution.md`. Features, their build order and the
per-feature workflow are in [`specs/README.md`](specs/README.md).

To upgrade Spec Kit later, install its CLI with
`uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`.

## Layout

```
thinkbible/
├─ CLAUDE.md, Makefile, pyproject.toml (uv workspace), thinkbible.code-workspace
├─ docs/            brief.md, design/ (DESIGN.md + screens/)
├─ api/             openapi.yaml (compare endpoint)
├─ content/         schema/ (pack contract), sources/manifest.json (snapshot checksums; text in S3), drafts/
├─ shared/          Python pack models (thinkbible_core)
├─ backend/         Lambdas: compare, authorizer
├─ pipeline/        batch jobs + versioned prompts
├─ infra/           Terraform modules + envs
├─ ios/             Xcode app + Packages/ (DesignSystem, ContentKit, ReflectionKit, APIClient)
├─ specs/           Spec Kit features (NNN-name/spec.md, plan.md, tasks.md) + README.md
├─ .specify/        Spec Kit: memory/constitution.md, templates, scripts, git extension
├─ .claude/skills/  /speckit-* commands for Claude Code
└─ .github/workflows/
```
