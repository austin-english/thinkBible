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

# Spec Kit (once, from the repo root)
specify init . --integration claude

# Xcode MCP for Claude Code
claude mcp add --transport stdio xcode -- xcrun mcpbridge
```

- **Backend, pipeline, infra:** open `thinkbible.code-workspace` in VS Code (it hides `ios/`).
- **App:** follow `ios/README.md` once to create the Xcode project in `ios/`, then work in Xcode.
- **Claude Code:** run it from the repo root so it sees every `CLAUDE.md`.

## Layout

```
thinkbible/
├─ CLAUDE.md, Makefile, pyproject.toml (uv workspace), thinkbible.code-workspace
├─ docs/            brief.md, design/ (DESIGN.md + screens/)
├─ api/             openapi.yaml (compare endpoint)
├─ content/         schema/ (pack contract), sources/ (frozen, checksummed), packs/
├─ shared/          Python pack models (thinkbible_core)
├─ backend/         Lambdas: compare, authorizer
├─ pipeline/        batch jobs + versioned prompts
├─ infra/           Terraform modules + envs
├─ ios/             Xcode app + Packages/ (DesignSystem, ContentKit, ReflectionKit, APIClient)
└─ .github/workflows/
```
