/**
 * Pure, IO-free decision logic for assigning PR leads.
 *
 * It lives in its own module so it can be unit tested: the entry scripts
 * (new_pr_labeler.mjs, pr_lead_sweep.mjs) run at import time and depend on
 * @octokit/action, so they cannot be imported in vitest. These functions touch
 * no network and no argv, so the tests import them directly.
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
 * The lead is assigned even when they wrote the PR: as the owner they still have
 * to see it through or hand it to someone else.
 *
 * A PR is never labeled "Needs: Lead": an unassigned PR already signals that it
 * needs a lead, so the label is redundant on PRs. ("Needs: Lead" stays
 * meaningful on issues, which this logic does not touch.)
 *
 * @param {{leadName: string|undefined, priority: string|undefined}} metadata
 * @returns {{assignee: string|null, labels: string[]}} `assignee` is the lead to
 *          assign, or null when there is none to assign. `labels` are the labels
 *          to add to the PR.
 */
export function decideLabelsAndAssignee({ leadName, priority }) {
    const assignee = leadName ?? null;

    const labels = [];
    if (priority) {
        labels.push(priority);
    }

    return { assignee, labels };
}

// A closing keyword (GitHub's own set), optionally followed by a colon.
const CLOSING_KEYWORDS = String.raw`close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved`;
// Phrases contributors use for work that does not close the issue (e.g. one PR of an epic).
const REFERENCE_PHRASES = String.raw`part\s+of|refs?|references|related\s+to|follow[\s-]*ups?\s+(?:to|of|on)|works?\s+on|towards?`;

/**
 * Builds a case-insensitive global regex matching `<phrase> #N`, or `<phrase>`
 * followed by a same-repo issue or pull URL. Capture group 1 is N.
 *
 * @param {string} phrases Alternation of phrases, as a regex source string.
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary"
 * @returns {RegExp}
 */
function referenceRegex(phrases, fullRepoName) {
    const repo = fullRepoName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(String.raw`\b(?:${phrases}):?\s+(?:#|https://github\.com/${repo}/(?:issues|pull)/)(\d+)\b`, 'gi');
}

/**
 * Lists the issue references in a PR body, most authoritative first: every
 * closing reference (`Closes #N`) in order, then every non-closing reference
 * (`Part of #N`, `Refs #N`, ...) in order. Duplicates are dropped.
 *
 * @param {string} body The PR body.
 * @param {string} fullRepoName e.g. "internetarchive/openlibrary"
 * @returns {Array<{number: number, kind: 'closing'|'reference'}>}
 */
export function findIssueReferences(body, fullRepoName) {
    // References inside HTML comments (e.g. left-over PR template text) don't count.
    const text = (body ?? '').replace(/<!--[\s\S]*?-->/g, ' ');
    const found = [];
    const seen = new Set();
    for (const [kind, phrases] of [
        ['closing', CLOSING_KEYWORDS],
        ['reference', REFERENCE_PHRASES]
    ]) {
        for (const match of text.matchAll(referenceRegex(phrases, fullRepoName))) {
            const number = Number(match[1]);
            if (!seen.has(number)) {
                seen.add(number);
                found.push({ number, kind });
            }
        }
    }
    return found;
}

/**
 * Works out the lead and priority to take from a referenced issue.
 *
 * - The lead comes from the issue, or failing that from its parent issue (the
 *   epic it is a sub-issue of).
 * - The priority is only inherited from a closing reference, and only from the
 *   issue itself: "Part of #N" usually points at an epic, whose priority says
 *   little about one PR.
 *
 * @param {{data: {labels: Array<{name: string}>}}} issue
 * @param {{data: {labels: Array<{name: string}>}}|null} parent
 * @param {'closing'|'reference'} kind
 * @returns {{leadName: string|undefined, priority: string|undefined, leadSource: 'issue'|'parent'|undefined}}
 */
export function resolveIssueMetadata(issue, parent, kind) {
    const own = getLinkedIssueMetadata(issue);
    const fromParent = getLinkedIssueMetadata(parent);
    const leadName = own.leadName ?? fromParent.leadName;
    return {
        leadName,
        priority: kind === 'closing' ? own.priority : undefined,
        leadSource: own.leadName ? 'issue' : fromParent.leadName ? 'parent' : undefined
    };
}

/**
 * Decides whether the scheduled sweep should consider a PR.
 *
 * Only PRs nobody has ever assigned are touched, so the sweep never re-assigns
 * someone a human deliberately removed. Any earlier assignment counts, including
 * a self-assignment, so such a PR never gets its lead added automatically.
 *
 * @param {{isDraft: boolean, authorLogin: string|null, authorIsBot: boolean, hasAssignees: boolean, everAssigned: boolean}} pr
 * @returns {string|null} The reason to skip, or null to sweep it.
 */
export function sweepSkipReason({ isDraft, authorLogin, authorIsBot, hasAssignees, everAssigned }) {
    if (isDraft) return 'draft';
    // openlibrary-bot is a regular User account, so its type alone does not mark it as a bot.
    if (authorIsBot || !authorLogin || authorLogin === 'openlibrary-bot') return 'bot author';
    if (hasAssignees) return 'already assigned';
    if (everAssigned) return 'previously assigned';
    return null;
}

/**
 * The labels the sweep adds: the planned priority, unless the PR already has a
 * `Priority:` label (set by a human or an earlier run).
 *
 * @param {string[]} plannedLabels
 * @param {string[]} prLabelNames
 * @returns {string[]}
 */
export function sweepLabels(plannedLabels, prLabelNames) {
    return prLabelNames.some(name => name.startsWith('Priority:')) ? [] : plannedLabels;
}

/**
 * Keeps an issue's `Needs: Lead` label in step with its `Lead: @` label: an
 * issue needs it exactly when it has no lead. Templates add `Needs: Lead` on
 * creation, but nothing removes it when a lead is added later, or adds it back
 * when a lead is removed.
 *
 * @param {string[]} labelNames The issue's current labels.
 * @returns {'add'|'remove'|null} The change to make, or null when it's already right.
 */
export function needsLeadChange(labelNames) {
    const hasLead = labelNames.some(name => name.startsWith('Lead: @'));
    const hasNeedsLead = labelNames.includes('Needs: Lead');
    if (!hasLead && !hasNeedsLead) return 'add';
    if (hasLead && hasNeedsLead) return 'remove';
    return null;
}

/**
 * Decides whether an issue a PR references should move from `Needs: Response`
 * to `Needs: Review`: once an open PR works on it, the next step is reviewing
 * the PR, not answering on the issue. Closed issues are left alone.
 *
 * @param {{state: string, labelNames: string[]}} issue `state` is GraphQL's OPEN or CLOSED.
 * @returns {boolean}
 */
export function needsReviewSwap({ state, labelNames }) {
    return state === 'OPEN' && labelNames.includes('Needs: Response');
}

/** Pure decision for the first closing reference only. Comments must be fully fetched before deciding to close. */
export function decideGfiAction({ pr, issue, kind, hasCommented }) {
    const skip = reason => ({ action: 'skip', reason });
    const labels = item => item.labels.map(label => (typeof label === 'string' ? label : label.name));
    const sameName = (a, b) => a.toLowerCase() === b.toLowerCase();
    if (kind !== 'closing') return skip('no closing reference');
    if (issue.pull_request || issue.state !== 'open' || !labels(issue).includes('Good First Issue')) return skip('not an open Good First Issue');
    if (pr.state !== 'open' || pr.draft) return skip('PR is closed or draft');
    if (labels(pr).includes('no-automation') || labels(issue).includes('no-automation')) return skip('no-automation');
    if (['MEMBER', 'OWNER', 'COLLABORATOR'].includes(pr.author_association)) return skip('staff author');
    const author = pr.user.login;
    if (sameName(author, 'openlibrary-bot') || /\[bot\]$/i.test(author)) return skip('bot author');
    if (issue.assignees.some(user => sameName(user.login, author))) return skip('already assigned to author');
    if (issue.assignees.length) return { action: 'close', reason: 'duplicate' };
    if (hasCommented === undefined) return skip('comments not fetched');
    return hasCommented ? { action: 'assign', reason: 'author commented' } : { action: 'close', reason: 'missing comment' };
}
