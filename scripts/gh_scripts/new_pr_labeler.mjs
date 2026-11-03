/**
 * Script to automatically assign and label new GitHub pull requests.
 *
 * Usage:
 * `node new_pr_labeler REPO_NAME PR_AUTHOR PR_NUMBER PR_BODY...`
 *
 * Where:
 * `REPO_NAME` is the owner and repository (e.g. "internetarchive/openlibrary")
 * `PR_AUTHOR` is the username of the PR's author
 * `PR_NUMBER` is the newly created PR's number
 * `PR_BODY`   is the body of the pull request
 *
 * Broadly, this script does the following:
 * 1. Finds the issues the PR body references: closing keywords ("Closes #N")
 *    first, then non-closing references ("Part of #N", "Refs #N", ...)
 * 2. Takes the lead from the first referenced issue that has one, falling back
 *    to the issue's parent (the epic it is a sub-issue of). The priority label
 *    is only inherited from a closing reference.
 * 3. Updates the PR, assigning the lead and adding the priority label, and
 *    writes the decision and its reason to the job summary
 *
 * A PR is never labeled "Needs: Lead": an unassigned PR already signals that it
 * needs a lead, so the label is redundant on PRs. ("Needs: Lead" stays meaningful
 * on issues, which this script does not touch.)
 *
 * PRs this misses (e.g. the issue's lead is added later) are picked up by the
 * scheduled sweep in ./pr_lead_sweep.mjs, which shares ./pr_lead_resolver.mjs.
 */
import { Octokit } from '@octokit/action';
import { applyPlan, planForPr, writeJobSummary } from './pr_lead_resolver.mjs';

console.log('Script starting....');
const octokit = new Octokit();
await main();
console.log('Script terminated....');

async function main() {
    const { fullRepoName, prAuthor, prNumber, prBody } = parseArgs();

    const plan = await planForPr(octokit, fullRepoName, prBody, prAuthor);
    const { assigned } = await applyPlan(octokit, fullRepoName, Number(prNumber), plan);
    const reason = assigned ? plan.reason : `could not assign @${plan.assignee} (no repo access?); planned: ${plan.reason}`;
    console.log(`PR #${prNumber}: ${reason}`);
    await writeJobSummary(`PR #${prNumber}: ${reason}${plan.labels.length ? `; add ${plan.labels.join(', ')}` : ''}`);
}

/**
 * Returns an object containing the parsed command-line arguments.
 *
 * @returns {Record<string, string>}
 */
function parseArgs() {
    if (process.argv.length < 6) {
        console.log('Unexpected number of arguments.');
        process.exit(1);
    }
    const prBody = process.argv.slice(5).join(' ');
    return {
        fullRepoName: process.argv[2],
        prAuthor: process.argv[3],
        prNumber: process.argv[4],
        prBody: prBody
    };
}
