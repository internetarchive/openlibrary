/**
 * Scheduled sweep that assigns leads to open PRs nobody has assigned.
 *
 * Usage:
 * `node pr_lead_sweep.mjs REPO_NAME`
 *
 * new_pr_labeler.mjs assigns a lead when a PR opens. It misses PRs whose issue
 * got its `Lead:` label later, and PRs whose body was edited to add a reference.
 * This sweep re-runs the same decision on every open PR that is not a draft,
 * was not opened by a bot, and has never had an assignee; see runSweep() in
 * ./pr_lead_resolver.mjs.
 */
import { Octokit } from '@octokit/action';
import { formatSweepSummary, runSweep, writeJobSummary } from './pr_lead_resolver.mjs';

const fullRepoName = process.argv[2];
if (!fullRepoName) {
    console.error('Usage: node pr_lead_sweep.mjs REPO_NAME');
    process.exit(1);
}
const result = await runSweep(new Octokit(), fullRepoName);
const summary = formatSweepSummary(result, fullRepoName);
console.log(summary);
await writeJobSummary(summary);
if (result.failed || result.listError) {
    // Report first, then fail the run so errors show up in the Actions tab.
    process.exitCode = 1;
}
