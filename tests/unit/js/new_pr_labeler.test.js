import { describe, expect, test } from 'vitest';
import {
    decideLabelsAndAssignee,
    findIssueReferences,
    getLinkedIssueMetadata,
    resolveIssueMetadata,
    sweepLabels,
    sweepSkipReason
} from '../../../scripts/gh_scripts/new_pr_labeler_core.mjs';
import { formatSweepSummary, linkify, planForPr, runSweep } from '../../../scripts/gh_scripts/pr_lead_resolver.mjs';

// Behavioural tests for how a PR's lead and labels are decided
// (new_pr_labeler_core.mjs, pr_lead_resolver.mjs), including the scheduled
// sweep. The entry scripts run at import time and need @octokit/action, so the
// logic is exercised here directly, with a fake Octokit and no network.
//
// Two past defects these guard against:
// 1. The lead was never assigned: getLinkedIssueMetadata returned a `lead` key
//    but the caller read `leadName`, so the assignee was always undefined.
// 2. Every PR got a "Needs: Lead" label. An unassigned PR already signals it
//    needs a lead, so the label is redundant on PRs and is never added.

// A fake Octokit issue response carrying the given label names.
function issueWithLabels(...names) {
    return { data: { labels: names.map(name => ({ name })) } };
}

// Chain the two pure steps: issue -> metadata -> decision.
function planFromIssue(issue) {
    return decideLabelsAndAssignee(getLinkedIssueMetadata(issue));
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
    test('assigns the lead and inherits the priority', () => {
        const plan = decideLabelsAndAssignee({ leadName: 'foo', priority: 'Priority: 1' });
        expect(plan.assignee).toBe('foo');
        expect(plan.labels).toEqual(['Priority: 1']);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('assigns the lead even when they are the PR author, and adds no label', () => {
        const plan = decideLabelsAndAssignee({ leadName: 'foo', priority: undefined });
        expect(plan.assignee).toBe('foo');
        expect(plan.labels).toEqual([]);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('inherits the priority even when there is no lead to assign', () => {
        const plan = decideLabelsAndAssignee({ leadName: undefined, priority: 'Priority: 0' });
        expect(plan.assignee).toBeNull();
        expect(plan.labels).toEqual(['Priority: 0']);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('adds no "Needs: Lead" label when no lead is found', () => {
        const plan = decideLabelsAndAssignee({ leadName: undefined, priority: undefined });
        expect(plan.assignee).toBeNull();
        expect(plan.labels).toEqual([]);
    });
});

describe('plan for a PR (issue -> metadata -> decision)', () => {
    test('a lead-labelled issue restores assignment, with no "Needs: Lead" label', () => {
        const plan = planFromIssue(issueWithLabels('Lead: @foo', 'Priority: 2'));
        expect(plan.assignee).toBe('foo');
        expect(plan.labels).toEqual(['Priority: 2']);
        expect(plan.labels).not.toContain('Needs: Lead');
    });

    test('a PR with no linked issue gets no assignee and no "Needs: Lead" label', () => {
        const plan = planFromIssue(null);
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

// A fake Octokit. graphql() answers issue lookups from `issues` (number -> node;
// an Error value is thrown, the way Octokit throws GraphQL errors) and PR
// listings from `prPages` (one page per call). request() records each write and
// answers an assignees POST with `assignable` users only, like GitHub does.
function fakeOctokit({ issues = {}, prPages = [], assignable = null } = {}) {
    const writes = [];
    let page = 0;
    return {
        writes,
        graphql: async (_query, vars) => {
            if ('number' in vars) {
                if (issues[vars.number] instanceof Error) throw issues[vars.number];
                return { repository: { issueOrPullRequest: issues[vars.number] ?? null } };
            }
            const next = prPages[page++];
            if (next instanceof Error) throw next;
            return { repository: { pullRequests: next } };
        },
        request: async (route, params) => {
            writes.push({ route, ...params });
            const assignees = (params.assignees ?? []).filter(login => !assignable || assignable.includes(login));
            return { data: { assignees: assignees.map(login => ({ login })) } };
        }
    };
}
const issueNode = (labels, parent = null) => ({ __typename: 'Issue', labels: { nodes: labels.map(name => ({ name })) }, parent });
const parentNode = (number, labels, repo = REPO) => ({ number, repository: { nameWithOwner: repo }, labels: { nodes: labels.map(name => ({ name })) } });
// Shaped like @octokit/graphql's GraphqlResponseError.
const graphqlError = (errors, data = null) => Object.assign(new Error('Request failed due to following response errors:\n - something'), { errors, data });
const notFound = () => graphqlError([{ type: 'NOT_FOUND', path: ['repository', 'issueOrPullRequest'] }]);

describe('planForPr', () => {
    test('assigns the lead of a "Part of" issue, without its priority', async () => {
        const plan = await planForPr(fakeOctokit({ issues: { 13412: issueNode(['Lead: @RayBB', 'Priority: 1']) } }), REPO, 'Part of #13412', 'contributor');
        expect(plan.assignee).toBe('RayBB');
        expect(plan.labels).toEqual([]);
        expect(plan.reason).toBe('assign @RayBB from #13412 (non-closing reference)');
    });

    test("uses the parent epic's lead when the issue has none", async () => {
        const plan = await planForPr(
            fakeOctokit({ issues: { 5: issueNode(['Priority: 2'], parentNode(100, ['Lead: @mekarpeles'])) } }),
            REPO,
            'Closes #5',
            'contributor'
        );
        expect(plan.assignee).toBe('mekarpeles');
        expect(plan.labels).toEqual(['Priority: 2']);
        expect(plan.reason).toBe('assign @mekarpeles from #5 (closing keyword) via its parent #100');
    });

    test('ignores a parent in another repo', async () => {
        const plan = await planForPr(
            fakeOctokit({ issues: { 5: issueNode([], parentNode(100, ['Lead: @other'], 'someone/else')) } }),
            REPO,
            'Closes #5',
            'contributor'
        );
        expect(plan.assignee).toBeNull();
        expect(plan.reason).toBe('#5 (closing keyword) has no Lead label');
    });

    test('skips a referenced PR and uses the next reference that is an issue', async () => {
        const plan = await planForPr(
            fakeOctokit({ issues: { 1: { __typename: 'PullRequest' }, 2: issueNode(['Lead: @foo']) } }),
            REPO,
            'Follow-up to #1. Part of #2',
            'bar'
        );
        expect(plan.assignee).toBe('foo');
    });

    test('reports why nobody was assigned', async () => {
        expect((await planForPr(fakeOctokit(), REPO, 'No issue here', 'bar')).reason).toBe('no issue reference in the PR body');
        const plan = await planForPr(fakeOctokit({ issues: { 7: issueNode(['Priority: 1']) } }), REPO, 'Closes #7', 'bar');
        expect(plan).toEqual({ assignee: null, labels: ['Priority: 1'], reason: '#7 (closing keyword) has no Lead label' });
    });

    test('assigns the lead when they are also the PR author', async () => {
        const plan = await planForPr(fakeOctokit({ issues: { 3: issueNode(['Lead: @foo']) } }), REPO, 'Closes #3', 'foo');
        expect(plan.assignee).toBe('foo');
        expect(plan.reason).toBe('assign @foo (the PR author) from #3 (closing keyword)');
    });

    test('keeps the closing issue priority when a later "Part of" reference supplies the lead', async () => {
        const plan = await planForPr(
            fakeOctokit({ issues: { 1: issueNode(['Priority: 2']), 2: issueNode(['Lead: @epic', 'Priority: 0']) } }),
            REPO,
            'Closes #1. Part of #2',
            'bar'
        );
        expect(plan.assignee).toBe('epic');
        expect(plan.labels).toEqual(['Priority: 2']);
    });

    test('ignores references inside HTML comments', async () => {
        const plan = await planForPr(fakeOctokit({ issues: { 2: issueNode(['Lead: @foo']) } }), REPO, '<!-- Part of #2 -->\nNo issue', 'bar');
        expect(plan.reason).toBe('no issue reference in the PR body');
    });
});

describe('planForPr: lookups that fail', () => {
    test('skips a number that is not an issue or PR (e.g. a Discussion) instead of throwing', async () => {
        const plan = await planForPr(fakeOctokit({ issues: { 13079: notFound(), 2: issueNode(['Lead: @foo']) } }), REPO, 'Closes #13079. Part of #2', 'bar');
        expect(plan.assignee).toBe('foo');
    });

    test('reports when no referenced number is an issue', async () => {
        const plan = await planForPr(fakeOctokit({ issues: { 9: notFound() } }), REPO, 'Refs #9', 'bar');
        expect(plan).toEqual({ assignee: null, labels: [], reason: 'none of the referenced numbers is an issue' });
    });

    test("keeps the issue's own labels when only its parent can't be read", async () => {
        const error = graphqlError([{ type: 'FORBIDDEN', path: ['repository', 'issueOrPullRequest', 'parent'] }], {
            repository: { issueOrPullRequest: issueNode(['Lead: @foo', 'Priority: 1']) }
        });
        const plan = await planForPr(fakeOctokit({ issues: { 4: error } }), REPO, 'Closes #4', 'bar');
        expect(plan).toMatchObject({ assignee: 'foo', labels: ['Priority: 1'] });
    });

    test('still throws other API errors', async () => {
        await expect(planForPr(fakeOctokit({ issues: { 9: new Error('rate limited') } }), REPO, 'Closes #9', 'bar')).rejects.toThrow('rate limited');
        const forbidden = graphqlError([{ type: 'FORBIDDEN', path: ['repository', 'issueOrPullRequest'] }]);
        await expect(planForPr(fakeOctokit({ issues: { 9: forbidden } }), REPO, 'Closes #9', 'bar')).rejects.toThrow();
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

describe('runSweep', () => {
    // An open PR as OPEN_PRS_QUERY returns it.
    const prNode = (number, body, { author = 'contributor', isDraft = false, assignees = 0, everAssigned = false, labels = [] } = {}) => ({
        number,
        isDraft,
        body,
        author: { __typename: 'User', login: author },
        assignees: { totalCount: assignees },
        labels: { nodes: labels.map(name => ({ name })) },
        timelineItems: { nodes: everAssigned ? [{ __typename: 'AssignedEvent' }] : [] }
    });
    const page = (nodes, endCursor = null) => ({ pageInfo: { hasNextPage: Boolean(endCursor), endCursor }, nodes });
    const issues = { 1: issueNode(['Lead: @lead', 'Priority: 1']) };

    test('assigns and labels, across pages, and skips ineligible PRs', async () => {
        const octokit = fakeOctokit({
            issues,
            prPages: [
                page([prNode(10, 'Closes #1'), prNode(11, 'Closes #1', { isDraft: true })], 'c1'),
                page([prNode(12, 'Part of #1', { labels: ['Priority: 3'] }), prNode(13, 'Closes #1', { everAssigned: true })])
            ]
        });
        const result = await runSweep(octokit, REPO);
        expect(result.skipped).toBe(2);
        expect(octokit.writes.map(w => [w.issue_number, w.assignees ?? w.labels])).toEqual([
            [10, ['lead']],
            [10, ['Priority: 1']],
            [12, ['lead']]
        ]);
    });

    test('reports a lead GitHub would not assign', async () => {
        const octokit = fakeOctokit({ issues, prPages: [page([prNode(10, 'Part of #1')])], assignable: [] });
        const { rows } = await runSweep(octokit, REPO);
        expect(rows[0].assignee).toBeNull();
        expect(rows[0].reason).toMatch(/^could not assign @lead/);
    });

    test('one failing PR is reported without stopping the rest', async () => {
        const octokit = fakeOctokit({ issues: { ...issues, 2: new Error('boom') }, prPages: [page([prNode(10, 'Closes #2'), prNode(11, 'Closes #1')])] });
        const result = await runSweep(octokit, REPO);
        expect(result.failed).toBe(1);
        expect(result.rows.map(r => r.number)).toEqual([10, 11]);
        expect(result.rows[0].reason).toBe('error: boom');
    });

    test('a listing failure keeps the rows collected so far', async () => {
        const octokit = fakeOctokit({ issues, prPages: [page([prNode(10, 'Closes #1')], 'c1'), new Error('502')] });
        const result = await runSweep(octokit, REPO);
        expect(result.listError).toBe('502');
        expect(result.rows).toHaveLength(1);
    });
});

describe('formatSweepSummary', () => {
    test('keeps multi-line and pipe-containing reasons inside one table row', () => {
        const summary = formatSweepSummary(
            { rows: [{ number: 10, assignee: null, labels: [], reason: 'error: Request failed:\n - a | b' }], skipped: 0, failed: 1, listError: null },
            REPO
        );
        const row = summary.split('\n').find(line => line.startsWith('| [#10]'));
        expect(row).toBe('| [#10](https://github.com/internetarchive/openlibrary/issues/10) | error: Request failed: - a \\| b |  |');
    });

    test('flags an incomplete run', () => {
        expect(formatSweepSummary({ rows: [], skipped: 0, failed: 0, listError: '502' }, REPO)).toContain('Listing open PRs failed partway');
    });

    test('links the PR and the issue numbers in the decision', () => {
        const summary = formatSweepSummary(
            {
                rows: [
                    {
                        number: 14125,
                        assignee: 'cdrini',
                        labels: [],
                        reason: 'assign @cdrini (the PR author) from #12688 (closing keyword) via its parent #100'
                    }
                ],
                skipped: 0,
                failed: 0,
                listError: null
            },
            REPO
        );
        expect(summary).toContain(
            '| [#14125](https://github.com/internetarchive/openlibrary/issues/14125) | assign @cdrini (the PR author) from [#12688](https://github.com/internetarchive/openlibrary/issues/12688) (closing keyword) via its parent [#100](https://github.com/internetarchive/openlibrary/issues/100) |'
        );
    });
});

describe('linkify', () => {
    test('leaves existing links, labels and words alone', () => {
        expect(linkify('[#5](x) Priority: 1 abc#5 me@example.com', REPO)).toBe('[#5](x) Priority: 1 abc#5 me@example.com');
    });
});
