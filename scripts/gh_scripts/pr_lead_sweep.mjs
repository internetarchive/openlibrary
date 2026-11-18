/**
 * Scheduled sweep that assigns leads to open PRs nobody has assigned, then
 * keeps `Needs: Lead` in step with `Lead:` labels on open issues.
 *
 * Usage:
 * `node pr_lead_sweep.mjs REPO_NAME`
 *
 * new_pr_labeler.mjs assigns a lead when a PR opens. It misses PRs whose issue
 * got its `Lead:` label later, and PRs whose body was edited to add a reference.
 * This sweep re-runs the same decision on every open PR that is not a draft,
 * was not opened by a bot, and has never had an assignee; see runSweep() in
 * ./pr_lead_resolver.mjs. The issue pass is syncNeedsLead() in
 * ./needs_lead_sync.mjs.
 */
import { Octokit } from '@octokit/action';
import { formatNeedsLeadSummary, syncNeedsLead } from './needs_lead_sync.mjs';
import { formatSweepSummary, runSweep, writeJobSummary } from './pr_lead_resolver.mjs';

const fullRepoName = process.argv[2];
if (!fullRepoName) {
    console.error('Usage: node pr_lead_sweep.mjs REPO_NAME');
    process.exit(1);
}
const octokit = new Octokit();
const prs = await runSweep(octokit, fullRepoName);
const issues = await syncNeedsLead(octokit, fullRepoName);
const summary = `${formatSweepSummary(prs, fullRepoName)}\n\n${formatNeedsLeadSummary(issues, fullRepoName)}`;
console.log(summary);
await writeJobSummary(summary);
if (prs.failed || prs.listError || issues.listError || issues.changes.some(c => c.error)) {
    // Report first, then fail the run so errors show up in the Actions tab.
    process.exitCode = 1;
}
