// Tests for the resolve job (resolve.cjs): it accepts only a short JSON list of review thread ids,
// and it does nothing but resolve them.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, '..', '..', '..');
const { parseThreadIds, resolveThreads } = createRequire(import.meta.url)(join(ROOT, '.github', 'scripts', 'code_review', 'resolve.cjs'));
const workflow = yaml.load(readFileSync(join(ROOT, '.github', 'workflows', 'code_review_action.yml'), 'utf8'));

test('parseThreadIds: a list of thread ids, deduplicated', () => {
    assert.deepEqual(parseThreadIds('["PRRT_kwDOAAEP6c64r1Dz","PRRT_a-b_c","PRRT_kwDOAAEP6c64r1Dz"]'), ['PRRT_kwDOAAEP6c64r1Dz', 'PRRT_a-b_c']);
    assert.deepEqual(parseThreadIds('[]'), []);
});
test('parseThreadIds: anything else is rejected', () => {
    for (const raw of [
        undefined,
        '',
        'not json',
        '"PRRT_x"',
        '{"id":"PRRT_x"}',
        '[1]',
        '["PRRT_"]',
        '["PR_kwDOAAEP6c"]', // a pull request id, not a thread
        '["PRRT_x y"]',
        '["PRRT_x\\n"]',
        JSON.stringify(Array.from({ length: 101 }, (_, i) => `PRRT_${i}`))
    ]) {
        assert.equal(parseThreadIds(raw), null, `rejects ${raw}`);
    }
});

function run(threadIds, { failOn = [] } = {}) {
    const calls = [];
    const out = { failed: null, warnings: [] };
    const github = {
        graphql: async (query, vars) => {
            calls.push({ query, vars });
            if (failOn.includes(vars.id)) throw new Error('Resource not accessible by integration');
            return { resolveReviewThread: { thread: { id: vars.id, isResolved: true } } };
        }
    };
    const core = {
        info: () => {},
        warning: m => out.warnings.push(m),
        setFailed: m => {
            out.failed = m;
        }
    };
    return resolveThreads({ github, core, process: { env: { THREAD_IDS: threadIds } } }).then(() => ({ ...out, calls }));
}

test('resolveThreads: one resolveReviewThread mutation per id, and no other call', async () => {
    const { calls, failed } = await run('["PRRT_a","PRRT_b"]');
    assert.equal(failed, null);
    assert.deepEqual(
        calls.map(c => c.vars),
        [{ id: 'PRRT_a' }, { id: 'PRRT_b' }]
    );
    for (const c of calls) assert.match(c.query, /^mutation\(\$id:ID!\)\{ resolveReviewThread\(input:\{threadId:\$id\}\)/);
});
test('resolveThreads: bad input fails the job before any API call', async () => {
    const { calls, failed } = await run('["PRRT_a","oops"]');
    assert.deepEqual(calls, []);
    assert.match(failed, /not a JSON list of review thread ids/);
});
test('resolveThreads: a failed resolve still tries the rest, then fails the job', async () => {
    const { calls, failed, warnings } = await run('["PRRT_a","PRRT_b"]', { failOn: ['PRRT_a'] });
    assert.equal(calls.length, 2);
    assert.equal(warnings.length, 1);
    assert.match(failed, /1 review thread\(s\) could not be resolved/);
});

test('workflow: the resolve job holds only the job token, gets only the ids, and runs after post', () => {
    const job = workflow.jobs.resolve;
    assert.deepEqual(job.needs, 'post');
    assert.deepEqual(job.permissions, { contents: 'write', 'pull-requests': 'write' });
    const text = JSON.stringify(job);
    assert.doesNotMatch(text, /secrets\./, 'no PAT or other secret');
    assert.doesNotMatch(text, /needs\.analyze/, "nothing from the model's job");
    const step = job.steps.find(s => (s.uses || '').startsWith('actions/github-script@'));
    assert.equal(step.with['github-token'], undefined, 'the default GITHUB_TOKEN');
    assert.deepEqual(step.env, { THREAD_IDS: '${{ needs.post.outputs.resolve_thread_ids }}' });
    assert.ok(workflow.jobs.status.needs.includes('resolve'), 'status reads the threads after they are resolved');
});
