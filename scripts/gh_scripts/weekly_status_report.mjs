import fs from 'node:fs'
import { Octokit } from "@octokit/action";

const octokit = new Octokit()

console.log('Starting script...')
main()
console.log('Finishing script...')

/**
 * Runs the weekly status report job.
 *
 * This function does the following:
 * 1. Reads in the configuration file
 * 2. Assembles a Slack message, one line at a time
 * 3. Publishes the assembled message to Slack
 */
async function main() {
    const config = getConfig()

    // Each line of the Slack message will be accumulated here:
    const lines = ['Project Management Helper']

    await prepareRecentComments(config.leads)
        .then((results) => lines.push(...results))
    
    const openPullRequests = await fetchOpenPullRequests()
    const nonDraftPullRequests = openPullRequests.filter((pull) => !pull.draft)

    if (config.forStaff) {
        await prepareUntriagedIssues()
            .then((results) => lines.push(...results))
        lines.push(...prepareUnassignedPullRequests(nonDraftPullRequests))
    }
    lines.push(...prepareAssignedPullRequests(nonDraftPullRequests, config.leads))
    if (config.forStaff) {
        lines.push(...prepareStaffPullRequests(nonDraftPullRequests, config.leads))
    }
    lines.push(...prepareSubmitterInput(nonDraftPullRequests, config.leads))

    // Publish message
    await publishToSlack(lines, config.slackChannel)
}

/**
 * Represents a project lead.
 *
 * @typedef {Object} Lead
 * @property {string} githubUsername The lead's GitHub username
 * @property {string} leadLabel      Label used to identify an issue's lead
 * @property {string} slackId        The lead's Slack identifier
 */

/**
 * Represents a configuration for this script.
 *
 * @typedef {Object} Config
 * @property {string} slackChannel The Slack channel where messages will be posted
 * @property {boolean} forStaff    `true` if this digest is for staff only
 * @property {Array<Lead>} leads   Project leads that will be included in this digest
 */

/**
 * Parses the configuration file and returns and returns the contents as an object.
 *
 * @returns {Config}
 */
function getConfig() {
    if (process.argv.length < 3) {
      throw new Error("Unexpected amount of arguments")
    }
    const configPath = process.argv[2]
    try {
        return JSON.parse(fs.readFileSync(configPath, 'utf8'))
    } catch (err) {
        throw err
    }
}

/**
 * Returns the Slack ID of the lead having the given GitHub username.
 *
 * @param {string} githubUsername 
 * @param {Array<Lead>} leads
 * @returns {string} The lead's Slack ID, or "UNKNOWN"
 */
function findSlackId(githubUsername, leads) {
    for (const lead of leads) {
        if (githubUsername === lead.githubUsername) {
            return lead.slackId
        }
    }

    // If we see "UNKNOWN" in the digest, our configurations
    // should be updated
    return 'UNKNOWN'
}

/**
 * Fetches and returns an array of all open pull requests for internetarchive/openlibrary.
 *
 * @returns {Promise<Array<Record>>}
 */
async function fetchOpenPullRequests() {
    return octokit.paginate('GET /repos/{owner}/{repo}/pulls', {
        owner: 'internetarchive',
        repo: 'openlibrary',
        per_page: 100,
        headers: {
          'X-GitHub-Api-Version': '2022-11-28'
        }
      })
}

/**
 * Finds all issues needing attention from the given leads, and prepares a message about them.
 *
 * @param {Array<Lead>} leads
 * @returns {Promise<Array<string>>} The recent comments, in order, line by line
 */
async function prepareRecentComments(leads) {
    const output = ['*Recent Comments*']
    const issuesAwaitingComments = await octokit.paginate('GET /repos/{owner}/{repo}/issues', {
        owner: 'internetarchive',
        repo: 'openlibrary',
        labels: `Needs: Response`,
        per_page: 100,
        headers: {
          'X-GitHub-Api-Version': '2022-11-28'
        }
      })
    for (const lead of leads) {
        const leadIssuesAwaitingComments = issuesAwaitingComments.filter((issue) => {
            for (const label of issue.labels) {
                if (label.name === lead.leadLabel) {
                    return true
                }
            }
            return false
        })
        const searchResultsUrl = `https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3A%22Needs%3A+Response%22+label%3A${encodeURIComponent('"' + lead.leadLabel + '"')}`
        output.push(`  • <${searchResultsUrl}|${leadIssuesAwaitingComments.length} issue(s)> need response from ${lead.slackId}`)
    }

    return output
}

/**
 * Finds all issues with the "Needs: Triage" label, prepares a message containing a link
 * for each, and returns the prepared messages.
 *
 * @returns {Promise<Array<string>>} Messages about untriaged issues
 */
async function prepareUntriagedIssues() {
    const searchResultsUrl = 'https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+label%3A%22Needs%3A+Triage%22'
    const untriagedIssues = await octokit.paginate('GET /repos/{owner}/{repo}/issues', {
        owner: 'internetarchive',
        repo: 'openlibrary',
        labels: `Needs: Triage`,
        per_page: 100,
        headers: {
          'X-GitHub-Api-Version': '2022-11-28'
        }
      })

    const output = [
        '*Untriaged Issues*', 
        `  <${searchResultsUrl}|Issues> with the "Needs: Triage" label:`
    ]
    for (const issue of untriagedIssues) {
        output.push(`  • <${issue.html_url}|${issue.title}>`)
    }

    return output
}

/**
 * Prepares a message containing links to unassigned pull requests.
 *
 * @param {Array<Record>} pullRequests Non-draft pull request records
 * @returns {Array<string>} Messages with links to our unassigned PRs
 */
function prepareUnassignedPullRequests(pullRequests) {
    const unassignedPrs = pullRequests.filter((pull) => !pull.assignee)
    const renovatebotPullCount = unassignedPrs.filter((pull) => pull.user.login === 'renovate[bot]').length
    const unassignedCount = unassignedPrs.length - renovatebotPullCount
    if (unassignedCount === 0) {
        return []
    }
    return [
        '*Unassigned PRs*',
        `  • <https://github.com/internetarchive/openlibrary/pulls?q=is%3Apr+is%3Aopen+no%3Aassignee+-is%3Adraft+-author:app/renovate|${unassignedCount} unassigned PRs> + <https://github.com/internetarchive/openlibrary/pulls/app%2Frenovate|${renovatebotPullCount} renovatebot>`
    ]
}

/**
 * Prepares and returns messages about each given lead's assigned PRs, including
 * their priorities.
 *
 * @param {Array<Record>} pullRequests Non-draft pull request records
 * @param {Array<Lead>} leads 
 * @returns {Array<string>} Messages with links to each lead's PRs
 */
function prepareAssignedPullRequests(pullRequests, leads) {
    const output = ['*Assigned PRs*']
    for (const lead of leads) {
        const searchResults = `https://github.com/internetarchive/openlibrary/pulls?q=is%3Aopen+is%3Apr+-is%3Adraft+assignee%3A${lead.githubUsername}`
        const assignedPulls = pullRequests.filter((pull) => {
            for (const assignee of pull.assignees || []) {
                if (assignee.login === lead.githubUsername) {
                    return true
                }
            }
            return false
        })

        let p0Count = 0,
            p1Count = 0,
            p2Count = 0
        assignedPulls.forEach((pull) => {
            for (const label of pull.labels) {
                switch(label.name) {
                    case 'Priority: 0':
                        ++p0Count;
                        break
                    case 'Priority: 1':
                        ++p1Count
                        break
                    case 'Priority: 2':
                        ++p2Count
                        break;
                }
            }
        })
        let statusText = `  • ${lead.slackId} <${searchResults}|${assignedPulls.length} PR(s)>`

        if (p0Count || p1Count || p2Count) {
            statusText += ' ['
            if (p0Count) {
                statusText += `<${searchResults + '+label%3A"Priority%3A+0"'}|P0:${p0Count}>, `
            }
            if (p1Count) {
                statusText += `<${searchResults + '+label%3A"Priority%3A+1"'}|P1:${p1Count}>, `
            }
            if (p2Count) {
                statusText += `<${searchResults + '+label%3A"Priority%3A+2"'}|P2:${p2Count}>`
            } else {
                // Remove the trailing `, ` characters:
                statusText = statusText.substring(0, statusText.length - 3)
            }
            statusText += ']'
        }
        output.push(statusText)
    }

    return output
}

/**
 * Prepares and returns messages about the status of open staff PRs.
 *
 * PRs labeled with any of the `excludedLabels` will not be included in the
 * output of this function.
 *
 * @param {Array<Record>} pullRequests 
 * @param {Array<Lead>} leads 
 * @returns {Array<string>} Messages with the current status of each staff PR
 */
function prepareStaffPullRequests(pullRequests, leads) {
    // Include PRs with authors that are in the `leads` configuration:
    const includeAuthors = []
    leads.forEach((lead) => includeAuthors.push(lead.githubUsername))

    // Exclude PRs that have these labels:
    const excludeLabels = ['Needs: Submitter Input', 'State: Blocked']

    const output = ['*Staff PRs*']
    for (const pull of pullRequests) {
        const authorName = pull.user?.login
        let highPriorityEmoji = ''
        if (!includeAuthors.includes(authorName)) {
            continue
        }
        let skipItem = false
        for (const label of pull.labels) {
            if (excludeLabels.includes(label.name)) {
                skipItem = true
                break
            }
            if (label.name === 'Priority: 0') {
                highPriorityEmoji = '| 🚨 '
            }
            if (label.name === 'Priority: 1' && !highPriorityEmoji) {  // Don't clobber higher priority emoji
                highPriorityEmoji = '| ❗️ '
            }
        }
        if (skipItem) {
            continue
        }

        const assigneeName = pull.assignee?.login
        // Issue title and link:
        output.push(`  • <${pull.html_url}|*#${pull.number}* | ${pull.title}>`)
        
        // Creator, assignee, and priority:
        const now = Date.now()
        const openedAt = Date.parse(pull.created_at)
        const elapsedTime = now - openedAt  // Time in milliseconds
        const daysPassed = Math.floor(elapsedTime / (24 * 60 * 60 * 1000))

        const assigneeSlackId = assigneeName ? findSlackId(assigneeName, leads) : '⚠️ None'
        output.push(`  by ${pull.user.login} ${daysPassed} days ago | Assigned: ${assigneeSlackId} ${highPriorityEmoji}`)
    }

    return output
}

/**
 * Prepares and returns messages about each given lead's pull requests that are labeled
 * `Needs: Submitter Input`.
 *
 * @param {Array<Record>} pullRequests 
 * @param {Array<Lead>} leads 
 * @returns {Array<string>} Messages about PRs that require submitter input before being reviewed
 */
function prepareSubmitterInput(pullRequests, leads) {
    const output = ['*Submitter Input for our PRs*']
    for (const lead of leads) {
        const searchResultsUrl = `https://github.com/internetarchive/openlibrary/pulls?q=is%3Aopen+is%3Apr+-is%3Adraft+assignee%3A${lead.githubUsername}+label%3A"Needs%3A+Submitter+Input"`
        const assignedPulls = pullRequests.filter((pull) => pull.assignee?.login === lead.githubUsername)
        let awaitingResponseCount = 0
        assignedPulls.forEach((pull) => {
            for (const label of pull.labels) {
                if (label.name === 'Needs: Response') {
                    ++awaitingResponseCount
                    break
                }
            }
        })

        output.push(`  • ${lead.slackId} <${searchResultsUrl}|${awaitingResponseCount} PR(s)>`)
    }

    return output
}

/**
 * Composes a message out of the given `lines` of text, and publishes the
 * message to the given Slack channel.
 *
 * Slack message is composed by joining each line of text in the `lines`
 * array with newline characters.
 *
 * @param {Array<string>} lines 
 * @param {string} slackChannel 
 * @returns {Promise<Response>}
 */
async function publishToSlack(lines, slackChannel) {
    const message = lines.join('\n')
    const bearerToken = process.env.SLACK_TOKEN
    return fetch('https://slack.com/api/chat.postMessage', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json;  charset=utf-8',
            Authorization: `Bearer ${bearerToken}`
        },
        body: JSON.stringify({
            channel: slackChannel,
            text: message
        })
    })
}
