# i18n Translation Pipeline — which repo is authoritative

> How Open Library's UI translations are stored, generated, and shipped to production. Companion:
> [[i18n-rendering]] covers *how* a translated string reaches the page (Templetor, Jinja, the
> `data-i18n` JS bridge); this page is *where translations live* and how they flow.

**Before editing a `.po` file, know which repo owns it.** Two repositories hold Open Library's
translations, and which one you touch depends on what you are doing.

---

## The short version

| | |
|---|---|
| **Authoritative source** | `internetarchive/openlibrary-i18n`, branch **`main`** |
| **Where the running code reads from** | `internetarchive/openlibrary`, `openlibrary/i18n/<lang>/messages.po` — populated at image build by the bake (below), not hand-edited |

⚠️ **`openlibrary-i18n`'s default branch is `main`, not `master`.** Branching off `origin/master`
there silently fails.

---

## The live pipeline, end to end

Four stages: **source strings change → the translation repo is notified → an AI job fills the gaps
and self-merges → the result is baked into the deploy image.** Each is a real, linkable artifact.

1. **Strings are extracted to a template.** Open Library's source strings live in
   `openlibrary/i18n/messages.pot`. A pre-commit/CI hook (`generate-pot`) regenerates it, so after
   any merge to `master` the `.pot` reflects the current UI.

2. **On a `.pot` change, the source repo notifies the translation repo (cross-repo trigger).**
   [`openlibrary/.github/workflows/trigger-i18n.yml`](https://github.com/internetarchive/openlibrary/blob/master/.github/workflows/trigger-i18n.yml)
   runs **only on a push to `master` that changes `openlibrary/i18n/messages.pot`** and fires a
   `repository_dispatch` (event type `openlibrary-pot-updated`) at `internetarchive/openlibrary-i18n`,
   authenticated with a **cross-repo PAT** (`secrets.OL_BOT_PAT`). *Not every merge — only when the
   `.pot` actually changes.*

3. **The translation repo runs the AI translation and self-merges.**
   [`openlibrary-i18n/.github/workflows/translate.yml`](https://github.com/internetarchive/openlibrary-i18n/blob/main/.github/workflows/translate.yml)
   listens for that dispatch (plus `workflow_dispatch` for manual runs). It pulls the latest `.pot`
   from `openlibrary` master → syncs each language's `.po` (new strings become untranslated) → runs
   `anthropics/claude-code-action` (model **pinned** to `claude-sonnet-5`) to fill the untranslated
   strings in batches → validates → opens a PR → **merges it only once its checks pass**
   ([`validate-pr.yml`](https://github.com/internetarchive/openlibrary-i18n/blob/main/.github/workflows/validate-pr.yml)
   + [`bake-regression.yml`](https://github.com/internetarchive/openlibrary-i18n/blob/main/.github/workflows/bake-regression.yml)).
   Secrets: the Claude token and the bot PAT.

4. **The agentic instructions tell the AI how to translate.**
   [`openlibrary-i18n/i18n-translation-instructions.md`](https://github.com/internetarchive/openlibrary-i18n/blob/main/i18n-translation-instructions.md)
   is the prompt `claude-code-action` follows — batch (~75 strings), preserve `%(name)s`/HTML
   verbatim, skip fuzzy, never bulk-unfuzzy, attribute the model. **Editing this file is a deploy**
   — the triggered run consumes it from `main`, so a change to it reaches production translations
   directly.

5. **On deploy, the translations are baked into the image.** The base image
   [`docker/Dockerfile.olbase`](https://github.com/internetarchive/openlibrary/blob/master/docker/Dockerfile.olbase),
   built by [`olbase.yaml`](https://github.com/internetarchive/openlibrary/blob/master/.github/workflows/olbase.yaml),
   clones `openlibrary-i18n` at build time (via
   [`scripts/i18n-pull-translations.sh`](https://github.com/internetarchive/openlibrary/blob/master/scripts/i18n-pull-translations.sh))
   at a pinned ref **`I18N_REF`** (default `main` = always-latest), copies each
   `locale/<lang>/messages.po` over the committed files, and `make i18n` compiles them to `.mo`.
   `deploy.sh` blocks a deploy until `olbase` is rebuilt, so **production serves the freshest
   translations with no manual copying.** A bad/missing language safely falls back to the committed
   file; a pinned `I18N_REF` ships an exact, verified set. The baked set is recorded in the image at
   `openlibrary/i18n/openlibrary-i18n.txt` (ref + per-locale installed/kept).

**Human contributions** come in through a shared self-hosted **Weblate** instance (openlibrary-i18n#116):
contributors edit in a UI, which opens PRs on a `weblate/*` branch of `openlibrary-i18n` (never `main`,
and outside `i18n/` so the AI pipeline neither auto-merges nor pauses on them). AI fills gaps; humans
correct.

### Replicating this for another app (e.g. archive.org)

Same five pieces: (1) extraction producing a `messages.pot`; (2) a `trigger-i18n.yml` copy in the
source repo with a cross-repo PAT firing a dispatch when its `.pot` changes; (3) a translation-store
repo (e.g. `archive.org-i18n`, or a project on the shared Weblate instance for the human side) running
a `translate.yml` + the agentic instructions + validate/bake checks, with the Claude token + bot PAT;
(4) those agentic instructions; (5) a bake step in that app's deploy that pulls the store's `.po`,
compiles, and ships — the analogue of `olbase`. The AI and Weblate paths are complementary.

---

## Why there are two repos

The pipeline was extracted (#13061) so translation PRs stop competing with feature work in the main
repo's CI and review queue, and so translations can refresh independently of `olbase`'s rebuild
cadence. `openlibrary-i18n` uses `locale/<lang>/messages.po`; `openlibrary` uses
`openlibrary/i18n/<lang>/messages.po`. The bake bridges them.

---

## The two stores diverged — why the rules below exist

Measured with `babel==2.18.0` (openlibrary's pin), parsing both sides into
`(msgctxt, msgid) → msgstr` maps (so header dates and entry ordering do not create false positives),
the stores had diverged in every shared language:

| | count |
|---|---|
| translations only in `openlibrary` | ~3,456 |
| translations only in `openlibrary-i18n` | ~4,574 |
| conflicting (both translated, different text) | 215 — **148 of them in `es`** (see rule 2) |

**The source strings are in sync.** Both `messages.pot` files carry **2,006 msgids with zero set
differences**; the diff between them is only `#:` source-reference comments drifting from the Jinja
migration (`foo.html` vs `foo.html.jinja`).

**`kn`, `mr`, `nl` are not migration scope.** They carry only `legacy-strings.<lang>.yml`, no
`messages.po`, so they are not in the gettext pipeline at all.

---

## Three rules that are not negotiable

### 1. Never bulk-unfuzzy. Anywhere.

"Skip fuzzy entries" and "never bulk-unfuzzy" read as the same rule and **are not**. You can
obey the first perfectly while translating and still run a bulk unfuzzy as a separate cleanup
step — which is the action that detonates this.

A fuzzy flag here is not "probably fine, needs a glance." `msgmerge` sets it when it
fuzzy-matches a *new* msgid against a similar-looking *old* entry and copies that entry's
`msgstr` wholesale. The result is frequently an unrelated string, kept harmless only because
gettext refuses to use fuzzy entries at runtime. **Clearing the flags ships them.**

### 2. `es` is quarantined. It needs a native reviewer, not a merge tool.

Spanish holds **148 of the 215 total conflicts — 69% in one language** — and a large share of
its `openlibrary-i18n` fuzzy entries are not translations of their msgid at all:

| msgid | `openlibrary` | `openlibrary-i18n` (fuzzy) | back-translates as |
|---|---|---|---|
| `Enable` | Activar | **Ejemplo** | "Example" |
| `Deploy` | Implementar | **Responder** | "Reply" |
| `Drift` | Desviación | **Editar** | "Edit" |
| `Stopped Reading` | Dejé de leer | **Tendencia** | "Trending" |
| `Verification failed. Please try again.` | La verificación ha fallado… | **Contraseña incorrecta…** | "Incorrect password…" |

A merge tool would silently bless every one of these.

### 3. "Delete the `.po` files" is not a cleanup. It destroys thousands of translations.

And it breaks local dev regardless: `OL_MOUNT_DIR` volume-mounts `openlibrary/i18n/` over
whatever `olbase` baked in, so removing the committed files leaves local dev with **no**
translations. A `make i18n-sync` or equivalent has to exist first.

---

## Plural entries — gotchas

- **An empty plural form renders English, silently.** Babel's `write_mo` substitutes the English
  msgid for an empty form, so a partly-filled plural shows English at the n values whose form is
  empty. The AI run does not fill them: `_untranslated_from_catalog` uses `any(msg.string)`, so a
  partly-empty plural counts as translated. Gate: `tests/test_plural_forms.py`.
- **Check `Plural-Forms` before counting empty forms.** `ar` declares `nplurals=3; plural=(n > 2)`,
  which never selects form 2, so empty 3rd forms are unreachable. Count only forms the locale's own
  rule can select (`gettext.c2py(catalog.plural_expr)` over n=0..999).
- **With `nplurals=1` (ja, ko, id) the single form answers to `msgid_plural`,** since it is shown for
  every n; comparing it to the singular is wrong, and tooling that does so rejects correct fixes.
- **Read the plural rule from the compiled catalog, not the `.po` header.** A catalog with no
  `Language` header compiles without its `Plural-Forms` and falls back to `n != 1`, whatever the `.po`
  declares. Use `Translations(...).plural`. `read_po` pads a short plural msgstr list to `nplurals`
  with `""`, so a missing form reads as an empty one.
- **A `.po` crash is not necessarily a site crash.** A malformed msgstr only matters if its msgid is
  still in `messages.pot`; check `grep -F '<msgid>' openlibrary/i18n/messages.pot` before calling a
  `.po` defect live.

---

## How olbase bakes translations

The base image `Dockerfile.olbase` bakes translations at build time:

- `scripts/i18n-pull-translations.sh [REF] [--strict]` runs under `set -euo pipefail`. It fetches
  `openlibrary-i18n` at `REF` (a branch, tag or SHA; `I18N_REPO` overrides the URL for tests) and runs
  `i18n-messages install`. `Dockerfile.olbase` runs it with `ARG I18N_REF=main`, **after** the
  `infogami` symlink (the installer imports `openlibrary.i18n`, which needs infogami) and **before**
  `make`, so the pulled files get compiled.
- **The gate (`openlibrary.i18n.check_po_file`):** strict parse (`abort_invalid=True`), `write_mo`,
  a load through `babel.support.Translations` with the plural function evaluated (a malformed
  Plural-Forms header compiles but raises in gettext on load, which would 500 every page in that
  language), then `msgstr % args` for every non-fuzzy msgstr, with args shaped like the msgid (ints,
  so `%s`/`%d`/`%f` all pass). Placeholder-free msgids get `% {}`, because **Jinja's newstyle
  gettext always formats**, even with no variables. It catches crash-class defects: positional→named,
  named→positional (renders a dict repr), unknown names, and `%(x)` followed by a non-conversion
  character. **It does not catch** `%(name)d` for a `%(name)s` msgid (raises only if the runtime
  value is a str, which the `.po` can't tell you), or dropped named placeholders (they don't raise).
- **Failure semantics:** a locale that fails the gate keeps its **committed** `.po` (fallback),
  including any defect already in it. A fetch failure, bad ref, or empty `locale/` fails the build.
- **Record:** `openlibrary/i18n/openlibrary-i18n.txt` in the image holds the ref, the resolved SHA,
  and `installed` / `kept committed` per locale.
- **CI:** the `i18n_upstream` job in `python_tests.yml` runs the same script with `--strict`, then
  `make i18n`, `make test-i18n` and `test_po_files.py` on the pulled files.
- **`olbase.yaml`:** the `i18n-ref` job resolves the SHA once for both architectures
  (`workflow_dispatch` input `i18n_ref` pins a last-good commit). `translations-summary` puts the
  manifest in the step summary and warns on any kept locale.
- **Why it doesn't reuse `validate_translations()`:** that function counts an error only when the
  same entry also has a (fuzzy) warning. So errors on shipped strings never count, and a gate built
  on it would agree with everything.

---

## The bake-regression check

`./i18n bake-regression --openlibrary-ref <ref> --ref <i18n ref> [--json out.json] [--list]`
answers *"if olbase baked openlibrary-i18n@X, what would get worse?"* It fetches openlibrary over
HTTPS at a full SHA (no checkout needed), compiles both sides with `write_mo` (default
`use_fuzzy=False`), loads via `babel.support.Translations`, keys on `(msgctxt, msgid)`, and limits to
msgids in openlibrary's `messages.pot`. Exit codes: 0 clean, 1 gating findings, 2 could not run.

- **Gates:** regressions to English, and placeholder defects that openlibrary's version of the same
  entry does not have. Reported without gating: all placeholder defects, and unreachable plural forms.
- **Locale classes:** a locale with no openlibrary directory is `new_locale` (reported, not gated);
  a locale whose file the gate would refuse is `rejected_locale` (gated, since none of its work would
  ship).
- **Findings compare by what is wrong, not only by entry.** A baseline, or openlibrary already
  shipping a defect, excuses a finding only if it covers all of that finding's detail: the n values
  that go English, and the placeholder signature at each n. Keying on the entry alone lets a new
  KeyError hide behind a harmless existing defect.
- **It also runs daily** (main vs main as of ~25 h earlier), because `translate.yml` merges with
  `github.token` and pushes made with that token start no workflows.

---

## See also

- [[i18n-rendering]] — how strings get translated in templates and JS
- [[README]] — index
