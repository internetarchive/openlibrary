import { describe, expect, test } from 'vitest';
import { decideLabelsAndAssignee, getLinkedIssueMetadata } from '../../../scripts/gh_scripts/new_pr_labeler_core.mjs';

// Behavioural tests for the two decisions new_pr_labeler makes about a new PR:
// who to assign, and which labels to add. The entry script runs main() on import
// and needs @octokit/action, so the logic lives in new_pr_labeler_core.mjs and is
// exercised here directly, with no network.
//
// Two defects this guards against, both live on master before this change:
// 1. The lead was never assigned: getLinkedIssueMetadata returned a `lead` key
//    but the caller read `leadName`, so the assignee was always undefined.
// 2. Every PR got a "Needs: Lead" label. An unassigned PR already signals it
//    needs a lead, so the label is redundant on PRs and is no longer added.
// Reintroducing either defect turns the assertions below red (proven by mutating
// the core module back to the old behaviour).

// A fake Octokit issue response carrying the given label names.
function issueWithLabels(...names) {
    return { data: { labels: names.map(name => ({ name })) } };
}

// Chain the two pure steps the way main() does: issue -> metadata -> decision.
function planFromIssue(issue, prAuthor) {
    return decideLabelsAndAssignee(getLinkedIssueMetadata(issue), prAuthor);
}

describe('getLinkedIssueMetadata', () => {
    test('reads the first Lead and a P0-P2 priority label', () => {
        const metadata = getLinkedIssueMetadata(issueWithLabels('Type: Bug', 'Lead: @foo', 'Priority: 1'));
        expect(metadata).toEqual({ leadName: 'foo', priority: 'Priority: 1' });
    });

    test('ignores Priority: 3 (only P0-P2 are inherited)', () => {
        expect(getLinkedIssueMetadata(issueWithLabels('Priority: 3')).priority).toBeUndefined();
    });

    test('returns no metadata when there is no linked issue', () => {
        expect(getLinkedIssueMetadata(null)).toEqual({ leadName: undefined, priority: undefined });
    });
});

describe('decideLabelsAndAssignee', () => {
    test('assigns the lead and inherits the priority when the author is not the lead', () => {
        const plan = decideLabelsAndAssignee({ leadName: 'foo', priority: 'Priority: 1' }, 'bar');
        expect(plan.assignee).toBe('foo');
        expect(plan.labels).toEqual(['Priority: 1']);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('does not self-assign when the PR author is the issue lead, and adds no label', () => {
        const plan = decideLabelsAndAssignee({ leadName: 'foo', priority: undefined }, 'foo');
        expect(plan.assignee).toBeNull();
        expect(plan.labels).toEqual([]);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('inherits the priority even when there is no lead to assign', () => {
        const plan = decideLabelsAndAssignee({ leadName: undefined, priority: 'Priority: 0' }, 'bar');
        expect(plan.assignee).toBeNull();
        expect(plan.labels).toEqual(['Priority: 0']);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('adds no "Needs: Lead" label when no lead is found', () => {
        const plan = decideLabelsAndAssignee({ leadName: undefined, priority: undefined }, 'bar');
        expect(plan.assignee).toBeNull();
        expect(plan.labels).toEqual([]);
    });
});

describe('plan for a PR (issue -> metadata -> decision)', () => {
    test('a lead-labelled issue restores assignment, with no "Needs: Lead" label', () => {
        const plan = planFromIssue(issueWithLabels('Lead: @foo', 'Priority: 2'), 'bar');
        expect(plan.assignee).toBe('foo');
        expect(plan.labels).toEqual(['Priority: 2']);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('a PR with no linked issue gets no assignee and no "Needs: Lead" label', () => {
        const plan = planFromIssue(null, 'bar');
        expect(plan.assignee).toBeNull();
        expect(plan.labels).toEqual([]);
        expect(plan.labels).not.toContain('Needs: Lead');
    });
});
