/**
 * Script to label a pull request when a reviewer requests changes.
 *
 * Usage:
 * `node pr_changes_requested_labeler.mjs REPO_NAME PR_NUMBER REVIEW_STATE`
 *
 * Where:
 * `REPO_NAME`     is the owner and repository (e.g. "internetarchive/openlibrary")
 * `PR_NUMBER`     is the pull request number
 * `REVIEW_STATE`  is the submitted review state (e.g. "changes_requested")
 */
import { fileURLToPath } from 'node:url';

const SUBMITTER_INPUT_LABEL = 'Needs: Submitter Input'
const RESPONSE_LABEL = 'Needs: Response'

export function parseArgs(argv = process.argv) {
    if (argv.length !== 5) {
        throw new Error('Unexpected number of arguments.')
    }

    return {
        fullRepoName: argv[2],
        prNumber: Number(argv[3]),
        reviewState: argv[4],
    }
}

export function shouldHandleReview(reviewState) {
    return reviewState?.toLowerCase() === 'changes_requested'
}

export async function syncLabels(octokit, fullRepoName, prNumber) {
    const [repoOwner, repoName] = fullRepoName.split('/')

    await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/labels', {
        owner: repoOwner,
        repo: repoName,
        issue_number: prNumber,
        labels: [SUBMITTER_INPUT_LABEL],
        headers: {
            'X-GitHub-Api-Version': '2022-11-28'
        }
    })

    try {
        await octokit.request('DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}', {
            owner: repoOwner,
            repo: repoName,
            issue_number: prNumber,
            name: RESPONSE_LABEL,
            headers: {
                'X-GitHub-Api-Version': '2022-11-28'
            }
        })
    } catch (error) {
        if (error.status !== 404) {
            throw error
        }
    }
}

async function main() {
    const { fullRepoName, prNumber, reviewState } = parseArgs()
    if (!shouldHandleReview(reviewState)) {
        console.log(`Review state "${reviewState}" does not require label updates.`)
        return
    }

    const { Octokit } = await import('@octokit/action')
    const octokit = new Octokit()
    await syncLabels(octokit, fullRepoName, prNumber)
    console.log(`Updated labels for PR #${prNumber}.`)
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
    try {
        await main()
    } catch (error) {
        console.error(error.message)
        process.exit(1)
    }
}
