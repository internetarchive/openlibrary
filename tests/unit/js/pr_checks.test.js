import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';
import {
    CHECK,
    CHECK_PREFIX,
    NOT_READY_LABEL,
    buildStatuses,
    clamp,
    contextFor,
    evaluateTemplate,
    hasDevRunEvidence,
    hasIssueReference,
    hasPriorityLabel,
    isIssueReady,
    isStaffOrLead,
    resolveIssueNumber
} from '../../../scripts/gh_scripts/pr_checks_core.mjs';

// Behavioural tests for the five PR checks (pr_checks_core.mjs). Each check is
// posted as its own named commit status, so the tests pin both the per-check
// decision (the pure helpers) and the assembled status rows (buildStatuses:
// context name + state). The entry script (pr_checks.mjs) does process.exit at
// import time and the network IO, so its offline path is exercised as a
// subprocess at the bottom.

// The payload shape GitHub gives: labels are an array of {name} objects.
function labelObjects(...names) {
    return names.map(name => ({ name }));
}

// A body that genuinely follows the template (used where another check is under
// test and template/evidence must not be the thing failing).
const FILLED_TEMPLATE = [
    'Closes #123',
    '',
    '### Technical',
    'Refactored the loader.',
    '### Testing',
    'Ran it locally against dev data.',
    '### Screenshot',
    'n/a',
    '### Stakeholders',
    '@cdrini'
].join('\n');

describe('contextFor / CHECK_PREFIX (single swappable prefix)', () => {
    test('every context is the prefix + the check suffix', () => {
        expect(contextFor(CHECK.priority)).toBe(`${CHECK_PREFIX}/priority`);
        expect(contextFor(CHECK.referencesIssue)).toBe(`${CHECK_PREFIX}/references-issue`);
        expect(contextFor(CHECK.issueIsReady)).toBe(`${CHECK_PREFIX}/issue-is-ready`);
        expect(contextFor(CHECK.passesTemplate)).toBe(`${CHECK_PREFIX}/passes-pr-template`);
        expect(contextFor(CHECK.ranTheCode)).toBe(`${CHECK_PREFIX}/ran-the-code`);
    });
});

describe('priority', () => {
    test('fails with no Priority label, empty, or missing list', () => {
        expect(hasPriorityLabel(labelObjects('Type: Bug'))).toBe(false);
        expect(hasPriorityLabel([])).toBe(false);
        expect(hasPriorityLabel(undefined)).toBe(false);
        expect(hasPriorityLabel(null)).toBe(false);
    });

    test('passes on Priority: 0 through 4 (the repo range), among others', () => {
        for (const n of [0, 1, 2, 3, 4]) {
            expect(hasPriorityLabel(labelObjects(`Priority: ${n}`))).toBe(true);
        }
        expect(hasPriorityLabel(labelObjects('Type: Bug', 'Priority: 2'))).toBe(true);
        expect(hasPriorityLabel(['Priority: 1'])).toBe(true);
    });

    test('a future Priority: 5 is not falsely failed, but a non-numeric suffix is rejected', () => {
        expect(hasPriorityLabel(['Priority: 5'])).toBe(true);
        expect(hasPriorityLabel(labelObjects('Priority: high'))).toBe(false);
    });
});

describe('references-issue', () => {
    test('fails on a body with no reference / empty / missing', () => {
        expect(hasIssueReference('This cleans up whitespace. No ticket.')).toBe(false);
        expect(hasIssueReference('')).toBe(false);
        expect(hasIssueReference(undefined)).toBe(false);
    });

    test('passes on a bare #NNNN or a full issue/pull URL', () => {
        expect(hasIssueReference('Part of the epic, see #13160.')).toBe(true);
        expect(hasIssueReference('#7 at start')).toBe(true);
        expect(hasIssueReference('Fixes https://github.com/internetarchive/openlibrary/issues/13160')).toBe(true);
    });

    test('does not read an HTML entity or a comment-only ref as a reference', () => {
        expect(hasIssueReference('the author&#39;s name is escaped')).toBe(false);
        expect(hasIssueReference('<!-- example: Closes #1234 -->\nNo real reference.')).toBe(false);
    });
});

describe('resolveIssueNumber (which issue issue-is-ready checks)', () => {
    test('extracts a bare #N', () => {
        expect(resolveIssueNumber('Closes #14449')).toBe(14449);
        expect(resolveIssueNumber('see #7 for context')).toBe(7);
    });

    test('extracts a same-repo issue/pull URL number', () => {
        expect(resolveIssueNumber('Fixes https://github.com/internetarchive/openlibrary/issues/13160')).toBe(13160);
    });

    test('ignores a cross-repo URL (not this repo to police) and a comment-only ref', () => {
        expect(resolveIssueNumber('see https://github.com/some/other/issues/5')).toBe(null);
        expect(resolveIssueNumber('<!-- Closes #999 -->\nnothing visible')).toBe(null);
    });

    test('returns null when there is no reference', () => {
        expect(resolveIssueNumber('no reference at all')).toBe(null);
        expect(resolveIssueNumber('')).toBe(null);
    });

    test('a #N inside a fenced code block is NOT a reference (quoted log, not a link)', () => {
        const body = 'Cleanup only.\n\n```\nlog line about #4000 in code\n```\n';
        expect(resolveIssueNumber(body)).toBe(null);
        expect(hasIssueReference(body)).toBe(false);
    });

    test('a URL anchor like /#42 is NOT read as issue 42', () => {
        const body = 'docs at https://example.com/x/#42';
        expect(resolveIssueNumber(body)).toBe(null);
        expect(hasIssueReference(body)).toBe(false);
    });
});

describe('isIssueReady (pure half of issue-is-ready)', () => {
    test('false when the issue carries the Not Ready label (exact string)', () => {
        expect(isIssueReady(labelObjects('Needs: Triage', NOT_READY_LABEL))).toBe(false);
        expect(isIssueReady([NOT_READY_LABEL])).toBe(false);
    });

    test('true when the issue is ready / has no labels', () => {
        expect(isIssueReady(labelObjects('Priority: 2', 'Type: Bug'))).toBe(true);
        expect(isIssueReady([])).toBe(true);
        expect(isIssueReady(undefined)).toBe(true);
    });

    test('a merely similar label does not count as Not Ready', () => {
        expect(isIssueReady(labelObjects('Not Ready'))).toBe(true);
        expect(isIssueReady(labelObjects('ready for work'))).toBe(true);
    });
});

describe('passes-pr-template (strict, structural)', () => {
    const template = readFileSync('.github/pull_request_template.md', 'utf8');

    test('the stock unmodified template FAILS (required sections are empty)', () => {
        const r = evaluateTemplate(template);
        expect(r.ok).toBe(false);
        expect(r.empty).toContain('Technical');
        expect(r.empty).toContain('Testing');
    });

    test('a genuinely filled-in template passes', () => {
        expect(evaluateTemplate(FILLED_TEMPLATE).ok).toBe(true);
    });

    test('deleting the template structure fails as missing sections', () => {
        const r = evaluateTemplate('Just a one-line description, no template at all.');
        expect(r.ok).toBe(false);
        expect(r.missing).toEqual(['Technical', 'Testing', 'Screenshot', 'Stakeholders']);
    });

    test('Screenshot/Stakeholders are presence-only: present-but-empty still passes', () => {
        // Technical + Testing filled, Screenshot + Stakeholders present but empty.
        const body = '### Technical\nx\n### Testing\nran locally\n### Screenshot\n### Stakeholders\n';
        expect(evaluateTemplate(body).ok).toBe(true);
    });

    test('a filled Technical but empty Testing fails and names Testing', () => {
        const body = '### Technical\nx\n### Testing\n### Screenshot\n### Stakeholders\n';
        const r = evaluateTemplate(body);
        expect(r.ok).toBe(false);
        expect(r.empty).toEqual(['Testing']);
        expect(r.missing).toEqual([]);
    });

    test('content that is only an HTML comment does NOT count as filled', () => {
        const body = '### Technical\n<!-- todo -->\n### Testing\nran it\n### Screenshot\nx\n### Stakeholders\nx\n';
        const r = evaluateTemplate(body);
        expect(r.ok).toBe(false);
        expect(r.empty).toEqual(['Technical']);
    });

    test('a template spoofed INSIDE a code fence does not satisfy the check', () => {
        // The real body has no template structure; it only quotes one in a fence.
        const body = [
            'Here is what the template looks like:',
            '',
            '```',
            '### Technical',
            'blah',
            '### Testing',
            'blah',
            '### Screenshot',
            'x',
            '### Stakeholders',
            'y',
            '```'
        ].join('\n');
        const r = evaluateTemplate(body);
        expect(r.ok).toBe(false);
        expect(r.missing).toEqual(['Technical', 'Testing', 'Screenshot', 'Stakeholders']);
    });

    test('a required section filled under a deeper sub-heading still counts as filled', () => {
        const body = [
            '### Technical',
            '#### Approach',
            'We did a big refactor here.',
            '### Testing',
            'Ran locally.',
            '### Screenshot',
            'x',
            '### Stakeholders',
            'y'
        ].join('\n');
        expect(evaluateTemplate(body).ok).toBe(true);
    });

    test('a required section whose only content is a code block counts as filled', () => {
        const body = ['### Technical', '```', 'diff --git a b', '```', '### Testing', 'ran it', '### Screenshot', 'x', '### Stakeholders', 'y'].join('\n');
        expect(evaluateTemplate(body).ok).toBe(true);
    });
});

describe('ran-the-code (evidence heuristic + exemption)', () => {
    test('fails when the body shows no sign the code was run', () => {
        expect(hasDevRunEvidence('Renamed a variable for clarity. Closes #1.')).toBe(false);
        expect(hasDevRunEvidence('')).toBe(false);
    });

    test('passes on a screenshot, a modern user-attachments video, output, or a testimonial', () => {
        expect(hasDevRunEvidence('Before/after:\n![shot](https://example.com/x.png)')).toBe(true);
        expect(hasDevRunEvidence('Demo:\nhttps://github.com/user-attachments/assets/6f1a2b3c-0000-4444-8888-abcdef012345')).toBe(true);
        expect(hasDevRunEvidence('I ran it:\n\n```\n200 OK\n```\n')).toBe(true);
        expect(hasDevRunEvidence('Tested locally against dev data and it works.')).toBe(true);
    });

    test('the stock PR template alone is NOT evidence, but a custom testimonial header still counts', () => {
        const template = readFileSync('.github/pull_request_template.md', 'utf8');
        expect(hasDevRunEvidence(template)).toBe(false);
        expect(hasDevRunEvidence('## Tested on localhost, works\n\nFixes the layout. Closes #5.')).toBe(true);
    });

    test('isStaffOrLead recognises staff case-insensitively and rejects unknowns', () => {
        expect(isStaffOrLead('mekarpeles')).toBe(true);
        expect(isStaffOrLead('CDRINI')).toBe(true);
        expect(isStaffOrLead('openlibrary-bot')).toBe(true);
        expect(isStaffOrLead('some-new-contributor')).toBe(false);
        expect(isStaffOrLead(undefined)).toBe(false);
    });
});

describe('buildStatuses (the five assembled commit statuses)', () => {
    const good = {
        labels: labelObjects('Priority: 2'),
        body: FILLED_TEMPLATE,
        authorLogin: 'external-contributor',
        issue: { kind: 'ok', number: 123, labels: labelObjects('Priority: 2') }
    };

    function byContext(rows, name) {
        return rows.find(r => r.context === contextFor(name));
    }

    test('returns exactly the five contexts, in stable order', () => {
        const rows = buildStatuses(good);
        expect(rows.map(r => r.context)).toEqual([
            contextFor(CHECK.priority),
            contextFor(CHECK.referencesIssue),
            contextFor(CHECK.issueIsReady),
            contextFor(CHECK.passesTemplate),
            contextFor(CHECK.ranTheCode)
        ]);
    });

    test('all green when every check is satisfied', () => {
        const rows = buildStatuses(good);
        expect(rows.every(r => r.state === 'success')).toBe(true);
    });

    test('a missing priority label fails only that check', () => {
        const rows = buildStatuses({ ...good, labels: [] });
        expect(byContext(rows, CHECK.priority).state).toBe('failure');
        expect(byContext(rows, CHECK.referencesIssue).state).toBe('success');
        expect(byContext(rows, CHECK.passesTemplate).state).toBe('success');
    });

    test('a non-staff author with a bare body fails only ran-the-code (+ template)', () => {
        const rows = buildStatuses({ labels: labelObjects('Priority: 1'), body: 'Fixes #123. Renamed a var.', authorLogin: 'ext', issue: { kind: 'none' } });
        expect(byContext(rows, CHECK.ranTheCode).state).toBe('failure');
        expect(byContext(rows, CHECK.priority).state).toBe('success');
        expect(byContext(rows, CHECK.referencesIssue).state).toBe('success');
    });

    test('staff/lead author is exempt from ran-the-code even with a bare body', () => {
        const rows = buildStatuses({
            labels: labelObjects('Priority: 1'),
            body: FILLED_TEMPLATE,
            authorLogin: 'cdrini',
            issue: { kind: 'ok', number: 1, labels: [] }
        });
        expect(byContext(rows, CHECK.ranTheCode).state).toBe('success');
        expect(byContext(rows, CHECK.ranTheCode).description).toMatch(/staff\/lead/);
    });

    describe('issue-is-ready reflects the resolved issue outcome', () => {
        test('ok + Not Ready label -> failure', () => {
            const rows = buildStatuses({ ...good, issue: { kind: 'ok', number: 99, labels: [{ name: NOT_READY_LABEL }] } });
            expect(byContext(rows, CHECK.issueIsReady).state).toBe('failure');
        });

        test('ok + ready -> success', () => {
            const rows = buildStatuses({ ...good, issue: { kind: 'ok', number: 99, labels: labelObjects('Priority: 2') } });
            expect(byContext(rows, CHECK.issueIsReady).state).toBe('success');
        });

        test('no referenced issue -> success (defers to references-issue, never double-fails)', () => {
            const rows = buildStatuses({ ...good, issue: { kind: 'none' } });
            expect(byContext(rows, CHECK.issueIsReady).state).toBe('success');
        });

        test('a transient read error -> error, NOT failure', () => {
            const rows = buildStatuses({ ...good, issue: { kind: 'error', number: 99 } });
            expect(byContext(rows, CHECK.issueIsReady).state).toBe('error');
        });

        test('dry-run (skipped) -> pending (never posted)', () => {
            const rows = buildStatuses({ ...good, issue: { kind: 'skipped', number: 99 } });
            expect(byContext(rows, CHECK.issueIsReady).state).toBe('pending');
        });
    });

    test("descriptions are clamped to GitHub's 140-char limit", () => {
        const rows = buildStatuses(good);
        for (const r of rows) {
            expect(r.description.length).toBeLessThanOrEqual(140);
        }
    });
});

describe('clamp (140-char commit-status limit)', () => {
    test('leaves a short string untouched', () => {
        expect(clamp('short')).toBe('short');
    });

    test('truncates an over-long string to exactly 140 chars ending in an ellipsis', () => {
        const long = 'x'.repeat(200);
        const out = clamp(long);
        expect(out.length).toBe(140);
        expect(out.endsWith('...')).toBe(true);
    });
});

describe('entry script pr_checks.mjs (offline dry-run IO path)', () => {
    // No PAT -> dry-run: computes + prints the five statuses, does NO network, and
    // exits 0 (a red CHECK is a posted status, not this job's exit code).
    const script = 'scripts/gh_scripts/pr_checks.mjs';

    function run(env) {
        try {
            const stdout = execFileSync(process.execPath, [script], {
                // Scrub any ambient PAT so the test is hermetic and offline.
                env: { ...process.env, OL_BOT_COMMIT_STATUS_PAT: '', HEAD_SHA: '', ...env },
                encoding: 'utf8'
            });
            return { code: 0, stdout };
        } catch (error) {
            return { code: error.status, stdout: `${error.stdout || ''}` };
        }
    }

    test('dry-run prints all five contexts and exits 0, even with a bad PR', () => {
        const { code, stdout } = run({
            PR_AUTHOR: 'external-dev',
            PR_LABELS: '[{"name":"Type: Bug"}]',
            PR_BODY: 'Renamed a variable. #42'
        });
        expect(code).toBe(0);
        expect(stdout).toContain('dry-run');
        for (const name of Object.values(CHECK)) {
            expect(stdout).toContain(contextFor(name));
        }
    });

    test('dry-run does not crash on malformed PR_LABELS or an empty body', () => {
        const { code, stdout } = run({ PR_AUTHOR: 'x', PR_LABELS: 'not json', PR_BODY: '' });
        expect(code).toBe(0);
        expect(stdout).toContain(contextFor(CHECK.priority));
    });

    test('exits non-zero when posting was attempted and every POST failed (e.g. dead PAT)', () => {
        // PAT + HEAD_SHA set -> not dry-run, so it tries to POST. Point the API at a
        // closed local port so every POST fails fast and offline; body references no
        // issue so there is no label fetch. Every post fails -> non-zero exit surfaces it.
        const { code, stdout } = run({
            OL_BOT_COMMIT_STATUS_PAT: 'dummy-token',
            HEAD_SHA: 'deadbeef',
            GITHUB_API_URL: 'http://127.0.0.1:1',
            PR_AUTHOR: 'external-dev',
            PR_LABELS: '[{"name":"Priority: 2"}]',
            PR_BODY: 'A change with no issue reference.'
        });
        expect(code).not.toBe(0);
        expect(stdout).toMatch(/every status POST failed/i);
    });
});
