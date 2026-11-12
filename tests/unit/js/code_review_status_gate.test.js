// Unit tests for the STATUS-GATE logic added to .github/workflows/code_review_action.yml (#14453):
// the `status` job (SHA-bound `ada/code-review` commit status + the SOLE producer of the
// `Needs: e2e testing` label) and the `strip_labels` job. Those jobs embed three pure helpers
// inline in their github-script steps; this test extracts the EXACT text that ships and exercises
// it, so the tested logic and the deployed logic cannot drift. The helpers are:
//   - unresolvedThreadCount(threads)       -- threads that are unresolved AND not outdated
//   - decideStatus({postSucceeded,...})    -- the pass/fail + state + non-leaky description
//   - verificationLabelsToStrip(names)     -- which labels a push invalidates
// (The public-findings count itself is a declared output of the analyze job, produced and tested
// by #14451; this gate only consumes it as a number, so decideStatus is exercised with one here.)
// See the E2E GATE INVARIANT banner at the top of the workflow for why each exists.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const YML = join(here, '..', '..', '..', '.github', 'workflows', 'code_review_action.yml');
const ymlLines = readFileSync(YML, 'utf8').split('\n');

// Extract a `const <name> = (…) => { … };` block from the workflow, keyed on the closing line that
// matches the declaration's own indentation (so a nested `};` cannot truncate it), and eval it. The
// helpers are pure -- they close over nothing from the step -- so a bare `new Function` suffices.
function extractFn(name) {
    const start = ymlLines.findIndex(l => l.includes(`const ${name} =`));
    assert.ok(start >= 0, `${name} not found in workflow`);
    const indent = ymlLines[start].match(/^(\s*)/)[1];
    const closer = `${indent}};`;
    const body = [ymlLines[start]];
    let end = -1;
    for (let j = start + 1; j < ymlLines.length; j++) {
        body.push(ymlLines[j]);
        if (ymlLines[j] === closer) {
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

const unresolvedThreadCount = extractFn('unresolvedThreadCount');
const decideStatus = extractFn('decideStatus');
const verificationLabelsToStrip = extractFn('verificationLabelsToStrip');

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
test('decideStatus never leaks finding content -- description is counts and fixed phrases only', () => {
    for (const c of [
        { postSucceeded: true, findings: 0, unresolved: 0 },
        { postSucceeded: false, findings: 0, unresolved: 0 },
        { postSucceeded: true, findings: 2, unresolved: 0 },
        { postSucceeded: true, findings: 0, unresolved: 2 }
    ]) {
        const { description } = decideStatus(c);
        // One of a small fixed set of templates -- a count plus fixed words, no free text that
        // could carry a finding's content.
        assert.match(
            description,
            /^(Review passed; all feedback resolved\.|No clean review for this commit\.|\d+ findings? to address\.|\d+ unresolved review threads?\.)$/
        );
    }
});

// ---- verificationLabelsToStrip: a push invalidates per-commit verification labels ----
test('verificationLabelsToStrip strips the e2e/code-review/Passed labels and nothing else', () => {
    const current = [
        'Needs: e2e testing',
        'Needs: Code Review',
        'Passed: e2e testing',
        'Passed: automated testing',
        'Priority: 1 (highest)',
        'bug',
        'Theme: Design'
    ];
    assert.deepEqual(verificationLabelsToStrip(current), ['Needs: e2e testing', 'Needs: Code Review', 'Passed: e2e testing', 'Passed: automated testing']);
    assert.deepEqual(verificationLabelsToStrip(['bug', 'Priority: 1 (highest)']), []);
});
