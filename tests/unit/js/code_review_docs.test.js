// docs/code-review-bot.md explains the code review bot to contributors. These tests fail when the doc
// and the code disagree on the facts most likely to drift.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const read = p => readFileSync(join(ROOT, p), 'utf8');
const doc = read('docs/code-review-bot.md');
const SCRIPTS = '.github/scripts/code_review';

test('the maintainers who can trigger a review by comment match the workflow', () => {
    const workflow = yaml.load(read('.github/workflows/code_review_action.yml'));
    const inWorkflow = JSON.parse(/fromJSON\('(\[[^\]]*\])'\)/.exec(workflow.jobs.analyze.if)[1]);
    const sentence = /Commenting works for the PR's author and for these maintainers: ([^.]*)\./.exec(doc);
    assert.ok(sentence, 'the doc lists the maintainers');
    const inDoc = [...sentence[1].matchAll(/`([^`]+)`/g)].map(m => m[1]);
    assert.deepEqual([...inDoc].sort(), [...inWorkflow].sort());
});

test('every push-review delay in the doc matches .pr_agent.toml', () => {
    const minutes = Number(/^push_review_delay_minutes\s*=\s*(\d+)/m.exec(read('.pr_agent.toml'))[1]);
    const mentioned = [...doc.matchAll(/(\d+) minutes/g)].map(m => Number(m[1]));
    assert.ok(mentioned.length > 0);
    for (const n of mentioned) assert.equal(n, minutes, `the doc says ${n} minutes`);
    assert.match(doc, new RegExp(`\\| \`push_review_delay_minutes\` \\| .*\\(${minutes}\\) \\|`));
});

test('the doc lists every review area', () => {
    const { dimensions } = createRequire(import.meta.url)(join(ROOT, SCRIPTS, 'gate.cjs'));
    for (const label of Object.values(dimensions)) assert.match(doc, new RegExp(`^\\| ${label} \\|`, 'm'), label);
});

test('every fixed code-review check message is in the doc', () => {
    const messages = ['status.cjs', 'awaiting.cjs', 'pending.cjs'].flatMap(f =>
        [...read(`${SCRIPTS}/${f}`).matchAll(/description(?: =|:) '([^']+)'/g)].map(m => m[1])
    );
    assert.ok(messages.length >= 6);
    for (const m of messages) assert.ok(doc.includes(`| ${m} |`), `missing from the check table: ${m}`);
});

test('the review footer links to the doc', () => {
    assert.match(
        read(`${SCRIPTS}/post.cjs`),
        /\[How this bot works\]\(https:\/\/github\.com\/internetarchive\/openlibrary\/blob\/master\/docs\/code-review-bot\.md\)/
    );
});

test('every file the doc links to exists', () => {
    const targets = [...doc.matchAll(/\]\(\.\.\/([^)#]+)\)/g)].map(m => m[1]);
    assert.ok(targets.length > 0);
    for (const t of targets) assert.ok(existsSync(join(ROOT, t)), t);
});

// The files whose behaviour the doc describes. Each starts with a note to keep the doc in step.
const DESCRIBED = [
    '.github/workflows/code_review_action.yml',
    '.github/workflows/code_review_awaiting.yml',
    '.github/workflows/auto_assign_reviewer.yml',
    '.github/workflows/code_review_report.yml',
    '.github/workflows/code_review.md',
    '.pr_agent.toml',
    ...['range', 'post', 'resolve', 'status', 'pending', 'awaiting', 'gate', 'analyze_gate', 'config', 'linked_issues', 'shared', 'reply'].map(
        n => `${SCRIPTS}/${n}.cjs`
    )
];
test('every file the doc describes starts with a note to update the doc', () => {
    for (const f of DESCRIBED) {
        const first = read(f).split('\n')[0];
        assert.match(first, /If you change how the code review bot behaves here, update docs\/code-review-bot\.md to match\./, f);
    }
});