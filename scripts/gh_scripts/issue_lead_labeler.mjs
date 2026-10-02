/**
 * Script to automatically assign a "Lead" to linked Pull Requests when a "Lead: ..." label
 * is added to an Issue.
 *
 * Usage:
 * `node issue_lead_labeler.mjs REPO_NAME ISSUE_NUMBER LEAD_LABEL`
 *
 * Where:
 * `REPO_NAME` is the owner and repository (e.g. "internetarchive/openlibrary")
 * `ISSUE_NUMBER` is the number of the issue that was labeled
 * `LEAD_LABEL` is the label name (e.g. "Lead: @username")
 */
import { Octokit } from "@octokit/action";

console.log('Script starting....')
const octokit = new Octokit()
await main()
console.log('Script terminated....')

async function main() {
    const { fullRepoName, issueNumber, leadLabel } = parseArgs()
    const [repoOwner, repoName] = fullRepoName.split('/')

    // Extract username from label "Lead: @username"
    const leadUsername = leadLabel.split('@')[1]
    if (!leadUsername) {
        console.log(`Could not extract username from label: ${leadLabel}`)
        return
    }

    console.log(`Searching for PRs linked to issue #${issueNumber} to assign to ${leadUsername}...`)

    // Search for open PRs that mention this issue using "#issueNumber" pattern
    // This matches the "Closes #123" syntax used in PR bodies to link issues.
    const q = `repo:${fullRepoName} is:pr is:open "#${issueNumber}"`
    const searchResult = await octokit.request('GET /search/issues', {
        q: q
    })

    const prs = searchResult.data.items
    console.log(`Found ${prs.length} candidate PRs.`)

    for (const pr of prs) {
        // Verify the PR body actually contains a "closes #issueNumber" (or fixes/resolves) statement
        // to avoid false positives from PRs that just mention the issue number
        const prBody = (pr.body || '').toLowerCase()
        const closingPattern = new RegExp(`(closes|fixes|resolves)\\s*#${issueNumber}\\b`, 'i')
        if (!closingPattern.test(prBody)) {
            console.log(`PR #${pr.number} mentions #${issueNumber} but does not close it. Skipping.`)
            continue
        }

        const isAssigned = pr.assignees.some(assignee => assignee.login === leadUsername)
        if (isAssigned) {
            console.log(`PR #${pr.number} is already assigned to ${leadUsername}. Skipping.`)
            continue
        }

        // Avoid assigning if the lead is the author of the PR
        if (pr.user.login === leadUsername) {
             console.log(`PR #${pr.number} author is the lead (${leadUsername}). Skipping assignment.`)
             continue
        }

        console.log(`Assigning PR #${pr.number} to ${leadUsername}...`)

        try {
            await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/assignees', {
                owner: repoOwner,
                repo: repoName,
                issue_number: pr.number,
                assignees: [leadUsername],
                headers: {
                    'X-GitHub-Api-Version': '2022-11-28'
                }
            })
            console.log(`Successfully assigned PR #${pr.number}`)
        } catch (error) {
            console.error(`Failed to assign PR #${pr.number}:`, error)
        }
    }
}

function parseArgs() {
    if (process.argv.length < 5) {
        console.log('Unexpected number of arguments.')
        console.log('Usage: node issue_lead_labeler.mjs REPO_NAME ISSUE_NUMBER LEAD_LABEL')
        process.exit(1)
    }
    return {
        fullRepoName: process.argv[2],
        issueNumber: process.argv[3],
        leadLabel: process.argv[4]
    }
}
