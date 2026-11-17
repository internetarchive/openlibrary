// Tests for ticket context, where the reviewer checks a PR against the issues it links to:
//   1. linked_issues.cjs: findIssueNumbers, branchIssueNumbers and the whole step.
//   2. gate.cjs on the `ticket_compliance` field.
//   3. post.cjs's renderTicketCompliance and the whole post step.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const WF = join(here, '..', '..', '..', '.github', 'workflows', 'code_review_action.yml');
const workflowText = readFileSync(WF, 'utf8');
const workflow = yaml.load(workflowText);
const SCRIPTS = join(here, '..', '..', '..', '.github', 'scripts', 'code_review');
const load = createRequire(import.meta.url);
const gate = load(join(SCRIPTS, 'gate.cjs'));
const linkedIssues = load(join(SCRIPTS, 'linked_issues.cjs'));
const post = load(join(SCRIPTS, 'post.cjs'));
const SHA = c => c.repeat(40);
const OWNER = 'internetarchive',
    REPO = 'openlibrary';
const URL = n => `https://github.com/${OWNER}/${REPO}/issues/${n}`;
const context = { repo: { owner: OWNER, repo: REPO }, eventName: 'pull_request_target', payload: {}, runId: 1, serverUrl: 'https://github.com' };

async function runScript(stepFn, { github, env, cwd }) {
    const recorded = { failed: null, infos: [] };
    const core = {
        setOutput: () => {},
        setFailed: m => {
            recorded.failed = m;
        },
        info: m => recorded.infos.push(m),
        warning: () => {},
        notice: () => {},
        debug: () => {}
    };
    const realRequire = (await import('node:module')).createRequire(import.meta.url);
    const realFs = realRequire('fs');
    const { isAbsolute, join: pjoin } = realRequire('path');
    const resolve = p => (cwd && typeof p === 'string' && !isAbsolute(p) ? pjoin(cwd, p) : p);
    const fs = new Proxy(realFs, {
        get(target, prop) {
            if (prop === 'readFileSync') return (p, ...a) => target.readFileSync(resolve(p), ...a);
            if (prop === 'writeFileSync') return (p, ...a) => target.writeFileSync(resolve(p), ...a);
            return target[prop];
        }
    });
    await stepFn({ github, context, core, require: id => (id === 'fs' ? fs : realRequire(id)), process: { env: { ...env } } });
    return recorded;
}

function withDir(fn) {
    const d = mkdtempSync(join(tmpdir(), 'cr14519-'));
    return Promise.resolve(fn(d)).finally(() => rmSync(d, { recursive: true, force: true }));
}

// ================================ 1. Fetching the linked issues ================================
const FETCH = linkedIssues.fetchLinkedIssues;
const { findIssueNumbers, branchIssueNumbers } = linkedIssues;

test("findIssueNumbers: #N, this repo's issue URLs and owner/repo#N, in order, deduped", () => {
    const body = `Closes #12. See ${URL(34)} and internetarchive/openlibrary#56, and #12 again. Also https://github.com/InternetArchive/OpenLibrary/issues/0078.`;
    assert.deepEqual(findIssueNumbers(body, OWNER, REPO), [12, 34, 56, 78]);
});

test('findIssueNumbers: skips other repos, HTML comments, link text, entities, glued and long numbers', () => {
    const body = [
        'https://github.com/other/repo/issues/1',
        'other/repo#2',
        '<!-- What issue does this PR close? #3 -->',
        '[#4](https://example.com/changelog)',
        '<a href="https://example.com">#5</a>',
        '&#6;',
        'word#7',
        '#1234567',
        'colour #0a0a0a',
        'pull request https://github.com/internetarchive/openlibrary/pull/8'
    ].join('\n');
    assert.deepEqual(findIssueNumbers(body, OWNER, REPO), []);
    assert.deepEqual(findIssueNumbers(null, OWNER, REPO), []);
});

test("branchIssueNumbers: this repo's {issue}/{type}/{slug} and PR-Agent's default pattern, not dates", () => {
    assert.deepEqual(branchIssueNumbers('14519/feature/code-review-linked-issues'), [14519]);
    assert.deepEqual(branchIssueNumbers('123-fix-thing'), [123]);
    assert.deepEqual(branchIssueNumbers('feature/45-thing'), [45]);
    assert.deepEqual(branchIssueNumbers('release/2026-11-15'), []);
    assert.deepEqual(branchIssueNumbers('master'), []);
    assert.deepEqual(branchIssueNumbers(undefined), []);
});

// A mocked GitHub for the fetch step. `issues` maps a number to an issue, a PR, or an HTTP status to throw.
function fetchGitHub({ pr, issues = {}, prThrows = false }) {
    const asked = [];
    const github = {
        rest: {
            pulls: {
                get: async () => {
                    if (prThrows) throw new Error('boom');
                    return { data: pr };
                }
            },
            issues: {
                get: async ({ owner, repo, issue_number }) => {
                    assert.equal(owner, OWNER);
                    assert.equal(repo, REPO);
                    asked.push(issue_number);
                    const v = issues[issue_number];
                    if (v === undefined || typeof v === 'number') {
                        const e = new Error('Not Found');
                        e.status = v || 404;
                        throw e;
                    }
                    return { data: v };
                }
            }
        }
    };
    return { github, asked };
}
const issue = (n, extra = {}) => ({ number: n, html_url: URL(n), title: `Issue ${n}`, body: `Body ${n}`, labels: [], ...extra });

test('fetch step: writes up to 3 linked issues with title, body and labels; skips PRs, missing and moved issues', () =>
    withDir(async d => {
        const { github, asked } = fetchGitHub({
            pr: { title: 'Fix the thing (#16)', body: 'Closes #10\nCloses #11, #12, #13, #14, #15', head: { ref: '17/fix/thing' } },
            issues: {
                10: issue(10, { pull_request: { url: 'x' } }), // a PR, not an issue
                11: issue(11, { body: `<!-- template hint -->Real ask.${'x'.repeat(20000)}`, labels: [{ name: 'Type: Bug' }, 'Priority: 2'] }),
                12: 410, // deleted
                13: issue(13, { html_url: 'https://github.com/elsewhere/repo/issues/99' }), // transferred
                14: issue(14, { body: null }),
                15: issue(15),
                16: issue(16),
                17: issue(17)
            }
        });
        const res = await runScript(FETCH, { github, env: { PR: '1', GITHUB_WORKSPACE: d } });
        assert.equal(res.failed, null);
        const out = JSON.parse(readFileSync(join(d, 'linked-issues.json'), 'utf8'));
        assert.deepEqual(
            out.map(t => t.ticket_id),
            [11, 14, 15]
        );
        assert.deepEqual(asked, [10, 11, 12, 13, 14, 15], 'stops once 3 issues are found');
        const [first, second] = out;
        assert.equal(first.ticket_url, URL(11));
        assert.equal(first.title, 'Issue 11');
        assert.deepEqual(first.labels, ['Type: Bug', 'Priority: 2']);
        assert.ok(first.body.startsWith('Real ask.'), 'HTML comments are dropped');
        assert.equal(first.body.length, 10000 + 3, 'body capped at 10,000 characters plus "..."');
        assert.ok(first.body.endsWith('...'));
        assert.equal(second.body, '');
    }));

test('fetch step: the branch name comes after the body and before the title', () =>
    withDir(async d => {
        const { github, asked } = fetchGitHub({
            pr: { title: 'Thing for #3', body: 'Part of #1', head: { ref: '2/feature/thing' } },
            issues: { 1: issue(1), 2: issue(2), 3: issue(3) }
        });
        await runScript(FETCH, { github, env: { PR: '1', GITHUB_WORKSPACE: d } });
        assert.deepEqual(asked, [1, 2, 3]);
    }));

test('fetch step: no linked issues, or a failed lookup, writes [] and never fails the run', () =>
    withDir(async d => {
        for (const opts of [{ pr: { title: 'x', body: null, head: { ref: 'master' } } }, { prThrows: true }]) {
            const { github } = fetchGitHub(opts);
            const res = await runScript(FETCH, { github, env: { PR: '1', GITHUB_WORKSPACE: d } });
            assert.equal(res.failed, null);
            assert.deepEqual(JSON.parse(readFileSync(join(d, 'linked-issues.json'), 'utf8')), []);
        }
    }));

test('fetch step runs before the model, only when a review runs, with a read-only issues scope', () => {
    const steps = workflow.jobs.analyze.steps;
    const fetchIdx = steps.findIndex(s => (s.name || '').includes('Fetch linked issues'));
    const modelIdx = steps.findIndex(s => (s.uses || '').includes('claude-code-action'));
    assert.ok(fetchIdx > 0 && fetchIdx < modelIdx, 'linked issues are fetched before the model runs');
    assert.match(steps[fetchIdx].if, /skip == 'false'/);
    assert.match(steps[fetchIdx].if, /repost != 'true'/);
    assert.equal(steps[fetchIdx].with['github-token'], undefined, 'uses the job token, not a PAT');
    assert.equal(workflow.jobs.analyze.permissions.issues, 'read');
});

// ================================ 2. The gate ================================
const dims = () => ({
    correctness: { status: 'none', note: 'ok' },
    security: { status: 'none', note: 'ok' },
    accessibility: { status: 'none', note: 'ok' },
    test_coverage: { status: 'none', note: 'ok' },
    styleguide: { status: 'none', note: 'ok' }
});
const ticket = (extra = {}) => ({
    ticket_url: URL(123),
    ticket_requirements: ['Show the count', 'Hide it for one edition'],
    fully_compliant_requirements: ['Show the count'],
    not_compliant_requirements: ['Hide it for one edition'],
    requires_further_human_verification: [],
    ...extra
});
const reviewWith = (ticket_compliance, findings = []) => ({ summary: 'A plain summary.', dimensions: dims(), findings, ticket_compliance });

test('gate: a well-formed ticket_compliance is published without ticket_requirements', () => {
    const res = gate.check(reviewWith([ticket()]));
    assert.equal(res.publish, true);
    assert.deepEqual(res.clean.ticket_compliance, [
        {
            ticket_url: URL(123),
            fully_compliant_requirements: ['Show the count'],
            not_compliant_requirements: ['Hide it for one edition'],
            requires_further_human_verification: []
        }
    ]);
});

test('gate: ticket_compliance is optional, and absent result lists become []', () => {
    assert.deepEqual(gate.check(reviewWith(undefined)).clean.ticket_compliance, []);
    assert.deepEqual(gate.check(reviewWith(null)).clean.ticket_compliance, []);
    const res = gate.check(reviewWith([{ ticket_url: URL(1), ticket_requirements: ['a'], fully_compliant_requirements: ['a'] }]));
    assert.equal(res.publish, true);
    assert.deepEqual(res.clean.ticket_compliance[0].not_compliant_requirements, []);
    assert.deepEqual(res.clean.ticket_compliance[0].requires_further_human_verification, []);
});

test('gate: a malformed ticket_compliance withholds the whole review', () => {
    const bad = [
        'not an array',
        { ticket_url: URL(1) },
        [ticket(), ticket({ ticket_url: URL(2) }), ticket({ ticket_url: URL(3) }), ticket({ ticket_url: URL(4) })], // more than 3
        [ticket(), ticket()], // duplicate
        [null],
        [[]],
        [ticket({ ticket_url: 'https://evil.example/issues/1' })],
        [ticket({ ticket_url: `${URL(1)})[click](https://evil.example` })],
        [ticket({ ticket_url: URL(0) })],
        [ticket({ ticket_url: 123 })],
        [ticket({ ticket_requirements: [] })],
        [ticket({ ticket_requirements: 'a string' })],
        [ticket({ ticket_requirements: [7] })],
        [ticket({ fully_compliant_requirements: 'a string, not a list' })],
        [ticket({ not_compliant_requirements: [''] })],
        [ticket({ requires_further_human_verification: [' '] })],
        [ticket({ fully_compliant_requirements: [42] })]
    ];
    for (const tc of bad) {
        const res = gate.check(reviewWith(tc));
        assert.equal(res.publish, false, JSON.stringify(tc));
        assert.equal(res.blocking, true, 'a malformed review fails closed');
    }
});

test('gate: published compliance text goes through the security scan; the unpublished requirements do not', () => {
    const tripped = gate.check(reviewWith([ticket({ not_compliant_requirements: ['The password reset token is never checked'] })]));
    assert.equal(tripped.publish, false);
    assert.equal(tripped.blocking, false, 'a backstop hit with no findings does not block (unchanged D3a rule)');
    const internal = gate.check(reviewWith([ticket({ ticket_requirements: ['Rotate the password reset token'] })]));
    assert.equal(internal.publish, true, 'ticket_requirements is never published, so it is not scanned');
    assert.ok(!JSON.stringify(internal.clean).includes('password'));
    // A secret shape in a published list withholds too.
    assert.equal(gate.check(reviewWith([ticket({ fully_compliant_requirements: [`ghp_${'a'.repeat(36)}`] })])).publish, false);
});

test('gate: the allowlisted copy passes the gate again (post re-checks it)', () => {
    const first = gate.check(reviewWith([ticket()]));
    const again = gate.check(JSON.parse(JSON.stringify(first.clean)));
    assert.equal(again.publish, true);
    assert.deepEqual(again.clean, first.clean);
});

test('gate: ticket compliance never changes the finding count or the blocking bit', () => {
    const allMissing = ticket({ fully_compliant_requirements: [], not_compliant_requirements: ['Show the count', 'Hide it'] });
    const res = gate.check(reviewWith([allMissing]));
    assert.equal(res.publish, true);
    assert.equal(res.findingsTotal, 0);
    assert.equal(res.blocking, false);
});

// ================================ 3. Rendering ================================
const POST = post.validateAndPost;
const render = post.renderTicketCompliance;
const entry = (n, met, notMet, human) => ({
    ticket_url: URL(n),
    fully_compliant_requirements: met,
    not_compliant_requirements: notMet,
    requires_further_human_verification: human
});

test('render: per-issue levels follow PR-Agent', () => {
    const cases = [
        [['a'], [], [], 'Fully compliant'],
        [['a'], ['b'], [], 'Partially compliant'],
        [['a'], ['b'], ['c'], 'Partially compliant'],
        [['a'], [], ['c'], 'PR Code Verified'],
        [[], ['b'], [], 'Not compliant'],
        [[], ['b'], ['c'], 'Not compliant'],
        [[], [], ['c'], 'PR Code Verified']
    ];
    for (const [met, notMet, human, level] of cases) {
        const md = render([entry(7, met, notMet, human)], OWNER, REPO);
        assert.ok(md.includes(`**[#7](${URL(7)}) - ${level}**`), `${JSON.stringify([met, notMet, human])} -> ${level}\n${md}`);
    }
});

test('render: overall mark follows PR-Agent', () => {
    const full = entry(1, ['a'], [], []),
        verified = entry(2, ['a'], [], ['c']),
        partial = entry(3, ['a'], ['b'], []),
        none = entry(4, [], ['b'], []);
    const mark = es => render(es, OWNER, REPO).split('\n')[2];
    assert.equal(mark([full]), '### 🎫 Ticket compliance analysis ✅');
    assert.equal(mark([full, verified]), '### 🎫 Ticket compliance analysis ✅');
    assert.equal(mark([full, partial]), '### 🎫 Ticket compliance analysis 🔶');
    assert.equal(mark([full, none]), '### 🎫 Ticket compliance analysis 🔶');
    assert.equal(mark([none]), '### 🎫 Ticket compliance analysis ❌');
});

test('render: lists as bullets on one line each; skips empty entries and other repos', () => {
    const md = render(
        [
            entry(1, ['Shows the\ncount'], ['Hides it'], ['Check on a phone']),
            entry(2, [], [], []),
            { ...entry(3, ['a'], [], []), ticket_url: 'https://github.com/other/repo/issues/3' }
        ],
        OWNER,
        REPO
    );
    assert.ok(md.includes('Compliant requirements:\n\n- Shows the count'));
    assert.ok(md.includes('Non-compliant requirements:\n\n- Hides it'));
    assert.ok(md.includes('Requires further human verification:\n\n- Check on a phone'));
    assert.ok(!md.includes('#2]') && !md.includes('other/repo'));
    assert.equal(render([], OWNER, REPO), '');
    assert.equal(render([entry(2, [], [], [])], OWNER, REPO), '');
});

function postGitHub() {
    const calls = { createReview: [] };
    const github = {
        rest: {
            pulls: {
                get: async () => ({ data: { head: { sha: SHA('a') }, user: { login: 'contributor' } } }),
                listReviews: async () => ({ data: [{ id: 999, user: { login: 'openlibrary-bot' }, commit_id: SHA('a') }] }),
                createReview: async p => {
                    calls.createReview.push(p);
                    return { data: { id: 999 } };
                }
            },
            repos: { compareCommitsWithBasehead: async () => ({ data: { commits: [] } }), listCommits: async () => ({ data: [] }) }
        },
        paginate: async (method, params) => (await method(params)).data,
        graphql: async () => ({ repository: { pullRequest: { reviewThreads: { nodes: [], pageInfo: { hasNextPage: false, endCursor: null } } } } })
    };
    return { github, calls };
}

test('post: the compliance section sits before Dimensions and does not change the verdict', () =>
    withDir(async d => {
        writeFileSync(join(d, 'review.json'), JSON.stringify(gate.check(reviewWith([ticket()])).clean));
        writeFileSync(join(d, 'review.diff'), '');
        const { github, calls } = postGitHub();
        const env = { PR: '1', HEAD_SHA: SHA('a'), BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: d };
        const res = await runScript(POST, { github, env, cwd: d });
        assert.equal(res.failed, null);
        assert.equal(calls.createReview.length, 1);
        const { body, event } = calls.createReview[0];
        assert.equal(event, 'APPROVE', 'a not-compliant requirement is information, not a blocking finding');
        const at = body.indexOf('### 🎫 Ticket compliance analysis 🔶');
        assert.ok(at > 0 && at < body.indexOf('<summary>Dimensions</summary>'), body);
        assert.ok(body.includes(`**[#123](${URL(123)}) - Partially compliant**`));
        assert.ok(body.includes('<!-- ol-pr-review-bot f=0 -->'), 'the findings marker is unchanged');
    }));

test('post: a review without ticket_compliance renders no compliance section', () =>
    withDir(async d => {
        writeFileSync(join(d, 'review.json'), JSON.stringify(gate.check(reviewWith(undefined)).clean));
        writeFileSync(join(d, 'review.diff'), '');
        const { github, calls } = postGitHub();
        const env = { PR: '1', HEAD_SHA: SHA('a'), BASE_SHA: SHA('b'), INCREMENTAL: 'false', GITHUB_WORKSPACE: d };
        await runScript(POST, { github, env, cwd: d });
        assert.ok(!calls.createReview[0].body.includes('Ticket compliance'));
    }));
