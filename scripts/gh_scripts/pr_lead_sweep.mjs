/**
 * Scheduled sweep that assigns leads to open PRs nobody has assigned.
 *
 * Usage:
 * `node pr_lead_sweep.mjs REPO_NAME`
 *
 * Environment:
 * `DRY_RUN` anything other than "false" (the default) only logs what would be
 *           done and writes nothing.
 *
 * new_pr_labeler.mjs assigns a lead when a PR opens. It misses PRs whose issue
 * got its `Lead:` label later, PRs whose body was edited to add a reference,
 * and PRs opened while it was broken. This sweep re-runs the same decision
 * (./pr_lead_resolver.mjs) on every open PR that:
 * - is not a draft and was not opened by a bot, and
 * - has no assignee and has never had one, so it never re-assigns someone a
 *   human removed or overrides a human's choice.
 * A priority label is only added when the PR has no `Priority:` label yet.
 */
import { Octokit } from '@octokit/action';
import { sweepLabels, sweepSkipReason } from './new_pr_labeler_core.mjs';
import { applyPlan, planForPr, writeJobSummary } from './pr_lead_resolver.mjs';

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
          # Note: totalCount ignores itemTypes, so check nodes instead.
          timelineItems(first: 1, itemTypes: [ASSIGNED_EVENT, UNASSIGNED_EVENT]) { nodes { __typename } }
        }
      }
    }
  }`;

const fullRepoName = process.argv[2];
if (!fullRepoName) {
    console.error('Usage: node pr_lead_sweep.mjs REPO_NAME');
    process.exit(1);
}
const dryRun = process.env.DRY_RUN !== 'false';
const octokit = new Octokit();
await main();

async function main() {
    const [owner, name] = fullRepoName.split('/');
    const rows = [];
    let skipped = 0;
    let failed = 0;
    let cursor = null;
    do {
        const result = await octokit.graphql(OPEN_PRS_QUERY, { owner, name, cursor });
        const page = result.repository.pullRequests;
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
            // One PR failing (API error, odd body) must not stop the rest of the sweep.
            try {
                const plan = await planForPr(octokit, fullRepoName, pr.body, pr.author.login);
                const labels = sweepLabels(
                    plan.labels,
                    pr.labels.nodes.map(label => label.name)
                );
                let { reason } = plan;
                if (!dryRun && (plan.assignee || labels.length)) {
                    const { assigned } = await applyPlan(octokit, fullRepoName, pr.number, { assignee: plan.assignee, labels });
                    if (!assigned) {
                        reason = `could not assign @${plan.assignee} (no repo access?); planned: ${reason}`;
                        plan.assignee = null;
                    }
                }
                rows.push({ number: pr.number, plan: { ...plan, labels, reason } });
            } catch (error) {
                failed++;
                rows.push({ number: pr.number, plan: { assignee: null, labels: [], reason: `error: ${error.message}` } });
            }
        }
        cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
    } while (cursor);

    const assigned = rows.filter(row => row.plan.assignee).length;
    const verb = dryRun ? 'would assign' : 'assigned';
    const summary = [
        `## PR lead sweep${dryRun ? ' (dry run: nothing was written)' : ''}`,
        '',
        `${rows.length} unassigned PRs checked, ${verb} ${assigned}; ${skipped} skipped (draft, bot, or has or had an assignee)${failed ? `; ${failed} failed` : ''}.`,
        '',
        '| PR | Decision | Labels |',
        '|---|---|---|',
        ...rows.map(({ number, plan }) => `| #${number} | ${plan.reason} | ${plan.labels.join(', ')} |`)
    ].join('\n');
    console.log(summary);
    await writeJobSummary(summary);
    if (failed) {
        // Report first, then fail the run so errors are visible in the Actions tab.
        process.exitCode = 1;
    }
}
