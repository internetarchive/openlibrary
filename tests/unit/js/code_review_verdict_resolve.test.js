// Tests for the review verdict and for resolving fixed threads (post.cjs):
//   1. The helpers: selectReviewEvent (APPROVE needs no findings and none of the bot's threads
//      open), shouldDismissTeamRequest, threadsToResolve and fixedInSha.
//   2. The post step against a mock GitHub: the verdict reaches createReview, a 422 falls back to
//      COMMENT, a bot-authored PR drops the team request, fixed threads are handed to the resolve
//      job and open ones kept, and a thread-enumeration failure doesn't fail the job.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const SCRIPTS = join(here, '..', '..', '..', '.github', 'scripts', 'code_review');
const load = createRequire(import.meta.url);
const post = load(join(SCRIPTS, 'post.cjs'));
const range = load(join(SCRIPTS, 'range.cjs'));
const gate = load(join(SCRIPTS, 'gate.cjs'));

// The gate's dimension LABELS -- the post step renders a finding header as "<SEV> · <Label> — <Title>",
// and threadsToResolve rebuilds the same identity. Keep this in lockstep with gate.cjs's dimensions.
const DIMS = {
    correctness: 'Correctness',
    security: 'Security',
    accessibility: 'Accessibility',
    test_coverage: 'Test coverage',
    styleguide: 'Styleguide'
};

const { selectReviewEvent, shouldDismissTeamRequest, threadsToResolve, fixedInSha, agentPrompt, threadStateLine } = post;

// A review thread as GraphQL returns it, with the bot's finding header as its first comment.
function thread(id, path, dim, title, { resolved = false, outdated = false, author = 'openlibrary-bot', severity = 'MEDIUM', line = 1 } = {}) {
    return {
        id,
        path,
        line,
        isResolved: resolved,
        isOutdated: outdated,
        comments: { nodes: [{ id: `C_${id}`, author: { login: author }, body: `**${severity} · ${DIMS[dim]} — ${title}**\n\nsome body text` }] }
    };
}

// ========================= selectReviewEvent (the verdict) =========================
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

// ========================= shouldDismissTeamRequest (bot-authored PRs) =========================
test('shouldDismissTeamRequest: a bot-authored PR that posted COMMENT -> dismiss the team request', () => {
    assert.equal(shouldDismissTeamRequest({ selfAuthored: true, event: 'COMMENT' }), true);
});
test('shouldDismissTeamRequest: a contributor verdict clears the pill itself -> no dismiss', () => {
    assert.equal(shouldDismissTeamRequest({ selfAuthored: false, event: 'APPROVE' }), false);
    assert.equal(shouldDismissTeamRequest({ selfAuthored: false, event: 'REQUEST_CHANGES' }), false);
    // Even a contributor PR that degraded to COMMENT on an unexpected 422: not self-authored -> no dismiss.
    assert.equal(shouldDismissTeamRequest({ selfAuthored: false, event: 'COMMENT' }), false);
});

// ========================= threadsToResolve (only threads the model judged fixed) =========================
const BOT = 'openlibrary-bot';
test('threadsToResolve: a thread the model listed as fixed resolves', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Off-by-one in the loop bound', { line: 50 })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['T1'], botLogin: BOT }), ['T1']);
});
test('threadsToResolve: a thread the model did NOT list stays open', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Off-by-one in the loop bound', { line: 50 })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: [], botLogin: BOT }), []);
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: undefined, botLogin: BOT }), []);
});
test('threadsToResolve: #14515 -- a fix on OTHER lines resolves the thread (no line-in-diff requirement)', () => {
    // The comment sat on line 34 and said "lines 10, 22, 28 have the same bug"; the fix touched only those.
    const threads = [thread('T1', 'header.html', 'correctness', 'Same bug left in 4 sibling strings', { line: 34 })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['T1'], botLogin: BOT }), ['T1']);
});
test('threadsToResolve: an OUTDATED thread (null line) the model listed as fixed resolves', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Moved code', { line: null, outdated: true })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['T1'], botLogin: BOT }), ['T1']);
});
test('threadsToResolve: a NON-bot thread is never resolved, even if listed', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Someone else said this', { author: 'alice', line: 10 })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['T1'], botLogin: BOT }), []);
});
test('threadsToResolve: an already-resolved thread is not re-emitted', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Already handled', { resolved: true, line: 10 })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['T1'], botLogin: BOT }), []);
});
test('threadsToResolve: an id that matches no live thread is ignored', () => {
    const threads = [thread('T1', 'a.py', 'correctness', 'Real one', { line: 10 })];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['INVENTED'], botLogin: BOT }), []);
});
test('threadsToResolve: mixed -- resolves only the listed thread; keeps the other', () => {
    const threads = [
        thread('FIXED', 'a.py', 'styleguide', 'Prefer double quotes', { line: 3 }),
        thread('STANDS', 'a.py', 'correctness', 'Null deref on empty list', { line: 7 })
    ];
    assert.deepEqual(threadsToResolve({ threads, resolvedIds: ['FIXED'], botLogin: BOT }), ['FIXED']);
});

// ========================= fixedInSha (which commit the "Addressed in" note credits) =========================
test('fixedInSha: the newest in-range commit that touched the file', () => {
    // rangeShas and pathShas are newest-first. 'old' touched the file before this range.
    assert.equal(fixedInSha({ rangeShas: ['c3', 'c2', 'c1'], pathShas: ['c2', 'c1', 'old'], headSha: 'c3' }), 'c2');
});
test('fixedInSha: falls back to the head when no in-range commit touched the file', () => {
    assert.equal(fixedInSha({ rangeShas: ['c3', 'c2'], pathShas: ['old'], headSha: 'c3' }), 'c3');
    assert.equal(fixedInSha({ rangeShas: [], pathShas: [], headSha: 'c3' }), 'c3');
});

// ========================= the gate keeps `resolved` (ids only) =========================
const cleanReview = extra => {
    const dims = {};
    for (const k of Object.keys(DIMS)) dims[k] = { status: 'none', note: 'ok' };
    return { summary: 'A plain summary.', dimensions: dims, findings: [], ...extra };
};
test('gate: resolved thread ids pass through to the clean copy (deduped)', () => {
    const res = gate.check(cleanReview({ resolved: ['PRRT_kwDOAB1', 'PRRT_kwDOAB1', 'PRRT_kwDOAB2'] }));
    assert.equal(res.publish, true);
    assert.deepEqual(res.clean.resolved, ['PRRT_kwDOAB1', 'PRRT_kwDOAB2']);
});
test('gate: no resolved field -> an empty list', () => {
    const res = gate.check(cleanReview({}));
    assert.equal(res.publish, true);
    assert.deepEqual(res.clean.resolved, []);
});
test('gate: a resolved entry that is not an id (prose, markdown, non-string) withholds the review', () => {
    for (const bad of [['fixed it'], ['[x](http://e)'], [42], 'PRRT_1']) {
        assert.equal(gate.check(cleanReview({ resolved: bad })).publish, false, JSON.stringify(bad));
    }
});

test('gate: dismissed thread ids pass through deduped, and a non-id withholds the review', () => {
    const res = gate.check(cleanReview({ dismissed: ['PRRT_1', 'PRRT_1'] }));
    assert.equal(res.publish, true);
    assert.deepEqual(res.clean.dismissed, ['PRRT_1']);
    assert.deepEqual(gate.check(cleanReview({})).clean.dismissed, []);
    for (const bad of [['not valid, see reply'], [42], 'PRRT_1']) {
        assert.equal(gate.check(cleanReview({ dismissed: bad })).publish, false, JSON.stringify(bad));
    }
});

// ========================= the gate requires `confidence` and demotes low-confidence findings =========================
const withFinding = f =>
    cleanReview({
        dimensions: { ...cleanReview({}).dimensions, correctness: { status: 'findings', note: 'ok' } },
        findings: [{ dimension: 'correctness', severity: 'high', title: 'Bug', body: 'Fix it.', ...f }]
    });
test('gate: a finding without an integer confidence from 1 to 10 withholds the review', () => {
    for (const confidence of [undefined, null, 0, 11, 5.5, '8', -1]) {
        assert.equal(gate.check(withFinding({ confidence })).publish, false, String(confidence));
    }
    for (const confidence of [1, 10]) assert.equal(gate.check(withFinding({ confidence })).publish, true);
});
test('gate: confidence below 6 demotes the finding to low; 6 and up keeps its severity', () => {
    assert.equal(gate.check(withFinding({ confidence: 5 })).clean.findings[0].severity, 'low');
    assert.equal(gate.check(withFinding({ confidence: 6 })).clean.findings[0].severity, 'high');
    // A finding held back by the text scan that is unsure doesn't block.
    const res = gate.check(withFinding({ confidence: 3, body: 'Store the password here.' }));
    assert.equal(res.heldBack, true);
    assert.equal(res.blocking, false);
});

test('gate: a test-coverage finding is always low, so it never blocks', () => {
    const review = cleanReview({
        dimensions: { ...cleanReview({}).dimensions, test_coverage: { status: 'findings', note: 'ok' } },
        findings: [{ dimension: 'test_coverage', severity: 'high', confidence: 9, title: 'No regression test', body: 'Add one.' }]
    });
    assert.equal(gate.check(review).clean.findings[0].severity, 'low');
});

// ========================= agentPrompt and threadStateLine =========================
test('agentPrompt: no location without a path, and a longer fence when the text has backticks', () => {
    const out = agentPrompt({ title: 'T', body: 'See:\n```\ncode\n```' }, false);
    assert.doesNotMatch(out, / At `/);
    assert.doesNotMatch(out, /file context/);
    assert.match(out, /````text\n/);
    assert.match(out, /say why in a comment on the PR/);
});
test('threadStateLine: only non-zero counts, with a check mark once nothing is open', () => {
    assert.equal(threadStateLine({ addressed: 2, dismissed: 1, open: 1 }), 'Earlier findings: 2 addressed, 1 dismissed, 1 still open.');
    assert.equal(threadStateLine({ addressed: 2, dismissed: 0, open: 0 }), '✅ Earlier findings: 2 addressed.');
    assert.equal(threadStateLine({ addressed: 0, dismissed: 0, open: 0 }), '');
});

// ========================= Integration: drive the real post step end-to-end =========================
async function runScript(stepFn, { github, context, env, cwd }) {
    const recorded = { failed: null, warnings: [], outputs: {} };
    const core = {
        setOutput: (k, v) => {
            recorded.outputs[k] = v;
        },
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
    // GITHUB_WORKSPACE is a temp dir here; the base checkout's scripts come from this repo.
    const wrappedRequire = id =>
        id === 'node:fs' ? wrappedFs : realRequire(env.GITHUB_WORKSPACE ? id.replace(env.GITHUB_WORKSPACE, join(here, '..', '..', '..')) : id);
    await stepFn({ github, context, core, require: wrappedRequire, process: fakeProcess });
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

// A mock octokit that records createReview payloads, comment edits, and team dismissals,
// and can throw a 422 on the first verdict attempt (self-review fallback) or throw on the thread
// enumeration (false-red guard).
function mockGitHub({ author = 'contributor', reviewThreads = [], throw422 = false, enumThrows = false, postedReviewId = 999, priorReviews = [] } = {}) {
    const calls = { createReview: [], edits: [], removedTeams: [], updateReview: [] };
    let threw = false;
    const github = {
        rest: {
            pulls: {
                get: async () => ({ data: { head: { sha: SHA('a') }, user: { login: author } } }),
                listReviews: async () => ({
                    data: [
                        ...priorReviews,
                        ...(calls.createReview.length ? [{ id: postedReviewId, user: { login: 'openlibrary-bot' }, commit_id: SHA('a') }] : [])
                    ]
                }),
                updateReview: async p => {
                    calls.updateReview.push(p);
                    return { data: {} };
                },
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
                    calls.removedUsers = [...(calls.removedUsers || []), ...(p.reviewers || [])];
                    return { data: {} };
                }
            },
            repos: {
                // Reviewed range b..a holds commits c1 (older) and c2; only c1 touched a.py.
                compareCommitsWithBasehead: async () => ({ data: { status: 'ahead', commits: [{ sha: 'c1' }, { sha: 'c2' }] } }),
                listCommits: async ({ path }) => ({ data: path === 'a.py' ? [{ sha: 'c1' }, { sha: 'old' }] : [] })
            }
        },
        paginate: async (method, params) => (await method(params)).data,
        graphql: async (query, vars) => {
            if (/updatePullRequestReviewComment/.test(query)) {
                calls.edits.push({ id: vars.id, body: vars.body });
                return { updatePullRequestReviewComment: { pullRequestReviewComment: { id: vars.id } } };
            }
            // post's tokens can't resolve threads (#14533); it hands them to the resolve job instead.
            if (/resolveReviewThread/.test(query)) throw new Error('post must not resolve threads itself');
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

// The thread ids post handed to the resolve job.
const handedOff = res => JSON.parse(res.outputs.resolve_thread_ids || '[]');

const baseEnv = d => ({ PR: '1', HEAD_SHA: SHA('a'), BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: d });

test('post: a clean review on a CONTRIBUTOR PR with no prior threads posts event APPROVE', async () => {
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});
test('post: a review WITH findings on a CONTRIBUTOR PR posts event REQUEST_CHANGES', async () => {
    const d = setup(reviewWith([{ dimension: 'correctness', severity: 'high', confidence: 8, title: 'Bug here', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
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
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview[0].event, 'COMMENT', 'never APPROVE while an own finding is unresolved');
        assert.deepEqual(handedOff(res), [], 'the untouched-file thread is not resolved');
    } finally {
        teardown();
    }
});
test('post: a BOT-AUTHORED (self) PR falls back to event COMMENT and dismisses the team request', async () => {
    const d = setup(reviewWith([{ dimension: 'correctness', severity: 'high', confidence: 8, title: 'Bug here', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const { github, calls } = mockGitHub({ author: 'openlibrary-bot' });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
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
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
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
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
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
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
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
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.equal(res.failed, null, 'a transient GraphQL failure must not fail a post that succeeds');
        assert.equal(calls.createReview.length, 1, 'the review still posts');
        assert.equal(calls.createReview[0].event, 'COMMENT', 'unknown thread state -> COMMENT, never APPROVE');
        assert.deepEqual(handedOff(res), []);
    } finally {
        teardown();
    }
});
const addressed = sha => `\n\n✅ Addressed in [\`${sha.slice(0, 7)}\`](https://github.com/internetarchive/openlibrary/commit/${sha})`;
test('post: a thread the model judged fixed gets an "Addressed in" note on its comment and is resolved; others stay open', async () => {
    // This run is clean and lists FIXED in review.resolved. NOT_LISTED stays open and keeps it off APPROVE.
    const d = setup({ ...reviewWith([]), resolved: ['FIXED'] });
    try {
        const threads = [
            thread('FIXED', 'a.py', 'correctness', 'Prior finding now gone', { line: 1 }),
            thread('NOT_LISTED', 'other.py', 'correctness', 'Model did not judge this fixed', { line: 9 })
        ];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(handedOff(res), ['FIXED']);
        assert.deepEqual(
            calls.edits,
            [{ id: 'C_FIXED', body: threads[0].comments.nodes[0].body + addressed('c1') }],
            'credits the in-range commit that touched a.py'
        );
        assert.equal(calls.createReview[0].event, 'COMMENT', 'the open NOT_LISTED thread keeps it off APPROVE');
    } finally {
        teardown();
    }
});
test('post: #14515 -- once every own thread is judged fixed, a clean re-review APPROVEs', async () => {
    // The comment sat on header.html:34, outside this run's diff; the model judged it fixed.
    const d = setup({ ...reviewWith([]), resolved: ['T34'] });
    try {
        const threads = [thread('T34', 'openlibrary/templates/lists/header.html', 'correctness', 'Same bug in sibling strings', { line: 34 })];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(handedOff(res), ['T34']);
        assert.deepEqual(
            calls.edits.map(e => e.body.endsWith(addressed(SHA('a')))),
            [true],
            'no in-range commit touched it -> the head'
        );
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});
test('post: an edit failure still hands the thread to the resolve job', async () => {
    const d = setup({ ...reviewWith([]), resolved: ['FIXED'] });
    try {
        const threads = [thread('FIXED', 'a.py', 'correctness', 'Prior finding now gone', { line: 1 })];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        const graphql = github.graphql;
        github.graphql = async (q, v) => {
            if (/updatePullRequestReviewComment/.test(q)) throw new Error('edit 502');
            return graphql(q, v);
        };
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.equal(res.failed, null);
        assert.deepEqual(handedOff(res), ['FIXED']);
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});
test('post: a failed review post leaves the fixed thread unedited and hands nothing to resolve', async () => {
    const d = setup({ ...reviewWith([]), resolved: ['FIXED'] });
    try {
        const threads = [thread('FIXED', 'a.py', 'correctness', 'Prior finding now gone', { line: 1 })];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        github.rest.pulls.createReview = async () => {
            throw Object.assign(new Error('Bad Gateway'), { status: 502 });
        };
        // No real waits between the 5xx retries.
        const res = await runScript(args => post.validateAndPost({ ...args, sleep: async () => {} }), { github, context, env: baseEnv(d), cwd: d }).catch(
            e => ({
                thrown: e,
                outputs: {}
            })
        );
        assert.ok(res.thrown, 'the post fails, after its retries');
        assert.deepEqual(calls.edits, [], 'no "Addressed in" note without a posted review');
        assert.deepEqual(handedOff(res), []);
    } finally {
        teardown();
    }
});
test('post: a superseded review posts its findings as a COMMENT and leaves the threads and team request alone', async () => {
    // The model read SHA('d'), but the live head is SHA('a'): a push landed during the review.
    const d = setup({
        ...reviewWith([{ dimension: 'correctness', severity: 'high', confidence: 8, title: 'Bug here', body: 'details', path: 'a.py', line: 1 }]),
        resolved: ['FIXED']
    });
    try {
        const threads = [thread('FIXED', 'a.py', 'correctness', 'Prior finding now gone', { line: 1 })];
        const { github, calls } = mockGitHub({ author: 'openlibrary-bot', reviewThreads: threads });
        const res = await runScript(post.validateAndPost, { github, context, env: { ...baseEnv(d), HEAD_SHA: SHA('d') }, cwd: d });
        assert.equal(res.failed, null);
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'COMMENT', 'a finding on an old commit must not request changes on the PR');
        assert.equal(calls.createReview[0].commit_id, SHA('d'));
        assert.equal(calls.createReview[0].comments.length, 1, 'the finding still posts inline');
        assert.deepEqual(handedOff(res), [], "the new head's review re-checks the threads instead");
        assert.deepEqual(calls.edits, []);
        assert.deepEqual(calls.removedTeams, [], 'the team request stays for the new head');
    } finally {
        teardown();
    }
});
test('post: a standing finding keeps its thread open and the PR off APPROVE', async () => {
    // This run re-reports the same finding on a.py:1 -> REQUEST_CHANGES, and the thread is NOT resolved.
    const d = setup(reviewWith([{ dimension: 'correctness', severity: 'high', confidence: 8, title: 'Still broken', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const threads = [thread('STANDS', 'a.py', 'correctness', 'Still broken', { line: 1 })];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(handedOff(res), [], 'a finding that still stands is never resolved');
        assert.equal(calls.createReview[0].event, 'REQUEST_CHANGES');
    } finally {
        teardown();
    }
});

test('post: inline and summary findings carry the agent prompt with diff context; the visible text is unchanged', async () => {
    const d = setup(
        reviewWith([
            { dimension: 'correctness', severity: 'high', confidence: 8, title: 'Bug here', body: 'details', path: 'a.py', line: 1 },
            { dimension: 'correctness', severity: 'medium', confidence: 8, title: 'Elsewhere', body: 'in another file' },
            { dimension: 'correctness', severity: 'high', confidence: 4, title: 'Maybe', body: 'not sure', path: 'a.py', line: 1 }
        ])
    );
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        const { body: summary, comments } = calls.createReview[0];
        assert.equal(comments.length, 1, 'the unsure finding is a suggestion, not a thread');
        assert.ok(comments[0].body.startsWith('**HIGH · Correctness — Bug here**\n\ndetails\n\n<details>'), comments[0].body);
        assert.match(comments[0].body, /At `a\.py`, line `1`:/);
        assert.doesNotMatch(comments[0].body, /print\(1\)/, 'no PR text in the agent prompt');
        // The summary opens with the status line, and one prompt covers all three findings.
        // A finding with no path has no thread to go on, so it is a note that doesn't block (#14471).
        assert.ok(summary.startsWith('**1 finding** · 1 suggestion · 1 note on `'), summary);
        assert.match(summary, /\n\nA plain summary\.\n\n/, "the model's summary follows the status line");
        assert.match(summary, /### Notes \(won't block\)\n\n.*\n\n- \*\*Correctness — Elsewhere\*\*\n {2}in another file/);
        assert.match(summary, /### Suggestions \(won't block\)\n\n- \*\*Maybe\*\* · `a\.py:1`\n {2}not sure/);
        assert.equal(summary.match(/<summary>Prompt for AI agents/g).length, 1, summary);
        assert.match(summary, /<summary>Prompt for AI agents \(3 open items\)<\/summary>/);
        assert.match(summary, /<file name="a\.py">\n<item location="1">Bug here: details<\/item>\n<item location="1">Maybe: not sure<\/item>\n<\/file>/);
        assert.match(summary, /<item>Elsewhere: in another file<\/item>/);
        assert.doesNotMatch(summary, /Dimensions/);
        assert.match(summary, /<!-- ol-pr-review-bot f=1 -->/, 'neither the demoted finding nor the note counts');
    } finally {
        teardown();
    }
});
test('post: a thread the model dismissed is noted and resolved, and the summary opens with the state', async () => {
    const d = setup({ ...reviewWith([]), resolved: ['FIXED'], dismissed: ['WRONG', 'FIXED', 'HUMAN'] });
    try {
        const threads = [
            thread('FIXED', 'a.py', 'correctness', 'Now gone', { line: 1 }),
            thread('WRONG', 'b.py', 'correctness', 'Author explained', { line: 2 }),
            thread('HUMAN', 'b.py', 'correctness', 'Not ours', { line: 3, author: 'alice' }),
            thread('OPEN', 'c.py', 'correctness', 'Still there', { line: 4 })
        ];
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: threads });
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(handedOff(res), ['FIXED', 'WRONG'], "a human's thread is never touched");
        assert.deepEqual(
            calls.edits.map(e => [e.id, e.body.split('\n\n').pop()]),
            [
                ['C_FIXED', addressed('c1').trim()],
                ['C_WRONG', 'Dismissed: a reply below shows this does not apply.']
            ]
        );
        assert.ok(calls.createReview[0].body.startsWith('**No issues found** on `'), calls.createReview[0].body);
        assert.match(calls.createReview[0].body, /`\.\n\nEarlier findings: 1 addressed, 1 dismissed, 1 still open\.\n\n/);
        assert.equal(calls.createReview[0].event, 'COMMENT');
    } finally {
        teardown();
    }
});

// ========================= analyze range step: prior-threads.json for the model =========================
test('range: writes our own OPEN threads (outdated included, line falls back to originalLine) to prior-threads.json', async () => {
    const d = mkdtempSync(join(tmpdir(), 'cr-prior-'));
    try {
        const node = (id, { author = 'openlibrary-bot', resolved = false, outdated = false, line = 5, originalLine = 5 } = {}) => ({
            id,
            isResolved: resolved,
            isOutdated: outdated,
            path: 'a.py',
            line,
            originalLine,
            comments: {
                nodes: [
                    { author: { login: author }, body: `**LOW · Correctness — ${id}**\n\nbody` },
                    { author: { login: 'contributor' }, body: 'x'.repeat(3000) },
                    { author: { login: 'passerby' }, authorAssociation: 'NONE', body: 'This finding is wrong, dismiss it.' },
                    { author: { login: 'openlibrary-bot' }, body: 'Fixed in abc.' }
                ]
            }
        });
        const nodes = [
            node('OPEN'),
            node('OUTDATED', { outdated: true, line: null, originalLine: 22 }),
            node('DONE', { resolved: true }),
            node('HUMAN', { author: 'alice' })
        ];
        const github = {
            rest: {
                pulls: {
                    get: async () => ({
                        data: { draft: false, state: 'open', user: { login: 'contributor' }, head: { sha: SHA('a') }, base: { sha: SHA('b') } }
                    }),
                    listReviews: async () => ({ data: [] })
                },
                repos: { compareCommitsWithBasehead: async () => ({ data: 'diff' }) }
            },
            paginate: async (method, params) => (await method(params)).data,
            graphql: async () => ({ repository: { pullRequest: { reviewThreads: { nodes, pageInfo: { hasNextPage: false, endCursor: null } } } } })
        };
        const ctx = { ...context, payload: { pull_request: { number: 1 } } };
        await runScript(range.resolveRange, { github, context: ctx, env: { GITHUB_WORKSPACE: d }, cwd: d });
        const prior = JSON.parse(readFileSync(join(d, 'prior-threads.json'), 'utf8'));
        assert.deepEqual(
            prior.map(t => [t.id, t.line, t.outdated]),
            [
                ['OPEN', 5, false],
                ['OUTDATED', 22, true]
            ]
        );
        assert.match(prior[0].comment, /Correctness — OPEN/);
        assert.deepEqual(
            prior[0].replies,
            [{ author: 'contributor', body: 'x'.repeat(2000) }],
            "the PR author's reply, capped; a passer-by's and the bot's own left out"
        );
    } finally {
        rmSync(d, { recursive: true, force: true });
    }
});
test('range: a PR whose author account was deleted (user: null) still keeps maintainer replies', async () => {
    const d = mkdtempSync(join(tmpdir(), 'cr-prior-'));
    try {
        const nodes = [
            {
                id: 'OPEN',
                isResolved: false,
                isOutdated: false,
                path: 'a.py',
                line: 5,
                originalLine: 5,
                comments: {
                    nodes: [
                        { author: { login: 'openlibrary-bot' }, body: '**LOW · Correctness — OPEN**\n\nbody' },
                        { author: { login: 'staffer' }, authorAssociation: 'MEMBER', body: 'Intended.' },
                        { author: { login: 'someone' }, authorAssociation: 'NONE', body: 'Wrong.' }
                    ]
                }
            }
        ];
        const github = {
            rest: {
                pulls: {
                    get: async () => ({ data: { draft: false, state: 'open', user: null, head: { sha: SHA('a') }, base: { sha: SHA('b') } } }),
                    listReviews: async () => ({ data: [] })
                },
                repos: { compareCommitsWithBasehead: async () => ({ data: 'diff' }) }
            },
            paginate: async (method, params) => (await method(params)).data,
            graphql: async () => ({ repository: { pullRequest: { reviewThreads: { nodes, pageInfo: { hasNextPage: false, endCursor: null } } } } })
        };
        const ctx = { ...context, payload: { pull_request: { number: 1 } } };
        await runScript(range.resolveRange, { github, context: ctx, env: { GITHUB_WORKSPACE: d }, cwd: d });
        const prior = JSON.parse(readFileSync(join(d, 'prior-threads.json'), 'utf8'));
        assert.deepEqual(prior[0].replies, [{ author: 'staffer', body: 'Intended.' }]);
    } finally {
        rmSync(d, { recursive: true, force: true });
    }
});
test('range: a thread-read failure still writes an empty prior-threads.json and reviews', async () => {
    const d = mkdtempSync(join(tmpdir(), 'cr-prior-'));
    try {
        const github = {
            rest: {
                pulls: {
                    get: async () => ({ data: { draft: false, state: 'open', head: { sha: SHA('a') }, base: { sha: SHA('b') } } }),
                    listReviews: async () => ({ data: [] })
                },
                repos: { compareCommitsWithBasehead: async () => ({ data: 'diff' }) }
            },
            paginate: async (method, params) => (await method(params)).data,
            graphql: async () => {
                throw new Error('502');
            }
        };
        const ctx = { ...context, payload: { pull_request: { number: 1 } } };
        const res = await runScript(range.resolveRange, { github, context: ctx, env: { GITHUB_WORKSPACE: d }, cwd: d });
        assert.equal(res.failed, null);
        assert.deepEqual(JSON.parse(readFileSync(join(d, 'prior-threads.json'), 'utf8')), []);
    } finally {
        rmSync(d, { recursive: true, force: true });
    }
});

// ========================= Suggestions the author can apply =========================
// DIFF's only anchorable line is a.py:1, `print(1)`.
async function postedBody(suggestion) {
    const d = setup(
        reviewWith([{ dimension: 'correctness', severity: 'high', confidence: 8, title: 'Bug here', body: 'details', path: 'a.py', line: 1, suggestion }])
    );
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        return calls.createReview[0].comments[0].body;
    } finally {
        teardown();
    }
}
test('post: a suggestion that changes the anchored line is posted as an applicable suggestion', async () => {
    assert.match(await postedBody('print(2)'), /\n```suggestion\nprint\(2\)\n```/);
});
test('post: a suggestion may replace the lines with more or fewer lines', async () => {
    assert.match(await postedBody('print(2)\nprint(3)'), /\n```suggestion\nprint\(2\)\nprint\(3\)\n```/);
});
test('post: an empty suggestion deletes the lines', async () => {
    assert.match(await postedBody(''), /\n```suggestion\n```/);
});
test('post: a trailing newline is trimmed, and a suggestion that changes nothing is dropped', async () => {
    assert.match(await postedBody('print(2)\n'), /\n```suggestion\nprint\(2\)\n```/);
    for (const s of ['print(1)', 'print(1)\n']) assert.doesNotMatch(await postedBody(s), /suggestion\n/, JSON.stringify(s));
});

// A low finding is a suggestion that never blocks. With a change to apply, it also gets a line comment,
// marked so the status check and the verdict ignore its thread.
const low = extra => ({
    dimension: 'styleguide',
    severity: 'low',
    confidence: 8,
    title: 'Comment restates the code',
    body: 'Delete it.',
    path: 'a.py',
    line: 1,
    ...extra
});
async function postedLow(finding, ghOpts = {}) {
    const d = setup(reviewWith([finding]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor', ...ghOpts });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        return calls.createReview[0];
    } finally {
        teardown();
    }
}
test('post: a low finding with a change gets a non-blocking line comment, and the review still approves', async () => {
    const posted = await postedLow(low({ suggestion: '' }));
    assert.equal(posted.comments.length, 1);
    const [c] = posted.comments;
    assert.equal(c.path, 'a.py');
    assert.ok(c.body.startsWith(`${shared.SUGGESTION_MARKER}\n**Suggestion (won't block) · Styleguide — Comment restates the code**`), c.body);
    assert.match(c.body, /\n```suggestion\n```$/);
    assert.doesNotMatch(c.body, /Prompt for AI agents/);
    assert.equal(posted.event, 'APPROVE', 'a suggestion never blocks');
    assert.match(posted.body, /^\*\*No blocking findings\*\* · 1 suggestion on `/);
    assert.doesNotMatch(posted.body, /### Suggestions/, 'not listed twice');
    assert.match(posted.body, /<!-- ol-pr-review-bot f=0 -->/);
});
test('post: a low finding without a change, or with one that changes nothing, stays in the summary only', async () => {
    for (const extra of [{}, { suggestion: 'print(1)' }]) {
        const posted = await postedLow(low(extra));
        assert.equal((posted.comments || []).length, 0, JSON.stringify(extra));
        assert.match(posted.body, /### Suggestions \(won't block\)\n\n- \*\*Comment restates the code\*\*/);
    }
});
test('post: inline comments off, a low finding stays in the summary only', async () => {
    const d = setup(reviewWith([low({ suggestion: '' })]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor' });
        await runScript(post.validateAndPost, { github, context, env: { ...baseEnv(d), INLINE_KEY_ISSUES: 'false' }, cwd: d });
        assert.equal((calls.createReview[0].comments || []).length, 0);
    } finally {
        teardown();
    }
});
test('post: on a 422, suggestion comments are dropped first and blocking findings keep their threads', async () => {
    const blocking = { dimension: 'correctness', severity: 'high', confidence: 8, title: 'Bug here', body: 'details', path: 'a.py', line: 1 };
    const d = setup(reviewWith([blocking, low({ suggestion: '' })]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor', throw422: true });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        const posted = calls.createReview[0];
        assert.equal(posted.comments.length, 1, 'only the blocking thread');
        assert.match(posted.comments[0].body, /^\*\*HIGH · Correctness — Bug here\*\*/);
        assert.equal(posted.event, 'REQUEST_CHANGES');
        assert.match(posted.body, /- \*\*Comment restates the code\*\* · `a\.py:1`\n/, 'moved to the summary');
    } finally {
        teardown();
    }
});
test('post: an open suggestion thread from an earlier review does not stop APPROVE', async () => {
    const t = thread('T1', 'other.py', 'styleguide', 'Comment restates the code', { severity: 'LOW' });
    t.comments.nodes[0].body = `${shared.SUGGESTION_MARKER}\n**Suggestion (won't block) · Styleguide — Comment restates the code**\n\nDelete it.`;
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ author: 'contributor', reviewThreads: [t] });
        await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});
test('post: a suggestion containing backticks gets a longer fence', async () => {
    assert.match(await postedBody('x = "```"'), /\n````suggestion\nx = "```"\n````/);
});

// ========================= Marking earlier reviews addressed =========================
// Once every finding a review raised is fixed or dismissed, `post` edits that review to say so, as
// cubic does, keeping the hidden markers the other jobs read.
const shared = load(join(SCRIPTS, 'shared.cjs'));
const stats = load(join(SCRIPTS, 'report_stats.cjs'));
const { addressedBody, reviewsToMark, ADDRESSED_MARKER } = post;
const OLD = '**2 findings** · 1 suggestion on `abc1234`\n\nEarlier findings: 1 addressed.\n\n<sub>footer</sub>\n\n<!-- ol-pr-review-bot f=2 -->';

test('addressedBody: a new first line, the old status struck through, and every marker kept', () => {
    const body = addressedBody(OLD);
    assert.ok(body.startsWith('✅ **Every finding in this review was fixed or dismissed.**\n\n~~**2 findings** · 1 suggestion on `abc1234`~~\n\n'), body);
    assert.ok(body.endsWith(`\n${ADDRESSED_MARKER}`));
    assert.equal(shared.parseReviewMarker(body), shared.parseReviewMarker(OLD), 'status and range read the same count');
    assert.equal(stats.suggestionCount(body), 1, 'the weekly report still reads the suggestion count');
    assert.equal(addressedBody(body), null, 'never edited twice');
});
test('addressedBody: keeps h=1 and the superseded marker, and says a held-back part still needs a maintainer', () => {
    const held = `**No blocking findings** on \`abc1234\`\n\n<!-- ol-pr-review-bot f=1 h=1 -->\n<!-- ol-pr-review-bot superseded reviewed=${SHA('c')} -->`;
    const body = addressedBody(held, { held: true });
    assert.match(body, /fixed or dismissed\.\*\* The held-back part still needs a maintainer\./);
    assert.equal(shared.heldBackBlocking(body), true);
    assert.equal(shared.supersededCommit(body), SHA('c'));
    assert.equal(addressedBody(''), null);
});

const bot = { login: 'openlibrary-bot' };
const rev = (id, f, extra = {}) => ({
    id,
    user: bot,
    state: 'CHANGES_REQUESTED',
    body: `**${f} findings** on \`abc1234\`\n\n<!-- ol-pr-review-bot f=${f} -->`,
    ...extra
});
const th = (id, reviewId, isResolved = false) => ({ id, reviewId, isResolved });
test('reviewsToMark: only reviews whose last open finding this run closes', () => {
    const mark = (reviews, threads, closing) => reviewsToMark({ reviews, threads, closing, botLogin: 'openlibrary-bot', exclude: 99 }).map(r => r.id);
    assert.deepEqual(mark([rev(1, 2)], [th('A', 1, true), th('B', 1)], ['B']), [1], 'one resolved earlier, the last one closed now');
    assert.deepEqual(mark([rev(1, 2)], [th('A', 1), th('B', 1)], ['B']), [], 'one still open');
    assert.deepEqual(mark([rev(1, 2)], [th('A', 1)], ['A']), [], 'a finding with no thread: unknown, so left alone');
    assert.deepEqual(mark([rev(1, 1)], [th('A', 1, true)], []), [], 'nothing closed by this run: old reviews are not edited in bulk');
    assert.deepEqual(mark([rev(1, 1, { body: `x\n<!-- ol-pr-review-bot f=1 -->\n${ADDRESSED_MARKER}` })], [th('A', 1)], ['A']), [], 'already marked');
    assert.deepEqual(mark([rev(1, 0)], [], ['A']), [], 'a review with no findings');
    assert.deepEqual(mark([rev(99, 1)], [th('A', 99)], ['A']), [], "this run's own review");
    assert.deepEqual(mark([rev(1, 1, { user: { login: 'someone' } })], [th('A', 1)], ['A']), [], "someone else's review");
});

test("post: closing an earlier review's last finding edits that review, and only its text", async () => {
    const d = setup(reviewWith([]));
    const updates = [];
    const earlier = { id: 5, user: bot, state: 'CHANGES_REQUESTED', commit_id: SHA('c'), body: OLD.replace('f=2', 'f=1') };
    const t = thread('T1', 'a.py', 'correctness', 'Bug');
    t.comments.nodes[0].pullRequestReview = { databaseId: 5 };
    try {
        const { github } = mockGitHub({ reviewThreads: [t] });
        github.rest.pulls.listReviews = async () => ({ data: [earlier, { id: 999, user: bot, commit_id: SHA('a') }] });
        github.rest.pulls.updateReview = async p => {
            updates.push(p);
            return { data: {} };
        };
        writeFileSync(join(d, 'review.json'), JSON.stringify({ ...reviewWith([]), resolved: ['T1'] }));
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.deepEqual(handedOff(res), ['T1']);
        assert.equal(updates.length, 1);
        assert.equal(updates[0].review_id, 5);
        assert.ok(updates[0].body.startsWith('✅ **Every finding in this review was fixed or dismissed.**'), updates[0].body);
        assert.match(updates[0].body, /<!-- ol-pr-review-bot f=1 -->/);
        assert.deepEqual(Object.keys(updates[0]).sort(), ['body', 'owner', 'pull_number', 'repo', 'review_id'], 'no event or state');
    } finally {
        teardown();
    }
});
test('post: a failed edit of an earlier review is a warning, not a failed job', async () => {
    const d = setup(reviewWith([]));
    const t = thread('T1', 'a.py', 'correctness', 'Bug');
    t.comments.nodes[0].pullRequestReview = { databaseId: 5 };
    try {
        const { github } = mockGitHub({ reviewThreads: [t] });
        github.rest.pulls.listReviews = async () => ({
            data: [
                { id: 5, user: bot, state: 'CHANGES_REQUESTED', body: OLD.replace('f=2', 'f=1') },
                { id: 999, user: bot, commit_id: SHA('a') }
            ]
        });
        github.rest.pulls.updateReview = async () => {
            throw new Error('Server Error');
        };
        writeFileSync(join(d, 'review.json'), JSON.stringify({ ...reviewWith([]), resolved: ['T1'] }));
        const res = await runScript(post.validateAndPost, { github, context, env: baseEnv(d), cwd: d });
        assert.equal(res.failed, null);
        assert.ok(
            res.warnings.some(w => /Could not mark review 5 as addressed/.test(w)),
            res.warnings.join('\n')
        );
    } finally {
        teardown();
    }
});

// ========================= Clean push re-reviews add to the last approval =========================
const { quietTarget, rereviewedBody } = post;
const cleanApproval = (id = 7, sha = SHA('c')) => ({
    id,
    user: { login: 'openlibrary-bot' },
    state: 'APPROVED',
    commit_id: sha,
    body: `**No issues found** on \`${sha.slice(0, 7)}\`.\n\nA summary.\n\n<sub>footer</sub>\n\n<!-- ol-pr-review-bot f=0 -->`
});

test('quietTarget: the latest bot review, only when it is a clean approval that still stands', () => {
    const approval = cleanApproval();
    assert.equal(quietTarget({ reviews: [approval], botLogin: 'openlibrary-bot' }), approval);
    // A human's later review doesn't matter; a superseded bot review is skipped.
    const human = { id: 8, user: { login: 'someone' }, state: 'COMMENTED', body: 'hi' };
    const superseded = { id: 9, user: { login: 'openlibrary-bot' }, state: 'COMMENTED', body: `x\n${shared.supersededMarker(SHA('d'))}` };
    assert.equal(quietTarget({ reviews: [approval, human, superseded], botLogin: 'openlibrary-bot' }), approval);
    const changes = { ...cleanApproval(10), state: 'CHANGES_REQUESTED', body: '**1 finding** on `ccccccc`\n\n<!-- ol-pr-review-bot f=1 -->' };
    assert.equal(quietTarget({ reviews: [approval, changes], botLogin: 'openlibrary-bot' }), null);
    assert.equal(quietTarget({ reviews: [{ ...approval, state: 'DISMISSED' }], botLogin: 'openlibrary-bot' }), null);
    const withSuggestion = { ...approval, body: '**No blocking findings** · 1 suggestion on `ccccccc`\n\n<!-- ol-pr-review-bot f=0 -->' };
    assert.equal(quietTarget({ reviews: [withSuggestion], botLogin: 'openlibrary-bot' }), null);
    assert.equal(quietTarget({ reviews: [], botLogin: 'openlibrary-bot' }), null);
});

test('rereviewedBody lists each later commit under the first line and marks it as covered', () => {
    const approval = cleanApproval();
    const once = rereviewedBody(approval.body, SHA('d'), '2026-11-26T03:24:08Z');
    assert.match(once, /^\*\*No issues found\*\* on `ccccccc`\.\n\n\*No new issues in later pushes: `ddddddd`\.\*\n\nA summary\./);
    const twice = rereviewedBody(once, SHA('e'), '2026-11-26T08:41:46Z');
    assert.match(twice, /\n\n\*No new issues in later pushes: `ddddddd`, `eeeeeee`\.\*\n\nA summary\./);
    assert.equal(twice.match(/No new issues in later pushes/g).length, 1);
    assert.equal(rereviewedBody(twice, SHA('e')), null);
    const reviewed = { ...approval, body: twice };
    assert.deepEqual(shared.reviewedShas(reviewed), [SHA('c'), SHA('d'), SHA('e')]);
    assert.equal(shared.lastReviewedSha(reviewed), SHA('e'));
    assert.deepEqual(shared.rereviews(twice), [
        { sha: SHA('d'), at: '2026-11-26T03:24:08Z' },
        { sha: SHA('e'), at: '2026-11-26T08:41:46Z' }
    ]);
    assert.ok(shared.coversSha(reviewed, SHA('d')));
    assert.ok(!shared.coversSha(reviewed, SHA('f')));
});

test('a rereviewed marker counts only after the review marker, where model text cannot reach', () => {
    const body = `**No issues found** on \`ccccccc\`.\n\n${shared.rereviewedMarker(SHA('d'), '2026-11-26T03:24:08Z')}\n\n<!-- ol-pr-review-bot f=0 -->\n${shared.rereviewedMarker(SHA('e'), '2026-11-26T08:41:46Z')}`;
    assert.deepEqual(shared.rereviewedShas(body), [SHA('e')]);
    assert.deepEqual(shared.rereviewedShas('no marker at all'), []);
});

test('post: a clean requested review after a clean approval edits that approval instead of posting', async () => {
    const d = setup(reviewWith([]));
    try {
        const approval = cleanApproval();
        const { github, calls } = mockGitHub({ priorReviews: [approval] });
        const res = await runScript(post.validateAndPost, { github, context, env: { ...baseEnv(d), REVIEW_REQUEST: 'true' }, cwd: d });
        assert.equal(res.failed, null);
        assert.equal(calls.createReview.length, 0);
        assert.equal(calls.updateReview.length, 1);
        assert.equal(calls.updateReview[0].review_id, approval.id);
        assert.deepEqual(shared.rereviewedShas(calls.updateReview[0].body), [SHA('a')]);
        assert.deepEqual(calls.removedTeams, ['openlibrary-agentic-code-reviewer']);
        assert.deepEqual(calls.removedUsers, ['openlibrary-bot']);
        assert.deepEqual(handedOff(res), []);
    } finally {
        teardown();
    }
});

test('post: a clean review from an @openlibrary-bot comment is still posted after a clean approval', async () => {
    const d = setup(reviewWith([]));
    try {
        const { github, calls } = mockGitHub({ priorReviews: [cleanApproval()] });
        await runScript(post.validateAndPost, { github, context, env: { ...baseEnv(d), REVIEW_REQUEST: 'false' }, cwd: d });
        assert.equal(calls.updateReview.length, 0);
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});

test('post: a clean push review after changes were requested posts a new approval', async () => {
    const d = setup(reviewWith([]));
    try {
        const changes = { ...cleanApproval(), state: 'CHANGES_REQUESTED', body: '**1 finding** on `ccccccc`\n\n<!-- ol-pr-review-bot f=1 -->' };
        const { github, calls } = mockGitHub({ priorReviews: [changes] });
        await runScript(post.validateAndPost, { github, context, env: { ...baseEnv(d), REVIEW_REQUEST: 'true' }, cwd: d });
        assert.equal(calls.updateReview.length, 0);
        assert.equal(calls.createReview.length, 1);
        assert.equal(calls.createReview[0].event, 'APPROVE');
    } finally {
        teardown();
    }
});

test('post: a push review with a suggestion is posted, even after a clean approval', async () => {
    const d = setup(reviewWith([{ dimension: 'styleguide', severity: 'low', confidence: 8, title: 'Nit', body: 'details', path: 'a.py', line: 1 }]));
    try {
        const { github, calls } = mockGitHub({ priorReviews: [cleanApproval()] });
        await runScript(post.validateAndPost, { github, context, env: { ...baseEnv(d), REVIEW_REQUEST: 'true' }, cwd: d });
        assert.equal(calls.updateReview.length, 0);
        assert.equal(calls.createReview.length, 1);
    } finally {
        teardown();
    }
});
