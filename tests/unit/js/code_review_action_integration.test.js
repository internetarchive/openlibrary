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
    const recorded = { outputs: {}, failed: null, summary: '' };
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
        warning: () => {},
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

// ===================== A push mid-run: post neither review nor status =====================
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
test('D1 post: head MOVED -> createReview is NOT called', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const pinned = SHA('a'),
        live = SHA('c');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: live } } }) });
    const env = { PR: '1', HEAD_SHA: pinned, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    const res = await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(calls.createReview.length, 0, 'a review must NOT post on a head the run did not review');
    assert.equal(res.failed, null, 'and it exits cleanly, not failed');
});
test('D1 status: head MOVED -> createCommitStatus is NOT called', async () => {
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
    assert.equal(calls.createCommitStatus.length, 0, 'no status may be posted when the reviewed SHA is no longer the head');
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
test('D3a analyze-gate: a backstop-tripping review with 0 findings -> withheld, NON-blocking', async () => {
    const review = cleanReview();
    review.summary = 'This change guards against a SQL injection in the query builder.'; // trips the backstop
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const env = { GITHUB_WORKSPACE: dir };
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env });
    assert.equal(res.outputs.withheld, 'true', 'the backstop withholds the public copy');
    assert.equal(res.outputs.withheld_blocking, 'false', 'but with 0 findings it is NON-blocking');
    assert.equal(res.outputs.public_findings_count, '0', 'the public count stays 0 (no leak)');
    const written = JSON.parse(readFileSync(join(dir, 'review.json'), 'utf8'));
    assert.deepEqual(written, { withheld: true }, 'only the withheld stub is kept, never the content');
});
test('D3a analyze-gate: a real security finding -> withheld AND blocking', async () => {
    const review = cleanReview();
    review.dimensions.security = { status: 'findings' };
    review.findings = [{ dimension: 'security', severity: 'high', title: 'authz gap', body: 'missing owner check' }];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const env = { GITHUB_WORKSPACE: dir };
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env });
    assert.equal(res.outputs.withheld, 'true');
    assert.equal(res.outputs.withheld_blocking, 'true');
    assert.equal(res.outputs.public_findings_count, '0', 'the public count stays 0 even for a real finding (no count leak)');
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
test('D3a status: withheld + blocking -> FAILURE with the non-leaky private-delivery phrase', async () => {
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
    assert.equal(calls.createCommitStatus[0].description, 'A finding was delivered privately; maintainer review required.');
    assert.ok(!/\d/.test(calls.createCommitStatus[0].description), 'the description carries no count');
});
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
    assert.match(summary, /\| Range \| incremental since bbbbbbb \|/);
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
test('summary: head moved during the review -> says so and that no status was posted', async () => {
    const { github } = mockGitHub({ prGet: async () => ({ data: { head: { sha: SHA('c') } } }) });
    const env = { PR: '7', HEAD_SHA: SHA('a'), POST_RESULT: 'success', RUN_URL: 'u' };
    const { summary } = await runScript(status.postStatus, { github, context, env });
    assert.match(summary, /\| Status \| none: the PR moved to ccccccc during the review/);
});

// ===================== LOW findings are non-blocking suggestions =====================
test('analyze-gate: LOW findings do not count toward the public findings count', async () => {
    const review = cleanReview();
    review.dimensions.test_coverage = { status: 'findings' };
    review.findings = [
        { dimension: 'test_coverage', severity: 'medium', title: 'a', body: 'b' },
        { dimension: 'test_coverage', severity: 'low', title: 'c', body: 'd' }
    ];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const res = await runScript(analyzeGate.gateAnalysis, { github, context, env: { GITHUB_WORKSPACE: dir } });
    assert.equal(res.outputs.public_findings_count, '1');
});
test('post: a LOW finding becomes a suggestion in the summary, not a blocking inline thread', async () => {
    const review = cleanReview();
    review.dimensions.test_coverage = { status: 'findings' };
    review.findings = [{ dimension: 'test_coverage', severity: 'low', title: 'Untested label', body: 'Add a test.', path: 'x', line: 1 }];
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    const posted = calls.createReview[0];
    assert.equal((posted.comments || []).length, 0, 'no inline thread for a LOW finding');
    assert.match(posted.body, /### Suggestions \(won't block\)\n\n- \*\*Untested label\*\* \(`x:1`\): Add a test\./);
    assert.match(posted.body, /<!-- ol-pr-review-bot f=0 -->/);
    assert.notEqual(posted.event, 'REQUEST_CHANGES');
});

// ===================== #14526: re-reviews after a base-branch merge =====================
// History: P (reviewed) <- O (the PR's own commit, a.py) <- M (merges master's X) [<- H (own, b.py)].
const P = SHA('1'),
    O = SHA('2'),
    X = SHA('3'),
    M = SHA('4'),
    H = SHA('5'),
    MB = SHA('6');
const prDiff = ['a.py', 'b.py', 'master_only.py'].map(f => `diff --git a/${f} b/${f}\n--- a/${f}\n+++ b/${f}\n@@ -1 +1 @@\n+${f}\n`).join('');
function mergeScenario({ head, chain, ownBeforeMerge = true }) {
    const commits = {
        [O]: { parents: [{ sha: P }], files: [{ filename: 'a.py' }] },
        [M]: { parents: [{ sha: ownBeforeMerge ? O : P }, { sha: X }], files: [{ filename: 'master_only.py' }] },
        [H]: { parents: [{ sha: M }], files: [{ filename: 'b.py' }] },
        ...chain
    };
    const basehead = [];
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b'), ref: 'master' }, draft: false, state: 'open' } }),
        listReviews: async () => ({
            data: [{ user: { login: 'openlibrary-bot' }, commit_id: P, submitted_at: '2026-01-01', body: 'x\n<!-- ol-pr-review-bot f=0 -->' }]
        })
    });
    github.rest.repos.getCommit = async ({ ref }) => {
        if (!commits[ref]) throw new Error(`no commit ${ref}`);
        return { data: commits[ref] };
    };
    github.rest.repos.compareCommitsWithBasehead = async p => {
        basehead.push(p.basehead);
        if (p.headers) return { data: prDiff };
        if (p.basehead === `${P}...${head}`) {
            return {
                data: {
                    status: 'ahead',
                    files: [{}],
                    total_commits: 3,
                    commits: [
                        { sha: O, parents: [{ sha: P }] },
                        { sha: M, parents: [{ sha: O }, { sha: X }] }
                    ]
                }
            };
        }
        if (p.basehead === `${X}...master`) return { data: { status: 'ahead' } };
        if (p.basehead === `master...${head}`) return { data: { status: 'diverged', merge_base_commit: { sha: MB } } };
        return { data: { status: 'diverged' } };
    };
    return { github, basehead };
}
const runRange = github =>
    runScript(range.resolveRange, { github, context: { ...context, payload: { pull_request: { number: 1 } } }, env: { PR: '1', GITHUB_WORKSPACE: dir } });

test('#14526 range: only a base merge since the last review -> no model run, the prior verdict is carried', async () => {
    const { github } = mergeScenario({ head: M, ownBeforeMerge: false });
    const res = await runRange(github);
    assert.equal(res.outputs.skip, 'false');
    assert.equal(res.outputs.repost, 'true', 'routes to a status repost, which runs no model');
    assert.equal(res.outputs.head_sha, M);
    assert.equal(res.outputs.verdict_sha, P, 'the verdict comes from the review of the last reviewed commit');
});
test('#14526 range: own commits and a base merge -> the PR diff for only the files the own commits touched', async () => {
    const { github, basehead } = mergeScenario({ head: H });
    const res = await runRange(github);
    assert.equal(res.outputs.repost, 'false');
    assert.equal(res.outputs.base_sha, MB, "diffs from the PR's merge base, not the reviewed commit");
    assert.equal(res.outputs.incremental, 'true');
    assert.deepEqual(JSON.parse(res.outputs.review_paths), ['a.py', 'b.py']);
    assert.ok(basehead.includes(`${MB}...${H}`));
    const diff = readFileSync(join(dir, 'review.diff'), 'utf8');
    assert.match(diff, /\+\+\+ b\/a\.py/);
    assert.match(diff, /\+\+\+ b\/b\.py/);
    assert.doesNotMatch(diff, /master_only\.py/, "the base branch's changes are not reviewed");
    assert.deepEqual(JSON.parse(readFileSync(join(dir, 'review-range.json'), 'utf8')).paths, ['a.py', 'b.py']);
});
test('#14526 range: a merge of a branch that is not the base counts as the PR own commit', async () => {
    const { github } = mergeScenario({ head: M, ownBeforeMerge: false });
    const compare = github.rest.repos.compareCommitsWithBasehead;
    github.rest.repos.compareCommitsWithBasehead = async p => (p.basehead === `${X}...master` ? { data: { status: 'diverged' } } : compare(p));
    const res = await runRange(github);
    assert.equal(res.outputs.repost, 'false', 'a real review runs');
    assert.deepEqual(JSON.parse(res.outputs.review_paths || 'null'), null, 'nothing is filtered: no base merge was skipped');
    assert.equal(res.outputs.base_sha, P);
});
test('#14526 range: no merge commits in the range -> the plain incremental review, unchanged', async () => {
    const { github } = mergeScenario({ head: O });
    github.rest.repos.compareCommitsWithBasehead = async p =>
        p.headers ? { data: prDiff } : { data: { status: 'ahead', files: [{}], total_commits: 1, commits: [{ sha: O, parents: [{ sha: P }] }] } };
    github.rest.repos.getCommit = async () => {
        throw new Error('no commit walk without a merge');
    };
    const res = await runRange(github);
    assert.equal(res.outputs.base_sha, P);
    assert.equal(res.outputs.incremental, 'true');
    assert.equal(res.outputs.review_paths, '');
});
test('#14526 range: a first-parent chain that never reaches the reviewed commit -> full review of the PR diff', async () => {
    const { github } = mergeScenario({ head: H, chain: { [O]: { parents: [{ sha: SHA('9') }], files: [] } } });
    const res = await runRange(github);
    assert.equal(res.outputs.incremental, 'false');
    assert.equal(res.outputs.base_sha, MB);
    assert.equal(res.outputs.review_paths, '');
});
test('#14526 status: a carried verdict is read from the review on VERDICT_SHA and posted on the head', async () => {
    for (const [marker, state] of [
        ['f=0', 'success'],
        ['f=2', 'failure']
    ]) {
        const { github, calls } = mockGitHub({
            prGet: async () => ({ data: { head: { sha: M } } }),
            listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: P, body: `x\n<!-- ol-pr-review-bot ${marker} -->` }] })
        });
        const env = { PR: '1', HEAD_SHA: M, POST_RESULT: 'skipped', REPOST: 'true', VERDICT_SHA: P, RUN_URL: 'u' };
        const { summary } = await runScript(status.postStatus, { github, context, env });
        assert.equal(calls.createCommitStatus[0].sha, M, 'posted on the new head');
        assert.equal(calls.createCommitStatus[0].state, state);
        assert.match(summary, /only base-branch merges since the review of 1111111/);
    }
});
test('#14526 post: re-fetching the diff keeps only REVIEW_PATHS', async () => {
    const { github } = mockGitHub();
    github.rest.repos.compareCommitsWithBasehead = async () => ({ data: prDiff });
    const env = { BASE_SHA: MB, HEAD_SHA: H, REVIEW_PATHS: JSON.stringify(['b.py']) };
    await runScript(post.refetchDiff, { github, context, env, cwd: dir });
    const diff = readFileSync(join(dir, 'review.diff'), 'utf8');
    assert.match(diff, /b\.py/);
    assert.doesNotMatch(diff, /a\.py|master_only\.py/);
});

// ===================== #14526: a rejected comment line never loses the review =====================
const reviewWithFinding = () => {
    const review = cleanReview();
    review.dimensions.correctness = { status: 'findings' };
    review.findings = [{ dimension: 'correctness', severity: 'medium', title: 'Off by one', body: 'Use <=.', path: 'x', line: 1 }];
    return review;
};
test('#14526 post: a 422 on an inline comment line reposts with every finding in the summary', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(reviewWithFinding()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head }, user: { login: 'alice' } } }) });
    const tried = [];
    github.rest.pulls.createReview = async p => {
        tried.push(p);
        if (p.comments.length) throw Object.assign(new Error('Line could not be resolved'), { status: 422 });
        calls.createReview.push(p);
        return { data: { id: 999 } };
    };
    github.rest.pulls.listReviews = async () => ({ data: [{ id: 999 }] });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    const res = await runScript(post.validateAndPost, { github, context, env, cwd: dir });
    assert.equal(res.failed, null);
    assert.deepEqual(
        tried.map(p => [p.event, p.comments.length]),
        [
            ['REQUEST_CHANGES', 1],
            ['COMMENT', 1],
            ['REQUEST_CHANGES', 0]
        ]
    );
    const posted = calls.createReview[0];
    assert.equal(posted.event, 'REQUEST_CHANGES', 'the verdict survives');
    assert.match(posted.body, /### Findings\n\n- \*\*MEDIUM · .* — Off by one\*\* \(`x:1`\)\n {2}Use <=\./);
    assert.match(posted.body, /<!-- ol-pr-review-bot f=1 -->/, 'the finding still counts');
});
test('#14526 post: a non-422 error is not retried', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(reviewWithFinding()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    let tries = 0;
    github.rest.pulls.createReview = async () => {
        tries++;
        throw Object.assign(new Error('boom'), { status: 500 });
    };
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: dir };
    await assert.rejects(runScript(post.validateAndPost, { github, context, env, cwd: dir }), /boom/);
    assert.equal(tries, 1);
});
test('#14526 postAttempts: verdict first, then COMMENT, then summary-only; no duplicates', () => {
    const show = a => a.map(x => `${x.event}/${x.inline ? 'inline' : 'summary'}`);
    assert.deepEqual(show(post.postAttempts({ event: 'APPROVE', hasInline: false })), ['APPROVE/inline', 'COMMENT/inline']);
    assert.deepEqual(show(post.postAttempts({ event: 'COMMENT', hasInline: true })), ['COMMENT/inline', 'COMMENT/summary']);
    assert.deepEqual(show(post.postAttempts({ event: 'REQUEST_CHANGES', hasInline: true })), [
        'REQUEST_CHANGES/inline',
        'COMMENT/inline',
        'REQUEST_CHANGES/summary',
        'COMMENT/summary'
    ]);
});

// ===================== #14526: review text =====================
async function postedBody(env) {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    await runScript(post.validateAndPost, { github, context, env: { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), GITHUB_WORKSPACE: dir, ...env }, cwd: dir });
    return calls.createReview[0].body;
}
test('#14526 post: the tip follows handle_push_trigger, and the footer names no one', async () => {
    const on = await postedBody({ INCREMENTAL: 'false', PUSH_REVIEW_MINUTES: '10' });
    assert.match(
        on,
        /> \[!TIP\]\n> When you push new commits, I review them once no more arrive for 10 minutes\. To review sooner, comment `@openlibrary-bot review`/
    );
    const off = await postedBody({ INCREMENTAL: 'false', PUSH_REVIEW_MINUTES: '' });
    assert.match(off, /pushed your changes, comment `@openlibrary-bot review`/);
    for (const body of [on, off]) assert.doesNotMatch(body, /on behalf of/);
});
test('#14526 post: a re-review after a base merge says which changes it covers', async () => {
    const body = await postedBody({ INCREMENTAL: 'true', REVIEW_PATHS: JSON.stringify(['x']) });
    assert.match(body, /^\*Reviewing the PR's own changes to the files its commits since my last pass touched\. Merges of the base branch are skipped\.\*/);
});
test('#14526 range: push_review_minutes is set only when push reviews are on', async () => {
    const { github } = mergeScenario({ head: H });
    writeFileSync(join(dir, '.pr_agent.toml'), '[github_action_config]\nhandle_push_trigger = true\n');
    const res = await runRange(github);
    assert.equal(res.outputs.push_review_minutes, '10');
});
test('#14526 filterDiff: keeps whole file blocks by path, matching either name of a rename', () => {
    const { filterDiff } = load(join(SCRIPTS, 'shared.cjs'));
    const renamed = 'diff --git a/old.py b/new.py\nsimilarity index 90%\nrename from old.py\nrename to new.py\n';
    const deleted = 'diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n';
    const diff = prDiff + renamed + deleted;
    assert.equal(filterDiff(diff, ['old.py']), renamed);
    assert.equal(filterDiff(diff, ['gone.py']), deleted);
    assert.equal(filterDiff(diff, ['a.py', 'nope.py']), 'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n+a.py\n');
    assert.equal(filterDiff(diff, []), '');
});
