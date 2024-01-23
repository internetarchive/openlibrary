/**
 * Runs the auto-unassigner script.
 *
 * Optional parameters:
 * --daysSince : Number : Issues that have had the same assignee for at least this many days are candidates for unassignment
 * --repoOwner : String : Pass to run on a specific OpenLibrary fork
 */
import {Octokit} from "@octokit/action";

console.log('Script starting...')

const DEFAULT_OPTIONS = {
    daysSince: 14,
    repoOwner: 'internetarchive'
}

const passedArguments = parseArgs()

const mainOptions = Object.assign({}, DEFAULT_OPTIONS, passedArguments)
// `daysSince` will be a string if passed in from the command line
mainOptions.daysSince = Number(mainOptions.daysSince)

// Octokit is authenticated with the `GITHUB_TOKEN` that is added to the
// environment in the `auto_unassigner` workflow
const octokit = new Octokit();

// XXX : What do we want to say when we remove assignees?
/**
 * Comment that will be left on issue when assignee is removed.
 *
 * @type {string}
 */
const issueComment = `Assignees removed automatically after ${mainOptions.daysSince} days.`

/**
 * List of GitHub usernames who, if assigned to an issue, should not be unassigned.
 * @type {String[]}
 * @see {excludeAssigneesFilter}
 */
const excludeAssignees = []

/**
 * List of GitHub labels that, if on an issue, excludes the issue from automation.
 * @type {String[]}
 */
const excludeLabels = ['no-automation']

/**
 * Functions used to filter out issues that should have their assignees removed.
 *
 * Each function in this array should take an array of records as a parameter, and
 * return a promise that resolves to an array of records.
 *
 * Functions will be called in order, and pass along their results to the next filter.
 * If possible, long-running or otherwise expensive calls should be added to the end
 * of this array.
 * @type {CallableFunction[]}
 * @see {filterIssues}
 */
const filters = [
    excludePullRequestsFilter,
    excludeLabelsFilter,
    excludeAssigneesFilter,
    recentAssigneeFilter,
    linkedPullRequestFilter
]

/**
 * Multiple filters will require data from the GitHub Timeline API before a decision
 * about an issue can be made. In order to avoid redundant API calls, timeline results
 * will be stored here. Issue number is used as the key.
 * @type {Record<Number, Record[]>}
 */
const issueTimelines = {}

await main()

console.log('Script terminated...')

/**
 * Runs the auto-unassigner job.
 *
 * @returns {Promise<void>}
 */
async function main() {  // XXX : Inject octokit for easier testing
    const issues = await fetchIssues()
    console.log(`Open issues with assignees: ${issues.length}`)

    if (issues.length === 0) {
        console.log('No issues were returned by the initial query')
        return
    }

    const actionableIssues = await filterIssues(issues, filters)
    console.log(`Issues remaining after filtering: ${actionableIssues.length}`)

    for (const issue of actionableIssues) {
        const assigneesToRemove = []
        for (const assignee of issue.assignees) {
            if (!('ol_unassign_ignore' in assignee)) {
                assigneesToRemove.push(assignee.login)
            }
        }

        if (assigneesToRemove.length > 0) {
            const wasRemoved = await unassignFromIssue(issue.number, assigneesToRemove)
            if (wasRemoved) {
                await commentOnIssue(issue.number, issueComment)
            }
        }
    }
}

/**
 * Parses any arguments that were passed when this script was executed, and returns
 * an object containing the arguments.
 *
 * Exits the script if an odd number of arguments are provided.  The script takes only
 * options as arguments, and we expect a space between the option flag and value:
 * `--flag value_of_flag`
 *
 * @returns {Record}
 */
function parseArgs() {
    const result = {}
    // XXX : Does this check make sense?
    if (process.argv.length % 2 !== 0) {
        console.log('Unexpected number of arguments')
        process.exit(1)
    }
    if (process.argv.length > 2) {
        for (let i = 2, j = 3; i < process.argv.length; i+=2, j+=2) {
            let arg = process.argv[i]
            // Remove leading `-` characters
            while (arg.charAt(0) === '-') {
                arg = arg.substring(1)
            }
            result[arg] = process.argv[j]
        }
    }

    return result
}

// START: API Calls
/**
 * Returns all GitHub issues that are open and one or more assignees.
 *
 * __Important:__ GitHub's REST API considers every pull request to be an
 * issue.  Pull requests may be included in the results returned by this
 * function, and can be identified by the presence of a `pull_request` key.
 *
 * @returns {Promise<Array<Record>>}
 * @see  [GitHub REST documentation]{@link https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#list-repository-issues}
 */
async function fetchIssues() {
    return await octokit.paginate('GET /repos/{owner}/{repo}/issues', {
            owner: mainOptions.repoOwner,
            repo: 'openlibrary',
            headers: {
                'X-GitHub-Api-Version': '2022-11-28'
            },
            assignee: '*',
            state: 'open',
            per_page: 100
        })
}

/**
 * Returns the timeline of the given issue.
 *
 * Attempts to get the timeline from the `issueTimelines` store. If no
 * timeline is found, calls GitHub's Timeline API and stores the result
 * before returning.
 *
 * @param issue {Record}
 * @returns {Promise<Array<Record>>}
 * @see {issueTimelines}
 */
async function getTimeline(issue) {
    const issueNumber = issue.number
    if (issueTimelines[issueNumber]) {
        return issueTimelines[issueNumber]
    }

    // Fetching timeline:
    const repoUrl = issue.repository_url
    const splitUrl = repoUrl.split('/')
    const repoOwner = splitUrl[splitUrl.length - 2]
    const timeline = await octokit.paginate('GET /repos/{owner}/{repo}/issues/{issue_number}/timeline', {
            owner: repoOwner,
            repo: 'openlibrary',
            issue_number: issueNumber,
            per_page: 100,
            headers: {
                'X-GitHub-Api-Version': '2022-11-28'
            }
        })

    // Store timeline for future use:
    issueTimelines[issueNumber] = timeline

    return timeline
}

/**
 * Removes the given assignees from the issue identified by the given issue number.
 *
 * @param issueNumber {number}
 * @param assignees {Array<string>}
 * @returns {Promise<boolean>} `true` if unassignment operation was successful
 */
async function unassignFromIssue(issueNumber, assignees) {
    return await octokit.request('DELETE /repos/{owner}/{repo}/issues/{issue_number}/assignees', {
        owner: mainOptions.repoOwner,
        repo: 'openlibrary',
        issue_number: issueNumber,
        assignees: assignees,
        headers: {
            'X-GitHub-Api-Version': '2022-11-28'
        }
    })
        .then(() => {
            return true
        })
        .catch((error) => {
            console.log(`Failed to remove assignees from issue #${issueNumber}`)
            console.log(`Response status: ${error.status}`)
            return false
        })
}

/**
 * Creates a new comment on the given issue.
 *
 * @param issueNumber {number}
 * @param comment {string}
 * @returns {Promise<boolean>} `true` if the comment was created
 */
async function commentOnIssue(issueNumber, comment) {
    return await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/comments', {
        owner: mainOptions.repoOwner,
        repo: 'openlibrary',
        issue_number: issueNumber,
        body: comment,
        headers: {
            'X-GitHub-Api-Version': '2022-11-28'
        },
    })
        .then(() => {
            return true
        })
        .catch((error) => {
            // Promise is rejected if the call fails
            console.log(`Failed to comment on issue #${issueNumber}`)
            console.log(`Response status: ${error.status}`)
            return false
        })
}
// END: API Calls

// START: Issue Filtering
/**
 * Returns the results of filtering the given issues.
 *
 * The given filters are functions that are meant to be
 * passed to Array.
 * @param issues {Array<Record>}
 * @param filters {Array<CallableFunction>}
 * @returns {Promise<Array<Record>>}
 */
async function filterIssues(issues, filters) {
    let results = issues

    for (const f of filters) {
        results = await f(results)
    }
    return results
}

// Filters:
/**
 * Iterates over given issues and filters out pull requests.
 *
 * Necessary because GitHub's REST API considers pull requests to be a
 * type of issue.
 * @param issues {Array<Record>}
 * @returns {Promise<Array<Record>>}
 */
async function excludePullRequestsFilter(issues) {
    const results = []
    for (const issue of issues) {
        if (!('pull_request' in issue)) {
            results.push(issue)
        }
    }
    return results
}

/**
 * Checks each given issue and returns array of issues that do not have
 * an exclusion label.
 *
 * @param issues {Array<Record>}
 * @returns {Promise<Array<Record>>}
 * @see {excludeLabels}
 */
async function excludeLabelsFilter(issues) {
    const results = []
    for (const issue of issues) {
        let hasLabel = false
        const labels = issue.labels
        for (const label of labels) {
            if (excludeLabels.includes(label.name)) {
                hasLabel = true
            }
        }
        if (!hasLabel) {
            results.push(issue)
        }
    }

    return results
}

/**
 * Checks each given issue and returns array of issues that have at least
 * one assignee who is not on the exclusion list.
 *
 * __Important__: This function also updates the given issue. A `ol_unassign_ignore`
 * flag is added to any `assignee` that appears on the exclude list.
 *
 * @param issues {Array<Record>}
 * @returns {Promise<Array<Record>>}
 * @see {excludeAssignees}
 */
async function excludeAssigneesFilter(issues) {
    const results = []

    for (const issue of issues) {
        let allAssigneesExcluded = true
        const assignees = issue.assignees

        for (const assignee of assignees) {
            const username = assignee.login
            if (!excludeAssignees.includes(username)) {
                allAssigneesExcluded = false
            } else {
                // Flag excluded assignees
                assignee.ol_unassign_ignore = true
            }
        }

        if (!allAssigneesExcluded) {
            results.push(issue)
        }
    }

    return results
}

/**
 * Iterates over given issues, returning array of issues that have stale
 * assignees.
 *
 * __Important__: This function adds the `ol_unassign_ignore` flag to
 * assignees that haven't yet been assigned for too long.
 * @param issues {Array<Record>}
 * @returns {Promise<Array<Record>>}
 */
async function recentAssigneeFilter(issues) {
    const results = []

    for (const issue of issues) {
        const timeline = await getTimeline(issue)
        const daysSince = mainOptions.daysSince

        const currentDate = new Date()
        const assignees = issue.assignees
        let staleAssigneeFound = false

        for (const assignee of assignees) {
            if ('ol_unassign_ignore' in assignee) {
                continue
            }
            const assignmentDate = getAssignmentDate(assignee, timeline)
            const timeDelta = currentDate.getTime() - assignmentDate.getTime()
            const daysPassed = timeDelta/(1000 * 60 * 60 * 24)
            if (daysPassed > daysSince) {
                staleAssigneeFound = true
            } else {
                assignee.ol_unassign_ignore = true
            }
        }

        if (staleAssigneeFound) {
            results.push(issue)
        }
    }

    return results
}

/**
 * Returns the date that the given assignee was assigned to an issue.
 *
 * @param assignee {Record}
 * @param issueTimeline {Record}
 * @returns {Date}
 */
function getAssignmentDate(assignee, issueTimeline) {
    const assigneeName = assignee.login
    const assignmentEvent = issueTimeline.findLast((event) => {
        return event.event === 'assigned' && event.assignee.login === assigneeName
    })

    if (!assignmentEvent) {  // Somehow, the assignment event was not found
        // Avoid accidental unassignment by sending the current time
        return new Date()
    }

    return new Date(assignmentEvent.created_at)
}

/**
 * Iterates over given issues, and returns array containing issues that
 * have no linked pull requests that are open.
 *
 * @param issues {Array<Record>}
 * @returns {Promise<*[]>}
 */
async function linkedPullRequestFilter(issues) {
    const results = []
    for (const issue of issues) {
        const timeline = await getTimeline(issue)
        const assignees = issue.assignees.filter((assignee) => !('ol_unassign_ignore' in assignee))
        const crossReferences = timeline.filter((event) => event.event === 'cross-referenced')

        let noLinkedPullRequest = true
        for (const assignee of assignees) {
            crossReferences.find((event) => {
                const hasLinkedPullRequest = event.source.type === 'issue' &&
                    event.source.issue.state === 'open' &&
                    ('pull_request' in event.source.issue) &&
                    event.source.issue.user.login === assignee.login &&
                    event.source.issue.body.toLowerCase().includes(`closes #${issue.number}`)
                if (hasLinkedPullRequest) {
                    noLinkedPullRequest = false
                }
            })
        }

        if (noLinkedPullRequest) {
            results.push(issue)
        }
    }

    return results
}
// END: Issue Filtering
