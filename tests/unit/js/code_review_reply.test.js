// Tests for the replies to an @openlibrary-bot comment that doesn't start a review (reply.cjs), and
// for the `decline` and `skipped` jobs in code_review_action.yml.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const load = createRequire(import.meta.url);
const reply = load(join(ROOT, '.github', 'scripts', 'code_review', 'reply.cjs'));
const range = load(join(ROOT, '.github', 'scripts', 'code_review', 'range.cjs'));
const config = load(join(ROOT, '.github', 'scripts', 'code_review', 'config.cjs'));
const workflow = yaml.load(readFileSync(join(ROOT, '.github', 'workflows', 'code_review_action.yml'), 'utf8'));

const settings = (push = true, minutes = 10) => {
    const s = config.defaults();
    s.github_action_config.handle_push_trigger = push;
    s.openlibrary_reviewer.push_review_delay_minutes = minutes;
    return s;
};
const DOC = /\[how the code review bot works\]\(https:\/\/github\.com\/internetarchive\/openlibrary\/blob\/master\/docs\/code-review-bot\.md\)/;

test('declineText: who can ask, when reviews start on their own, and the doc', () => {
    const t = reply.declineText({ login: 'someone', settings: settings(true, 15) });
    assert.match(t, /^Hi @someone, I can only start a review when this PR's author or an Open Library maintainer asks\./);
    assert.match(t, /I review new PRs, and review again 15 minutes after new commits stop arriving\./);
    assert.match(t, DOC);
    assert.doesNotMatch(reply.declineText({ login: 'x', settings: settings(false) }), /minutes/, 'no push promise when push reviews are off');
});
test('skippedText: draft, closed, and an already-reviewed commit', () => {
    assert.match(reply.skippedText({ reason: 'draft', settings: settings() }), /is a draft/);
    assert.match(reply.skippedText({ reason: 'closed', settings: settings() }), /is closed/);
    const t = reply.skippedText({ reason: 'reviewed', sha: 'abcdef1234', settings: settings() });
    assert.match(t, /already reviewed this commit \(`abcdef1`\)/);
    assert.match(t, /I'll review them 10 minutes after new commits stop arriving\./);
    assert.match(t, DOC);
    assert.match(reply.skippedText({ reason: 'reviewed', sha: 'a', settings: settings(false) }), /Push new commits, then ask again\./);
    assert.equal(reply.skippedText({ reason: 'other', settings: settings() }), null);
});

function mockGitHub(existing = []) {
    const created = [];
    const github = {
        paginate: async () => existing,
        rest: { issues: { listComments: () => {}, createComment: async p => created.push(p) } }
    };
    return { github, created };
}
test('postOnce: posts with the tag, and never twice', async () => {
    const tag = reply.marker('decline', 'someone');
    let m = mockGitHub();
    assert.equal(await reply.postOnce({ ...m, owner: 'o', repo: 'r', issue_number: 1, body: 'Hi', tag }), true);
    assert.equal(m.created[0].body, `Hi\n\n${tag}`);
    m = mockGitHub([{ user: { login: 'openlibrary-bot' }, body: `Hi\n\n${tag}` }]);
    assert.equal(await reply.postOnce({ ...m, owner: 'o', repo: 'r', issue_number: 1, body: 'Hi', tag }), false);
    assert.equal(m.created.length, 0);
    m = mockGitHub([{ user: { login: 'someone' }, body: tag }]);
    assert.equal(await reply.postOnce({ ...m, owner: 'o', repo: 'r', issue_number: 1, body: 'Hi', tag }), true, "someone else's copy of the tag doesn't count");
});

test('range: a draft or closed PR skips with a reason', async () => {
    for (const [pr, reason] of [
        [{ draft: true, state: 'open' }, 'draft'],
        [{ draft: false, state: 'closed' }, 'closed']
    ]) {
        const outputs = {};
        const core = { info: () => {}, setOutput: (k, v) => (outputs[k] = v) };
        const github = { rest: { pulls: { get: async () => ({ data: pr }) } } };
        await range.resolveRange({
            github,
            context: { repo: { owner: 'o', repo: 'r' }, eventName: 'issue_comment', payload: { issue: { number: 1 } } },
            core,
            require: load,
            process: { env: {} }
        });
        assert.deepEqual(outputs, { skip: 'true', skip_reason: reason });
    }
});

// ========================= the jobs =========================
const staffList = cond => /fromJSON\('(\[[^\]]*\])'\)/.exec(cond)[1];
test('decline: the same maintainers as analyze, inverted, and never for bots', () => {
    const d = workflow.jobs.decline.if;
    assert.equal(staffList(d), staffList(workflow.jobs.analyze.if));
    assert.match(
        d,
        /!\(\s*contains\(fromJSON\('\[[^\]]*\]'\), github\.event\.comment\.user\.login\) \|\|\s*github\.event\.comment\.user\.login == github\.event\.issue\.user\.login\s*\)/
    );
    assert.match(d, /github\.event\.comment\.user\.type != 'Bot'/);
    assert.match(d, /github\.event\.comment\.user\.login != 'openlibrary-bot'/);
    assert.match(d, /contains\(github\.event\.comment\.body, '@openlibrary-bot'\)/);
});
test('skipped: only for comments, after analyze skipped with a reason', () => {
    const j = workflow.jobs.skipped;
    assert.equal(j.needs, 'analyze');
    assert.match(j.if, /github\.event_name == 'issue_comment'/);
    assert.match(j.if, /needs\.analyze\.outputs\.skip == 'true'/);
    assert.equal(workflow.jobs.analyze.outputs.skip_reason, '${{ steps.range.outputs.skip_reason }}');
});
test('decline and skipped: fixed text with the PR PAT, no model, nothing else', () => {
    for (const name of ['decline', 'skipped']) {
        const j = workflow.jobs[name];
        assert.deepEqual(j.permissions, { contents: 'read' }, name);
        const text = JSON.stringify(j);
        assert.doesNotMatch(text, /claude-code-action/, name);
        assert.deepEqual(text.match(/secrets\.\w+/g), ['secrets.OL_BOT_PR_PAT'], name);
        assert.equal(j.steps[0].with['sparse-checkout'], '/.github/scripts/\n/.pr_agent.toml\n', name);
    }
});
