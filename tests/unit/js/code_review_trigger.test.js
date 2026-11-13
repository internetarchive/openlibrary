// Unit tests for the CODE-REVIEW TRIGGER ROUTING (#14461 follow-up to the merged #14455).
//
// The design DRYs the code reviewer onto ONE model-run path, keyed on a TEAM:
//   * auto_assign_reviewer.yml requests the team `openlibrary-agentic-code-reviewer` on
//     opened/ready_for_review (same-repo only).
//   * code_review_action.yml runs the model ONLY on `review_requested` whose `requested_team.slug`
//     is that team (plus the staff `issue_comment` path and `workflow_dispatch`). It no longer
//     auto-runs on `opened`/`ready_for_review`, and no longer keys on an INDIVIDUAL reviewer.
//
// A team-request event carries `github.event.requested_team` and NO `requested_reviewer`; an
// individual request is the reverse. These tests evaluate the ACTUAL `if:` expression that ships
// (parsed from the YAML and transpiled 1:1 to JS) against synthetic events, so tested logic ==
// deployed logic -- and pin the team slug identically in BOTH workflows (a drift silently breaks
// the open->request->review chain: auto_assign would request a team the reviewer never matches).
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const WF = join(here, '..', '..', '..', '.github', 'workflows');
const reviewText = readFileSync(join(WF, 'code_review_action.yml'), 'utf8');
const assignText = readFileSync(join(WF, 'auto_assign_reviewer.yml'), 'utf8');
const reviewWf = yaml.load(reviewText);
const assignWf = yaml.load(assignText);

// The one canonical reviewer team. Both workflows must spell it identically.
const TEAM_SLUG = 'openlibrary-agentic-code-reviewer';

// YAML 1.1 can resolve the mapping key `on` to boolean true; grab the trigger block either way.
const onBlock = wf => wf.on ?? wf['true'] ?? wf[true];

// --- Transpile a GitHub Actions `if:` expression to JS and evaluate it against a `github` context.
// GHA expression syntax is a near-subset of JS; the only rewrites needed for THIS file's guards:
//   `!=` -> `!==`, `==` -> `===` (one alternation pass so neither rewrite overlaps the other), and
//   the helper funcs `contains`/`fromJSON` provided in scope. Everything else (`&&`, `||`, `!`,
//   parens, string/null literals, `github.*` member access) is identical in JS.
function toJs(expr) {
    return expr.replace(/!=|==/g, m => (m === '!=' ? '!==' : '==='));
}
function evalIf(expr, github) {
    // GitHub Actions `contains()` is case-INSENSITIVE for both substring and array membership
    // (docs: "Casing is ignored."); mirror that so the harness cannot green a guard that would
    // behave differently in prod on a case-variant login or @-mention.
    const contains = (a, b) => {
        const needle = String(b ?? '').toLowerCase();
        return Array.isArray(a)
            ? a.some(x => String(x ?? '').toLowerCase() === needle)
            : String(a ?? '')
                  .toLowerCase()
                  .includes(needle);
    };
    const fromJSON = s => JSON.parse(s);
    // eslint-disable-next-line no-new-func
    return new Function('github', 'contains', 'fromJSON', `return (${toJs(expr)});`)(github, contains, fromJSON);
}

// A fully-populated context (every leaf the `if` reads exists, defaulting to a non-matching value)
// so the JS eval never dereferences undefined; overrides are deep-merged per case.
function ctx(overrides = {}) {
    const base = {
        event_name: '',
        event: {
            action: '',
            pull_request: { draft: false },
            requested_team: { slug: null },
            requested_reviewer: { login: null },
            issue: { pull_request: null, number: 1 },
            comment: { body: '', user: { login: '' } }
        }
    };
    const merge = (a, b) => {
        for (const k of Object.keys(b)) {
            a[k] = b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) ? merge(a[k] ?? {}, b[k]) : b[k];
        }
        return a;
    };
    return merge(base, overrides);
}

const reviewIf = reviewWf.jobs.analyze.if;
assert.ok(typeof reviewIf === 'string' && reviewIf.trim(), 'analyze job must have an if: guard');

// Self-check the transpiler on a known-true and known-false fragment, so a transpiler bug cannot
// mask a workflow bug (a dead evaluator would pass every "expect false" assertion vacuously).
test('if-evaluator transpiles == / != / contains faithfully (harness self-check)', () => {
    assert.equal(evalIf("github.event_name == 'x'", ctx({ event_name: 'x' })), true);
    assert.equal(evalIf("github.event_name == 'x'", ctx({ event_name: 'y' })), false);
    assert.equal(evalIf("github.event.comment.user.login != 'openlibrary-bot'", ctx({ event: { comment: { user: { login: 'mek' } } } })), true);
    assert.equal(evalIf('contains(fromJSON(\'["a","b"]\'), github.event.comment.user.login)', ctx({ event: { comment: { user: { login: 'b' } } } })), true);
    // contains() must be case-INSENSITIVE like GHA's, for both array membership and substring.
    assert.equal(evalIf('contains(fromJSON(\'["a","b"]\'), github.event.comment.user.login)', ctx({ event: { comment: { user: { login: 'B' } } } })), true);
    assert.equal(
        evalIf("contains(github.event.comment.body, '@openlibrary-bot')", ctx({ event: { comment: { body: 'please @OpenLibrary-Bot review' } } })),
        true
    );
});

// ---- The model-run guard: single team-keyed path ----
test('a team review_requested for openlibrary-agentic-code-reviewer FIRES the model', () => {
    const ev = ctx({ event_name: 'pull_request_target', event: { action: 'review_requested', requested_team: { slug: TEAM_SLUG } } });
    assert.equal(evalIf(reviewIf, ev), true);
});

test('re-requesting the same team FIRES again (re-review runs -- the guard is stateless on the event)', () => {
    // Re-review = re-request the team -> another review_requested event, structurally identical, so
    // it must evaluate true every time (there is no "already requested" suppression in the guard).
    const ev = ctx({ event_name: 'pull_request_target', event: { action: 'review_requested', requested_team: { slug: TEAM_SLUG } } });
    assert.equal(evalIf(reviewIf, ev), true);
});

test('a team review_requested for a DIFFERENT team does NOT fire', () => {
    const ev = ctx({ event_name: 'pull_request_target', event: { action: 'review_requested', requested_team: { slug: 'some-other-team' } } });
    assert.equal(evalIf(reviewIf, ev), false);
});

test('an INDIVIDUAL reviewer request (requested_reviewer, no requested_team) no longer fires', () => {
    // The old design keyed on github.event.requested_reviewer.login == 'openlibrary-bot'. The single
    // team-keyed path replaces it: an individual request carries no requested_team.slug, so it skips.
    const ev = ctx({
        event_name: 'pull_request_target',
        event: { action: 'review_requested', requested_reviewer: { login: 'openlibrary-bot' }, requested_team: { slug: null } }
    });
    assert.equal(evalIf(reviewIf, ev), false);
});

test('a DRAFT PR does not fire even with the right team requested', () => {
    const ev = ctx({
        event_name: 'pull_request_target',
        event: { action: 'review_requested', requested_team: { slug: TEAM_SLUG }, pull_request: { draft: true } }
    });
    assert.equal(evalIf(reviewIf, ev), false);
});

test('opened / ready_for_review no longer trigger the model directly (routed via auto_assign -> team request)', () => {
    for (const action of ['opened', 'ready_for_review']) {
        const ev = ctx({ event_name: 'pull_request_target', event: { action } });
        assert.equal(evalIf(reviewIf, ev), false, `${action} must not fire the model directly`);
    }
});

// ---- The staff issue_comment path and workflow_dispatch survive unchanged ----
test('a staff @openlibrary-bot comment on a PR still fires; a non-staff comment does not', () => {
    const staff = ctx({
        event_name: 'issue_comment',
        event: { issue: { pull_request: { url: 'x' } }, comment: { body: 'hey @openlibrary-bot review', user: { login: 'mekarpeles' } } }
    });
    assert.equal(evalIf(reviewIf, staff), true);
    const outsider = ctx({
        event_name: 'issue_comment',
        event: { issue: { pull_request: { url: 'x' } }, comment: { body: 'hey @openlibrary-bot review', user: { login: 'randodev' } } }
    });
    assert.equal(evalIf(reviewIf, outsider), false);
});

test('workflow_dispatch fires', () => {
    assert.equal(evalIf(reviewIf, ctx({ event_name: 'workflow_dispatch' })), true);
});

// ---- Trigger surface: the model workflow no longer lists opened/ready_for_review ----
test('code_review_action on.pull_request_target.types is exactly [review_requested]', () => {
    const types = onBlock(reviewWf).pull_request_target.types;
    assert.deepEqual(types, ['review_requested'], `expected only review_requested, got ${JSON.stringify(types)}`);
});

// ---- The team slug is spelled identically in BOTH workflows (the open->request->review chain) ----
test('the reviewer team slug appears in the code_review guard', () => {
    assert.ok(reviewIf.includes(`requested_team.slug == '${TEAM_SLUG}'`), 'guard must key on the team slug');
});

test('auto_assign requests the TEAM (team_reviewers), not the individual bot, and uses the same slug', () => {
    assert.ok(/team_reviewers\s*:/.test(assignText), 'auto_assign must request team_reviewers');
    assert.ok(assignText.includes(TEAM_SLUG), `auto_assign must request the '${TEAM_SLUG}' team`);
    // The individual-bot request is gone (it is the thing being replaced).
    assert.ok(!/reviewers\s*:\s*\[\s*'openlibrary-bot'\s*\]/.test(assignText), 'auto_assign must no longer request the individual openlibrary-bot');
});

test('auto_assign no longer excludes bot-authored PRs (team request works on them -- proven on #14450)', () => {
    assert.ok(!/user\.login\s*!=\s*'openlibrary-bot'/.test(assignWf.jobs.assign.if), 'the bot-authored exclusion must be dropped');
    // ...but it still only auto-requests on SAME-REPO PRs (the fork spend gate).
    assert.ok(/head\.repo\.full_name\s*==\s*github\.repository/.test(assignWf.jobs.assign.if), 'auto_assign must stay same-repo only');
});
