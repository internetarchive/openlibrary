/**
 * Keeps `Needs: Lead` on exactly the open issues that have no `Lead: @` label.
 *
 * Run by pr_lead_sweep.mjs after the PR pass, so it shares that schedule and job
 * summary. The decision is needsLeadChange() in ./new_pr_labeler_core.mjs.
 * Nothing here runs at import time, so the tests drive it with a fake Octokit.
 */
import { needsLeadChange } from './new_pr_labeler_core.mjs';
import { linkify } from './pr_lead_resolver.mjs';

const OPEN_ISSUES_QUERY = `
  query ($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
      issues(states: OPEN, first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { number labels(first: 50) { nodes { name } } }
      }
    }
  }`;

/**
 * Adds or removes `Needs: Lead` on every open issue whose label is out of step.
 *
 * Like runSweep(), errors never stop it early: a failed write is recorded on
 * that issue, and a failure while listing issues is returned as `listError`.
 *
 * @param {import('@octokit/core').Octokit} octokit
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary"
 * @returns {Promise<{changes: Array<{number: number, change: 'add'|'remove', error?: string}>, listError: string|null}>}
 */
export async function syncNeedsLead(octokit, fullRepoName) {
    const [owner, repo] = fullRepoName.split('/');
    const changes = [];
    let cursor = null;
    try {
        do {
            const page = (await octokit.graphql(OPEN_ISSUES_QUERY, { owner, name: repo, cursor })).repository.issues;
            for (const { number, labels } of page.nodes) {
                const change = needsLeadChange(labels.nodes.map(label => label.name));
                if (!change) {
                    continue;
                }
                const params = { owner, repo, issue_number: number, headers: { 'X-GitHub-Api-Version': '2022-11-28' } };
                try {
                    if (change === 'add') {
                        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', { ...params, labels: ['Needs: Lead'] });
                    } else {
                        await octokit.request('DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}', { ...params, name: 'Needs: Lead' });
                    }
                    changes.push({ number, change });
                } catch (error) {
                    // 404 on DELETE: someone removed the label after we listed it, which is the goal anyway.
                    changes.push(change === 'remove' && error.status === 404 ? { number, change } : { number, change, error: error.message });
                }
            }
            cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
        } while (cursor);
    } catch (error) {
        return { changes, listError: error.message };
    }
    return { changes, listError: null };
}

/**
 * Formats a syncNeedsLead() result as markdown for the job summary.
 *
 * @param {Awaited<ReturnType<typeof syncNeedsLead>>} result
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary", for links
 * @returns {string}
 */
export function formatNeedsLeadSummary({ changes, listError }, fullRepoName) {
    const oneLine = text => text.replace(/\s*\n\s*/g, ' ');
    const done = change => changes.filter(c => c.change === change && !c.error).map(c => linkify(`#${c.number}`, fullRepoName));
    const added = done('add');
    const removed = done('remove');
    const lines = [
        '## Needs: Lead',
        '',
        `Added to issues with no lead (${added.length}): ${added.join(', ')}`,
        '',
        `Removed from issues that have a lead (${removed.length}): ${removed.join(', ')}`
    ];
    for (const c of changes.filter(c => c.error)) {
        lines.push('', `Failed to ${c.change} on ${linkify(`#${c.number}`, fullRepoName)}: ${oneLine(c.error)}`);
    }
    if (listError) {
        lines.push('', `**Listing open issues failed partway, so this is incomplete:** ${oneLine(listError)}`);
    }
    return lines.join('\n');
}
