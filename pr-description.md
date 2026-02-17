<!-- What does this PR achieve? [feature|hotfix|fix|refactor] -->

**[feature] Add AI instruction bridge: one canonical guide, thin wrappers for each AI tool**

Sets up a maintainable system for guiding AI coding assistants (Claude Code, OpenAI Codex, GitHub Copilot, Cursor) without duplicating a 150-line doc four times. A single canonical guide lives at `docs/ai/README.md`; each tool gets a minimal bridge file in the location it natively discovers.

**Files added/changed:**

| File | What | Why |
|---|---|---|
| `docs/ai/README.md` (new) | Canonical guide (~150 lines) | Single source of truth for all AI tools |
| `CLAUDE.md` (modified) | Thin bridge (~40 lines) | Claude Code auto-discovers this at repo root |
| `AGENTS.md` (new) | Thin bridge (~40 lines) | OpenAI Codex and Cursor natively read this |
| `.github/copilot-instructions.md` (new) | Thin bridge (~40 lines) | GitHub Copilot natively reads this path |

**No `.cursorrules` file is added** — Cursor reads `AGENTS.md` natively and `.cursorrules` is legacy/deprecated.

### Technical

- **Zero runtime impact.** These are documentation-only markdown files. No code, config, build, or dependency changes.
- **The canonical doc** (`docs/ai/README.md`) is the migrated content from the previous `CLAUDE.md`, rewritten with tool-agnostic language (e.g., "AI Coding Guide for Open Library" instead of "guidance to Claude Code").
- **Each bridge file** contains an identical quick-reference section (stack summary, key commands, code style rules, critical entry points) so an AI agent can orient on small tasks without reading the full guide. Each opens with a callout pointing to the canonical doc for deeper context.
- **Relative link in `.github/copilot-instructions.md`** uses `../docs/ai/README.md` since it's nested one level down. The root-level bridges use `docs/ai/README.md`.
- **Maintenance going forward:** update only `docs/ai/README.md` when project guidance changes. The bridges should rarely need touching — they contain only stable quick-reference content (commands, style rules, entry points).
- **No duplication risk for stale content:** the bridges intentionally omit architecture details, the data model, template syntax, and the full file-location table. Any agent that needs that depth is directed to the canonical file.

### Testing

1. **Verify file structure:**
   - `docs/ai/README.md` exists and contains the full guide (~150 lines covering project overview through key file locations)
   - `CLAUDE.md` at root is ~40 lines, opens with a callout to `docs/ai/README.md`
   - `AGENTS.md` at root is ~40 lines, same structure as `CLAUDE.md`
   - `.github/copilot-instructions.md` is ~40 lines, same structure but with `../docs/ai/README.md` relative path
2. **Verify no content loss:** compare `docs/ai/README.md` against the previous `CLAUDE.md` (from `main` branch) — all sections should be present (Project Overview, Development Setup, Build Commands, Testing, Linting, Architecture, Code Style, Key File Locations)
3. **Verify links resolve:** from the repo root, confirm `docs/ai/README.md` is a valid path; from `.github/`, confirm `../docs/ai/README.md` resolves
4. **Spot-check bridge consistency:** the three bridge files should have identical Quick Reference, Key Commands, Code Style, and Entry Points sections (only the title and canonical-link path differ)
