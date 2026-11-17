// Tests for what triggers a code review. auto_assign_reviewer.yml requests the team
// `openlibrary-agentic-code-reviewer`, and code_review_action.yml runs the model on a
// `review_requested` for that team or the bot user, a staff or author @-mention, or a dispatch.
// The `if:` expressions are transpiled to JS and evaluated against synthetic events. The team slug
// must match in both workflows, or the request would never start a review.
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
    // Built from known leaves rather than a deep merge, which assigns dynamic keys (a
    // prototype-pollution shape CodeQL flags).
    const e = overrides.event ?? {};
    return {
        event_name: overrides.event_name ?? '',
        event: {
            action: e.action ?? '',
            pull_request: { draft: e.pull_request?.draft ?? false },
            requested_team: { slug: e.requested_team?.slug ?? null },
            requested_reviewer: { login: e.requested_reviewer?.login ?? null },
            // Defaults to a value that matches nobody, so the author clause can't fire via '' == ''.
            issue: { pull_request: e.issue?.pull_request ?? null, number: e.issue?.number ?? 1, user: { login: e.issue?.user?.login ?? '__no_author__' } },
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

test('a request for the openlibrary-bot user fires (the re-request button on its review)', () => {
    const ev = ctx({
        event_name: 'pull_request_target',
        event: { action: 'review_requested', requested_reviewer: { login: 'openlibrary-bot' }, requested_team: { slug: null } }
    });
    assert.equal(evalIf(reviewIf, ev), true);
});

test('a request for any other user, or for the bot on a draft, does NOT fire', () => {
    for (const event of [
        { action: 'review_requested', requested_reviewer: { login: 'someone-else' }, requested_team: { slug: null } },
        { action: 'review_requested', pull_request: { draft: true }, requested_reviewer: { login: 'openlibrary-bot' }, requested_team: { slug: null } }
    ]) {
        assert.equal(evalIf(reviewIf, ctx({ event_name: 'pull_request_target', event })), false);
    }
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

// ---- The PR author may re-run the review on their own PR by @-mention ----
// A fork contributor can't re-request a reviewer but can comment. Other commenters stay blocked.
test('#14484: the PR author @-mentioning the bot on their OWN PR fires the re-review (fork-safe)', () => {
    const author = ctx({
        event_name: 'issue_comment',
        event: {
            issue: { pull_request: { url: 'x' }, user: { login: 'forkcontributor' } },
            comment: { body: 'addressed the feedback, @openlibrary-bot review', user: { login: 'forkcontributor' } }
        }
    });
    assert.equal(evalIf(reviewIf, author), true);
});

test('#14484: a non-author, non-staff commenter still does NOT fire (not opened to arbitrary commenters)', () => {
    const outsider = ctx({
        event_name: 'issue_comment',
        event: {
            issue: { pull_request: { url: 'x' }, user: { login: 'forkcontributor' } },
            comment: { body: 'hey @openlibrary-bot review', user: { login: 'randodrive-by' } }
        }
    });
    assert.equal(evalIf(reviewIf, outsider), false);
});

test('#14484: the author guard still requires the @openlibrary-bot mention (a plain author comment does not fire)', () => {
    const noMention = ctx({
        event_name: 'issue_comment',
        event: {
            issue: { pull_request: { url: 'x' }, user: { login: 'forkcontributor' } },
            comment: { body: 'pushed a fix, thanks!', user: { login: 'forkcontributor' } }
        }
    });
    assert.equal(evalIf(reviewIf, noMention), false);
});

test('#14484: an issue_comment with neither login set does NOT fire (author clause cannot match via empty defaults)', () => {
    // Guards the ctx default: if issue.user.login defaulted to '' like comment.user.login, an
    // event that omits both would spuriously fire via '' == ''. The sentinel default keeps it false.
    const empty = ctx({
        event_name: 'issue_comment',
        event: { issue: { pull_request: { url: 'x' } }, comment: { body: '@openlibrary-bot review' } }
    });
    assert.equal(evalIf(reviewIf, empty), false);
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
    // Forks are auto-requested too, so the same-repo clause must not come back.
    assert.ok(
        !/head\.repo\.full_name\s*==\s*github\.repository/.test(assignWf.jobs.assign.if),
        'the same-repo fork gate must be dropped (forks now covered -- #14482)'
    );
});

// ---- The assign `if:` guard, evaluated like the model-run guard above ----
// The job runs for every non-draft PR, forks included; the script decides who gets the team.
const assignIf = assignWf.jobs.assign.if;
assert.ok(typeof assignIf === 'string' && assignIf.trim(), 'assign job must have an if: guard');

// assignCtx still sets github.repository and head.repo.full_name, so re-adding a same-repo
// clause would fail these cases.
function assignCtx({ draft = false, headRepo = 'internetarchive/openlibrary', repository = 'internetarchive/openlibrary' } = {}) {
    return { repository, event: { pull_request: { draft, head: { repo: { full_name: headRepo } } } } };
}

test('auto_assign the JOB runs on a non-draft FORK PR (same-repo if: gate removed -- #14482)', () => {
    const fork = assignCtx({ headRepo: 'someexternaluser/openlibrary' });
    assert.equal(evalIf(assignIf, fork), true, 'the assign job if: must fire for a non-draft fork (author gate applies inside the script)');
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
// auto_assign_reviewer.yml keeps its script inline, so extract the shipped `const NAME =` block
// and eval it.
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
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: 'MEMBER' });
    assert.equal(gh.calls.requested, true, 'it must call requestReviewers');
    assert.deepEqual(gh.calls.requestedWith.team_reviewers, [TEAM_SLUG], 'it must request the team by slug');
    assert.equal(state.failed, null, 'a landed request must not fail the job');
});

test('requestReviewTeam: request returns OK but team is ABSENT afterward -> fails loud (silent no-op caught)', async () => {
    const gh = mockGithub({ before: [], after: [], reviews: [] }); // post-request read still empty
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: 'MEMBER' });
    assert.equal(gh.calls.requested, true, 'it must have attempted the request');
    assert.ok(state.failed, 'an unlanded team request MUST core.setFailed, not pass silently');
    assert.ok(state.failed.includes(TEAM_SLUG), 'the failure message must name the team');
});

test('requestReviewTeam: team already requested -> skips without requesting again', async () => {
    const gh = mockGithub({ before: [TEAM_OBJ], after: [TEAM_OBJ], reviews: [] });
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: 'MEMBER' });
    assert.equal(gh.calls.requested, false, 'an already-requested team must not be re-requested');
    assert.equal(state.failed, null, 'the skip path must not fail the job');
});

test('requestReviewTeam: an existing openlibrary-bot review -> skips without requesting', async () => {
    const gh = mockGithub({ before: [], after: [], reviews: [{ user: { login: 'openlibrary-bot' } }] });
    const { core, state } = mockCore();
    await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: 'MEMBER' });
    assert.equal(gh.calls.requested, false, 'a PR already reviewed by the bot must not get a fresh request');
    assert.equal(state.failed, null, 'the skip path must not fail the job');
});

// ---- Spend gate: auto-request only for known authors ----
// pull_request_target skips GitHub's "Approve and run" gate for first-time contributors, so
// requestReviewTeam checks author_association itself: unknown authors are left for a maintainer.
// Same-repo authors are always MEMBER or above.
for (const association of ['OWNER', 'MEMBER', 'COLLABORATOR', 'CONTRIBUTOR']) {
    test(`requestReviewTeam: a known author (${association}) STILL gets the team requested (incl. forks)`, async () => {
        const gh = mockGithub({ before: [], after: [TEAM_OBJ], reviews: [] });
        const { core, state } = mockCore();
        await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: association });
        assert.equal(gh.calls.requested, true, `a ${association} author must get the team auto-requested`);
        assert.equal(state.failed, null, 'a landed request must not fail the job');
    });
}

for (const association of ['NONE', 'FIRST_TIME_CONTRIBUTOR', 'FIRST_TIMER', 'MANNEQUIN']) {
    test(`requestReviewTeam: a first-timer/untrusted author (${association}) is SKIPPED -- no request, no fail (spend gate)`, async () => {
        const gh = mockGithub({ before: [], after: [TEAM_OBJ], reviews: [] });
        const { core, state } = mockCore();
        await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: association });
        assert.equal(gh.calls.requested, false, `a ${association} author must NOT trigger an auto-request (the fork spend gate)`);
        assert.equal(state.failed, null, 'the spend-gate skip is normal, not a failure');
    });
}

test('requestReviewTeam: an unexpected/empty author_association fails SAFE -> skipped (allowlist, not denylist)', async () => {
    for (const association of [undefined, '', 'SOMETHING_NEW', 'member' /* wrong case still normalized -> MEMBER fires */]) {
        const gh = mockGithub({ before: [], after: [TEAM_OBJ], reviews: [] });
        const { core } = mockCore();
        await requestReviewTeam({ github: gh, core, owner: 'o', repo: 'r', prNumber: 1, team: TEAM_SLUG, authorAssociation: association });
        const shouldFire = association === 'member'; // normalized to MEMBER
        assert.equal(gh.calls.requested, shouldFire, `author_association=${JSON.stringify(association)} -> requested should be ${shouldFire}`);
    }
});
