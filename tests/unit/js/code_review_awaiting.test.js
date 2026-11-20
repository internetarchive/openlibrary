// code_review_awaiting.yml: the awaiting status on an unreviewed head, and the review it requests
// once a reviewed PR stops getting pushes.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const load = createRequire(import.meta.url);
const SCRIPTS = join(here, '..', '..', '..', '.github', 'scripts', 'code_review');
const { markAwaiting, requestAfterQuiet } = load(join(SCRIPTS, 'awaiting.cjs'));
const config = load(join(SCRIPTS, 'config.cjs'));

const SHA = c => c.repeat(40);
const settings = (push = {}) => {
    const s = config.defaults();
    Object.assign(s.github_action_config, { handle_push_trigger: true, ...push });
    return s;
};
const core = () => {
    const out = {};
    return { out, info: () => {}, setOutput: (k, v) => (out[k] = v) };
};

function mockGitHub({ statuses = [], reviews = [], requested = { teams: [], users: [] }, parents = [SHA('p')], cmpStatus = 'diverged', live = {} } = {}) {
    const calls = { statuses: [], removed: [], requested: [] };
    const github = {
        paginate: async (method, params) => (await method(params)).data,
        rest: {
            repos: {
                listCommitStatusesForRef: async () => ({ data: statuses }),
                createCommitStatus: async p => calls.statuses.push(p),
                getCommit: async () => ({ data: { parents: parents.map(sha => ({ sha })) } }),
                compareCommitsWithBasehead: async () => ({ data: { status: cmpStatus } })
            },
            pulls: {
                listReviews: async () => ({ data: reviews }),
                listRequestedReviewers: async () => ({ data: requested }),
                get: async () => ({ data: { head: { sha: SHA('a') }, state: 'open', draft: false, ...live } }),
                removeRequestedReviewers: async p => calls.removed.push(p),
                requestReviewers: async p => calls.requested.push(p)
            }
        }
    };
    return { github, calls };
}

const context = (action = 'synchronize', sender = { login: 'alice', type: 'User' }, pr = {}) => ({
    repo: { owner: 'internetarchive', repo: 'openlibrary' },
    payload: {
        action,
        sender,
        before: SHA('p'),
        after: SHA('a'),
        pull_request: { number: 1, head: { sha: SHA('a') }, base: { ref: 'master' }, draft: false, state: 'open', ...pr }
    }
});
const reviewed = [{ user: { login: 'openlibrary-bot' } }];

async function mark(gh, ctx = context(), s = settings()) {
    const c = core();
    await markAwaiting({ github: gh.github, context: ctx, core: c, settings: s, runUrl: 'u' });
    return { posted: gh.calls.statuses, minutes: c.out.review_after_minutes };
}

test('a push to a reviewed PR says a review will start, and asks for one after the delay', async () => {
    const { posted, minutes } = await mark(mockGitHub({ reviews: reviewed }));
    assert.equal(posted.length, 1);
    assert.equal(posted[0].state, 'pending');
    assert.equal(posted[0].sha, SHA('a'));
    assert.match(posted[0].description, /^Waiting for pushes to stop\. Review starts ~\d\d:\d\d UTC, or comment @openlibrary-bot review to start now\.$/);
    assert.equal(minutes, '10');
});
test('push reviews off: a reviewed PR asks for a re-request instead', async () => {
    const { posted, minutes } = await mark(mockGitHub({ reviews: reviewed }), context(), settings({ handle_push_trigger: false }));
    assert.match(posted[0].description, /Re-request review from openlibrary-bot/);
    assert.equal(minutes, undefined);
});
test('a push while the first review is still running (team requested, no review yet) still asks for one', async () => {
    const { minutes } = await mark(mockGitHub({ requested: { teams: [{ slug: 'openlibrary-agentic-code-reviewer' }], users: [] } }));
    assert.equal(minutes, '10');
});
test('a re-requested bot user also counts as a requested review', async () => {
    const { minutes } = await mark(mockGitHub({ requested: { teams: [], users: [{ login: 'openlibrary-bot' }] } }));
    assert.equal(minutes, '10');
});
test('a PR never reviewed is not reviewed on push: a maintainer requests the first review', async () => {
    const { posted, minutes } = await mark(mockGitHub());
    assert.match(posted[0].description, /^Not reviewed yet/);
    assert.equal(minutes, undefined);
});
test('opened and ready_for_review never schedule a review (auto_assign handles those)', async () => {
    for (const action of ['opened', 'reopened', 'ready_for_review']) {
        const { minutes } = await mark(mockGitHub({ reviews: reviewed }), context(action));
        assert.equal(minutes, undefined, action);
    }
});
test('push_trigger_ignore_bot_commits: a bot push is not reviewed', async () => {
    for (const sender of [
        { login: 'renovate[bot]', type: 'Bot' },
        { login: 'openlibrary-bot', type: 'User' }
    ]) {
        const { minutes } = await mark(mockGitHub({ reviews: reviewed }), context('synchronize', sender));
        assert.equal(minutes, undefined, sender.login);
    }
    const { minutes } = await mark(
        mockGitHub({ reviews: reviewed }),
        context('synchronize', { login: 'x[bot]', type: 'Bot' }),
        settings({ push_trigger_ignore_bot_commits: false })
    );
    assert.equal(minutes, '10');
});
test('push_trigger_ignore_merge_commits: a push that only merges the base branch is not reviewed', async () => {
    const baseMerge = { reviews: reviewed, parents: [SHA('p'), SHA('m')], cmpStatus: 'ahead' };
    assert.equal((await mark(mockGitHub(baseMerge))).minutes, undefined);
    // A merge of something other than the base branch, or onto another commit, is reviewed.
    assert.equal((await mark(mockGitHub({ ...baseMerge, cmpStatus: 'diverged' }))).minutes, '10');
    assert.equal((await mark(mockGitHub({ ...baseMerge, parents: [SHA('q'), SHA('m')] }))).minutes, '10');
});
test('never overwrites an existing code-review status, and skips drafts and closed PRs', async () => {
    assert.equal((await mark(mockGitHub({ reviews: reviewed, statuses: [{ context: 'code-review', state: 'success' }] }))).posted.length, 0);
    assert.equal((await mark(mockGitHub({ reviews: reviewed }), context('synchronize', undefined, { draft: true }))).posted.length, 0);
    assert.equal((await mark(mockGitHub({ reviews: reviewed }), context('synchronize', undefined, { state: 'closed' }))).posted.length, 0);
});
test('every status description fits GitHub limit of 140 characters', async () => {
    for (const [gh, s] of [
        [mockGitHub({ reviews: reviewed }), settings()],
        [mockGitHub({ reviews: reviewed }), settings({ handle_push_trigger: false })],
        [mockGitHub(), settings()]
    ]) {
        const { posted } = await mark(gh, context(), s);
        assert.ok(posted[0].description.length <= 140, posted[0].description);
    }
});

const waiting = [{ context: 'code-review', state: 'pending', description: 'New commits. A review starts after 10 minutes with no more pushes.' }];
test('after the wait, re-requests the review team (removing a pending request first)', async () => {
    const gh = mockGitHub({ statuses: waiting });
    let waited;
    await requestAfterQuiet({ github: gh.github, context: context(), core: core(), minutes: 10, sleep: async ms => (waited = ms) });
    assert.equal(waited, 10 * 60 * 1000);
    assert.deepEqual(gh.calls.removed[0].team_reviewers, ['openlibrary-agentic-code-reviewer']);
    assert.deepEqual(gh.calls.requested[0].team_reviewers, ['openlibrary-agentic-code-reviewer']);
});
test('requests nothing if the PR moved on, closed or became a draft while waiting', async () => {
    for (const live of [{ head: { sha: SHA('b') } }, { state: 'closed' }, { draft: true }]) {
        const gh = mockGitHub({ live, statuses: waiting });
        await requestAfterQuiet({ github: gh.github, context: context(), core: core(), minutes: 10, sleep: async () => {} });
        assert.equal(gh.calls.requested.length, 0, JSON.stringify(live));
    }
});
test('requests nothing if a review was requested by hand while waiting', async () => {
    for (const status of [
        { context: 'code-review', state: 'pending', description: 'Review in progress.' },
        { context: 'code-review', state: 'success', description: 'Review passed; all feedback resolved.' }
    ]) {
        const gh = mockGitHub({ statuses: [status, ...waiting] });
        await requestAfterQuiet({ github: gh.github, context: context(), core: core(), minutes: 10, sleep: async () => {} });
        assert.equal(gh.calls.requested.length, 0, status.description);
    }
});
test('a PR with the no-automation label is not reviewed on push', async () => {
    const { posted, minutes } = await mark(mockGitHub({ reviews: reviewed }), context('synchronize', undefined, { labels: [{ name: 'no-automation' }] }));
    assert.equal(minutes, undefined);
    assert.match(posted[0].description, /Re-request review from openlibrary-bot/);
});

test('a push to a PR stacked on another branch starts no review and says how to ask', async () => {
    const ctx = context();
    ctx.payload.repository = { default_branch: 'master' };
    ctx.payload.pull_request.base = { ref: 'feature' };
    const { posted, minutes } = await mark(mockGitHub({ reviews: reviewed }), ctx);
    assert.equal(minutes, undefined);
    assert.equal(posted[0].description, 'Stacked on another branch. Comment @openlibrary-bot review to review it.');
    ctx.payload.pull_request.base = { ref: 'master' };
    assert.equal((await mark(mockGitHub({ reviews: reviewed }), ctx)).minutes, '10', 'a PR into master is reviewed as before');
});

test('the waiting status names the time the review starts, in UTC', async () => {
    const gh = mockGitHub({ reviews: reviewed });
    const c = core();
    const now = Date.parse('2026-11-20T21:25:50Z');
    await markAwaiting({ github: gh.github, context: context(), core: c, settings: settings(), runUrl: 'u', now });
    assert.equal(gh.calls.statuses[0].description, 'Waiting for pushes to stop. Review starts ~21:35 UTC, or comment @openlibrary-bot review to start now.');
    assert.ok(gh.calls.statuses[0].description.length <= 140);
});
test('after the wait, the new waiting text is recognised too; a hand-started review is not followed by another', async () => {
    const fresh = [
        {
            context: 'code-review',
            state: 'pending',
            description: 'Waiting for pushes to stop. Review starts ~21:35 UTC, or comment @openlibrary-bot review to start now.'
        }
    ];
    let gh = mockGitHub({ statuses: fresh });
    await requestAfterQuiet({ github: gh.github, context: context(), core: core(), minutes: 10, sleep: async () => {} });
    assert.equal(gh.calls.requested.length, 1);
    gh = mockGitHub({ statuses: [{ context: 'code-review', state: 'pending', description: 'Review in progress.' }] });
    await requestAfterQuiet({ github: gh.github, context: context(), core: core(), minutes: 10, sleep: async () => {} });
    assert.equal(gh.calls.requested.length, 0, 'someone commented to start it already');
});
