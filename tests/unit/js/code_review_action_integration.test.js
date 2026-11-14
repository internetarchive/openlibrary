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
    const recorded = { outputs: {}, failed: null };
    const core = {
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
test('D1 status: head UNCHANGED + clean -> success on the reviewed SHA', async () => {
    const head = SHA('a');
    const { github, calls } = mockGitHub({ prGet: async () => ({ data: { head: { sha: head } } }) });
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

// ===================== D2: status-aware skip + idempotent repost =====================
test('D2 range: already-reviewed head WITH a code-review status -> skip', async () => {
    const head = SHA('a');
    const { github } = mockGitHub({
        prGet: async () => ({ data: { number: 1, head: { sha: head }, base: { sha: SHA('b') }, draft: false, state: 'open' } }),
        listReviews: async () => ({ data: [{ user: { login: 'openlibrary-bot' }, commit_id: head, submitted_at: '2026-01-01' }] }),
        listStatuses: async () => ({ data: [{ context: 'code-review', state: 'success' }] })
    });
    const env = { PR: '1', GITHUB_WORKSPACE: dir };
    const ctx = { ...context, eventName: 'pull_request_target', payload: { pull_request: { number: 1 } } };
    const res = await runScript(scriptOf('analyze', 'Resolve review range'), { github, context: ctx, env });
    assert.equal(res.outputs.skip, 'true', 'a reviewed head that already has a status is skipped');
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
