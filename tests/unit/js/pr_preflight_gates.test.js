import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';
import {
    evaluatePreflight,
    hasDevRunEvidence,
    hasIssueReference,
    hasPriorityLabel,
    isStaffOrLead
} from '../../../scripts/gh_scripts/pr_preflight_gates_core.mjs';

// Behavioural tests for the three PR preflight gates
// (pr_preflight_gates_core.mjs). The entry script (pr_preflight_gates.mjs) reads
// process.env and calls process.exit at import time, so the pure logic is
// exercised here directly, with no IO.
//
// Each gate is tested for both its FAIL case (the thing it exists to catch) and
// its PASS case. Gate 3 (dev-evidence) additionally pins the staff/lead
// exemption and the deliberately-permissive, err-toward-passing heuristic.

// The payload shape GitHub gives: labels are an array of {name} objects.
function labelObjects(...names) {
    return names.map(name => ({ name }));
}

describe('hasPriorityLabel (gate 1)', () => {
    test('fails with no Priority label', () => {
        expect(hasPriorityLabel(labelObjects('Type: Bug', 'Needs: Review'))).toBe(false);
    });

    test('fails with an empty or missing label list', () => {
        expect(hasPriorityLabel([])).toBe(false);
        expect(hasPriorityLabel(undefined)).toBe(false);
        expect(hasPriorityLabel(null)).toBe(false);
    });

    test('passes on Priority: 0 through 3', () => {
        for (const n of [0, 1, 2, 3]) {
            expect(hasPriorityLabel(labelObjects(`Priority: ${n}`))).toBe(true);
        }
    });

    test('passes when a Priority label sits among others', () => {
        expect(hasPriorityLabel(labelObjects('Type: Bug', 'Priority: 2', 'Lead: @cdrini'))).toBe(true);
    });

    test('accepts a plain array of label name strings too', () => {
        expect(hasPriorityLabel(['Priority: 1'])).toBe(true);
        expect(hasPriorityLabel(['Type: Bug'])).toBe(false);
    });

    test('does not match a label that merely mentions priority', () => {
        expect(hasPriorityLabel(labelObjects('Priority: high', 'deprioritized'))).toBe(false);
    });
});

describe('hasIssueReference (gate 2)', () => {
    test('fails on a body with no reference', () => {
        expect(hasIssueReference('This cleans up some whitespace. No ticket.')).toBe(false);
    });

    test('fails on an empty or missing body', () => {
        expect(hasIssueReference('')).toBe(false);
        expect(hasIssueReference(undefined)).toBe(false);
        expect(hasIssueReference(null)).toBe(false);
    });

    test('passes on a bare #NNNN mention (no closing keyword required)', () => {
        expect(hasIssueReference('Part of the epic, see #13160 for context.')).toBe(true);
        expect(hasIssueReference('Refs #42')).toBe(true);
        expect(hasIssueReference('#7 at start of body')).toBe(true);
    });

    test('passes on a full GitHub issue or pull URL', () => {
        expect(hasIssueReference('Fixes https://github.com/internetarchive/openlibrary/issues/13160')).toBe(true);
        expect(hasIssueReference('Supersedes https://github.com/internetarchive/openlibrary/pull/14438')).toBe(true);
    });

    test('does not read an HTML entity like &#39; as an issue reference', () => {
        expect(hasIssueReference('the author&#39;s name is escaped')).toBe(false);
    });
});

describe('hasDevRunEvidence (gate 3 body heuristic)', () => {
    test('fails when the body shows no sign the code was run', () => {
        expect(hasDevRunEvidence('Renamed a variable for clarity. Closes #1.')).toBe(false);
    });

    test('fails on an empty or missing body', () => {
        expect(hasDevRunEvidence('')).toBe(false);
        expect(hasDevRunEvidence(undefined)).toBe(false);
    });

    test('passes on a markdown image embed (screenshot)', () => {
        expect(hasDevRunEvidence('Before/after:\n![screenshot](https://example.com/x.png)')).toBe(true);
    });

    test('passes on a pasted GitHub attachment (no extension)', () => {
        expect(hasDevRunEvidence('Recording:\nhttps://github.com/internetarchive/openlibrary/assets/123/abc-def')).toBe(true);
        expect(hasDevRunEvidence('https://user-images.githubusercontent.com/1/2.gif-ish')).toBe(true);
    });

    test('passes on a fenced code block (output/logs)', () => {
        expect(hasDevRunEvidence('I ran it:\n\n```\n200 OK\n{"ok": true}\n```\n')).toBe(true);
    });

    test('passes on a written testimonial', () => {
        expect(hasDevRunEvidence('Tested locally against dev data and it works.')).toBe(true);
        expect(hasDevRunEvidence('I ran this on localhost and the page renders.')).toBe(true);
        expect(hasDevRunEvidence('Verified the output below is correct.')).toBe(true);
    });
});

describe('isStaffOrLead (gate 3 exemption)', () => {
    test('recognises known staff/leads case-insensitively', () => {
        expect(isStaffOrLead('mekarpeles')).toBe(true);
        expect(isStaffOrLead('RayBB')).toBe(true);
        expect(isStaffOrLead('CDRINI')).toBe(true);
        expect(isStaffOrLead('openlibrary-bot')).toBe(true);
    });

    test('does not exempt an unknown contributor', () => {
        expect(isStaffOrLead('some-new-contributor')).toBe(false);
        expect(isStaffOrLead('')).toBe(false);
        expect(isStaffOrLead(undefined)).toBe(false);
    });
});

describe('evaluatePreflight (all three gates together)', () => {
    // A PR that satisfies every gate, authored by a non-staff contributor.
    const goodPr = {
        labels: labelObjects('Priority: 2'),
        body: 'Fixes #123.\n\nTested locally:\n```\n200 OK\n```',
        authorLogin: 'external-contributor'
    };

    test('passes when all three gates are satisfied', () => {
        const { passed, results } = evaluatePreflight(goodPr);
        expect(passed).toBe(true);
        expect(results.map(r => r.ok)).toEqual([true, true, true]);
    });

    test('fails and names the priority gate when the label is missing', () => {
        const { passed, results } = evaluatePreflight({ ...goodPr, labels: [] });
        expect(passed).toBe(false);
        expect(results.find(r => r.id === 'priority').ok).toBe(false);
        // The other two still pass -- the failure is attributed, not blanket.
        expect(results.find(r => r.id === 'issue-ref').ok).toBe(true);
        expect(results.find(r => r.id === 'dev-evidence').ok).toBe(true);
    });

    test('fails and names the issue-ref gate when the body has no reference', () => {
        const { passed, results } = evaluatePreflight({
            ...goodPr,
            body: 'Tested locally:\n```\n200 OK\n```'
        });
        expect(passed).toBe(false);
        expect(results.find(r => r.id === 'issue-ref').ok).toBe(false);
    });

    test('fails the dev-evidence gate for a non-staff author with a bare body', () => {
        const { passed, results } = evaluatePreflight({
            labels: labelObjects('Priority: 1'),
            body: 'Fixes #123. Renamed a variable.',
            authorLogin: 'external-contributor'
        });
        expect(passed).toBe(false);
        const evidence = results.find(r => r.id === 'dev-evidence');
        expect(evidence.ok).toBe(false);
        expect(evidence.exempt).toBe(false);
    });

    test('exempts staff/leads from the dev-evidence gate even with a bare body', () => {
        const { passed, results } = evaluatePreflight({
            labels: labelObjects('Priority: 1'),
            body: 'Fixes #123. Renamed a variable.',
            authorLogin: 'cdrini'
        });
        expect(passed).toBe(true);
        const evidence = results.find(r => r.id === 'dev-evidence');
        expect(evidence.ok).toBe(true);
        expect(evidence.exempt).toBe(true);
    });

    test('a staff author still fails the priority and issue-ref gates (exemption is gate-3 only)', () => {
        const { passed, results } = evaluatePreflight({
            labels: [],
            body: 'no reference here',
            authorLogin: 'mekarpeles'
        });
        expect(passed).toBe(false);
        expect(results.find(r => r.id === 'priority').ok).toBe(false);
        expect(results.find(r => r.id === 'issue-ref').ok).toBe(false);
        expect(results.find(r => r.id === 'dev-evidence').ok).toBe(true);
    });
});

// Regression tests for the two gate-3 defects the adversarial review found, plus
// the Priority-4 false-negative. Each was proven to fail against the pre-fix code.

describe("hasPriorityLabel accepts the repo's full Priority range (regression)", () => {
    test('passes on Priority: 4 (a real repo label) -- restricting to 0..3 would falsely fail it', () => {
        expect(hasPriorityLabel([{ name: 'Priority: 4' }])).toBe(true);
    });

    test('passes on any digit, so a future Priority: 5 is not falsely failed', () => {
        expect(hasPriorityLabel(['Priority: 5'])).toBe(true);
    });

    test('still rejects a non-numeric priority suffix', () => {
        expect(hasPriorityLabel([{ name: 'Priority: high' }])).toBe(false);
    });
});

describe('hasDevRunEvidence is not satisfied by the stock PR template (regression)', () => {
    // Feed the *real* committed template, not a hand-rolled approximation: its
    // `### Testing` / `### Screenshot` headers and HTML-comment hints previously
    // tripped the testimonial matcher, so every templated PR passed gate 3.
    // vitest runs with the repo root as cwd.
    const template = readFileSync('.github/pull_request_template.md', 'utf8');

    test('the unmodified template alone is NOT evidence', () => {
        expect(hasDevRunEvidence(template)).toBe(false);
    });

    test('the template plus a real written testimonial IS evidence', () => {
        expect(hasDevRunEvidence(`${template}\n\nI ran it locally against dev data and the page renders.`)).toBe(true);
    });

    test('the template plus a pasted screenshot IS evidence', () => {
        expect(hasDevRunEvidence(`${template}\n\n![after](https://example.com/after.png)`)).toBe(true);
    });

    test('a bare "### Testing" header with no prose under it is not evidence', () => {
        expect(hasDevRunEvidence('### Testing\n\n### Screenshot\n')).toBe(false);
    });

    test('a contributor whose only testimonial IS a header still counts (err toward passing)', () => {
        // Only the template's own section headers are scaffolding; a custom header
        // the author wrote is real prose and must not be stripped away.
        expect(hasDevRunEvidence('## Tested on localhost, works\n\nThis fixes the layout. Closes #5.')).toBe(true);
    });
});

describe('hasDevRunEvidence matches the modern GitHub attachment URL (regression)', () => {
    test('a bare user-attachments video URL (no extension, no give-away prose) passes', () => {
        // Deliberately no testimonial words ("recording", "tested", ...) -- this
        // pins the attachment-URL matcher alone, which is what a drag-dropped video
        // renders as. Pre-fix this returned false: the exact err-toward-passing miss.
        expect(hasDevRunEvidence('Demo:\nhttps://github.com/user-attachments/assets/6f1a2b3c-0000-4444-8888-abcdef012345')).toBe(true);
    });

    test('the older owner/repo/assets form still passes', () => {
        expect(hasDevRunEvidence('https://github.com/internetarchive/openlibrary/assets/123/abc')).toBe(true);
    });
});

describe('hasIssueReference scans visible text only (regression)', () => {
    test('a #N that exists only inside an HTML comment is not a reference', () => {
        expect(hasIssueReference('<!-- example: Closes #1234 -->\nNo real reference here.')).toBe(false);
    });

    test('a visible #N is still a reference', () => {
        expect(hasIssueReference('Closes #1234')).toBe(true);
    });
});

describe('entry script pr_preflight_gates.mjs (shipping IO path)', () => {
    // The entry script runs process.exit at import time, so it cannot be imported;
    // spawn it as a subprocess to pin the exit code -- the one line that turns a
    // failing decision into a red check -- and its input tolerance.
    const script = 'scripts/gh_scripts/pr_preflight_gates.mjs';

    function run(env) {
        try {
            const stdout = execFileSync(process.execPath, [script], {
                env: { ...process.env, ...env },
                encoding: 'utf8'
            });
            return { code: 0, stdout };
        } catch (error) {
            return { code: error.status, stdout: `${error.stdout || ''}` };
        }
    }

    test('exits 0 and reports all-passed for a complete non-staff PR', () => {
        const { code, stdout } = run({
            PR_AUTHOR: 'external-dev',
            PR_LABELS: '[{"name":"Priority: 2"}]',
            PR_BODY: 'Fixes #123.\n\nTested locally:\n```\n200 OK\n```'
        });
        expect(code).toBe(0);
        expect(stdout).toContain('All preflight gates passed');
    });

    test('exits 1 when a gate fails', () => {
        const { code, stdout } = run({
            PR_AUTHOR: 'external-dev',
            PR_LABELS: '[{"name":"Type: Bug"}]',
            PR_BODY: 'Renamed a variable.'
        });
        expect(code).toBe(1);
        expect(stdout).toContain('One or more preflight gates failed');
    });

    test('does not crash on malformed PR_LABELS or an empty body (exits 1, no throw)', () => {
        const { code, stdout } = run({ PR_AUTHOR: 'x', PR_LABELS: 'not json', PR_BODY: '' });
        expect(code).toBe(1);
        expect(stdout).toContain('Priority');
    });
});
