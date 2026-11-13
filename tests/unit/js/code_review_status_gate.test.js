// Unit tests for the CODE-REVIEW STATUS gate (#14453). Covers three things that must not drift:
//   1. The three pure helpers embedded inline in the `status` job's github-script step; this test
//      extracts the EXACT text that ships and exercises it, so tested logic == deployed logic:
//        - parseFindings(raw)                 -- the env->findings derivation, FAIL CLOSED on absent
//        - unresolvedThreadCount(threads)     -- threads that are unresolved AND not outdated
//        - decideStatus({postSucceeded,...})  -- the pass/fail + state + non-leaky description
//      (The public-findings COUNT is produced INSIDE this workflow's analyze-gate step -- the
//      `public_findings_count` output -- and consumed here via parseFindings, which blocks when absent.)
//   2. The posted commit-status context string is EXACTLY `code-review` (the branch-protection
//      ruleset requires that string; a drift makes the required gate unsatisfiable -> every PR blocked).
//   3. The ANALYZE-EXECUTION INVARIANT: the `analyze` job (which runs with secrets on untrusted fork
//      PRs under pull_request_target) must NEVER execute PR content -- no build/install/test/cache/
//      cloud-auth/language-setup step. This is the load-bearing control that makes pull_request_target
//      safe here, so a CI test fails the build if analyze gains a disallowed action or run command.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const WF = join(here, '..', '..', '..', '.github', 'workflows');
const workflowText = readFileSync(join(WF, 'code_review_action.yml'), 'utf8');
const statusLines = workflowText.split('\n');

// Extract a `const <name> = (…) => { … };` block from a workflow's lines, keyed on the closing line
// that matches the declaration's own indentation (so a nested `};` cannot truncate it), and eval it.
// The helpers are pure -- they close over nothing from the step -- so a bare `new Function` suffices.
function extractFn(lines, name) {
    const start = lines.findIndex(l => l.includes(`const ${name} =`));
    assert.ok(start >= 0, `${name} not found in workflow`);
    const indent = lines[start].match(/^(\s*)/)[1];
    const closer = `${indent}};`;
    const body = [lines[start]];
    let end = -1;
    for (let j = start + 1; j < lines.length; j++) {
        body.push(lines[j]);
        if (lines[j] === closer) {
            end = j;
            break;
        }
    }
    assert.ok(end >= 0, `end of ${name} not found`);
    const src = body
        .join('\n')
        .trim()
        .replace(new RegExp(`^const ${name} =\\s*`), '')
        .replace(/;\s*$/, '');
    // eslint-disable-next-line no-new-func
    return new Function(`return (${src});`)();
}

const parseFindings = extractFn(statusLines, 'parseFindings');
const unresolvedThreadCount = extractFn(statusLines, 'unresolvedThreadCount');
const decideStatus = extractFn(statusLines, 'decideStatus');

// ---- parseFindings: the env->findings derivation. FAIL CLOSED (absent/garbage -> null, blocks) ----
test('parseFindings returns the integer for a well-formed non-negative count', () => {
    assert.equal(parseFindings('0'), 0);
    assert.equal(parseFindings('3'), 3);
    assert.equal(parseFindings(' 7 '), 7);
});
test('parseFindings returns null (=> blocks) for absent or malformed input -- NOT 0', () => {
    // This is the H1 fail-closed guard: before the #14451 producer lands, or on a skip path, the
    // output is absent. null -> decideStatus blocks. Treating absent as 0/clean would let a review
    // with only orphaned (summary-only, un-threaded) findings pass. Each of these MUST be null.
    for (const raw of ['', undefined, null, 'abc', '-1', '3.5', '1e2', 'NaN', '0x3', ' ']) {
        assert.equal(parseFindings(raw), null, `expected null for ${JSON.stringify(raw)}`);
    }
});

// ---- unresolvedThreadCount: GitHub's own isResolved/isOutdated are authoritative ----
test('unresolvedThreadCount counts only threads that are unresolved AND not outdated', () => {
    const threads = [
        { isResolved: false, isOutdated: false }, // blocks
        { isResolved: true, isOutdated: false }, // resolved -> ok
        { isResolved: false, isOutdated: true }, // outdated by a later push -> ok
        { isResolved: true, isOutdated: true }, // ok
        { isResolved: false, isOutdated: false } // blocks
    ];
    assert.equal(unresolvedThreadCount(threads), 2);
    assert.equal(unresolvedThreadCount([]), 0);
});

// ---- decideStatus: PASS = posted-clean AND fully-resolved; bias to blocking; non-leaky text ----
test('decideStatus PASSES only when posted, zero public findings, zero unresolved', () => {
    const d = decideStatus({ postSucceeded: true, findings: 0, unresolved: 0 });
    assert.equal(d.pass, true);
    assert.equal(d.state, 'success');
    assert.match(d.description, /passed/i);
});
test('decideStatus FAILS when the review did not post cleanly (greenlight-a)', () => {
    const d = decideStatus({ postSucceeded: false, findings: 0, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
    assert.equal(d.description, 'No clean review for this commit.');
});
test('decideStatus FAILS when this pass posted public findings (singular/plural)', () => {
    const one = decideStatus({ postSucceeded: true, findings: 1, unresolved: 0 });
    assert.equal(one.state, 'failure');
    assert.equal(one.description, '1 finding to address.');
    const many = decideStatus({ postSucceeded: true, findings: 4, unresolved: 0 });
    assert.equal(many.description, '4 findings to address.');
});
test('decideStatus FAILS when prior feedback is unresolved, even with a clean pass (singular/plural)', () => {
    const one = decideStatus({ postSucceeded: true, findings: 0, unresolved: 1 });
    assert.equal(one.state, 'failure');
    assert.equal(one.description, '1 unresolved review thread.');
    const many = decideStatus({ postSucceeded: true, findings: 0, unresolved: 3 });
    assert.equal(many.description, '3 unresolved review threads.');
});
test('decideStatus FAILS CLOSED when the findings count is unavailable (null), even with zero unresolved', () => {
    // H1: an unknown count must NOT pass. null is what parseFindings returns when the producer
    // output is absent -- a review could have orphaned/summary-only findings we cannot see.
    const d = decideStatus({ postSucceeded: true, findings: null, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
    assert.equal(d.description, 'Review findings count unavailable.');
});
test('decideStatus never leaks finding content -- description is counts and fixed phrases only', () => {
    for (const c of [
        { postSucceeded: true, findings: 0, unresolved: 0 },
        { postSucceeded: false, findings: 0, unresolved: 0 },
        { postSucceeded: true, findings: 2, unresolved: 0 },
        { postSucceeded: true, findings: 0, unresolved: 2 },
        { postSucceeded: true, findings: null, unresolved: 0 }
    ]) {
        const { description } = decideStatus(c);
        // One of a small fixed set of templates -- a count plus fixed words, no free text that
        // could carry a finding's content.
        assert.match(
            description,
            /^(Review passed; all feedback resolved\.|No clean review for this commit\.|Review findings count unavailable\.|\d+ findings? to address\.|\d+ unresolved review threads?\.)$/
        );
    }
});

// ---- Context string: EXACTLY `code-review` (must match the ruleset's required-check string) ----
test('the status job posts commit status context === "code-review" (ruleset-required string)', () => {
    // A rename makes the required gate unsatisfiable (ruleset requires a string nothing posts) or
    // unenforcing. Pin the single source of truth: the createCommitStatus `context:` line.
    const contextLines = statusLines.filter(l => /^\s*context:\s*/.test(l));
    assert.equal(contextLines.length, 1, 'expected exactly one `context:` line in the workflow');
    assert.match(contextLines[0], /^\s*context:\s*'code-review',?\s*$/, `status context must be exactly 'code-review', got: ${contextLines[0].trim()}`);
});

// ---- ANALYZE-EXECUTION INVARIANT: analyze never executes PR content (the pull_request_target belt) ----
// analyze runs with secrets on untrusted fork PRs. Its safety rests entirely on "reads the diff as
// data, never runs it." This asserts that structurally: only an allowlist of actions, and no
// build/install/test/cache command in any `run:`. Fails the build the moment analyze gains a
// cache/cloud/setup/exec step -- the #1 regression risk Locke flagged for pull_request_target.
const workflow = yaml.load(workflowText);
const analyzeJob = workflow.jobs.analyze;

// Action name = the part before `@`, e.g. `actions/cache` from `actions/cache@<sha>`.
const ALLOWED_ANALYZE_ACTIONS = new Set(['actions/checkout', 'actions/github-script', 'anthropics/claude-code-action', 'actions/upload-artifact']);
// Commands that would mean analyze is building/installing/running fork code.
const FORBIDDEN_RUN =
    /\b(npm|yarn|pnpm|npx|pip|pipenv|poetry|uv|make|docker|docker-compose|gradle|mvn|cargo|go\s+(build|test|run)|bundle|composer|node|python[0-9.]*|setup\.py)\b/;

test('analyze job uses only allowlisted actions (no cache/cloud/setup -> no fork-code execution)', () => {
    const used = (analyzeJob.steps || []).filter(s => s.uses).map(s => s.uses.split('@')[0]);
    assert.ok(used.length > 0, 'expected analyze to have `uses:` steps');
    for (const name of used) {
        assert.ok(
            ALLOWED_ANALYZE_ACTIONS.has(name),
            `analyze uses a non-allowlisted action "${name}" -- if this is a cache/cloud/setup ` +
                `action it can execute or poison fork content under pull_request_target. If the addition ` +
                `is genuinely safe, extend ALLOWED_ANALYZE_ACTIONS deliberately and re-justify the banner invariant.`
        );
    }
});

test('analyze job runs no build/install/test/cache command (reads the diff as data, never runs it)', () => {
    for (const step of analyzeJob.steps || []) {
        if (typeof step.run !== 'string') continue;
        assert.ok(
            !FORBIDDEN_RUN.test(step.run),
            `analyze has a run step that looks like it executes PR content:\n${step.run}\n` +
                `analyze must only fetch + inertly extract the PR head (git/tar/find/chmod), never build/install/run it.`
        );
    }
});

test('analyze job holds no PAT and no write permission (the no-write half of the split)', () => {
    const text = JSON.stringify(analyzeJob);
    // No PAT secret referenced anywhere in the analyze job (OAuth model token + GITHUB_TOKEN only).
    assert.ok(!/secrets\.OL_BOT_\w*PAT/.test(text), 'analyze must not reference any OL_BOT_*PAT secret -- PATs live only in post/status.');
    // Permissions are read-only (id-token:write is the OIDC exception, not repo write).
    const perms = analyzeJob.permissions || {};
    for (const [scope, level] of Object.entries(perms)) {
        if (scope === 'id-token') continue; // OIDC token exchange only; not repo write
        assert.notEqual(level, 'write', `analyze must not hold write scope "${scope}: write".`);
    }
});
