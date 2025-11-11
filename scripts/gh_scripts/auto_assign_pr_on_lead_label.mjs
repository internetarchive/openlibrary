/**
 * Script to automatically assign PRs when a Lead label is added to a linked issue.
 *
 * Usage:
 * `node auto_assign_pr_on_lead_label.mjs REPO_NAME ISSUE_NUMBER LEAD_LABEL`
 *
 * Where:
 * `REPO_NAME` is the owner and repository (e.g. "internetarchive/openlibrary")
 * `ISSUE_NUMBER` is the issue number that received the Lead label
 * `LEAD_LABEL` is the Lead label that was added (e.g. "Lead: @username")
 *
 * Broadly, this script does the following:
 * 1. Extracts the lead username from the label
 * 2. Searches for open pull requests that reference the issue
 * 3. Assigns the lead to any PRs that reference this issue (if they are not already assigned)
 */
import { Octokit } from "@octokit/action";

console.log('Script starting....')
const octokit = new Octokit()
await main()
console.log('Script terminated....')

async function main() {
    // Parse and assign all command-line variables
    const {fullRepoName, issueNumber, leadLabel} = parseArgs()

    // Extract the lead username from the label
    const leadName = leadLabel.split('@')[1]
    if (!leadName) {
        console.log('Could not extract lead username from label.')
        return
    }

    console.log(`Lead name extracted: ${leadName}`)
    console.log(`Issue number: ${issueNumber}`)

    // Find all PRs that reference this issue
    const [repoOwner, repoName] = fullRepoName.split('/')
    
    // Search for PRs that close this issue
    const searchQuery = `repo:${fullRepoName} is:pr is:open ${issueNumber} in:body`
    console.log(`Searching for PRs with query: ${searchQuery}`)
    
    const searchResults = await octokit.request('GET /search/issues', {
        q: searchQuery,
        headers: {
            'X-GitHub-Api-Version': '2022-11-28'
        }
    })

    if (!searchResults.data.items || searchResults.data.items.length === 0) {
        console.log(`No open PRs found that reference issue #${issueNumber}`)
        return
    }

    console.log(`Found ${searchResults.data.items.length} PR(s) referencing issue #${issueNumber}`)

    // Process each PR found
    for (const pr of searchResults.data.items) {
        const prNumber = pr.number
        const prAuthor = pr.user.login
        
        console.log(`Processing PR #${prNumber} by @${prAuthor}`)

        // Check if the PR body actually contains a "Closes" statement for this issue
        const prBody = pr.body || ''
        if (!isLinkedIssue(prBody, issueNumber)) {
            console.log(`PR #${prNumber} does not close issue #${issueNumber}, skipping.`)
            continue
        }

        // Don't assign lead to PR if PR author is the issue lead
        if (leadName === prAuthor) {
            console.log(`PR #${prNumber} author is the lead, skipping assignment.`)
            continue
        }

        // Check if lead is already assigned
        const currentAssignees = pr.assignees.map(a => a.login)
        if (currentAssignees.includes(leadName)) {
            console.log(`Lead @${leadName} is already assigned to PR #${prNumber}`)
            continue
        }

        // Assign the lead to the PR
        console.log(`Assigning @${leadName} to PR #${prNumber}`)
        try {
            await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/assignees', {
                owner: repoOwner,
                repo: repoName,
                issue_number: prNumber,
                assignees: [leadName],
                headers: {
                    'X-GitHub-Api-Version': '2022-11-28'
                }
            })
            console.log(`Successfully assigned @${leadName} to PR #${prNumber}`)
        } catch (error) {
            console.error(`Failed to assign @${leadName} to PR #${prNumber}:`, error.message)
        }
    }
}

/**
 * Returns an object containing the parsed command-line arguments.
 *
 * @returns {Record<string, string|number>}
 */
function parseArgs() {
    if (process.argv.length < 5) {
        console.log('Unexpected number of arguments.')
        process.exit(1)
    }
    return {
        fullRepoName: process.argv[2],
        issueNumber: Number(process.argv[3]),
        leadLabel: process.argv[4]
    }
}

/**
 * Checks if the PR body contains a "Closes" statement for the given issue number.
 *
 * @param {string} body The body of a GitHub pull request
 * @param {number} issueNumber The issue number to check for
 * @returns {boolean} True if the PR closes the given issue, false otherwise
 */
function isLinkedIssue(body, issueNumber) {
    const lowerBody = body.toLowerCase()
    // Match various forms: "Closes #123", "Fixes #123", "Resolves #123", etc.
    const patterns = [
        new RegExp(`closes #${issueNumber}\\b`, 'i'),
        new RegExp(`fixes #${issueNumber}\\b`, 'i'),
        new RegExp(`resolves #${issueNumber}\\b`, 'i'),
        new RegExp(`close #${issueNumber}\\b`, 'i'),
        new RegExp(`fix #${issueNumber}\\b`, 'i'),
        new RegExp(`resolve #${issueNumber}\\b`, 'i')
    ]
    
    return patterns.some(pattern => pattern.test(lowerBody))
}
