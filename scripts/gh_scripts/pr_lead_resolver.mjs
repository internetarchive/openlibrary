/**
 * Shared GitHub I/O for working out who should be assigned to a PR.
 *
 * Used by both new_pr_labeler.mjs (on PR open) and pr_lead_sweep.mjs (on a
 * schedule), so the two always reach the same decision for the same PR.
 * The decision logic itself lives in ./new_pr_labeler_core.mjs.
 */
import { decideLabelsAndAssignee, findIssueReferences, resolveIssueMetadata } from './new_pr_labeler_core.mjs';

const ISSUE_QUERY = `
  query ($owner: String!, $name: String!, $number: Int!) {
    repository(owner: $owner, name: $name) {
      issueOrPullRequest(number: $number) {
        __typename
        ... on Issue {
          labels(first: 50) { nodes { name } }
          parent { number labels(first: 50) { nodes { name } } }
        }
      }
    }
  }`;

/** Converts GraphQL label nodes to the Octokit REST issue shape the core helpers take. */
const asIssue = node => (node ? { data: { labels: node.labels.nodes } } : null);

/**
 * True when a GraphQL error only says the number is not an issue or PR (e.g. a
 * Discussion, which shares the number space, or a typo). Octokit throws these.
 */
function isNotFound(error) {
    return Boolean(error?.errors?.length) && error.errors.every(e => e.type === 'NOT_FOUND');
}

/**
 * Plans the assignee and labels for a PR from the issues its body references.
 *
 * Tries each reference in order (closing references first):
 * - The lead comes from the first one that is an issue, rather than a PR, a
 *   Discussion or a missing number, and has a lead on it or its parent.
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
    for (const { number, kind } of references.slice(0, 5)) {
        let node;
        try {
            node = (await octokit.graphql(ISSUE_QUERY, { owner, name, number })).repository.issueOrPullRequest;
        } catch (error) {
            if (isNotFound(error)) {
                continue;
            }
            throw error;
        }
        if (node?.__typename !== 'Issue') {
            continue;
        }
        const metadata = resolveIssueMetadata(asIssue(node), asIssue(node.parent), kind);
        priority ??= metadata.priority;
        const via = `#${number} (${kind === 'closing' ? 'closing keyword' : 'non-closing reference'})`;

        if (!metadata.leadName) {
            noLeadReason ??= `${via} has no Lead label${node.parent ? `, nor does its parent #${node.parent.number}` : ''}`;
            continue;
        }
        const plan = decideLabelsAndAssignee({ leadName: metadata.leadName, priority }, prAuthor);
        const source = metadata.leadSource === 'parent' ? ` via its parent #${node.parent.number}` : '';
        const reason = plan.assignee ? `assign @${plan.assignee} from ${via}${source}` : `no assignee: the PR author is the lead of ${via}${source}`;
        return { ...plan, reason };
    }
    const plan = decideLabelsAndAssignee({ leadName: undefined, priority }, prAuthor);
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
        assigned = (response.data.assignees ?? []).some(user => user.login.toLowerCase() === assignee.toLowerCase());
    }
    if (labels.length) {
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', { owner, repo, issue_number: prNumber, labels, headers });
    }
    return { assigned };
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
