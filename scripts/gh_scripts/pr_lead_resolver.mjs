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
 * Plans the assignee and labels for a PR from the issues its body references.
 *
 * Tries each reference in order (closing references first) and uses the first
 * one that is an issue, rather than a PR, and has a lead on it or its parent.
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

    let fallback = null;
    for (const { number, kind } of references.slice(0, 5)) {
        const result = await octokit.graphql(ISSUE_QUERY, { owner, name, number });
        const node = result.repository.issueOrPullRequest;
        if (node?.__typename !== 'Issue') {
            continue;
        }
        const metadata = resolveIssueMetadata(asIssue(node), asIssue(node.parent), kind);
        const plan = decideLabelsAndAssignee(metadata, prAuthor);
        const via = `#${number} (${kind === 'closing' ? 'closing keyword' : 'non-closing reference'})`;

        if (!metadata.leadName) {
            fallback ??= { ...plan, reason: `${via} has no Lead label${node.parent ? `, nor does its parent #${node.parent.number}` : ''}` };
            continue;
        }
        const source = metadata.leadSource === 'parent' ? ` via its parent #${node.parent.number}` : '';
        const reason = plan.assignee ? `assign @${plan.assignee} from ${via}${source}` : `no assignee: the PR author is the lead of ${via}${source}`;
        return { ...plan, reason };
    }
    return fallback ?? { assignee: null, labels: [], reason: 'the referenced numbers are PRs, not issues' };
}

/**
 * Assigns the planned lead and adds the planned labels to a PR.
 *
 * @param {import('@octokit/core').Octokit} octokit
 * @param {string} fullRepoName
 * @param {number} prNumber
 * @param {{assignee: string|null, labels: string[]}} plan
 */
export async function applyPlan(octokit, fullRepoName, prNumber, { assignee, labels }) {
    const [owner, repo] = fullRepoName.split('/');
    const headers = { 'X-GitHub-Api-Version': '2022-11-28' };
    if (assignee) {
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/assignees', {
            owner,
            repo,
            issue_number: prNumber,
            assignees: [assignee],
            headers
        });
    }
    if (labels.length) {
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', { owner, repo, issue_number: prNumber, labels, headers });
    }
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
