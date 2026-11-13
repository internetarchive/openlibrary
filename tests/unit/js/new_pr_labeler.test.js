import { describe, expect, test } from 'vitest';
import {
    decideGfiAction,
    decideLabelsAndAssignee,
    findIssueReferences,
    getLinkedIssueMetadata,
    needsReviewSwap,
    resolveIssueMetadata,
    sweepLabels,
    sweepSkipReason
} from '../../../scripts/gh_scripts/new_pr_labeler_core.mjs';
import { handleGfiPr } from '../../../scripts/gh_scripts/gfi_pr_assignment.mjs';
import { formatNeedsLeadSummary, syncNeedsLead } from '../../../scripts/gh_scripts/needs_lead_sync.mjs';
import { formatSweepSummary, linkify, planForPr, runSweep, swapNeedsResponseForReview } from '../../../scripts/gh_scripts/pr_lead_resolver.mjs';

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

describe('needsReviewSwap', () => {
    test('swaps only an open issue that has Needs: Response', () => {
        expect(needsReviewSwap({ state: 'OPEN', labelNames: ['Type: Bug', 'Needs: Response'] })).toBe(true);
        expect(needsReviewSwap({ state: 'CLOSED', labelNames: ['Needs: Response'] })).toBe(false);
        expect(needsReviewSwap({ state: 'OPEN', labelNames: ['Needs: Review'] })).toBe(false);
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

describe('swapNeedsResponseForReview', () => {
    test('adds Needs: Review then removes Needs: Response on referenced open issues, tolerating a 404', async () => {
        const open = labels => ({ ...issueNode(labels), state: 'OPEN' });
        const octokit = fakeOctokit({
            issues: {
                1: open(['Needs: Response']),
                2: open(['Needs: Response']),
                3: { __typename: 'PullRequest' },
                4: { ...issueNode(['Needs: Response']), state: 'CLOSED' }
            }
        });
        const { request } = octokit;
        octokit.request = async (route, params) => {
            const response = await request(route, params);
            if (route.startsWith('DELETE') && params.issue_number === 2) throw Object.assign(new Error('Not Found'), { status: 404 });
            return response;
        };
        expect(await swapNeedsResponseForReview(octokit, REPO, 'Closes #1, closes #3, fixes #4. Part of #2')).toEqual([1, 2]);
        expect(octokit.writes.map(w => [w.route.split(' ')[0], w.issue_number])).toEqual([
            ['POST', 1],
            ['DELETE', 1],
            ['POST', 2],
            ['DELETE', 2]
        ]);
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

    test('escapes backslashes so a backslash before a pipe cannot unescape it', () => {
        const summary = formatSweepSummary(
            { rows: [{ number: 10, assignee: null, labels: [], reason: 'a\\|b' }], skipped: 0, failed: 0, listError: null },
            REPO
        );
        const row = summary.split('\n').find(line => line.startsWith('| [#10]'));
        expect(row).toBe('| [#10](https://github.com/internetarchive/openlibrary/issues/10) | a\\\\\\|b |  |');
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

describe('syncNeedsLead', () => {
    // graphql() returns one page of open issues per call (an Error value is
    // thrown); request() records each write, or throws the Error in `errors`.
    function fakeOctokit(pages, errors = {}) {
        const writes = [];
        let page = 0;
        return {
            writes,
            graphql: async () => {
                const next = pages[page++];
                if (next instanceof Error) throw next;
                return { repository: { issues: next } };
            },
            request: async (route, params) => {
                if (errors[params.issue_number]) throw errors[params.issue_number];
                writes.push([route.split(' ')[0], params.issue_number, params.name ?? params.labels]);
                return { data: {} };
            }
        };
    }
    const issue = (number, ...labels) => ({ number, labels: { nodes: labels.map(name => ({ name })) } });
    const page = (nodes, endCursor = null) => ({ pageInfo: { hasNextPage: Boolean(endCursor), endCursor }, nodes });

    test('adds Needs: Lead where there is no lead and removes it where there is one, across pages', async () => {
        const octokit = fakeOctokit([
            page([issue(1, 'Type: Bug'), issue(2, 'Lead: @foo', 'Needs: Lead')], 'c1'),
            page([issue(3, 'Needs: Lead'), issue(4, 'Lead: @foo')])
        ]);
        const result = await syncNeedsLead(octokit, REPO);
        expect(octokit.writes).toEqual([
            ['POST', 1, ['Needs: Lead']],
            ['DELETE', 2, 'Needs: Lead']
        ]);
        expect(result).toEqual({
            changes: [
                { number: 1, change: 'add' },
                { number: 2, change: 'remove' }
            ],
            listError: null
        });
    });

    test('a failed write is recorded without stopping the rest; a 404 on remove counts as done', async () => {
        const gone = Object.assign(new Error('Label does not exist'), { status: 404 });
        const octokit = fakeOctokit([page([issue(1), issue(2, 'Lead: @foo', 'Needs: Lead'), issue(3)])], { 1: new Error('403'), 2: gone });
        const { changes } = await syncNeedsLead(octokit, REPO);
        expect(changes).toEqual([
            { number: 1, change: 'add', error: '403' },
            { number: 2, change: 'remove' },
            { number: 3, change: 'add' }
        ]);
    });

    test('a listing failure keeps the changes made so far, and the summary says so', async () => {
        const result = await syncNeedsLead(fakeOctokit([page([issue(1)], 'c1'), new Error('502')]), REPO);
        expect(result.changes).toHaveLength(1);
        const summary = formatNeedsLeadSummary(result, REPO);
        expect(summary).toContain('Added to issues with no lead (1): [#1](https://github.com/internetarchive/openlibrary/issues/1)');
        expect(summary).toContain('Listing open issues failed partway');
    });
});

describe('Good First Issue assignment', () => {
    const pr = () => ({ state: 'open', draft: false, user: { login: 'newcomer' }, labels: [], author_association: 'NONE' });
    const issue = () => ({ state: 'open', labels: [{ name: 'Good First Issue' }, { name: 'Lead: @mentor' }], assignees: [] });
    const comment = (login, body = '') => ({ user: { login }, body });

    test.each([
        [{ hasCommented: true }, 'assign', 'author commented'],
        [{ hasCommented: false }, 'close', 'missing comment'],
        [{ hasCommented: undefined }, 'skip', 'comments not fetched'],
        [{ kind: 'reference' }, 'skip', 'no closing reference'],
        [{ issue: { ...issue(), labels: [] } }, 'skip', 'not an open Good First Issue'],
        [{ issue: { ...issue(), state: 'closed' } }, 'skip', 'not an open Good First Issue'],
        [{ issue: { ...issue(), pull_request: {} } }, 'skip', 'not an open Good First Issue'],
        [{ issue: { ...issue(), labels: ['Good First Issue', 'no-automation'] } }, 'skip', 'no-automation'],
        [{ pr: { ...pr(), labels: ['no-automation'] } }, 'skip', 'no-automation'],
        ...['MEMBER', 'OWNER', 'COLLABORATOR'].map(author_association => [{ pr: { ...pr(), author_association } }, 'skip', 'staff author']),
        ...['OpenLibrary-Bot', 'dependabot[bot]'].map(login => [{ pr: { ...pr(), user: { login, type: 'User' } } }, 'skip', 'bot author']),
        [{ pr: { ...pr(), state: 'closed' } }, 'skip', 'PR is closed or draft'],
        [{ pr: { ...pr(), draft: true } }, 'skip', 'PR is closed or draft'],
        [{ issue: { ...issue(), assignees: [{ login: 'NEWCOMER' }, { login: 'someone' }] } }, 'skip', 'already assigned to author'],
        [{ issue: { ...issue(), assignees: [{ login: 'someone' }] } }, 'close', 'duplicate']
    ])('decides %o', (change, action, reason) => {
        expect(decideGfiAction({ pr: pr(), issue: issue(), kind: 'closing', hasCommented: true, ...change })).toEqual({ action, reason });
    });

    // Stateful REST fake: records only writes and models full pagination, including
    // a later-page failure. Reopening retains comments, like a real fork PR.
    function fakeGfi({ pull = pr(), ticket = issue(), issuePages = [[]], prPages = [[]], assignable = true } = {}) {
        const writes = [];
        const reads = [];
        return {
            writes,
            reads,
            pull,
            ticket,
            request: async (route, params) => {
                if (route.startsWith('GET')) {
                    reads.push(params.pull_number ?? params.issue_number);
                    return { data: route.includes('/pulls/') ? pull : ticket };
                }
                writes.push({ route, ...params });
                if (route.endsWith('/assignees') && assignable) ticket.assignees = params.assignees.map(login => ({ login }));
                if (route.endsWith('/comments')) {
                    const pages = params.issue_number === 1 ? issuePages : prPages;
                    pages[0].push(comment('github-actions[bot]', params.body));
                }
                if (route.startsWith('PATCH')) pull.state = params.state;
                return { data: ticket };
            },
            paginate: async (_route, params) => {
                expect(params.per_page).toBe(100);
                const pages = params.issue_number === 1 ? issuePages : prPages;
                const result = [];
                for (const page of pages) {
                    if (page instanceof Error) throw page;
                    result.push(...page);
                }
                return result;
            }
        };
    }
    const run = (api, body = 'Closes #1') => handleGfiPr(api, REPO, 10, body, 'NONE');

    test('assigns using a later-page comment, posts one note, and is a no-op on rerun', async () => {
        const api = fakeGfi({ issuePages: [[comment('other')], [comment('NEWCOMER')]] });
        expect((await run(api)).action).toBe('assign');
        expect(api.writes).toHaveLength(2);
        expect(api.writes[1].body).toContain('opened #10');
        expect(api.writes[1].body).toContain('<!-- ol-bot -->');
        await run(api);
        expect(api.writes).toHaveLength(2);
    });

    test('closes without a comment, then assigns after a comment and reopen', async () => {
        const pages = [[]];
        const api = fakeGfi({ issuePages: pages });
        expect(await run(api)).toEqual({ action: 'close', reason: 'missing comment' });
        expect(api.writes[0].body).toContain('or open a new one');
        expect(api.writes[0].body).toContain('or tag @mentor');
        await run(api);
        expect(api.writes).toHaveLength(2);
        api.pull.state = 'open';
        // A retry before commenting closes again but does not repeat the bot comment.
        await run(api);
        expect(api.writes).toHaveLength(3);
        pages[0].push(comment('newcomer'));
        api.pull.state = 'open';
        expect((await run(api)).action).toBe('assign');
        expect(api.pull.state).toBe('open');
        expect(api.ticket.assignees).toEqual([{ login: 'newcomer' }]);
    });

    test('closes an already-owned issue as duplicate, without requiring an author comment', async () => {
        const api = fakeGfi({ ticket: { ...issue(), assignees: [{ login: 'owner' }] } });
        expect(await run(api)).toEqual({ action: 'close', reason: 'duplicate' });
        expect(api.writes[0].body).toContain('already assigned to @owner');
    });

    test.each(['issue', 'PR'])('failed %s comment pagination never closes or writes', async target => {
        const api = fakeGfi({ [target === 'issue' ? 'issuePages' : 'prPages']: [[], new Error('rate limited')] });
        await expect(run(api)).rejects.toThrow('rate limited');
        expect(api.writes).toEqual([]);
    });

    test('ignores non-closing references and only evaluates the first closing reference', async () => {
        const api = fakeGfi({ ticket: { ...issue(), labels: [] } });
        await run(api, 'Part of #2');
        expect(api.reads).toEqual([10]);
        api.reads.length = 0;
        await run(api, 'Part of #2. Closes #1. Fixes #3');
        expect(api.reads).toEqual([10, 1]);
        expect(api.writes).toEqual([]);
    });

    test.each([
        { pull: { ...pr(), labels: ['no-automation'] } },
        { ticket: { ...issue(), labels: ['Good First Issue', 'no-automation'] } },
        { pull: { ...pr(), author_association: 'MEMBER' } },
        { pull: { ...pr(), user: { login: 'openlibrary-bot', type: 'User' } } }
    ])('excluded PRs are untouched: %o', async options => {
        const api = fakeGfi(options);
        expect((await run(api)).action).toBe('skip');
        expect(api.writes).toEqual([]);
    });

    test('does not announce an assignment GitHub silently rejected', async () => {
        const api = fakeGfi({ issuePages: [[comment('newcomer')]], assignable: false });
        await expect(run(api)).rejects.toThrow('did not assign');
        expect(api.writes).toHaveLength(1);
    });

    test('finds an existing bot marker on a later PR-comment page', async () => {
        const pages = [[]];
        const api = fakeGfi({ prPages: pages });
        await run(api);
        pages.push(pages[0].splice(0));
        api.pull.state = 'open';
        await run(api);
        expect(api.writes.filter(write => write.route.endsWith('/comments'))).toHaveLength(1);
        expect(api.writes.filter(write => write.route.startsWith('PATCH'))).toHaveLength(2);
    });

    test.each(['Part of #2', null, ''])('uses the live PR body %s instead of an outdated event closing reference', async body => {
        const api = fakeGfi({ pull: { ...pr(), body } });
        expect((await run(api, 'Closes #1')).action).toBe('skip');
        expect(api.reads).toEqual([10]);
        expect(api.writes).toEqual([]);
    });

    test('does not repeat a closure comment when its lead mention changes', async () => {
        const api = fakeGfi();
        await run(api);
        api.pull.state = 'open';
        api.ticket.labels = [{ name: 'Good First Issue' }, { name: 'Lead: @new-mentor' }];
        await run(api);
        expect(api.writes.filter(write => write.route.endsWith('/comments'))).toHaveLength(1);
    });

    test('a failed explanatory comment leaves the PR open', async () => {
        const api = fakeGfi();
        const request = api.request;
        api.request = async (route, params) => {
            if (route.endsWith('/comments')) throw new Error('comment failed');
            return request(route, params);
        };
        await expect(run(api)).rejects.toThrow('comment failed');
        expect(api.pull.state).toBe('open');
        expect(api.writes).toEqual([]);
    });

    test('omits the lead mention when the issue has no lead', async () => {
        const api = fakeGfi({ ticket: { ...issue(), labels: [{ name: 'Good First Issue' }] } });
        await run(api);
        expect(api.writes[0].body).not.toContain('@undefined');
        expect(api.writes[0].body).toContain('reply here and');
    });
});
