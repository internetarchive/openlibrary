// Unit tests for the CODE-REVIEW TRIGGER ROUTING (#14461 follow-up to the merged #14455).
//
// The design DRYs the code reviewer onto ONE model-run path, keyed on a TEAM:
//   * auto_assign_reviewer.yml requests the team `openlibrary-agentic-code-reviewer` on
//     opened/ready_for_review for every non-draft PR, forks included (#14482 dropped the
//     same-repo spend gate).
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
    // Build the context explicitly from the known override leaves the tests set, rather than a
    // hand-rolled deep merge. A deep merge would assign `a[k] = b[k]` for a dynamically-computed
    // key `k` taken from the overrides object -- a prototype-pollution shape (CodeQL flags it, and
    // a __proto__/constructor/prototype guard to silence it is then dead code in a test helper that
    // only ever sees literal overrides). The explicit builder has no dynamic-key assignment at all,
    // so neither the alert nor a guard applies, and every leaf still defaults to a non-matching value.
    const e = overrides.event ?? {};
    return {
        event_name: overrides.event_name ?? '',
        event: {
            action: e.action ?? '',
            pull_request: { draft: e.pull_request?.draft ?? false },
            requested_team: { slug: e.requested_team?.slug ?? null },
            requested_reviewer: { login: e.requested_reviewer?.login ?? null },
            issue: { pull_request: e.issue?.pull_request ?? null, number: e.issue?.number ?? 1 },
            comment: { body: e.comment?.body ?? '', user: { login: e.comment?.user?.login ?? '' } }
        }
    };
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
    // #14482: the same-repo spend gate is removed -- forks are now auto-requested too, so the
    // head.repo.full_name == github.repository clause must NO LONGER be present in the guard.
    assert.ok(
        !/head\.repo\.full_name\s*==\s*github\.repository/.test(assignWf.jobs.assign.if),
        'the same-repo fork gate must be dropped (forks now covered -- #14482)'
    );
});

// ---- The assign `if:` guard, evaluated like the model-run guard above ----
// #14482 widens auto_assign to forks. We evaluate the ACTUAL assign `if:` string (transpiled 1:1 to
// JS by the same evalIf harness used for the model guard) against synthetic PR events, so the tested
// logic == the deployed logic -- not just a regex over the source.
const assignIf = assignWf.jobs.assign.if;
assert.ok(typeof assignIf === 'string' && assignIf.trim(), 'assign job must have an if: guard');

// Post-#14482 the deployed guard reads only github.event.pull_request.draft; assignCtx still
// over-provides github.repository and head.repo.full_name so these cases keep exercising the real
// fork-vs-same-repo distinction and would also catch a regression that re-added the same-repo gate.
function assignCtx({ draft = false, headRepo = 'internetarchive/openlibrary', repository = 'internetarchive/openlibrary' } = {}) {
    return { repository, event: { pull_request: { draft, head: { repo: { full_name: headRepo } } } } };
}

test('auto_assign FIRES on a non-draft FORK PR (same-repo spend gate removed -- #14482)', () => {
    const fork = assignCtx({ headRepo: 'someexternaluser/openlibrary' });
    assert.equal(evalIf(assignIf, fork), true, 'a non-draft fork PR must now get the reviewer team auto-requested');
});

test('auto_assign FIRES on a non-draft same-repo PR (unchanged)', () => {
    assert.equal(evalIf(assignIf, assignCtx({})), true, 'a non-draft same-repo PR must still fire');
});

test('auto_assign SKIPS a draft PR, fork or same-repo (draft exclusion kept)', () => {
    assert.equal(evalIf(assignIf, assignCtx({ draft: true, headRepo: 'someexternaluser/openlibrary' })), false, 'a draft fork PR must not fire');
    assert.equal(evalIf(assignIf, assignCtx({ draft: true })), false, 'a draft same-repo PR must not fire');
});

// ---- The team is requested with the elevated (org-aware) PAT, not the default GITHUB_TOKEN ----
test('auto_assign supplies OL_BOT_REVIEW_PAT to the team-request step', () => {
    // Requesting a TEAM reviewer needs an identity that can resolve the org team; the default
    // repo-scoped GITHUB_TOKEN cannot reliably do so (silent no-op). The step must wire the PAT.
    assert.ok(
        /github-token:\s*\$\{\{\s*secrets\.OL_BOT_REVIEW_PAT\s*\}\}/.test(assignText),
        'the team-request step must set github-token to secrets.OL_BOT_REVIEW_PAT'
    );
});

// ---- The request/verify script itself (extracted and driven with a mock github/core) ----
// Mirrors tests/unit/js/code_review_status_gate.test.js's extractFn: pull the EXACT `const NAME =`
// arrow block that ships (keyed on the closer at the declaration's indentation) and eval it, so the
// tested logic == the deployed logic.
function extractFn(lines, name) {
    const start = lines.findIndex(l => l.includes(`const ${name} =`));
    assert.ok(start >= 0, `${name} not found in workflow`);
    const indent = lines[start].match(/^(\s*)/)[1];
    const closer = `${indent}};`;
    const body = [lines[start]];
    let end = -1;
    for (let j = start + 1; j < lines.length; j++) {
        body.push(lines[j]);
        if (lines[j] === closer) {
            end = j;
            break;
        }
    }
    assert.ok(end >= 0, `end of ${name} not found`);
    const src = body
        .join('\n')
        .trim()
        .replace(new RegExp(`^const ${name} =\\s*`), '')
        .replace(/;\s*$/, '');
    // eslint-disable-next-line no-new-func
    return new Function(`return (${src});`)();
}

const requestReviewTeam = extractFn(assignText.split('\n'), 'requestReviewTeam');

// Build a mock `github` whose two listRequestedReviewers reads (pre-request, post-request) return the
// given team arrays, records whether requestReviewers fired, and serves listReviews via paginate.
function mockGithub({ before = [], after = [], reviews = [] }) {
    const calls = { requested: false, requestedWith: null };
    let reads = 0;
    return {
        calls,
        paginate: async () => reviews,
        rest: {
            pulls: {
                listReviews: 'listReviews',
                listRequestedReviewers: async () => {
                    reads += 1;
                    return { data: { teams: reads === 1 ? before : after } };
                },
                requestReviewers: async params => {
                    calls.requested = true;
                    calls.requestedWith = params;
                    return { data: {} };
                }
            }
        }
    };
}
function mockCore() {
    const state = { failed: null, infos: [] };
    const core = {
        setFailed: m => {
            state.failed = m;
        },
        info: m => state.infos.push(m)
    };
    return { core, state };
}
const TEAM_OBJ = { slug: TEAM_SLUG };

test('requestReviewTeam: team lands after the request -> succeeds, no setFailed', async () => {
    const gh = mockGithub({ before: [], after: [TEAM_OBJ], reviews: [] });
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG });
    assert.equal(gh.calls.requested, true, 'it must call requestReviewers');
    assert.deepEqual(gh.calls.requestedWith.team_reviewers, [TEAM_SLUG], 'it must request the team by slug');
    assert.equal(state.failed, null, 'a landed request must not fail the job');
});

test('requestReviewTeam: request returns OK but team is ABSENT afterward -> fails loud (silent no-op caught)', async () => {
    const gh = mockGithub({ before: [], after: [], reviews: [] }); // post-request read still empty
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG });
    assert.equal(gh.calls.requested, true, 'it must have attempted the request');
    assert.ok(state.failed, 'an unlanded team request MUST core.setFailed, not pass silently');
    assert.ok(state.failed.includes(TEAM_SLUG), 'the failure message must name the team');
});

test('requestReviewTeam: team already requested -> skips without requesting again', async () => {
    const gh = mockGithub({ before: [TEAM_OBJ], after: [TEAM_OBJ], reviews: [] });
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG });
    assert.equal(gh.calls.requested, false, 'an already-requested team must not be re-requested');
    assert.equal(state.failed, null, 'the skip path must not fail the job');
});

test('requestReviewTeam: an existing openlibrary-bot review -> skips without requesting', async () => {
    const gh = mockGithub({ before: [], after: [], reviews: [{ user: { login: 'openlibrary-bot' } }] });
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG });
    assert.equal(gh.calls.requested, false, 'a PR already reviewed by the bot must not get a fresh request');
    assert.equal(state.failed, null, 'the skip path must not fail the job');
});
