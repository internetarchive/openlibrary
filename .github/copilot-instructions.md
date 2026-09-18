# Copilot Instructions

> **Canonical guides:** [`AGENTS.md`](../AGENTS.md) for stack, commands, and conventions; [`docs/ai/README.md`](../docs/ai/README.md) for architecture and data-model. Path-specific review guidance lives in [`instructions/`](instructions/).

### Code Style

- **Python:** Ruff for linting and `ruff format` for formatting, line length 162, double quotes
- **JS:** ESLint, single quotes, no jQuery in new code
- **CSS:** Stylelint — semantic tokens only, no hex/named colors
- **Templates:** Jinja2 for new templates; Templetor is legacy
- **Branches:** `{issue-number}/{type}/{slug}`

### Code Quality Guidelines

**Code Cleanup:** Remove dead/commented code, unused variables, and redundant comments that restate the code.

**Naming Conventions:** Use descriptive names consistent with project style (snake_case for Python, UpperCamelCase for Vue components). Avoid vague names like `data`, `p`, `item`.

**Idiomatic Code:** Use language idioms (e.g., comprehensions in Python, modern JS features). Simplify verbose patterns like `if len(items) > 0:` → `if items:`.

**DRY:** Abstract repeated code blocks into shared helpers.

**Dependencies:** When updating a dependency, ensure it's updated across all dependency locations: requirements*.txt files, package.json files, and .pre-commit-config.yaml.

**i18n:** Wrap all user-facing strings in translation functions (`$_(...)` or `$:_('...')`). Do not use string concatenation to construct user-visible strings; prefer a single parameterized translation string instead. Use named placeholders (`_('Hello, %(name)s')`) rather than positional placeholders such as `%s` so translators have more context. Use `$:_()` for HTML content to prevent double-escaping.

**FastAPI:** When touching FastAPI code, follow [FastAPI best practices](https://raw.githubusercontent.com/fastapi/fastapi/refs/heads/master/fastapi/.agents/skills/fastapi/SKILL.md) and ensure compliance with their recommendations. When in doubt, reference other parts of our FastAPI codebase for how we do things, as we generally follow established best practices.

**web.py Migration:** When modifying a web.py endpoint that is marked as deprecated, update the corresponding FastAPI endpoint instead. FastAPI is the preferred framework for new features and migrations. Ensure backward compatibility by checking that the same inputs are accepted. Validation errors and status codes may differ slightly, which is acceptable.
