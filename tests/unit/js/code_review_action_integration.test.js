// Integration tests for #14476 -- drive the ACTUAL github-script step bodies from
// code_review_action.yml against a mocked GitHub, end to end, for the three defect scenarios.
//
// Why this exists: a workflow-file change cannot be exercised from a PR (pull_request_target and
// workflow_dispatch both run the DEFAULT branch's copy of the workflow, never the PR branch's), so
// the real live run only happens post-merge. These tests are the closest pre-merge substitute: they
// extract each step's `script:` verbatim, wrap it the way actions/github-script does (an async fn
// with github/context/core/require/process injected), and run it with a mock octokit that records
// the API calls. Tested bytes == shipped bytes.
import { test, beforeEach, afterEach } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const WF = join(here, '..', '..', '..', '.github', 'workflows', 'code_review_action.yml');
const workflow = yaml.load(readFileSync(WF, 'utf8'));
const REVIEW_GATE_JS = workflow.env.REVIEW_GATE_JS;

const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

// Pull a step's script body straight out of the parsed workflow (js-yaml hands back the literal).
function scriptOf(jobName, stepMatch) {
    const job = workflow.jobs[jobName];
    const step = (job.steps || []).find(s => s.with && typeof s.with.script === 'string' && (s.name || '').includes(stepMatch));
    assert.ok(step, `step "${stepMatch}" not found in job ${jobName}`);
    return step.with.script;
}

// Run a github-script body with injected globals, exactly as actions/github-script does.
// `cwd` (optional) redirects the script's RELATIVE fs paths (review.json / review.diff, which the
// post step reads from the working directory) into the test's temp dir -- process.chdir() is not
// available in vitest workers, so we wrap fs instead.
async function runScript(body, { github, context, env, cwd }) {
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
    const wrappedRequire = id => (id === 'fs' ? wrappedFs : realRequire(id));
    const fn = new AsyncFunction('github', 'context', 'core', 'require', 'process', body);
    await fn(github, context, core, wrappedRequire, fakeProcess);
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

// ===================== D1: a push mid-run -> post NEITHER review nor status =====================
test('D1 post: head UNCHANGED -> createReview IS called', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', REVIEW_GATE_JS, GITHUB_WORKSPACE: dir };
    // post reads review.json/review.diff from cwd; run with cwd = dir.
    await runScript(scriptOf('post', 'Validate anchors'), { github, context, env, cwd: dir });
    assert.equal(calls.createReview.length, 1, 'a review on the still-current head must post');
    assert.equal(calls.createReview[0].commit_id, head);
});
test('D1 post: head MOVED -> createReview is NOT called', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify(cleanReview()));
    writeFileSync(join(dir, 'review.diff'), 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n+ok\n');
    const pinned = SHA('a'),
        live = SHA('c');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: live } } }) });
    const env = { PR: '1', HEAD_SHA: pinned, BASE_SHA: SHA('b'), INCREMENTAL: 'false', REVIEW_GATE_JS, GITHUB_WORKSPACE: dir };
    const res = await runScript(scriptOf('post', 'Validate anchors'), { github, context, env, cwd: dir });
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.equal(calls.createCommitStatus[0].sha, head);
    assert.equal(calls.createCommitStatus[0].state, 'success');
});
test('D1 status FALSE-GREEN guard: POST_RESULT=success but NO review on this head (force-push revert) -> NOT success', async () => {
    // Finding 1 (adversarial): post returns success WITHOUT posting when its head-guard fires. If the
    // head is then force-pushed back to the reviewed SHA, the status head-guard passes (same SHA) and
    // the normal path would green an UNREVIEWED commit. The normal path must confirm a bot review was
    // actually posted on this exact head (ground truth), mirroring the repost path -- not trust
    // POST_RESULT alone. With no bot review on the head, success is forbidden.
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.equal(calls.createCommitStatus.length, 1);
    assert.notEqual(calls.createCommitStatus[0].state, 'success', 'a head with no posted review must never read success');
});

// ===================== D2: status-aware skip + idempotent repost =====================
test('D2 range: already-reviewed head WITH a MATCHING code-review status -> skip', async () => {
    // #14486: "skip" now means the present status MATCHES the review's implied verdict -- here a clean
    // review (marker f=0, no unresolved threads) and a present `success`. (Pre-#14486 this skipped on
    // mere presence of any code-review status; that is exactly the bug the stale-status test below pins.)
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
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'true', 'a reviewed head whose status matches the verdict is skipped');
});
// #14486 -- STATE-aware skip. The headline blocker: an already-reviewed head carrying a STALE status
// (a prior `failure` that should now be `success`) was skipped on mere presence and stranded red
// forever. These cases must re-post the correct status instead of skipping.
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
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env });
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
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env });
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
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env });
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
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env });
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure');
});
test('D2 status repost: a LEGACY review with no marker FAILS CLOSED (red), never green', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({
        prGet: async () => ({ data: { head: { sha: head } } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, body: 'old review\n<!-- ol-pr-review-bot -->' }] })
    });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', REPOST: 'true', RUN_URL: 'u' };
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure', 'an unreadable count must never fabricate a green');
});

// #14486 DRIFT PIN: the resolver's implied-verdict comparison must agree with the state the status
// job's repost path would actually post for the SAME inputs. If they drift, the resolver could skip a
// head the status job would have flipped (re-stranding it) or repost one that is already correct. For
// each (marker, unresolved-thread) input we (1) run the real status repost to learn the authoritative
// state, then (2) assert the resolver skips iff the present status equals that state and reposts iff it
// differs -- so the two code paths are pinned to the same verdict by construction.
const HEAD_SHA = SHA('a');
const reviewObjs = bodies => bodies.map(body => ({ user: { login: 'openlibrary-bot' }, commit_id: HEAD_SHA, submitted_at: '2026-01-01', body }));
for (const scenario of [
    { reviews: ['x\n<!-- ol-pr-review-bot f=0 -->'], threads: [] }, // clean -> success
    { reviews: ['x\n<!-- ol-pr-review-bot f=3 -->'], threads: [] }, // findings -> failure
    { reviews: ['x\n<!-- ol-pr-review-bot f=0 -->'], threads: [{ isResolved: false, isOutdated: false }] }, // open thread -> failure
    { reviews: ['legacy, no marker'], threads: [] }, // unreadable -> failure (fail closed)
    // Finding 1 divergence class: >=2 bot reviews on the head where the LAST has an empty body and an
    // EARLIER one carries the readable marker. The status path filters `&& r.body` (picks the f=0 one);
    // the resolver must select the SAME review, or it picks the trailing empty body (-> fail closed)
    // and the two verdicts disagree -- re-stranding the head. Pins resolver selection == status path.
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
        await runScript(scriptOf('status', 'Decide the gate'), {
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
            return runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env: { PR: '1', GITHUB_WORKSPACE: dir } });
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
    // The resolver's new threads read must not throw out of the range step: an unset `skip` would stop
    // the status job (its `if` needs skip=='false'), so a transient GraphQL 502/rate-limit would make
    // the run red AND skip the repost. On a threads-read failure we fail SAFE -> repost, and the
    // authoritative status job recomputes.
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
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env: { PR: '1', GITHUB_WORKSPACE: dir } });
    assert.equal(res.failed, null, 'a transient threads read must not fail the analyze job');
    assert.equal(res.outputs.skip, 'false', 'it falls back to NOT skipping');
    assert.equal(res.outputs.repost, 'true', 'and routes to the authoritative status repost');
});

// ===================== D3a: finding-driven status (withhold -> not automatically red) =========
test('D3a analyze-gate: a backstop-tripping review with 0 findings -> withheld, NON-blocking', async () => {
    const review = cleanReview();
    review.summary = 'This change guards against a SQL injection in the query builder.'; // trips the backstop
    writeFileSync(join(dir, 'review.json'), JSON.stringify(review));
    const { github } = mockGitHub();
    const env = { REVIEW_GATE_JS, GITHUB_WORKSPACE: dir };
    const res = await runScript(scriptOf('analyze', 'Gate the analysis'), { github, context, env });
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
    const env = { REVIEW_GATE_JS, GITHUB_WORKSPACE: dir };
    const res = await runScript(scriptOf('analyze', 'Gate the analysis'), { github, context, env });
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
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
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.equal(calls.createCommitStatus[0].state, 'failure');
    assert.equal(calls.createCommitStatus[0].description, 'A finding was delivered privately; maintainer review required.');
    assert.ok(!/\d/.test(calls.createCommitStatus[0].description), 'the description carries no count');
});
test('D3a post: a withheld stub -> createReview NOT called, exits clean (no hard failure)', async () => {
    writeFileSync(join(dir, 'review.json'), JSON.stringify({ withheld: true }));
    writeFileSync(join(dir, 'review.diff'), '');
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, BASE_SHA: SHA('b'), INCREMENTAL: 'false', REVIEW_GATE_JS, GITHUB_WORKSPACE: dir };
    const res = await runScript(scriptOf('post', 'Validate anchors'), { github, context, env, cwd: dir });
    assert.equal(calls.createReview.length, 0, 'nothing public is posted for a withheld review');
    assert.equal(res.failed, null, 'and the job does not hard-fail -- the status job decides');
});

// ===================== pending: early "review in progress" status =====================
const prCtx = { ...context, payload: { pull_request: { number: 1 } } };
const runPending = async handlers => {
    const { github, calls } = mockGitHub(handlers);
    await runScript(scriptOf('pending', 'review in progress'), { github, context: prCtx, env: { RUN_URL: 'u' } });
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
test('status: analyze died before posting a review -> the pending head gets failure', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '1', HEAD_SHA: head, POST_RESULT: 'skipped', RUN_URL: 'u' };
    await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
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
    const { summary } = await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.match(summary, /## Code review: #7 @ aaaaaaa/);
    assert.match(summary, /\| Range \| incremental since bbbbbbb \|/);
    assert.match(summary, /\| Findings \| 0 \|/);
    assert.match(summary, /\| Status \| success: Review passed; all feedback resolved\. \|/);
});
test('summary: a withheld review shows no findings count', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
    const env = { PR: '7', HEAD_SHA: head, POST_RESULT: 'success', PUBLIC_FINDINGS_COUNT: '0', WITHHELD: 'true', WITHHELD_BLOCKING: 'true', RUN_URL: 'u' };
    const { summary } = await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.match(summary, /\| Findings \| — \|/);
    assert.ok(!/\d+ findings?/.test(summary), 'no count of withheld findings');
});
test('summary: head moved during the review -> says so and that no status was posted', async () => {
    const { github } = mockGitHub({ prGet: async () => ({ data: { head: { sha: SHA('c') } } }) });
    const env = { PR: '7', HEAD_SHA: SHA('a'), POST_RESULT: 'success', RUN_URL: 'u' };
    const { summary } = await runScript(scriptOf('status', 'Decide the gate'), { github, context, env });
    assert.match(summary, /\| Status \| none: the PR moved to ccccccc during the review/);
});
