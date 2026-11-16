// Unit + integration tests for #14487 -- the code-review action must post a real VERDICT
// (Approve / Request changes, not a bare Comment) and RESOLVE fixed threads on re-review.
//
// Two layers, both "tested bytes == shipped bytes":
//   1. The three PURE helpers embedded in the `post` job's github-script step, extracted verbatim
//      from the workflow YAML and exercised directly:
//        - selectReviewEvent({selfAuthored, findingCount, unresolvedOwnThreads})  -- the verdict
//          (PART A). APPROVE requires 0 findings AND 0 surviving own threads, so it can never
//          contradict a red code-review status.
//        - shouldDismissTeamRequest({selfAuthored, event})  -- clear a bot-authored PR's pill (A.2).
//        - threadsToResolve({threads, findings, dimensions, botLogin, reviewedLines}) -- which of OUR
//          OWN threads are now fixed and may be resolved (PART B), guarded LINE-granular so an
//          incremental run never resolves a finding on a line it did not re-examine.
//   2. The ACTUAL post step driven end-to-end against a mocked GitHub, to prove the wiring: the
//      verdict reaches createReview, the self-review 422 degrades to COMMENT, a bot-authored PR
//      dismisses the team request, a fixed finding's thread is resolved while a surviving one is
//      kept (and keeps the verdict off APPROVE), and a thread-enumeration failure never fails the job.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const WF = join(here, '..', '..', '..', '.github', 'workflows', 'code_review_action.yml');
const workflowText = readFileSync(WF, 'utf8');
const workflow = yaml.load(workflowText);
const REVIEW_GATE_JS = workflow.env.REVIEW_GATE_JS;
const lines = workflowText.split('\n');

// The gate's dimension LABELS -- the post step renders a finding header as "<SEV> · <Label> — <Title>",
// and threadsToResolve rebuilds the same identity. Keep this in lockstep with REVIEW_GATE_JS.dimensions.
const DIMS = {
    correctness: 'Correctness',
    security: 'Security',
    accessibility: 'Accessibility',
    test_coverage: 'Test coverage',
    styleguide: 'Styleguide'
};

// Extract a `const <name> = (…) => { … };` block from the workflow lines, keyed on the closing line
// that matches the declaration's own indentation (so a nested `};` cannot truncate it), and eval it.
// Pure helpers close over nothing, so a bare `new Function` suffices. (Same technique as the
// status-gate test -- if the helper is absent, this throws, which is exactly the red state pre-fix.)
function extractFn(name) {
    const start = lines.findIndex(l => l.includes(`const ${name} =`));
    assert.ok(start >= 0, `${name} not found in workflow (expected a const ${name} = (…) => {…};)`);
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

const selectReviewEvent = extractFn('selectReviewEvent');
const shouldDismissTeamRequest = extractFn('shouldDismissTeamRequest');
const threadsToResolve = extractFn('threadsToResolve');

// A review thread as GraphQL returns it for PART B, with the bot's finding header as its first comment.
function thread(id, path, dim, title, { resolved = false, outdated = false, author = 'openlibrary-bot', severity = 'MEDIUM', line = 1 } = {}) {
    return {
        id,
        path,
        line,
        isResolved: resolved,
        isOutdated: outdated,
        comments: { nodes: [{ author: { login: author }, body: `**${severity} · ${DIMS[dim]} — ${title}**\n\nsome body text` }] }
    };
}
const finding = (path, dim, title) => ({ path, dimension: dim, title });
// reviewedLines: path -> Set of RIGHT-side lines this run examined. rl(['a.py', 1, 2]) => Map{'a.py'=>{1,2}}.
const rl = (...entries) => new Map(entries.map(([p, ...ls]) => [p, new Set(ls)]));

// ========================= PART A: selectReviewEvent (the verdict) =========================
test('selectReviewEvent: blocking findings on a contributor PR -> REQUEST_CHANGES', () => {
    assert.equal(selectReviewEvent({ selfAuthored: false, findingCount: 1, unresolvedOwnThreads: 0 }), 'REQUEST_CHANGES');
    assert.equal(selectReviewEvent({ selfAuthored: false, findingCount: 9, unresolvedOwnThreads: 3 }), 'REQUEST_CHANGES');
});
test('selectReviewEvent: a clean contributor PR with NO surviving own thread -> APPROVE', () => {
    assert.equal(selectReviewEvent({ selfAuthored: false, findingCount: 0, unresolvedOwnThreads: 0 }), 'APPROVE');
});
test('selectReviewEvent: a clean contributor PR with a SURVIVING own thread -> COMMENT (never APPROVE while red)', () => {
    // The status job blocks while an own finding is unresolved; APPROVE here would contradict it.
    assert.equal(selectReviewEvent({ selfAuthored: false, findingCount: 0, unresolvedOwnThreads: 1 }), 'COMMENT');
});
test('selectReviewEvent: UNKNOWN thread state (null, e.g. enumeration failed) -> COMMENT, never APPROVE', () => {
    assert.equal(selectReviewEvent({ selfAuthored: false, findingCount: 0, unresolvedOwnThreads: null }), 'COMMENT');
});
test('selectReviewEvent: a bot-authored (self) PR -> COMMENT regardless (422 avoidance)', () => {
    assert.equal(selectReviewEvent({ selfAuthored: true, findingCount: 0, unresolvedOwnThreads: 0 }), 'COMMENT');
    assert.equal(selectReviewEvent({ selfAuthored: true, findingCount: 4, unresolvedOwnThreads: 2 }), 'COMMENT');
});

// ========================= PART A.2: shouldDismissTeamRequest (clear the bot-PR pill) =========================
test('shouldDismissTeamRequest: a bot-authored PR that posted COMMENT -> dismiss the team request', () => {
    assert.equal(shouldDismissTeamRequest({ selfAuthored: true, event: 'COMMENT' }), true);
});
test('shouldDismissTeamRequest: a contributor verdict clears the pill itself -> no dismiss', () => {
    assert.equal(shouldDismissTeamRequest({ selfAuthored: false, event: 'APPROVE' }), false);
    assert.equal(shouldDismissTeamRequest({ selfAuthored: false, event: 'REQUEST_CHANGES' }), false);
    // Even a contributor PR that degraded to COMMENT on an unexpected 422: not self-authored -> no dismiss.
    assert.equal(shouldDismissTeamRequest({ selfAuthored: false, event: 'COMMENT' }), false);
});

// ========================= PART B: threadsToResolve (resolve fixed only, line-granular) =========================
test('threadsToResolve: a fixed finding (gone, line re-examined) -> its thread resolves', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Off-by-one in the loop bound', { line: 50 })];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 50]) });
    assert.deepEqual(ids, ['T1']);
});
test('threadsToResolve: a still-present finding -> its thread stays open (byte-identical key match)', () => {
    // The key threadsToResolve parses from the shipped thread body must equal the key it builds from a
    // live finding, or a standing finding would be wrongly resolved (false green).
    const threads = [thread('T1', 'a.py', 'correctness', 'Off-by-one in the loop bound', { line: 50 })];
    const findings = [finding('a.py', 'correctness', 'Off-by-one in the loop bound')];
    const ids = threadsToResolve({ threads, findings, dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 50]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: LINE-granular -- a finding on a line this run did NOT re-examine stays open', () => {
    // The incremental HIGH bug: file a.py is in the diff (line 200 changed), but the prior finding is at
    // line 50, which this run never saw. It must NOT be resolved even though it is absent from findings.
    const threads = [thread('T1', 'a.py', 'correctness', 'Unaddressed, on an unchanged line', { line: 50 })];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 200]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: a thread on a file NOT reviewed this run stays open', () => {
    const threads = [thread('T1', 'untouched.py', 'correctness', 'Old finding', { line: 10 })];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 10]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: a thread with a null line (outdated anchor) stays open', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Moved code', { line: null })];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 50]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: a NON-bot thread is never resolved', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Someone else said this', { author: 'alice', line: 10 })];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 10]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: an already-resolved thread is not re-emitted', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Already handled', { resolved: true, line: 10 })];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 10]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: an unparseable thread body is left open (fail safe)', () => {
    const threads = [
        {
            id: 'T1',
            path: 'a.py',
            line: 10,
            isResolved: false,
            isOutdated: false,
            comments: { nodes: [{ author: { login: 'openlibrary-bot' }, body: 'not a finding header' }] }
        }
    ];
    const ids = threadsToResolve({ threads, findings: [], dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 10]) });
    assert.deepEqual(ids, []);
});
test('threadsToResolve: mixed -- resolves only the fixed, re-examined thread; keeps the standing one', () => {
    const threads = [
        thread('FIXED', 'a.py', 'styleguide', 'Prefer double quotes', { line: 3 }),
        thread('STANDS', 'a.py', 'correctness', 'Null deref on empty list', { line: 7 })
    ];
    const findings = [finding('a.py', 'correctness', 'Null deref on empty list')];
    const ids = threadsToResolve({ threads, findings, dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 3, 7]) });
    assert.deepEqual(ids, ['FIXED']);
});
test('threadsToResolve: a title containing an em-dash is matched whole (no spurious resolve)', () => {
    const title = 'Guard — then dereference';
    const threads = [thread('T1', 'a.py', 'correctness', title, { line: 4 })];
    const findings = [finding('a.py', 'correctness', title)];
    const ids = threadsToResolve({ threads, findings, dimensions: DIMS, botLogin: 'openlibrary-bot', reviewedLines: rl(['a.py', 4]) });
    assert.deepEqual(ids, []);
});

// ========================= Integration: drive the real post step end-to-end =========================
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

function scriptOf(jobName, stepMatch) {
    const job = workflow.jobs[jobName];
    const step = (job.steps || []).find(s => s.with && typeof s.with.script === 'string' && (s.name || '').includes(stepMatch));
    assert.ok(step, `step "${stepMatch}" not found in job ${jobName}`);
    return step.with.script;
}

async function runScript(body, { github, context, env, cwd }) {
    const recorded = { failed: null, warnings: [] };
    const core = {
        setOutput: () => {},
        setFailed: m => {
            recorded.failed = m;
        },
        info: () => {},
        warning: m => recorded.warnings.push(m),
        notice: () => {},
        debug: () => {}
    };
    const fakeProcess = { env: { ...env } };
    const realRequire = (await import('node:module')).createRequire(import.meta.url);
    const realFs = realRequire('fs');
    const { isAbsolute, join: pjoin } = realRequire('path');
    const resolve = p => (cwd && typeof p === 'string' && !isAbsolute(p) ? pjoin(cwd, p) : p);
    const wrappedFs = new Proxy(realFs, {
        get(target, prop) {
            if (prop === 'readFileSync') return (p, ...a) => target.readFileSync(resolve(p), ...a);
            if (prop === 'writeFileSync') return (p, ...a) => target.writeFileSync(resolve(p), ...a);
            if (prop === 'existsSync') return p => target.existsSync(resolve(p));
            return target[prop];
        }
    });
    const wrappedRequire = id => (id === 'fs' ? wrappedFs : realRequire(id));
    const fn = new AsyncFunction('github', 'context', 'core', 'require', 'process', body);
    await fn(github, context, core, wrappedRequire, fakeProcess);
    return { ...recorded, core };
}

const context = {
    repo: { owner: 'internetarchive', repo: 'openlibrary' },
    eventName: 'pull_request_target',
    payload: {},
    runId: 1,
    serverUrl: 'https://github.com'
};
const SHA = c => c.repeat(40);

// A mock octokit that records createReview payloads, resolveReviewThread mutations, and team dismissals,
// and can throw a 422 on the first verdict attempt (self-review fallback) or throw on the thread
// enumeration (false-red guard).
function mockGitHub({ author = 'contributor', reviewThreads = [], throw422 = false, enumThrows = false, postedReviewId = 999 } = {}) {
    const calls = { createReview: [], resolved: [], removedTeams: [] };
    let threw = false;
    const github = {
        rest: {
            pulls: {
                get: async () => ({ data: { head: { sha: SHA('a') }, user: { login: author } } }),
                listReviews: async () => ({ data: [{ id: postedReviewId, user: { login: 'openlibrary-bot' }, commit_id: SHA('a') }] }),
                createReview: async p => {
                    if (throw422 && !threw && p.event !== 'COMMENT') {
                        threw = true;
                        const e = new Error('Unprocessable Entity');
                        e.status = 422;
                        throw e;
                    }
                    calls.createReview.push(p);
                    return { data: { id: postedReviewId } };
                },
                removeRequestedReviewers: async p => {
                    calls.removedTeams.push(...(p.team_reviewers || []));
                    return { data: {} };
                }
            },
            repos: {
                compareCommitsWithBasehead: async () => ({ data: '' })
            }
        },
        paginate: async (method, params) => (await method(params)).data,
        graphql: async (query, vars) => {
            if (/resolveReviewThread/.test(query)) {
                calls.resolved.push(vars.id);
                return { resolveReviewThread: { thread: { id: vars.id, isResolved: true } } };
            }
            if (enumThrows) throw new Error('transient GraphQL 502');
            return { repository: { pullRequest: { reviewThreads: { nodes: reviewThreads, pageInfo: { hasNextPage: false, endCursor: null } } } } };
        }
    };
    return { github, calls };
}

// A review whose single finding is anchored to a RIGHT-side line of this diff (so it posts inline and
// creates a thread). The diff makes line 1 of a.py anchorable (== reviewedLines {'a.py': {1}}).
const DIFF = 'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+print(1)\n';
function reviewWith(findings) {
    const dims = {};
    for (const k of Object.keys(DIMS)) dims[k] = { status: 'none', note: 'ok' };
    for (const f of findings) dims[f.dimension] = { status: 'findings', note: 'ok' };
    return { summary: 'A plain summary.', dimensions: dims, findings };
}

let dir;
function setup(reviewObj) {
    dir = mkdtempSync(join(tmpdir(), 'cr14487-'));
    writeFileSync(join(dir, 'review.json'), JSON.stringify(reviewObj));
    writeFileSync(join(dir, 'review.diff'), DIFF);
    return dir;
}
function teardown() {
    if (dir) rmSync(dir, { recursive: true, force: true });
}

const baseEnv = d => ({ PR: '1', HEAD_SHA: SHA('a'), BASE_SHA: SHA('b'), INCREMENTAL: 'false', REVIEW_GATE_JS, GITHUB_WORKSPACE: d });

test('post: a clean review on a CONTRIBUTOR PR with no prior threads posts event APPROVE', async () => {
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});
test('post: a review WITH findings on a CONTRIBUTOR PR posts event REQUEST_CHANGES', async () => {
    const d = setup(reviewWith([{ dimension: 'correctness', severity: 'high', title: 'Bug here', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'REQUEST_CHANGES');
    } finally {
        teardown();
    }
});
test('post: a clean CONTRIBUTOR PR with a SURVIVING own thread posts COMMENT, not APPROVE', async () => {
    // A prior bot finding on a file this run did not re-examine (other.py) survives resolution -> the
    // verdict must NOT be APPROVE (the status is still red on it).
    const d = setup(reviewWith([]));
    try {
        const threads = [thread('SURVIVES', 'other.py', 'correctness', 'Still open on an untouched file', { line: 20 })];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview[0].event, 'COMMENT', 'never APPROVE while an own finding is unresolved');
        assert.deepEqual(calls.resolved, [], 'the untouched-file thread is not resolved');
    } finally {
        teardown();
    }
});
test('post: a BOT-AUTHORED (self) PR falls back to event COMMENT and dismisses the team request', async () => {
    const d = setup(reviewWith([{ dimension: 'correctness', severity: 'high', title: 'Bug here', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const { github, calls } = mockGitHub({ author: 'openlibrary-bot' });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview[0].event, 'COMMENT');
        assert.deepEqual(calls.removedTeams, ['openlibrary-agentic-code-reviewer']);
    } finally {
        teardown();
    }
});
test('post: a CONTRIBUTOR PR does NOT dismiss the team request (the verdict clears the pill)', async () => {
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview[0].event, 'APPROVE');
        assert.deepEqual(calls.removedTeams, []);
    } finally {
        teardown();
    }
});
test('post: a withheld review (no post) never dismisses the team request', async () => {
    const d = setup({ withheld: true });
    writeFileSync(join(d, 'review.diff'), '');
    try {
        const { github, calls } = mockGitHub({ author: 'openlibrary-bot' });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview.length, 0);
        assert.deepEqual(calls.removedTeams, []);
    } finally {
        teardown();
    }
});
test('post: an unexpected 422 on a verdict degrades to COMMENT without failing the job', async () => {
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor', throw422: true });
        const res = await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(res.failed, null, 'a 422 must not hard-fail the post job');
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'COMMENT');
    } finally {
        teardown();
    }
});
test('post: a thread-enumeration failure never fails the job and never auto-approves', async () => {
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor', enumThrows: true });
        const res = await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.equal(res.failed, null, 'a transient GraphQL failure must not fail a post that succeeds');
        assert.equal(calls.createReview.length, 1, 'the review still posts');
        assert.equal(calls.createReview[0].event, 'COMMENT', 'unknown thread state -> COMMENT, never APPROVE');
        assert.deepEqual(calls.resolved, []);
    } finally {
        teardown();
    }
});
test('post: a fixed finding on a re-examined line gets its thread resolved on re-review', async () => {
    // This run is clean. A prior bot thread on a.py:1 (a line this run reviewed) has no matching current
    // finding -> fixed -> resolved. A prior thread on an untouched file stays open (and keeps it off APPROVE).
    const d = setup(reviewWith([]));
    try {
        const threads = [
            thread('FIXED', 'a.py', 'correctness', 'Prior finding now gone', { line: 1 }),
            thread('UNTOUCHED', 'other.py', 'correctness', 'On a file this run did not review', { line: 9 })
        ];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(calls.resolved, ['FIXED'], 'only the fixed finding on a re-examined line is resolved');
        assert.equal(calls.createReview[0].event, 'COMMENT', 'the surviving UNTOUCHED thread keeps it off APPROVE');
    } finally {
        teardown();
    }
});
test('post: a standing finding keeps its thread open and the PR off APPROVE', async () => {
    // This run re-reports the same finding on a.py:1 -> REQUEST_CHANGES, and the thread is NOT resolved.
    const d = setup(reviewWith([{ dimension: 'correctness', severity: 'high', title: 'Still broken', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const threads = [thread('STANDS', 'a.py', 'correctness', 'Still broken', { line: 1 })];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        await runScript(scriptOf('post', 'Validate anchors'), { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(calls.resolved, [], 'a finding that still stands is never resolved');
        assert.equal(calls.createReview[0].event, 'REQUEST_CHANGES');
    } finally {
        teardown();
    }
});
