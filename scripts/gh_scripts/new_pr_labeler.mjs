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
 * 4. Assigns Good First Issues to contributors who commented, or closes the PR
 *    with recovery instructions. PR_AUTHOR_ASSOCIATION supplies the payload association.
 * 5. Swaps "Needs: Response" for "Needs: Review" on the open issues it references
 *
 * A PR is never labeled "Needs: Lead": an unassigned PR already signals that it
 * needs a lead, so the label is redundant on PRs. ("Needs: Lead" stays meaningful
 * on issues, which this script does not touch.)
 *
 * PRs this misses (e.g. the issue's lead is added later) are picked up by the
 * scheduled sweep in ./pr_lead_sweep.mjs, which shares ./pr_lead_resolver.mjs.
 */
import { Octokit } from '@octokit/action';
import { handleGfiPr } from './gfi_pr_assignment.mjs';
import { applyPlan, planForPr, swapNeedsResponseForReview, writeJobSummary } from './pr_lead_resolver.mjs';

console.log('Script starting....');
const octokit = new Octokit();
await main();
console.log('Script terminated....');

async function main() {
    const { fullRepoName, prAuthor, prNumber, prBody } = parseArgs();

    try {
        const plan = await planForPr(octokit, fullRepoName, prBody, prAuthor);
        const { assigned } = await applyPlan(octokit, fullRepoName, Number(prNumber), plan);
        const reason = assigned ? plan.reason : `could not assign @${plan.assignee} (no repo access?); planned: ${plan.reason}`;
        console.log(`PR #${prNumber}: ${reason}`);
        await writeJobSummary(`PR #${prNumber}: ${reason}${plan.labels.length ? `; add ${plan.labels.join(', ')}` : ''}`);
    } catch (error) {
        console.error('PR lead step failed:', error);
        process.exitCode = 1;
    }
    try {
        const decision = await handleGfiPr(octokit, fullRepoName, Number(prNumber), prBody, process.env.PR_AUTHOR_ASSOCIATION);
        await writeJobSummary(`GFI: ${decision.action} — ${decision.reason}`);
    } catch (error) {
        console.error('GFI step failed:', error);
        process.exitCode = 1;
    }
    try {
        // Runs even if either assignment step fails.
        const swapped = await swapNeedsResponseForReview(octokit, fullRepoName, prBody);
        if (swapped.length) {
            const message = `Needs: Response -> Needs: Review on ${swapped.map(number => `#${number}`).join(', ')}`;
            console.log(message);
            await writeJobSummary(message);
        }
    } catch (error) {
        console.error('Issue review label step failed:', error);
        process.exitCode = 1;
    }
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
