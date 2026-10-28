/**
 * Pure, IO-free decision logic for new_pr_labeler.
 *
 * It lives in its own module so it can be unit tested: the entry script
 * (new_pr_labeler.mjs) runs main() at import time and depends on
 * @octokit/action, so it cannot be imported in vitest. These functions touch
 * no network and no argv, so the test imports them directly.
 */

/**
 * Returns the given issue's lead and priority labels, if any.
 *
 * @param {{data: {labels: Array<{name: string}>}}|null} issue An Octokit issue
 *        response, or null when the PR links no issue.
 * @returns {{leadName: string|undefined, priority: string|undefined}}
 */
export function getLinkedIssueMetadata(issue) {
    let leadName, priority;
    if (issue) {
        for (const label of issue.data.labels) {
            if (!leadName && label.name.startsWith('Lead: @')) {
                leadName = label.name.split('@')[1];
            }
            if (!priority && label.name.match(/Priority: [012]/)) {
                priority = label.name;
            }
        }
    }

    return { leadName, priority };
}

/**
 * Decides the assignee and labels a PR should receive from its linked issue's
 * metadata.
 *
 * A PR is never labeled "Needs: Lead": an unassigned PR already signals that it
 * needs a lead, so the label is redundant on PRs. ("Needs: Lead" stays
 * meaningful on issues, which this script does not touch.)
 *
 * @param {{leadName: string|undefined, priority: string|undefined}} metadata
 * @param {string} prAuthor The PR author's username.
 * @returns {{assignee: string|null, labels: string[]}} `assignee` is the lead to
 *          assign, or null when there is none to assign. `labels` are the labels
 *          to add to the PR.
 */
export function decideLabelsAndAssignee({ leadName, priority }, prAuthor) {
    // Don't assign the lead to the PR if the PR author is the issue lead.
    const assignee = leadName && leadName !== prAuthor ? leadName : null;

    const labels = [];
    if (priority) {
        labels.push(priority);
    }

    return { assignee, labels };
}
