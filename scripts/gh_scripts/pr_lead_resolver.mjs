/**
 * Shared GitHub I/O for working out who should be assigned to a PR.
 *
 * Used by both new_pr_labeler.mjs (on PR open) and pr_lead_sweep.mjs (on a
 * schedule), so the two always reach the same decision for the same PR.
 * The pure decision logic lives in ./new_pr_labeler_core.mjs. Nothing here runs
 * at import time, so the tests drive it with a fake Octokit.
 */
import { decideLabelsAndAssignee, findIssueReferences, needsReviewSwap, resolveIssueMetadata, sweepLabels, sweepSkipReason } from './new_pr_labeler_core.mjs';

// `issueOrPullRequest` because a `#N` may point at a PR as well as an issue.
// `parent` is the issue this one is a sub-issue of (typically its epic).
const ISSUE_QUERY = `
  query ($owner: String!, $name: String!, $number: Int!) {
    repository(owner: $owner, name: $name) {
      issueOrPullRequest(number: $number) {
        __typename
        ... on Issue {
          state
          labels(first: 50) { nodes { name } }
          parent { number repository { nameWithOwner } labels(first: 50) { nodes { name } } }
        }
      }
    }
  }`;

const OPEN_PRS_QUERY = `
  query ($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
      pullRequests(states: OPEN, first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          number
          isDraft
          body
          author { __typename login }
          assignees(first: 1) { totalCount }
          labels(first: 50) { nodes { name } }
          # Any assign/unassign event means a human has already handled assignment.
          # totalCount ignores itemTypes (it counts every timeline item), so check nodes.
          timelineItems(first: 1, itemTypes: [ASSIGNED_EVENT, UNASSIGNED_EVENT]) { nodes { __typename } }
        }
      }
    }
  }`;

// Lookups per PR. Bodies rarely reference more, and closing references come first.
const MAX_REFERENCES = 5;

/** Converts GraphQL label nodes to the Octokit REST issue shape the core helpers take. */
const asIssue = node => (node ? { data: { labels: node.labels.nodes } } : null);

const sameName = (a, b) => a.toLowerCase() === b.toLowerCase();

/**
 * Fetches a referenced number. Returns null when it is not an issue or PR:
 * Octokit throws a NOT_FOUND error for Discussions (which share the number
 * space) and for typos. If only the parent can't be read, keeps the issue
 * without its parent rather than losing the issue's own labels.
 */
async function lookUpReference(octokit, owner, name, number) {
    try {
        return (await octokit.graphql(ISSUE_QUERY, { owner, name, number })).repository.issueOrPullRequest;
    } catch (error) {
        const errors = error?.errors ?? [];
        if (!errors.length) {
            throw error;
        }
        if (errors.every(e => e.type === 'NOT_FOUND' && (!e.path || e.path.at(-1) === 'issueOrPullRequest'))) {
            return null;
        }
        const node = error.data?.repository?.issueOrPullRequest;
        if (node && errors.every(e => e.path?.includes('parent'))) {
            return { ...node, parent: null };
        }
        throw error;
    }
}

/**
 * Plans the assignee and labels for a PR from the issues its body references.
 *
 * Tries up to MAX_REFERENCES references in order, closing references first:
 * - The lead comes from the first reference that is an issue (not a PR,
 *   Discussion or missing number) and has a lead on it or on its same-repo parent.
 * - The priority comes from the first closing reference that has one, even when
 *   a later reference supplies the lead ("Closes #1. Part of #<epic>").
 *
 * @param {import('@octokit/core').Octokit} octokit
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary"
 * @param {string} prBody
 * @param {string} prAuthor
 * @returns {Promise<{assignee: string|null, labels: string[], reason: string}>}
 */
export async function planForPr(octokit, fullRepoName, prBody, prAuthor) {
    const [owner, name] = fullRepoName.split('/');
    const references = findIssueReferences(prBody, fullRepoName);
    if (!references.length) {
        return { assignee: null, labels: [], reason: 'no issue reference in the PR body' };
    }

    let priority;
    let noLeadReason = null;
    for (const { number, kind } of references.slice(0, MAX_REFERENCES)) {
        const node = await lookUpReference(octokit, owner, name, number);
        if (node?.__typename !== 'Issue') {
            continue;
        }
        // A parent in another repo would point the lead (and the "#N" in the reason) at the wrong place.
        const parent = node.parent && sameName(node.parent.repository.nameWithOwner, fullRepoName) ? node.parent : null;
        const metadata = resolveIssueMetadata(asIssue(node), asIssue(parent), kind);
        priority ??= metadata.priority;
        const via = `#${number} (${kind === 'closing' ? 'closing keyword' : 'non-closing reference'})`;

        if (!metadata.leadName) {
            noLeadReason ??= `${via} has no Lead label${parent ? `, nor does its parent #${parent.number}` : ''}`;
            continue;
        }
        const plan = decideLabelsAndAssignee({ leadName: metadata.leadName, priority });
        const source = metadata.leadSource === 'parent' ? ` via its parent #${parent.number}` : '';
        const author = prAuthor && sameName(plan.assignee, prAuthor) ? ' (the PR author)' : '';
        const reason = `assign @${plan.assignee}${author} from ${via}${source}`;
        return { ...plan, reason };
    }
    const plan = decideLabelsAndAssignee({ leadName: undefined, priority });
    return { ...plan, reason: noLeadReason ?? 'none of the referenced numbers is an issue' };
}

/**
 * Assigns the planned lead and adds the planned labels to a PR.
 *
 * GitHub silently ignores an assignee who cannot be assigned (e.g. no longer
 * has repo access) and still returns 201, so the response is checked.
 *
 * @param {import('@octokit/core').Octokit} octokit
 * @param {string} fullRepoName
 * @param {number} prNumber
 * @param {{assignee: string|null, labels: string[]}} plan
 * @returns {Promise<{assigned: boolean}>} Whether the planned assignee is now assigned
 *          (true when there was nobody to assign).
 */
export async function applyPlan(octokit, fullRepoName, prNumber, { assignee, labels }) {
    const [owner, repo] = fullRepoName.split('/');
    const headers = { 'X-GitHub-Api-Version': '2022-11-28' };
    let assigned = true;
    if (assignee) {
        const response = await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/assignees', {
            owner,
            repo,
            issue_number: prNumber,
            assignees: [assignee],
            headers
        });
        assigned = (response.data.assignees ?? []).some(user => sameName(user.login, assignee));
    }
    if (labels.length) {
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', { owner, repo, issue_number: prNumber, labels, headers });
    }
    return { assigned };
}

/**
 * Swaps `Needs: Response` for `Needs: Review` on each open same-repo issue the
 * PR body references (closing or not; see findIssueReferences()). PRs,
 * Discussions and missing numbers are skipped. Safe to re-run: the new label is
 * added before the old one is removed, so a failure part-way leaves both.
 *
 * @param {import('@octokit/core').Octokit} octokit
 * @param {string} fullRepoName
 * @param {string} prBody
 * @returns {Promise<number[]>} The issues that were swapped.
 */
export async function swapNeedsResponseForReview(octokit, fullRepoName, prBody) {
    const [owner, repo] = fullRepoName.split('/');
    const headers = { 'X-GitHub-Api-Version': '2022-11-28' };
    const swapped = [];
    for (const { number } of findIssueReferences(prBody, fullRepoName).slice(0, MAX_REFERENCES)) {
        const node = await lookUpReference(octokit, owner, repo, number);
        if (node?.__typename !== 'Issue' || !needsReviewSwap({ state: node.state, labelNames: node.labels.nodes.map(label => label.name) })) {
            continue;
        }
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', {
            owner,
            repo,
            issue_number: number,
            labels: ['Needs: Review'],
            headers
        });
        try {
            await octokit.request('DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}', {
                owner,
                repo,
                issue_number: number,
                name: 'Needs: Response',
                headers
            });
        } catch (error) {
            // Already removed (e.g. by a concurrent run or a human) is fine.
            if (error.status !== 404) {
                throw error;
            }
        }
        swapped.push(number);
    }
    return swapped;
}

/**
 * Runs the sweep: plans and applies a lead for every open PR
 * that sweepSkipReason() lets through.
 *
 * Errors never stop the sweep early: a failure on one PR becomes that PR's row,
 * and a failure while listing PRs is returned as `listError` along with the rows
 * collected so far, so the summary always reports what was done.
 *
 * @param {import('@octokit/core').Octokit} octokit
 * @param {string} fullRepoName
 * @returns {Promise<{rows: Array<{number: number, assignee: string|null, labels: string[], reason: string}>, skipped: number, failed: number, listError: string|null}>}
 */
export async function runSweep(octokit, fullRepoName) {
    const [owner, name] = fullRepoName.split('/');
    const rows = [];
    let skipped = 0;
    let failed = 0;
    let cursor = null;
    try {
        do {
            const page = (await octokit.graphql(OPEN_PRS_QUERY, { owner, name, cursor })).repository.pullRequests;
            for (const pr of page.nodes) {
                const skip = sweepSkipReason({
                    isDraft: pr.isDraft,
                    authorLogin: pr.author?.login ?? null,
                    authorIsBot: pr.author?.__typename === 'Bot',
                    hasAssignees: pr.assignees.totalCount > 0,
                    everAssigned: pr.timelineItems.nodes.length > 0
                });
                if (skip) {
                    skipped++;
                    continue;
                }
                try {
                    const plan = await planForPr(octokit, fullRepoName, pr.body, pr.author.login);
                    const labels = sweepLabels(
                        plan.labels,
                        pr.labels.nodes.map(label => label.name)
                    );
                    let { assignee, reason } = plan;
                    if (assignee || labels.length) {
                        const { assigned } = await applyPlan(octokit, fullRepoName, pr.number, { assignee, labels });
                        if (!assigned) {
                            reason = `could not assign @${assignee} (no repo access?); planned: ${reason}`;
                            assignee = null;
                        }
                    }
                    rows.push({ number: pr.number, assignee, labels, reason });
                } catch (error) {
                    failed++;
                    rows.push({ number: pr.number, assignee: null, labels: [], reason: `error: ${error.message}` });
                }
            }
            cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
        } while (cursor);
    } catch (error) {
        return { rows, skipped, failed, listError: error.message };
    }
    return { rows, skipped, failed, listError: null };
}

/** Makes text safe for one markdown table cell: one line, no column breaks. */
const tableCell = text =>
    String(text)
        .replace(/\s*\n\s*/g, ' ')
        .replace(/\\/g, '\\\\')
        .replace(/\|/g, '\\|');

/**
 * Turns `#N` into a link. Job summaries don't autolink issue and PR numbers the
 * way issues and PRs do (they do autolink `@mentions`). `/issues/N` redirects to
 * `/pull/N` for a PR, so one URL form covers both.
 *
 * @param {string} text
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary"
 * @returns {string}
 */
export function linkify(text, fullRepoName) {
    return text.replace(/(^|[^\w[])#(\d+)\b/g, `$1[#$2](https://github.com/${fullRepoName}/issues/$2)`);
}

/**
 * Formats a runSweep() result as markdown for the job summary.
 *
 * @param {Awaited<ReturnType<typeof runSweep>>} result
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary", for links
 * @returns {string}
 */
export function formatSweepSummary({ rows, skipped, failed, listError }, fullRepoName) {
    const assigned = rows.filter(row => row.assignee).length;
    const lines = [
        '## PR lead sweep',
        '',
        `${rows.length} unassigned PRs checked, assigned ${assigned}; ${skipped} skipped (draft, bot, or has or had an assignee)${failed ? `; ${failed} failed` : ''}.`
    ];
    if (listError) {
        lines.push('', `**Listing open PRs failed partway, so this is incomplete:** ${tableCell(listError)}`);
    }
    lines.push('', '| PR | Decision | Labels |', '|---|---|---|');
    const prLink = number => `[#${number}](https://github.com/${fullRepoName}/issues/${number})`;
    lines.push(...rows.map(row => `| ${prLink(row.number)} | ${linkify(tableCell(row.reason), fullRepoName)} | ${tableCell(row.labels.join(', '))} |`));
    return lines.join('\n');
}

/**
 * Appends markdown to the GitHub Actions job summary, when running in Actions.
 *
 * @param {string} markdown
 */
export async function writeJobSummary(markdown) {
    if (process.env.GITHUB_STEP_SUMMARY) {
        const { appendFile } = await import('node:fs/promises');
        await appendFile(process.env.GITHUB_STEP_SUMMARY, `${markdown}\n`);
    }
}
