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
 * 1. Searches the given PR body for a "closes" statement
 * 2. Fetches the issue referenced by the "closes" statement, storing references
 *    to the first priority and lead label encountered
 * 3. Updates PR, adding same priority label as issue, and assigning the lead (or labeling the issue
 *    as "Needs: Lead")
 */
import { Octokit } from "@octokit/action";

const CLOSES_REGEX = /\b(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved):?\s+#(\d+)/i
const DEFAULT_REQUEST_HEADERS = {"X-GitHub-Api-Version": "2022-11-28"}

console.log('Script starting....')
const octokit = new Octokit()
await main()
console.log('Script terminated....')

async function main() {
    // Parse and assign all command-line variables
    const {fullRepoName, prAuthor, prNumber, prBody} = parseArgs()
    const [repoOwner, repoName] = fullRepoName.split('/')

    // Fetch linked issue, if any
    const issue = await findLinkedIssue(prBody, repoOwner, repoName)
    let prLabelSet = new Set()
    if (!issue) {
        console.log('No linked issue found for this pull request.')
        prLabelSet.add("Needs: Lead")
    }

    const {leadName, priority} = getLinkedIssueMetadata(issue)
    // Don't assign lead to PR if PR author is the issue lead
    const assignLead = (leadName && !(leadName === prAuthor))

    // If lead was identified, assign lead to PR:
    if (assignLead) {
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/assignees', {
            owner: repoOwner,
            repo: repoName,
            issue_number: prNumber,
            assignees: [leadName],
            headers: DEFAULT_REQUEST_HEADERS
          })
    }

    if (priority) {
        prLabelSet.add(priority)
    }
    if (!assignLead) {
        prLabelSet.add("Needs: Lead")
    }
    // Add labels to PR, if needed:
    if (prLabelSet.size) {
        await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', {
            owner: repoOwner,
            repo: repoName,
            issue_number: prNumber,
            labels: Array.from(prLabelSet),
            headers: DEFAULT_REQUEST_HEADERS
          })
    }
}

/**
 * Returns an object containing the parsed command-line arguments.
 *
 * Any newline characters in the PR's body are replaced by space characters.
 *
 * @returns {Record<string, string>}
 */
function parseArgs() {
    if (process.argv.length < 6) {
        console.log('Unexpected number of arguments.')
        process.exit(1)
    }
    const prBody = process.argv.slice(5).join(' ')
    return {
        fullRepoName: process.argv[2],
        prAuthor: process.argv[3],
        prNumber: process.argv[4],
        prBody: prBody
    }
}

/**
 * Finds first "Closes" statement in the given pull request body, then
 * returns the linked issue (or `null` if no such issue exists).
 *
 * @param {string} body The body of a GitHub pull request
 * @param {string} repoOwner The owner of the repo (e.g. internetarchive)
 * @param {string} repoName The name of the repo (e.g. openlibrary)
 * @returns {Promise<OctokitResponse<T>>|null} The linked issue that will be closed by
 *                         this pull request, or null if no "Closes"
 *                         statement is found.
 */
async function findLinkedIssue(body, repoOwner, repoName) {
    const matches = body.match(CLOSES_REGEX)
    const issueNumber =  matches?.length ? Number(matches[1]) : null

    if (!issueNumber) {
        return null
    }

    return octokit.request('GET /repos/{owner}/{repo}/issues/{issue_number}', {
            owner: repoOwner,
            repo: repoName,
            issue_number: issueNumber,
            headers: DEFAULT_REQUEST_HEADERS
          })
}

/**
 * Returns the given issue's lead and priority, if any.
 *
 * @param {OctokitResponse<T>} issue
 * @returns {{lead: string|undefined, priority: string|undefined}}
 */
function getLinkedIssueMetadata(issue) {
    let leadName, priority
    if (issue) {
        for (const label of issue.data.labels) {
            if (!leadName && label.name.startsWith('Lead: @')) {
                leadName = label.name.split('@')[1]
            }
            if (!priority && label.name.match(/Priority: [012]/)) {
                priority = label.name
            }
        }
    }

    return {
        lead: leadName,
        priority: priority
    }
}
