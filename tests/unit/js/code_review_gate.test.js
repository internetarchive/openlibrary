// Unit tests for the DISCLOSURE GATE embedded as REVIEW_GATE_JS in
// .github/workflows/code_review_action.yml. The gate is inline in the workflow and both jobs run
// it via `eval(process.env.REVIEW_GATE_JS)`; this test extracts that exact block and evals it, so
// it exercises the text that ships. See .github/workflows/code_review.md for the model contract.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const YML = join(here, '..', '..', '..', '.github', 'workflows', 'code_review_action.yml');

function extractGateSrc(ymlPath) {
    const lines = readFileSync(ymlPath, 'utf8').split('\n');
    const i = lines.findIndex(l => /^\s*REVIEW_GATE_JS:\s*\|/.test(l));
    assert.ok(i >= 0, 'REVIEW_GATE_JS block not found in the workflow');
    const body = [];
    for (let j = i + 1; j < lines.length; j++) {
        const l = lines[j];
        if (l.trim() === '') {
            body.push('');
            continue;
        }
        if (l.startsWith('    ')) body.push(l.slice(4));
        else break;
    }
    return body.join('\n');
}
// eslint-disable-next-line no-eval
const gate = (0, eval)(extractGateSrc(YML));

// ---- helpers ----
function ctx({ added = {}, baseSymbols = [] } = {}) {
    const toMap = o => new Map(Object.entries(o).map(([k, v]) => [k, new Set(v)]));
    return { added: toMap(added), baseHasSymbol: r => baseSymbols.includes(r) };
}
function review(findings = [], summary = 'This PR does a thing.') {
    const dims = {};
    for (const k of Object.keys(gate.dimensions)) {
        const n = findings.filter(f => f.dimension === k).length;
        dims[k] = { status: n ? 'findings' : 'none', note: n ? '' : 'nothing here' };
    }
    return { summary, dimensions: dims, findings };
}
const F = o => ({ dimension: 'correctness', severity: 'high', title: 't', body: 'b', ...o });
const added = { 'a.py': [10, 11, 12] };

test('clean review (no findings) -> ok, 0 public', () => {
    const r = gate.classify(review([]), ctx());
    assert.equal(r.ok, true);
    assert.equal(r.public.findings.length, 0);
});

test('malformed review -> fail-closed (ok:false, no public)', () => {
    assert.equal(gate.classify({ nope: 1 }, ctx()).ok, false);
    assert.equal(gate.classify(null, ctx()).ok, false);
    assert.equal(gate.classify({ summary: 'x', dimensions: {}, findings: 'no' }, ctx()).ok, false);
});

test('pr-introduced security finding on added lines PUBLISHES', () => {
    const f = F({
        dimension: 'security',
        title: 'Open redirect introduced',
        body: 'This PR adds a redirect to a user-supplied target without validating the host.',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced',
        sink_ref: 'new_redirect_handler'
    });
    const r = gate.classify(review([f]), ctx({ added, baseSymbols: [] }));
    assert.equal(r.public.findings.length, 1);
    assert.equal(r.private.length, 0);
});

test('pre-existing-live finding routes PRIVATE, not public', () => {
    const f = F({
        dimension: 'security',
        title: 'Live auth hole',
        body: 'Deployed code lacks a check.',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pre-existing-live',
        sink_ref: 'x'
    });
    const r = gate.classify(review([f]), ctx({ added }));
    assert.equal(r.public.findings.length, 0);
    assert.equal(r.private.length, 1);
});

test('absent disclosure field -> treated pre-existing-live (PRIVATE)', () => {
    const f = F({ path: 'a.py', start_line: 10, line: 10, sink_ref: 'x' });
    const r = gate.classify(review([f]), ctx({ added }));
    assert.equal(r.public.findings.length, 0);
    assert.equal(r.private.length, 1);
});

test('invalid disclosure enum -> malformed (fail-closed)', () => {
    const f = F({ path: 'a.py', line: 10, disclosure: 'maybe' });
    assert.equal(gate.classify(review([f]), ctx({ added })).ok, false);
});

test('sink_ref resolving on BASE -> escalate PRIVATE even if labelled pr-introduced', () => {
    const f = F({
        dimension: 'security',
        title: 'Calls unsanitized sink',
        body: 'This PR passes input to render_raw(), which does not escape.',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced',
        sink_ref: 'render_raw'
    });
    const r = gate.classify(review([f]), ctx({ added, baseSymbols: ['render_raw'] }));
    assert.equal(r.public.findings.length, 0);
    assert.equal(r.private.length, 1);
});

test('base/context-anchored pr-introduced -> escalate PRIVATE', () => {
    const f = F({ dimension: 'security', title: 'x', body: 'y', path: 'a.py', start_line: 6, line: 6, disclosure: 'pr-introduced', sink_ref: 'z' });
    const r = gate.classify(review([f]), ctx({ added }));
    assert.equal(r.public.findings.length, 0);
    assert.equal(r.private.length, 1);
});

test('shape finding with NO sink_ref -> fail-closed PRIVATE', () => {
    const f = F({
        dimension: 'security',
        title: 'SQL injection',
        body: 'User input is interpolated into the query.',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced'
    });
    assert.equal(gate.classify(review([f]), ctx({ added })).public.findings.length, 0);
});

test('non-shape pr-introduced finding with no sink_ref still POSTS (ordinary nit)', () => {
    const f = F({
        dimension: 'styleguide',
        title: 'Prefer f-string',
        body: 'Use an f-string here.',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced'
    });
    assert.equal(gate.classify(review([f]), ctx({ added })).public.findings.length, 1);
});

test('literal secret VALUE is redacted from public text; finding still posts by location', () => {
    const leaked = `ghp_${'A'.repeat(36)}`;
    const f = F({
        dimension: 'security',
        title: 'Hardcoded credential',
        body: `This PR hardcodes a token ${leaked} here.`,
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced',
        sink_ref: 'config_token'
    });
    const r = gate.classify(review([f]), ctx({ added, baseSymbols: [] }));
    assert.equal(r.public.findings.length, 1);
    assert.ok(!r.public.findings[0].body.includes(leaked), 'literal value must never appear in public text');
    assert.ok(/rotate/i.test(r.public.findings[0].body));
});

test('all-private run yields the SAME public shape as a clean run (0 public findings)', () => {
    const priv = F({ dimension: 'security', title: 'live', body: 'live', path: 'a.py', line: 10, disclosure: 'pre-existing-live', sink_ref: 'x' });
    const allPrivate = gate.classify(review([priv]), ctx({ added }));
    const clean = gate.classify(review([]), ctx());
    assert.equal(allPrivate.public.findings.length, clean.public.findings.length);
    assert.equal(allPrivate.public.findings.length, 0);
});

test('containment: private finding substance never appears in the public payload', () => {
    const secretBody = 'EXPLOIT-DETAIL-deployed-ssrf-via-internal-metadata-endpoint';
    const priv = F({
        dimension: 'security',
        title: 'SSRF in prod',
        body: secretBody,
        path: 'a.py',
        line: 10,
        disclosure: 'pre-existing-live',
        sink_ref: 'fetch_url'
    });
    const pubF = F({ dimension: 'styleguide', title: 'nit', body: 'minor', path: 'a.py', start_line: 11, line: 11, disclosure: 'pr-introduced' });
    const r = gate.classify(review([priv, pubF], 'Summary describing the PR.'), ctx({ added }));
    const blob = JSON.stringify(r.public);
    assert.ok(!blob.includes(secretBody));
    assert.ok(!blob.includes('SSRF in prod'));
    assert.equal(r.public.findings.length, 1);
});

test('MUST-FIX 1: with a private finding, the model summary is NOT rendered (neutral line)', () => {
    const leaky = 'This PR sits next to the unauthenticated /admin endpoint in deployed code.';
    const priv = F({ dimension: 'security', title: 'x', body: 'y', path: 'a.py', line: 10, disclosure: 'pre-existing-live', sink_ref: 'q' });
    const pubF = F({ dimension: 'styleguide', title: 'nit', body: 'minor', path: 'a.py', start_line: 11, line: 11, disclosure: 'pr-introduced' });
    const r = gate.classify(review([priv, pubF], leaky), ctx({ added }));
    assert.ok(!r.public.summary.includes('unauthenticated'));
    assert.ok(!r.public.summary.includes('/admin'));
    assert.match(r.public.summary, /Review of this PR's changes/);
});

test('MUST-FIX 1: with NO private findings, the model summary IS rendered (redacted)', () => {
    const s = 'This PR refactors the carousel component.';
    assert.equal(gate.classify(review([], s), ctx()).public.summary, s);
});

test('MUST-FIX 2: public finding retains disclosure + sink_ref for independent POST re-classify', () => {
    const f = F({
        dimension: 'security',
        title: 'Open redirect',
        body: 'adds a redirect',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced',
        sink_ref: 'new_handler'
    });
    const r = gate.classify(review([f]), ctx({ added, baseSymbols: [] }));
    const c = r.public.findings[0];
    assert.equal(c.disclosure, 'pr-introduced');
    assert.equal(c.sink_ref, 'new_handler');
    assert.equal(gate.routeFinding(c, ctx({ added, baseSymbols: [] })), 'public');
    assert.equal(gate.routeFinding(c, ctx({ added, baseSymbols: ['new_handler'] })), 'private');
});

test('model dimension inconsistency (status none but a finding present) -> malformed', () => {
    const r = review([F({ path: 'a.py', line: 10, disclosure: 'pr-introduced' })]);
    r.dimensions.correctness = { status: 'none', note: 'lie' };
    assert.equal(gate.classify(r, ctx({ added })).ok, false);
});

// Adversarial-review regressions (F1): a credential must not reach the public artifact through
// an un-redacted sink_ref/path, and the secrets test must be stateless.
test('[F1] credential-shaped sink_ref -> routed PRIVATE', () => {
    const leaked = `ghp_${'A'.repeat(36)}`;
    const f = F({
        dimension: 'security',
        title: 'x',
        body: 'y',
        path: 'a.py',
        start_line: 10,
        line: 10,
        disclosure: 'pr-introduced',
        sink_ref: leaked
    });
    const r = gate.classify(review([f]), ctx({ added, baseSymbols: [] }));
    assert.equal(r.public.findings.length, 0);
    assert.ok(!JSON.stringify(r.public).includes(leaked));
});
test('[F1] credential-shaped path -> routed PRIVATE', () => {
    const leaked = `AKIA${'A'.repeat(16)}`;
    const f = F({ dimension: 'styleguide', title: 'x', body: 'y', path: leaked, start_line: 10, line: 10, disclosure: 'pr-introduced' });
    assert.equal(gate.classify(review([f]), ctx({ added })).public.findings.length, 0);
});
test('[F1] secretsTest is stateless (no /g lastIndex bug)', () => {
    const v = `ghp_${'B'.repeat(36)}`;
    assert.equal(gate.secretsTest(v), true);
    assert.equal(gate.secretsTest(v), true);
});
