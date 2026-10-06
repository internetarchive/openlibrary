# Open Library .pam

Open Library's PAM config: authored, committed, shared. It reads on its own, so you do not need to run
pam or cmux to use it as a team standard.

## How an agent briefs (two layers)

1. **Role type (generic, from the pam tool):** your type's manual that ships with pam, at
   `pam/agents/<type>/` (for an ADA, `pam/agents/ada/AGENTS.md`). This is project-agnostic.
2. **Your identity (project-specific, here):** `.pam/agents/<your-name>/identity.md`, which `@link`s your
   type manual and adds Open Library specifics, plus `orders.md` (your specific marching orders).

So a new agent reads the generic manual for its type, then its own identity and orders here. Nothing
project-specific lives in the generic manual; nothing generic is duplicated here.

## Layout

- `project.toml`   the Project config (tracker, label to state map, epic labels).
- `roles.md`       the role catalog (generic, seeded by the tool).
- `team.toml`      the division-lead chart (who leads what).
- `agents/<name>/` each agent's definition: `agent.toml`, `identity.md`, and optional `orders.md`.
- `kb/`            the knowledge base (Obsidian-style markdown with `[[wikilinks]]`).
- `rules/`         the bucket for all rules, processes, and doctrine (epic updates, labels, modsec,
                   dependabot, and anything else worth standardizing, even if not read yet).

## Provenance

Built by mapping Open Library's real docs (from `pm`, `openlibrary-pm`, `ada`, `ada-framework`, and the
repo's own `docs/`) into this schema, to test and inform the pam tool by leading with reality.
