import { describe, expect, test } from 'vitest';
import {
    decideLabelsAndAssignee,
    findIssueReferences,
    getLinkedIssueMetadata,
    resolveIssueMetadata,
    sweepLabels,
    sweepSkipReason
} from '../../../scripts/gh_scripts/new_pr_labeler_core.mjs';
import { planForPr } from '../../../scripts/gh_scripts/pr_lead_resolver.mjs';

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

const REPO = 'internetarchive/openlibrary';

describe('findIssueReferences', () => {
    test('finds a closing keyword, with or without a colon', () => {
        expect(findIssueReferences('Closes #12', REPO)).toEqual([{ number: 12, kind: 'closing' }]);
        expect(findIssueReferences('fixes: #7', REPO)).toEqual([{ number: 7, kind: 'closing' }]);
    });

    test.each(['Part of #5', 'part of: #5', 'Refs #5', 'References #5', 'Related to #5', 'Follow-up to #5', 'Follow up on #5', 'Works on #5', 'Towards #5'])(
        'finds the non-closing reference in "%s"',
        body => {
            expect(findIssueReferences(body, REPO)).toEqual([{ number: 5, kind: 'reference' }]);
        }
    );

    test('accepts a same-repo issue URL but not another repo', () => {
        expect(findIssueReferences('Part of https://github.com/internetarchive/openlibrary/issues/9', REPO)).toEqual([{ number: 9, kind: 'reference' }]);
        expect(findIssueReferences('Closes https://github.com/someone/else/issues/9', REPO)).toEqual([]);
    });

    test('lists closing references before non-closing ones, without duplicates', () => {
        expect(findIssueReferences('Part of #1. Closes #2. Also closes #3. Refs #2', REPO)).toEqual([
            { number: 2, kind: 'closing' },
            { number: 3, kind: 'closing' },
            { number: 1, kind: 'reference' }
        ]);
    });

    test('ignores a bare #N and an empty body', () => {
        expect(findIssueReferences('See #4 for context', REPO)).toEqual([]);
        expect(findIssueReferences('', REPO)).toEqual([]);
        expect(findIssueReferences(null, REPO)).toEqual([]);
    });
});

describe('resolveIssueMetadata', () => {
    test('takes the lead and priority from the issue for a closing reference', () => {
        expect(resolveIssueMetadata(issueWithLabels('Lead: @foo', 'Priority: 1'), null, 'closing')).toEqual({
            leadName: 'foo',
            priority: 'Priority: 1',
            leadSource: 'issue'
        });
    });

    test('falls back to the parent epic lead when the issue has none', () => {
        const metadata = resolveIssueMetadata(issueWithLabels('Priority: 2'), issueWithLabels('Lead: @epic'), 'closing');
        expect(metadata).toEqual({ leadName: 'epic', priority: 'Priority: 2', leadSource: 'parent' });
    });

    test("prefers the issue's own lead over the parent's", () => {
        expect(resolveIssueMetadata(issueWithLabels('Lead: @foo'), issueWithLabels('Lead: @epic'), 'reference').leadName).toBe('foo');
    });

    test('does not inherit a priority from a non-closing reference', () => {
        expect(resolveIssueMetadata(issueWithLabels('Lead: @foo', 'Priority: 0'), null, 'reference').priority).toBeUndefined();
    });
});

describe('sweepSkipReason', () => {
    const pr = { isDraft: false, authorLogin: 'someone', authorIsBot: false, hasAssignees: false, everAssigned: false };

    test('sweeps an open, never-assigned PR by a person', () => {
        expect(sweepSkipReason(pr)).toBeNull();
    });

    test.each([
        [{ isDraft: true }, 'draft'],
        [{ authorIsBot: true }, 'bot author'],
        [{ authorLogin: 'openlibrary-bot' }, 'bot author'],
        [{ authorLogin: null }, 'bot author'],
        [{ hasAssignees: true }, 'already assigned'],
        [{ everAssigned: true }, 'previously assigned']
    ])('skips %o as "%s"', (change, reason) => {
        expect(sweepSkipReason({ ...pr, ...change })).toBe(reason);
    });
});

describe('planForPr', () => {
    // A fake Octokit whose graphql() answers from a map of number -> issueOrPullRequest node.
    // A node value that is an Error is thrown, the way Octokit throws GraphQL errors.
    function fakeOctokit(nodes) {
        return {
            graphql: async (_query, { number }) => {
                if (nodes[number] instanceof Error) throw nodes[number];
                return { repository: { issueOrPullRequest: nodes[number] ?? null } };
            }
        };
    }
    const issueNode = (labels, parent = null) => ({ __typename: 'Issue', labels: { nodes: labels.map(name => ({ name })) }, parent });

    test('assigns the lead of a "Part of" issue, without its priority', async () => {
        const plan = await planForPr(fakeOctokit({ 13412: issueNode(['Lead: @RayBB', 'Priority: 1']) }), REPO, 'Part of #13412', 'contributor');
        expect(plan.assignee).toBe('RayBB');
        expect(plan.labels).toEqual([]);
        expect(plan.reason).toBe('assign @RayBB from #13412 (non-closing reference)');
    });

    test("uses the parent epic's lead when the issue has none", async () => {
        const parent = { number: 100, labels: { nodes: [{ name: 'Lead: @mekarpeles' }] } };
        const plan = await planForPr(fakeOctokit({ 5: issueNode(['Priority: 2'], parent) }), REPO, 'Closes #5', 'contributor');
        expect(plan.assignee).toBe('mekarpeles');
        expect(plan.labels).toEqual(['Priority: 2']);
        expect(plan.reason).toBe('assign @mekarpeles from #5 (closing keyword) via its parent #100');
    });

    test('skips a referenced PR and uses the next reference that is an issue', async () => {
        const plan = await planForPr(
            fakeOctokit({ 1: { __typename: 'PullRequest' }, 2: issueNode(['Lead: @foo']) }),
            REPO,
            'Follow-up to #1. Part of #2',
            'bar'
        );
        expect(plan.assignee).toBe('foo');
    });

    test('reports why nobody was assigned', async () => {
        expect((await planForPr(fakeOctokit({}), REPO, 'No issue here', 'bar')).reason).toBe('no issue reference in the PR body');
        const plan = await planForPr(fakeOctokit({ 7: issueNode(['Priority: 1']) }), REPO, 'Closes #7', 'bar');
        expect(plan).toEqual({ assignee: null, labels: ['Priority: 1'], reason: '#7 (closing keyword) has no Lead label' });
    });

    test('does not self-assign when the author is the lead', async () => {
        const plan = await planForPr(fakeOctokit({ 3: issueNode(['Lead: @foo']) }), REPO, 'Closes #3', 'foo');
        expect(plan.assignee).toBeNull();
        expect(plan.reason).toBe('no assignee: the PR author is the lead of #3 (closing keyword)');
    });
});

describe('planForPr: lookups that fail, and priority with a later lead', () => {
    function fakeOctokit(nodes) {
        return {
            graphql: async (_query, { number }) => {
                if (nodes[number] instanceof Error) throw nodes[number];
                return { repository: { issueOrPullRequest: nodes[number] ?? null } };
            }
        };
    }
    // Shaped like @octokit/graphql's GraphqlResponseError for a missing number.
    const notFound = () => Object.assign(new Error('Could not resolve to an issue or pull request'), { errors: [{ type: 'NOT_FOUND' }] });
    const issueNode = labels => ({ __typename: 'Issue', labels: { nodes: labels.map(name => ({ name })) }, parent: null });

    test('skips a number that is not an issue or PR (e.g. a Discussion) instead of throwing', async () => {
        const plan = await planForPr(fakeOctokit({ 13079: notFound(), 2: issueNode(['Lead: @foo']) }), REPO, 'Closes #13079. Part of #2', 'bar');
        expect(plan.assignee).toBe('foo');
    });

    test('reports when no referenced number is an issue', async () => {
        const plan = await planForPr(fakeOctokit({ 9: notFound() }), REPO, 'Refs #9', 'bar');
        expect(plan).toEqual({ assignee: null, labels: [], reason: 'none of the referenced numbers is an issue' });
    });

    test('still throws other API errors', async () => {
        await expect(planForPr(fakeOctokit({ 9: new Error('rate limited') }), REPO, 'Closes #9', 'bar')).rejects.toThrow('rate limited');
    });

    test('keeps the closing issue priority when a later "Part of" reference supplies the lead', async () => {
        const plan = await planForPr(
            fakeOctokit({ 1: issueNode(['Priority: 2']), 2: issueNode(['Lead: @epic', 'Priority: 0']) }),
            REPO,
            'Closes #1. Part of #2',
            'bar'
        );
        expect(plan.assignee).toBe('epic');
        expect(plan.labels).toEqual(['Priority: 2']);
    });

    test('ignores references inside HTML comments', async () => {
        const plan = await planForPr(fakeOctokit({ 2: issueNode(['Lead: @foo']) }), REPO, '<!-- Part of #2 -->\nNo issue', 'bar');
        expect(plan.reason).toBe('no issue reference in the PR body');
    });
});

describe('findIssueReferences: HTML comments', () => {
    test('drops references inside comments, keeps those outside', () => {
        expect(findIssueReferences('<!-- Closes #1\nPart of #2 --> Refs #3', REPO)).toEqual([{ number: 3, kind: 'reference' }]);
    });
});

describe('sweepLabels', () => {
    test('adds the planned priority when the PR has none', () => {
        expect(sweepLabels(['Priority: 1'], ['Needs: Review'])).toEqual(['Priority: 1']);
    });

    test('adds no priority when the PR already has one', () => {
        expect(sweepLabels(['Priority: 1'], ['Priority: 3'])).toEqual([]);
    });
});
