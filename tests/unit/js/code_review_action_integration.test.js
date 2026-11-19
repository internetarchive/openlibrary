// End-to-end tests of the code review steps: each step's module function is called the way its
// github-script step calls it, against a mock GitHub that records the API calls. Workflow changes
// only run after merge (pull_request_target runs the base branch's copy), so these are the
// closest pre-merge check.
import { test, beforeEach, afterEach } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, '..', '..', '..');
const WF = join(ROOT, '.github', 'workflows', 'code_review_action.yml');
const workflow = yaml.load(readFileSync(WF, 'utf8'));
const SCRIPTS = join(ROOT, '.github', 'scripts', 'code_review');
const load = createRequire(import.meta.url);
const range = load(join(SCRIPTS, 'range.cjs'));
const analyzeGate = load(join(SCRIPTS, 'analyze_gate.cjs'));
const post = load(join(SCRIPTS, 'post.cjs'));
const pending = load(join(SCRIPTS, 'pending.cjs'));
const status = load(join(SCRIPTS, 'status.cjs'));

// Run a step function with injected globals, as the workflow's github-script step does.
// `cwd` redirects the step's relative fs paths (review.json, review.diff) into the temp dir, since
// vitest workers can't process.chdir().
async function runScript(stepFn, { github, context, env, cwd }) {
    const recorded = { outputs: {}, failed: null, summary: '', warnings: [] };
    const core = {
        summary: {
            addRaw(text) {
                recorded.summary += text;
                return this;
            },
            write: async () => {}
        },
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
    const wrappedFs = cwd
        ? new Proxy(realFs, {
              get(target, prop) {
                  if (prop === 'readFileSync') return (p, ...a) => target.readFileSync(resolve(p), ...a);
                  if (prop === 'writeFileSync') return (p, ...a) => target.writeFileSync(resolve(p), ...a);
                  if (prop === 'existsSync') return p => target.existsSync(resolve(p));
                  return target[prop];
              }
          })
        : realFs;
    // GITHUB_WORKSPACE is a temp dir here; the base checkout's scripts come from this repo.
    const wrappedRequire = id =>
        id === 'fs' ? wrappedFs : realRequire(env.GITHUB_WORKSPACE ? id.replace(env.GITHUB_WORKSPACE, join(here, '..', '..', '..')) : id);
    await stepFn({ github, context, core, require: wrappedRequire, process: fakeProcess });
    return { ...recorded, core };
}

// A minimal octokit mock. Each test overrides the handlers it needs; calls are recorded.
function mockGitHub(handlers = {}) {
    const calls = { createReview: [], createCommitStatus: [] };
    const h = {
        prGet: async () => ({ data: { number: 1, head: { sha: 'a'.repeat(40) }, base: { sha: 'b'.repeat(40) }, draft: false, state: 'open' } }),
        listReviews: async () => ({ data: [] }),
        listStatuses: async () => ({ data: [] }),
        reviewThreads: [],
        ...handlers
    };
    const github = {
        rest: {
            pulls: {
                get: async p => h.prGet(p),
                listReviews: async p => h.listReviews(p),
                createReview: async p => {
                    calls.createReview.push(p);
                    return { data: { id: 999 } };
                }
            },
            repos: {
                listCommitStatusesForRef: async p => h.listStatuses(p),
                createCommitStatus: async p => {
                    calls.createCommitStatus.push(p);
                    return { data: {} };
                },
                compareCommitsWithBasehead: async () => ({ data: { status: 'ahead', files: [{}] } })
            }
        },
        paginate: async (method, params) => (await method(params)).data,
        graphql: async () => ({
            repository: { pullRequest: { reviewThreads: { nodes: h.reviewThreads, pageInfo: { hasNextPage: false, endCursor: null } } } }
        })
    };
    return { github, calls };
}

const context = {
    repo: { owner: 'internetarchive', repo: 'openlibrary' },
    eventName: 'pull_request_target',
    payload: {},
    runId: 1,
    serverUrl: 'https://github.com'
};
const SHA = c => c.repeat(40);
const cleanReview = () => ({
    summary: 'A plain summary with nothing sensitive.',
    dimensions: {
        correctness: { status: 'none', note: 'ok' },
        security: { status: 'none', note: 'ok' },
        accessibility: { status: 'none', note: 'ok' },
        test_coverage: { status: 'none', note: 'ok' },
        styleguide: { status: 'none', note: 'ok' }
    },
    findings: []
});

let dir;
beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'cr14476-'));
});
afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
});

// ===================== A push mid-run: the review posts on its own commit, as a COMMENT, and sets no verdict =====================
test('D1 post: head UNCHANGED -> createReview IS called', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    // post reads review.json/review.diff from cwd; run with cwd = dir.
    await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(calls.createReview.length, 1, 'a review on the still-current head must post');
    assert.equal(calls.createReview[0].commit_id, head);
});
test('D1 post: head MOVED -> the review posts on the commit it read, as a COMMENT, saying so', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const pinned = SHA('a'),
        live = SHA('c');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: live } } }),
        // The posted review, so post's check that it landed passes.
        listReviews: async () => ({ data: [{ id: 999 }] })
    });
    const env = { PR: '1', HEAD_SHA: pinned, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    const res = await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(res.failed, null, 'it exits cleanly, not failed');
    assert.equal(calls.createReview.length, 1, 'the feedback is not thrown away');
    const r = calls.createReview[0];
    assert.equal(r.commit_id, pinned, 'pinned to the commit the model read, never the live head');
    assert.equal(r.event, 'COMMENT', 'a clean review of an old commit must not APPROVE the PR');
    assert.ok(r.body.startsWith(`*This review is of \`${pinned.slice(0, 7)}\`. \`${live.slice(0, 7)}\` was pushed while it ran`), r.body);
    assert.ok(r.body.endsWith(`<!-- ol-pr-review-bot superseded reviewed=${pinned} -->`), 'marked superseded, naming the commit it read');
});
test('D1 post: head MOVED by a force-push -> nothing is posted, since the reviewed commit left the PR', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const pinned = SHA('a'),
        live = SHA('c');
    for (const compare of [async () => ({ data: { status: 'diverged' } }), async () => Promise.reject(new Error('No common ancestor'))]) {
        const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: live } } }) });
        github.rest.repos.compareCommitsWithBasehead = compare;
        const env = { PR: '1', HEAD_SHA: pinned, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
        const res = await runScript(post.validateAndPost, { github, context, env, cwd: dir });
        assert.equal(res.failed, null, 'a clean exit, not a failed job');
        assert.equal(calls.createReview.length, 0);
    }
});
test('D1 status: head MOVED -> no verdict, only a pending "superseded" status on the reviewed SHA', async () => {
    const pinned = SHA('a'),
        live = SHA('c');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: live } } }) });
    const env = {
        PR: '1',
        HEAD_SHA: pinned,
        POST_RESULT: 'success',
        PUBLIC_FINDINGS_COUNT: '0',
        WITHHELD: 'false',
        WITHHELD_BLOCKING: 'false',
        REPOST: 'false',
        RUN_URL: 'u'
    };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].sha, pinned);
    assert.equal(calls.createCommitStatus[0].state, 'pending', 'no pass/fail verdict when the reviewed SHA is no longer the head');
    assert.match(calls.createCommitStatus[0].description, /^Superseded by ccccccc/);
});
test('D1 status: head UNCHANGED + clean + a review actually posted -> success on the reviewed SHA', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        // A bot review actually exists on this exact head (post really posted it).
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'x\n<!-- ol-pr-review-bot f=0 -->' }] })
    });
    const env = {
        PR: '1',
        HEAD_SHA: head,
        POST_RESULT: 'success',
        PUBLIC_FINDINGS_COUNT: '0',
        WITHHELD: 'false',
        WITHHELD_BLOCKING: 'false',
        REPOST: 'false',
        RUN_URL: 'u'
    };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].sha, head);
    assert.equal(calls.createCommitStatus[0].state, 'success');
});
test('D1 status FALSE-GREEN guard: POST_RESULT=success but NO review on this head (force-push revert) -> NOT success', async () => {
    // `post` succeeds without posting when the head moved. If the head then moves back to the
    // reviewed SHA, the status must still not pass unless a bot review exists on it.
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [] }) // post did NOT post a review on this head this run
    });
    const env = {
        PR: '1',
        HEAD_SHA: head,
        POST_RESULT: 'success',
        PUBLIC_FINDINGS_COUNT: '0',
        WITHHELD: 'false',
        WITHHELD_BLOCKING: 'false',
        REPOST: 'false',
        RUN_URL: 'u'
    };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.notEqual(calls.createCommitStatus[0].state, 'success', 'a head with no posted review must never read success');
});

// ===================== Already reviewed: skip or repost the status =====================
test('D2 range: already-reviewed head WITH a MATCHING code-review status -> skip', async () => {
    // Skip when the present status matches the verdict: a clean review and a present `success`.
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01', body: 'ok\n<!-- ol-pr-review-bot f=0 -->' }]
        }),
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'success' }] }),
        reviewThreads: []
    });
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, eventName: 'pull_request_target', payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'true', 'a reviewed head whose status matches the verdict is skipped');
});
// A stale status on an already-reviewed head must be re-posted, not skipped.
test('D2 range STATE-AWARE: reviewed head + STALE failure status + now-clean verdict -> repost (NOT skip)', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        // The existing review is clean: marker f=0 and no unresolved threads -> implied verdict success.
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01', body: 'clean\n<!-- ol-pr-review-bot f=0 -->' }]
        }),
        // ...but the present status is a stale `failure` ("No clean review for this commit").
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'failure' }] }),
        reviewThreads: []
    });
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'false', 'a head on a status that contradicts its review must NOT be skipped');
    assert.equal(res.outputs.repost, 'true', 'it routes to an idempotent status repost (no model re-run)');
    assert.equal(res.outputs.head_sha, head);
});
test('D2 range STATE-AWARE: reviewed head + status already MATCHING (failure for f=2) -> skip', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        // The review has findings (marker f=2) -> implied verdict failure, and the present status is
        // already failure -> they match -> skip (no wasted repost).
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01', body: 'has findings\n<!-- ol-pr-review-bot f=2 -->' }]
        }),
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'failure' }] }),
        reviewThreads: []
    });
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'true', 'a reviewed head whose failure status matches its findings is skipped');
});
test('D2 range STATE-AWARE: reviewed head (clean f=0) but an UNRESOLVED thread + present success -> repost', async () => {
    // The marker says 0 findings, but a live unresolved+current thread means the implied verdict is
    // failure; a present `success` contradicts it and must be corrected, mirroring the status job.
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01', body: 'clean marker\n<!-- ol-pr-review-bot f=0 -->' }]
        }),
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'success' }] }),
        reviewThreads: [{ isResolved: false, isOutdated: false }]
    });
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'false', 'an unresolved thread makes success stale -> not skipped');
    assert.equal(res.outputs.repost, 'true');
});
test('D2 range: already-reviewed head with NO code-review status -> repost (not skip)', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01' }] }),
        listStatuses: async () => ({ data: [{ context: 'ci/other', state: 'success' }] }) // NO code-review
    });
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'false', 'a stranded head must NOT be skipped');
    assert.equal(res.outputs.repost, 'true', 'it routes to a status repost');
    assert.equal(res.outputs.head_sha, head);
});
test('D2 status repost: reconstructs SUCCESS from an f=0 marker, no model', async () => {
    const head = SHA('a');
    const body = 'summary\n<!-- ol-pr-review-bot f=0 -->';
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body }] }),
        reviewThreads: []
    });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', REPOST: 'true', RUN_URL: 'u' };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].state, 'success', 'a clean reviewed head reposts as success');
});
// A review posted after the PR moved on carries a superseded marker naming the commit it read. Even if
// GitHub recorded it on the head, it must never count as the head's review or verdict.
const supersededBody = (sha, f = 0) => `summary\n<!-- ol-pr-review-bot f=${f} -->\n<!-- ol-pr-review-bot superseded reviewed=${sha} -->`;
test('superseded status repost: a clean superseded review on the head never reposts SUCCESS', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: supersededBody(SHA('e')) }] }),
        reviewThreads: []
    });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', REPOST: 'true', RUN_URL: 'u' };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure', 'no verdict to carry: fail closed');
});
test('superseded range: a superseded review recorded on the head does not make the head count as reviewed', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01', body: supersededBody(SHA('e')) }]
        }),
        // A matching status would make a real review of the head skip.
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'success' }] })
    });
    // The full diff for the review that follows; the compare from the superseded commit fails, so it's a full review.
    github.rest.repos.compareCommitsWithBasehead = async p => {
        if (p.headers) return { data: 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n' };
        throw new Error('not an ancestor');
    };
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'false', 'the head still gets its own review');
    assert.notEqual(res.outputs.repost, 'true', 'and not a repost of the superseded verdict');
});
test('superseded range: the next review starts from the last review that was not superseded', async () => {
    // A real review of P, then a superseded review of A; the head is now B.
    const P = SHA('p'),
        A = SHA('e'),
        B = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: B }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({
            data: [
                { user: { login: 'openlibrary-bot' }, commit_id: P, submitted_at: '2026-01-01', body: 'x\n<!-- ol-pr-review-bot f=0 -->' },
                { user: { login: 'openlibrary-bot' }, commit_id: A, submitted_at: '2026-01-02', body: supersededBody(A, 1) }
            ]
        })
    });
    const compared = [];
    github.rest.repos.compareCommitsWithBasehead = async p => {
        if (p.headers) return { data: 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n' };
        compared.push(p.basehead);
        throw new Error('stop here: only the base matters');
    };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env: { PR: '1', GITHUB_WORKSPACE: dir } });
    assert.equal(compared[0], `${P}...${B}`, "from P, so B's review covers everything the superseded review of A saw");
    assert.equal(res.outputs.skip, 'false');
});
test('superseded status: a superseded review on the head does not count as the posted review', async () => {
    // The head moved back to A after post marked A's review superseded.
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: supersededBody(head) }] }),
        reviewThreads: []
    });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'success', PUBLIC_FINDINGS_COUNT: '0', WITHHELD: 'false', RUN_URL: 'u' };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure', 'no real review of this commit: not green');
});
test('D2 status repost: an f=2 marker reposts FAILURE', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'x\n<!-- ol-pr-review-bot f=2 -->' }] })
    });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', REPOST: 'true', RUN_URL: 'u' };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure');
});
test('D2 status repost: a LEGACY review with no marker FAILS CLOSED (red), never green', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'old review\n<!-- ol-pr-review-bot -->' }] })
    });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', REPOST: 'true', RUN_URL: 'u' };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure', 'an unreadable count must never fabricate a green');
});

// The resolver must skip exactly when the present status equals what the status job's repost path
// would post for the same inputs. For each input, run the real repost to get that state, then check
// the resolver skips if the present status matches and reposts if it doesn't.
const HEAD_SHA = SHA('a');
const reviewObjs = bodies => bodies.map(body => ({ user: { login: 'openlibrary-bot' }, commit_id: HEAD_SHA, submitted_at: '2026-01-01', body }));
for (const scenario of [
    { reviews: ['x\n<!-- ol-pr-review-bot f=0 -->'], threads: [] }, // clean -> success
    { reviews: ['x\n<!-- ol-pr-review-bot f=3 -->'], threads: [] }, // findings -> failure
    { reviews: ['x\n<!-- ol-pr-review-bot f=0 -->'], threads: [{ isResolved: false, isOutdated: false }] }, // open thread -> failure
    { reviews: ['legacy, no marker'], threads: [] }, // unreadable -> failure (fail closed)
    // The last bot review on the head has an empty body and an earlier one has the marker. Both
    // paths must pick the earlier one.
    { reviews: ['first\n<!-- ol-pr-review-bot f=0 -->', ''], threads: [] }, // trailing-empty -> still success
    { reviews: ['first\n<!-- ol-pr-review-bot f=1 -->', null], threads: [] } // trailing-null, earlier f=1 -> failure
]) {
    const label = `${JSON.stringify(scenario.reviews)} + ${scenario.threads.length} thread(s)`;
    test(`D2 drift pin: resolver matches status-job verdict for ${label}`, async () => {
        // (1) Authoritative state from the real status repost path.
        const s = mockGitHub({
            prGet: async () => ({ data: { head: { sha: HEAD_SHA } } }),
            listReviews: async () => ({ data: reviewObjs(scenario.reviews) }),
            reviewThreads: scenario.threads
        });
        await runScript(status.postStatus, {
            github: s.github,
            context,
            env: { PR: '1', HEAD_SHA, POST_RESULT: 'skipped', REPOST: 'true', RUN_URL: 'u' }
        });
        const authoritative = s.calls.createCommitStatus[0].state;

        const runResolver = async presentState => {
            const { github } = mockGitHub({
                prGet: async () => ({ data: { number: 1, head: { sha: HEAD_SHA }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
                listReviews: async () => ({ data: reviewObjs(scenario.reviews) }),
                listStatuses: async () => ({ data: [{ context: 'code-review', state: presentState }] }),
                reviewThreads: scenario.threads
            });
            const ctx = { ...context, payload: { pull_request: { number: 1 } } };
            return runScript(range.resolveRange, { github, context: ctx, env: { PR: '1', GITHUB_WORKSPACE: dir } });
        };

        // (2a) present status equals the authoritative verdict -> skip.
        const match = await runResolver(authoritative);
        assert.equal(match.outputs.skip, 'true', `present=${authoritative} matches the verdict -> skip`);
        // (2b) present status differs -> repost.
        const other = authoritative === 'success' ? 'failure' : 'success';
        const mismatch = await runResolver(other);
        assert.equal(mismatch.outputs.skip, 'false', `present=${other} contradicts the verdict -> not skip`);
        assert.equal(mismatch.outputs.repost, 'true');
    });
}
test('#14486 Finding 2: a transient reviewThreads GraphQL error routes to a repost, never fails the run', async () => {
    // A failed threads read must not throw: an unset `skip` would also skip the status job. It reposts
    // instead, and the status job recomputes.
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01', body: 'x\n<!-- ol-pr-review-bot f=0 -->' }]
        }),
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'success' }] })
    });
    github.graphql = async () => {
        throw new Error('API rate limit exceeded (secondary)');
    };
    const ctx = { ...context, payload: { pull_request: { number: 1 } } };
    const res = await runScript(range.resolveRange, { github, context: ctx, env: { PR: '1', GITHUB_WORKSPACE: dir } });
    assert.equal(res.failed, null, 'a transient threads read must not fail the analyze job');
    assert.equal(res.outputs.skip, 'false', 'it falls back to NOT skipping');
    assert.equal(res.outputs.repost, 'true', 'and routes to the authoritative status repost');
});

// ===================== A withheld review is not automatically red =====================
test('D3a analyze-gate: a backstop-tripping summary -> held back, NON-blocking, rest kept', async () => {
    const review = cleanReview();
    review.summary = 'This change guards against a SQL injection in the query builder.'; // trips the backstop
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const env = { GITHUB_WORKSPACE: dir };
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env });
    assert.equal(res.outputs.withheld, 'false', 'the review is still posted');
    assert.equal(res.outputs.held_back, 'true', 'with its summary held back');
    assert.equal(res.outputs.withheld_blocking, 'false', 'with 0 findings it is NON-blocking');
    const written = JSON.parse(readFileSync(join(dir, 'review.json'), 'utf8'));
    assert.equal(written.summary, '', 'the summary is never kept');
    assert.ok(!JSON.stringify(written).includes('injection'));
});
test('D3a analyze-gate: a security finding in existing code -> held back AND blocking; the count leaves it out', async () => {
    const review = cleanReview();
    review.dimensions.security = { status: 'findings' };
    review.findings = [{ dimension: 'security', severity: 'high', confidence: 8, title: 'authz gap', body: 'missing owner check' }];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const env = { GITHUB_WORKSPACE: dir };
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env });
    assert.equal(res.outputs.withheld, 'false');
    assert.equal(res.outputs.held_back, 'true');
    assert.equal(res.outputs.withheld_blocking, 'true');
    assert.equal(res.outputs.public_findings_count, '0', 'the public count leaves it out (no count leak)');
    assert.ok(!readFileSync(join(dir, 'review.json'), 'utf8').includes('owner'));
});
test('analyze-gate: a security finding the PR introduces, on lines it adds, is published', async () => {
    const review = cleanReview();
    review.dimensions.security = { status: 'findings' };
    review.findings = [
        { dimension: 'security', scope: 'introduced', severity: 'high', confidence: 8, title: 'authz gap', body: 'Check the owner.', path: 'a.py', line: 1 }
    ];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+edit(list)\n');
    const { github } = mockGitHub();
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env: { GITHUB_WORKSPACE: dir } });
    assert.equal(res.outputs.held_back, 'false');
    assert.equal(res.outputs.public_findings_count, '1');
    assert.equal(JSON.parse(readFileSync(join(dir, 'review.json'), 'utf8')).findings[0].title, 'authz gap');
});
test('analyze-gate: a malformed review is withheld in full and blocks', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify({ summary: 5 }));
    const { github } = mockGitHub();
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env: { GITHUB_WORKSPACE: dir } });
    assert.equal(res.outputs.withheld, 'true');
    assert.equal(res.outputs.held_back, 'false');
    assert.equal(res.outputs.withheld_blocking, 'true');
    assert.deepEqual(JSON.parse(readFileSync(join(dir, 'review.json'), 'utf8')), { withheld: true });
});
test('D3a status: withheld + non-blocking -> SUCCESS (the no-defect PR greens itself)', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = {
        PR: '1',
        HEAD_SHA: head,
        POST_RESULT: 'success',
        PUBLIC_FINDINGS_COUNT: '0',
        WITHHELD: 'true',
        WITHHELD_BLOCKING: 'false',
        REPOST: 'false',
        RUN_URL: 'u'
    };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'success');
});
test('D3a status: withheld + blocking -> FAILURE with the non-leaky withheld phrase', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = {
        PR: '1',
        HEAD_SHA: head,
        POST_RESULT: 'success',
        PUBLIC_FINDINGS_COUNT: '0',
        WITHHELD: 'true',
        WITHHELD_BLOCKING: 'true',
        REPOST: 'false',
        RUN_URL: 'u'
    };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure');
    assert.equal(calls.createCommitStatus[0].description, 'Feedback withheld for maintainer review.');
    assert.ok(!/\d/.test(calls.createCommitStatus[0].description), 'the description carries no count');
});
for (const [blocking, state] of [
    ['true', 'failure'],
    ['false', 'success'],
    ['', 'failure']
]) {
    test(`status: a posted review with a part held back (blocking=${blocking || 'missing'}) -> ${state}`, async () => {
        const head = SHA('a');
        const { github, calls } = mockGitHub({
            prGet: async () => ({ data: { head: { sha: head } } }),
            listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'x' }] })
        });
        const env = {
            PR: '1',
            HEAD_SHA: head,
            POST_RESULT: 'success',
            PUBLIC_FINDINGS_COUNT: '0',
            WITHHELD: 'false',
            HELD_BACK: 'true',
            WITHHELD_BLOCKING: blocking,
            REPOST: 'false',
            RUN_URL: 'u'
        };
        await runScript(status.postStatus, { github, context, env });
        assert.equal(calls.createCommitStatus[0].state, state);
        if (blocking === 'true') assert.equal(calls.createCommitStatus[0].description, 'Feedback withheld for maintainer review.');
    });
}
test('D3a post: a withheld stub -> createReview NOT called, exits clean (no hard failure)', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify({ withheld: true }));
    writeFileSync(join(dir, 'review.diff'), '');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    const res = await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(calls.createReview.length, 0, 'nothing public is posted for a withheld review');
    assert.equal(res.failed, null, 'and the job does not hard-fail -- the status job decides');
});

// ===================== pending: early "review in progress" status =====================
const prCtx = { ...context, payload: { pull_request: { number: 1 } } };
const runPending = async handlers => {
    const { github, calls } = mockGitHub(handlers);
    await runScript(pending.markPending, { github, context: prCtx, env: { RUN_URL: 'u' } });
    return calls;
};

test('pending: head with no code-review status -> posts pending', async () => {
    const calls = await runPending({ prGet: async () => ({ data: { head: { sha: SHA('a') }, draft: false, state: 'open' } }) });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].sha, SHA('a'));
    assert.equal(calls.createCommitStatus[0].state, 'pending');
});
test('pending: posts nothing on a head with a status, a draft, or a closed PR', async () => {
    for (const handlers of [
        { listStatuses: async () => ({ data: [{ context: 'code-review', state: 'success' }] }) },
        { prGet: async () => ({ data: { head: { sha: SHA('a') }, draft: true, state: 'open' } }) },
        { prGet: async () => ({ data: { head: { sha: SHA('a') }, draft: false, state: 'closed' } }) }
    ]) {
        const calls = await runPending(handlers);
        assert.equal(calls.createCommitStatus.length, 0);
    }
});
test('pending: replaces an earlier pending status (e.g. awaiting review) with review in progress', async () => {
    const calls = await runPending({ listStatuses: async () => ({ data: [{ context: 'code-review', state: 'pending', description: 'Not reviewed yet.' }] }) });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].description, 'Review in progress.');
});

// ===================== pending: 👀 on the @-mention that asked for the review =====================
test('pending: an @-mention review request gets an eyes reaction on that comment', async () => {
    const step = workflow.jobs.pending.steps.find(s => (s.name || '').includes('React to the review request'));
    assert.ok(step, 'react step exists');
    assert.equal(step.if, "github.event_name == 'issue_comment'", 'only comments get a reaction');
    assert.equal(step['continue-on-error'], true, 'a failed reaction never blocks the review');
    // Reacting to an issue comment needs Issues: write; OL_BOT_REVIEW_PAT has only Pull requests.
    assert.equal(step.with['github-token'], '${{ secrets.OL_BOT_PR_PAT }}');
    const reactions = [];
    const github = {
        rest: {
            reactions: {
                createForIssueComment: async p => {
                    reactions.push(p);
                    return { data: {} };
                }
            }
        }
    };
    const ctx = { ...context, eventName: 'issue_comment', payload: { comment: { id: 42 }, issue: { number: 1 } } };
    const res = await runScript(pending.reactToComment, { github, context: ctx, env: {} });
    assert.equal(res.failed, null);
    assert.deepEqual(reactions, [{ owner: 'internetarchive', repo: 'openlibrary', comment_id: 42, content: 'eyes' }]);
});
test('pending: a refused reaction only warns', async () => {
    const github = {
        rest: {
            reactions: {
                createForIssueComment: async () => {
                    throw new Error('Resource not accessible by personal access token');
                }
            }
        }
    };
    const ctx = { ...context, eventName: 'issue_comment', payload: { comment: { id: 42 }, issue: { number: 1 } } };
    const res = await runScript(pending.reactToComment, { github, context: ctx, env: {} });
    assert.equal(res.failed, null);
});
test('status: analyze died before posting a review -> the pending head gets failure', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', RUN_URL: 'u' };
    await runScript(status.postStatus, { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].state, 'failure');
});

// ===================== run-page summary =====================
test('summary: a clean review lists the commit, range, counts and status', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'x\n<!-- ol-pr-review-bot f=0 -->' }] })
    });
    const env = {
        PR: '7',
        HEAD_SHA: head,
        POST_RESULT: 'success',
        PUBLIC_FINDINGS_COUNT: '0',
        WITHHELD: 'false',
        INCREMENTAL: 'true',
        BASE_SHA: SHA('b'),
        RUN_URL: 'u'
    };
    const { summary } = await runScript(status.postStatus, { github, context, env });
    assert.match(summary, /## Code review: #7 @ aaaaaaa/);
    assert.match(summary, /\| Range \| incremental: files changed since the last review \|/);
    assert.match(summary, /\| Findings \| 0 \|/);
    assert.match(summary, /\| Status \| success: Review passed; all feedback resolved\. \|/);
});
test('summary: a withheld review shows no findings count', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '7', HEAD_SHA: head, POST_RESULT: 'success', PUBLIC_FINDINGS_COUNT: '0', WITHHELD: 'true', WITHHELD_BLOCKING: 'true', RUN_URL: 'u' };
    const { summary } = await runScript(status.postStatus, { github, context, env });
    assert.match(summary, /\| Findings \| — \|/);
    assert.ok(!/\d+ findings?/.test(summary), 'no count of withheld findings');
});
test('summary: head moved during the review -> says the commit was superseded', async () => {
    const { github } = mockGitHub({ prGet: async () => ({ data: { head: { sha: SHA('c') } } }) });
    const env = { PR: '7', HEAD_SHA: SHA('a'), POST_RESULT: 'success', RUN_URL: 'u' };
    const { summary } = await runScript(status.postStatus, { github, context, env });
    assert.match(summary, /\| Status \| pending: superseded by ccccccc/);
});

// ===================== LOW findings are non-blocking suggestions =====================
test('analyze-gate: LOW findings do not count toward the public findings count', async () => {
    const review = cleanReview();
    review.dimensions.correctness = { status: 'findings' };
    review.findings = [
        { dimension: 'correctness', severity: 'medium', confidence: 8, title: 'a', body: 'b' },
        { dimension: 'correctness', severity: 'low', confidence: 8, title: 'c', body: 'd' }
    ];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env: { GITHUB_WORKSPACE: dir } });
    assert.equal(res.outputs.public_findings_count, '1');
});
test('post: a LOW finding becomes a suggestion in the summary, not a blocking inline thread', async () => {
    const review = cleanReview();
    review.dimensions.test_coverage = { status: 'findings' };
    review.findings = [{ dimension: 'test_coverage', severity: 'low', confidence: 8, title: 'Untested label', body: 'Add a test.', path: 'x', line: 1 }];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    const posted = calls.createReview[0];
    assert.equal((posted.comments || []).length, 0, 'no inline thread for a LOW finding');
    assert.match(posted.body, /### Suggestions \(won't block\)\n\n- \*\*Untested label\*\* · `x:1`\n {2}Add a test\./);
    assert.match(posted.body, /^\*\*No blocking findings\*\* · 1 suggestion on `/, 'a suggestion is not called a finding');
    assert.match(posted.body, /<!-- ol-pr-review-bot f=0 -->/);
    assert.notEqual(posted.event, 'REQUEST_CHANGES');
});

// ===================== Re-review after the author merges the base branch =====================
// Shaped like #14495: since the last review (P), the author merged master (M, bringing in master's
// commits X1 and X2) and then pushed one commit (A). The PR's diff touches a.py and b.py.
const P = SHA('1'),
    M = SHA('2'),
    A = SHA('3'),
    X1 = SHA('4'),
    X2 = SHA('5'),
    MB = SHA('6');
const commit = (sha, ...parents) => ({ sha, parents: parents.map(p => ({ sha: p })) });
const PR_DIFF =
    'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+a\n' + 'diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1,2 @@\n+b\n+b2\n';
function baseMergeGitHub({ sinceCommits, mergeFiles = ['master_only.py'], authorFiles = ['b.py'] }) {
    const calls = { getCommit: [], compare: [] };
    const github = {
        rest: {
            pulls: {
                get: async () => ({ data: { number: 1, draft: false, state: 'open', head: { sha: A }, base: { sha: SHA('b'), ref: 'master' } } }),
                listReviews: async () => ({
                    data: [{ user: { login: 'openlibrary-bot' }, commit_id: P, submitted_at: '2026-01-01', body: 'x\n<!-- ol-pr-review-bot f=0 -->' }]
                })
            },
            repos: {
                compareCommitsWithBasehead: async ({ basehead, headers }) => {
                    calls.compare.push(basehead);
                    if (headers) return { data: PR_DIFF };
                    // The merge against its base-side parent: the PR's own changes, plus any conflict fixes.
                    if (basehead === `${X2}...${M}`)
                        return { data: { files: ['a.py', 'b.py', ...mergeFiles.filter(f => f !== 'master_only.py')].map(filename => ({ filename })) } };
                    if (basehead === `${P}...${A}`)
                        return { data: { status: 'ahead', files: [{}], total_commits: sinceCommits.length, commits: sinceCommits } };
                    // master...head: the PR's own commits.
                    const own = [commit(SHA('0'), MB), commit(P, SHA('0')), commit(M, P, X2), commit(A, M)];
                    return { data: { status: 'diverged', merge_base_commit: { sha: MB }, total_commits: own.length, commits: own } };
                },
                getCommit: async ({ ref }) => {
                    calls.getCommit.push(ref);
                    // A merge's own files are its diff against the PR-side parent: master's changes.
                    return { data: { files: (ref === A ? authorFiles : mergeFiles).map(filename => ({ filename })) } };
                }
            }
        },
        paginate: async (method, params) => (await method(params)).data,
        graphql: async () => ({ repository: { pullRequest: { reviewThreads: { nodes: [], pageInfo: { hasNextPage: false, endCursor: null } } } } })
    };
    return { github, calls };
}

test("range: a base merge plus one author commit reviews the PR diff for that commit's files only", async () => {
    const { github, calls } = baseMergeGitHub({ sinceCommits: [commit(X1, MB), commit(X2, X1), commit(M, P, X2), commit(A, M)] });
    const res = await runScript(range.resolveRange, { github, context: prCtx, env: { GITHUB_WORKSPACE: dir }, cwd: dir });
    assert.equal(res.outputs.repost, 'false');
    assert.equal(res.outputs.incremental, 'true');
    assert.equal(res.outputs.base_sha, MB, 'the PR diff, from the merge base');
    assert.equal(res.outputs.files, JSON.stringify(['b.py']));
    assert.deepEqual(calls.getCommit, [A, M], "master's own commits are never read; the merge only for conflict fixes");
    assert.equal(readFileSync(join(dir, 'review.diff'), 'utf8'), 'diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1,2 @@\n+b\n+b2\n');
    const rangeJson = JSON.parse(readFileSync(join(dir, 'review-range.json'), 'utf8'));
    assert.equal(rangeJson.prior_review_sha, P);
    assert.deepEqual(rangeJson.files, ['b.py']);
});
test('range: only a base merge since the last review -> no model, carry the last verdict', async () => {
    const { github, calls } = baseMergeGitHub({ sinceCommits: [commit(X1, MB), commit(X2, X1), commit(M, P, X2)] });
    const res = await runScript(range.resolveRange, { github, context: prCtx, env: { GITHUB_WORKSPACE: dir }, cwd: dir });
    assert.equal(res.outputs.skip, 'false');
    assert.equal(res.outputs.repost, 'true');
    assert.equal(res.outputs.verdict_sha, P);
    assert.deepEqual(calls.getCommit, [M]);
});
test('range: a conflict fixed by hand in a base merge is re-reviewed', async () => {
    // The merge changed a.py relative to both parents: the author resolved a conflict there.
    const { github } = baseMergeGitHub({ sinceCommits: [commit(X1, MB), commit(X2, X1), commit(M, P, X2)], mergeFiles: ['master_only.py', 'a.py'] });
    const res = await runScript(range.resolveRange, { github, context: prCtx, env: { GITHUB_WORKSPACE: dir }, cwd: dir });
    assert.equal(res.outputs.repost, 'false', 'a resolved conflict is new code to review');
    assert.equal(res.outputs.files, JSON.stringify(['a.py']));
});
test('range: a commit listing 300 files (GitHub truncates there) falls back to a full review', async () => {
    const many = Array.from({ length: 300 }, (_, i) => `f${i}.py`);
    const { github } = baseMergeGitHub({ sinceCommits: [commit(M, P, X2), commit(A, M)], authorFiles: many });
    const res = await runScript(range.resolveRange, { github, context: prCtx, env: { GITHUB_WORKSPACE: dir }, cwd: dir });
    assert.equal(res.outputs.incremental, 'false');
    assert.equal(res.outputs.files || '', '');
});
test('status repost: carries the verdict of the review on VERDICT_SHA, an earlier commit', async () => {
    for (const [f, state] of [
        [0, 'success'],
        [2, 'failure']
    ]) {
        const { github, calls } = mockGitHub({
            prGet: async () => ({ data: { head: { sha: A } } }),
            listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: P, body: `x\n<!-- ol-pr-review-bot f=${f} -->` }] })
        });
        await runScript(status.postStatus, { github, context, env: { PR: '1', HEAD_SHA: A, REPOST: 'true', VERDICT_SHA: P, RUN_URL: 'u' } });
        assert.equal(calls.createCommitStatus[0].sha, A);
        assert.equal(calls.createCommitStatus[0].state, state);
    }
});
test('post refetchDiff: cuts the PR diff to the files analyze listed', async () => {
    const { github } = baseMergeGitHub({ sinceCommits: [] });
    const env = { BASE_SHA: MB, HEAD_SHA: A, FILES: JSON.stringify(['b.py']) };
    await runScript(post.refetchDiff, { github, context, env: { ...env, GITHUB_WORKSPACE: dir }, cwd: dir });
    assert.equal(readFileSync(join(dir, 'review.diff'), 'utf8'), 'diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1,2 @@\n+b\n+b2\n');
    const bad = await runScript(post.refetchDiff, { github, context, env: { ...env, FILES: '{"x":1}', GITHUB_WORKSPACE: dir }, cwd: dir });
    assert.equal(bad.failed, 'Unexpected review range.');
});

// ===================== A comment anchor GitHub can't resolve =====================
test('post: a 422 on an anchor posts again with the inline comments in the summary', async () => {
    const review = cleanReview();
    review.dimensions.correctness = { status: 'findings' };
    review.findings = [{ dimension: 'correctness', severity: 'medium', confidence: 8, title: 'Off by one', body: 'Use <=.', path: 'x', line: 1 }];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    github.rest.pulls.createReview = async p => {
        calls.createReview.push(p);
        if (p.comments.length) throw Object.assign(new Error('Unprocessable Entity: "Line could not be resolved"'), { status: 422 });
        return { data: { id: 999 } };
    };
    github.rest.pulls.listReviews = async () => ({ data: [{ id: 999 }] });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    const res = await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(res.failed, null);
    assert.equal(calls.createReview.length, 2);
    const retry = calls.createReview[1];
    assert.equal(retry.event, 'REQUEST_CHANGES', 'the verdict is kept');
    assert.deepEqual(retry.comments, []);
    assert.match(retry.body, /### Findings without an in-diff anchor\n\n- \*\*MEDIUM · Correctness — Off by one\*\*/);
    assert.match(retry.body, /<!-- ol-pr-review-bot f=1 -->/);
    assert.equal(res.warnings.length, 1);
});

// ===================== Review text =====================
test('post: the one-line footer gives the next step, and asks for no comments', async () => {
    const head = SHA('a');
    const bodies = [];
    const withFinding = cleanReview();
    withFinding.dimensions.correctness = { status: 'findings' };
    withFinding.findings = [{ dimension: 'correctness', severity: 'low', confidence: 8, title: 'Off by one', body: 'Use <=.', path: 'x', line: 1 }];
    for (const [minutes, review] of [
        ['10', withFinding],
        ['', withFinding],
        ['10', cleanReview()]
    ]) {
        writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
        writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
        const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
        const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', PUSH_REVIEW_MINUTES: minutes, GITHUB_WORKSPACE: dir };
        await runScript(post.validateAndPost, { github, context, env, cwd: dir });
        bodies.push(calls.createReview[0].body);
    }
    const link = String.raw`\[How this bot works\]\([^)]*docs/code-review-bot\.md\)`;
    const ask = 'Please address the feedback above before a maintainer reviews this PR';
    assert.match(bodies[0], new RegExp(`<sub>${ask} · ${link} · Reviews new pushes after 10 minutes</sub>`), 'a suggestion is feedback too');
    assert.match(bodies[1], new RegExp(`<sub>${ask} · ${link}</sub>`));
    assert.match(bodies[2], /^\*\*No issues found\*\* on `aaaaaaa`\.\n\nA plain summary with nothing sensitive\.\n\n<sub>/);
    assert.match(bodies[2], new RegExp(`<sub>A maintainer will review this PR next · ${link}</sub>`));
    for (const b of bodies) assert.doesNotMatch(b, /on behalf of|@openlibrary-bot review|\[!TIP\]|Dimensions|optional/);
});

// ===================== Part of a review held back =====================
const heldBackPost = async env => {
    const review = cleanReview();
    review.dimensions.correctness = { status: 'findings' };
    review.findings = [{ dimension: 'correctness', severity: 'medium', confidence: 8, title: 'Off by one', body: 'Use <=.', path: 'x', line: 1 }];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const res = await runScript(post.validateAndPost, {
        github,
        context,
        env: { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir, ...env },
        cwd: dir
    });
    return { res, calls };
};
test('post: a blocking held-back part -> the rest is posted, with a fixed note and h=1 in the marker', async () => {
    const { calls } = await heldBackPost({ HELD_BACK: 'true', WITHHELD_BLOCKING: 'true' });
    const body = calls.createReview[0].body;
    assert.match(
        body,
        /> \[!IMPORTANT\]\n> Part of this review was held back because it may be security-sensitive\. A maintainer needs to look at this PR before it can merge\./
    );
    assert.match(body, /<!-- ol-pr-review-bot f=1 h=1 -->/);
    assert.equal(calls.createReview[0].comments.length, 1, 'the published finding is still posted');
});
test('post: a non-blocking held-back part -> a note that says so, and no h=1', async () => {
    const { calls } = await heldBackPost({ HELD_BACK: 'true', WITHHELD_BLOCKING: 'false' });
    const body = calls.createReview[0].body;
    assert.match(body, /None of it blocks this PR\./);
    assert.match(body, /<!-- ol-pr-review-bot f=1 -->/);
});
test('post: nothing held back -> no note', async () => {
    const { calls } = await heldBackPost({ HELD_BACK: 'false', WITHHELD_BLOCKING: 'false' });
    assert.ok(!/held back/.test(calls.createReview[0].body));
});
test('post: if its own gate would hold back more than analyze did, it posts nothing and fails', async () => {
    const review = cleanReview();
    review.summary = 'Guards against SQL injection.';
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), '');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const res = await runScript(post.validateAndPost, {
        github,
        context,
        env: { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), GITHUB_WORKSPACE: dir },
        cwd: dir
    });
    assert.equal(calls.createReview.length, 0);
    assert.ok(res.failed);
});
test('status: a repost reads a blocking held-back part from the marker', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'x\n<!-- ol-pr-review-bot f=0 h=1 -->' }] })
    });
    await runScript(status.postStatus, { github, context, env: { PR: '1', HEAD_SHA: head, REPOST: 'true', RUN_URL: 'u' } });
    assert.equal(calls.createCommitStatus[0].state, 'failure');
    assert.equal(calls.createCommitStatus[0].description, 'Feedback withheld for maintainer review.');
});
test('status: a later clean review stays red while an earlier blocking held-back part is not dismissed', async () => {
    const head = SHA('a');
    for (const [state, want] of [
        ['CHANGES_REQUESTED', 'failure'],
        ['DISMISSED', 'success']
    ]) {
        const { github, calls } = mockGitHub({
            prGet: async () => ({ data: { head: { sha: head } } }),
            listReviews: async () => ({
                data: [
                    { user: { login: 'openlibrary-bot' }, commit_id: SHA('c'), state, body: 'x\n<!-- ol-pr-review-bot f=0 h=1 -->' },
                    { user: { login: 'openlibrary-bot' }, commit_id: head, state: 'APPROVED', body: 'y\n<!-- ol-pr-review-bot f=0 -->' }
                ]
            })
        });
        const env = {
            PR: '1',
            HEAD_SHA: head,
            POST_RESULT: 'success',
            PUBLIC_FINDINGS_COUNT: '0',
            WITHHELD: 'false',
            HELD_BACK: 'false',
            REPOST: 'false',
            RUN_URL: 'u'
        };
        await runScript(status.postStatus, { github, context, env });
        assert.equal(calls.createCommitStatus[0].state, want, state);
    }
});
test('post: never approves while a blocking part is held back', async () => {
    const review = cleanReview();
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), '');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), GITHUB_WORKSPACE: dir, HELD_BACK: 'true', WITHHELD_BLOCKING: 'true' };
    await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(calls.createReview[0].event, 'REQUEST_CHANGES');
});