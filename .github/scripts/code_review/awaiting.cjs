// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// code_review_awaiting.yml: on a new or pushed-to PR, mark a head that has no review yet as
// code-review=pending with what happens next, and with handle_push_trigger on, re-request the
// review once no more commits arrive for push_review_delay_minutes.
'use strict';

const BOT = 'openlibrary-bot';
const TEAM = 'openlibrary-agentic-code-reviewer';
// The status while a push review waits for pushes to stop. requestAfterQuiet checks the status still
// starts with it, so a hand-started review (which replaces it with "Review in progress.") isn't
// followed by a second one. The older wording is still recognised for runs started before the change.
const WAITING = 'Waiting for pushes to stop.';
const OLD_WAITING = 'New commits. A review starts after';
const isWaiting = description => [WAITING, OLD_WAITING].some(p => String(description || '').startsWith(p));
// "Review starts ~21:36 UTC": when the wait ends if no more commits arrive. A status shows the
// same yellow dot while waiting and while reviewing, so the text has to say which, and how to skip
// the wait. Kept under GitHub's 140-character limit for a status description.
const waitingText = (minutes, now) => {
    const at = new Date(now + minutes * 60 * 1000).toISOString().slice(11, 16);
    return `${WAITING} Review starts ~${at} UTC, or comment @openlibrary-bot review to start now.`;
};

// True when the push only merged the base branch into the previous head, as "Update branch" does.
// Same test as PR-Agent's is_base_branch_merge.
async function mergesOnlyBase({ github, owner, repo, payload }) {
    const { data: commit } = await github.rest.repos.getCommit({ owner, repo, ref: payload.after });
    const parents = commit.parents.map(p => p.sha);
    if (parents.length !== 2 || parents[0] !== payload.before) return false;
    const { data: cmp } = await github.rest.repos.compareCommitsWithBasehead({
        owner,
        repo,
        basehead: `${parents[1]}...${payload.pull_request.base.ref}`
    });
    return cmp.status === 'ahead' || cmp.status === 'identical';
}

// A PR into a branch other than the default one, such as another PR's branch.
const stacked = payload => Boolean(payload.repository && payload.pull_request.base.ref !== payload.repository.default_branch);

// Whether this push should start a review after the quiet period, and why not if it shouldn't.
async function pushReview({ github, owner, repo, payload, settings, reviewedBefore }) {
    const cfg = settings.github_action_config;
    if (payload.action !== 'synchronize' || !cfg.handle_push_trigger) return 'push reviews are off';
    // A review request on a stacked PR starts nothing (see code_review_action.yml's analyze job).
    if (stacked(payload)) return 'the PR is stacked on another branch';
    // The first review is a maintainer's call (or auto_assign_reviewer.yml's): it is the spend gate.
    if (!reviewedBefore) return 'the PR has not been reviewed yet';
    if ((payload.pull_request.labels || []).some(l => l.name === 'no-automation')) return 'the PR has the no-automation label';
    if (cfg.push_trigger_ignore_bot_commits && (payload.sender.type === 'Bot' || payload.sender.login === BOT)) return 'a bot pushed';
    if (cfg.push_trigger_ignore_merge_commits && (await mergesOnlyBase({ github, owner, repo, payload }))) return 'the push only merged the base branch';
    return null;
}

async function markAwaiting({ github, context, core, settings, runUrl, now = Date.now() }) {
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const { payload } = context;
    const pr = payload.pull_request;
    if (pr.draft || pr.state !== 'open') return;

    const statuses = await github.paginate(github.rest.repos.listCommitStatusesForRef, { owner, repo, ref: pr.head.sha, per_page: 100 });
    if (statuses.some(s => s.context === 'code-review')) return;

    const reviews = await github.paginate(github.rest.pulls.listReviews, { owner, repo, pull_number: pr.number, per_page: 100 });
    // A review still running, or one that was withheld, has posted nothing yet, but the team is still requested.
    const { data: requested } = await github.rest.pulls.listRequestedReviewers({ owner, repo, pull_number: pr.number });
    const reviewedBefore =
        reviews.some(r => r.user && r.user.login === BOT) || requested.teams.some(t => t.slug === TEAM) || requested.users.some(u => u.login === BOT);
    const skip = await pushReview({ github, owner, repo, payload, settings, reviewedBefore });
    const minutes = settings.openlibrary_reviewer.push_review_delay_minutes;
    if (skip) core.info(`No review on this push: ${skip}.`);
    else core.setOutput('review_after_minutes', String(minutes));

    let description = 'Not reviewed yet. A maintainer can request review from openlibrary-agentic-code-reviewer.';
    if (!skip) description = waitingText(minutes, now);
    else if (stacked(payload)) description = 'Stacked on another branch. Comment @openlibrary-bot review to review it.';
    else if (reviewedBefore) description = 'New commits since the last review. Re-request review from openlibrary-bot to review them.';
    await github.rest.repos.createCommitStatus({
        owner,
        repo,
        sha: pr.head.sha,
        context: 'code-review',
        state: 'pending',
        target_url: runUrl,
        description
    });
}

// Waits, then re-requests the review team, which starts code_review_action.yml as a manual request
// would. A later push cancels this run (the workflow's concurrency group), so only the last push of
// a burst gets reviewed.
async function requestAfterQuiet({ github, context, core, minutes, sleep = ms => new Promise(r => setTimeout(r, ms)) }) {
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const pr = context.payload.pull_request;
    await sleep(minutes * 60 * 1000);

    const { data: live } = await github.rest.pulls.get({ owner, repo, pull_number: pr.number });
    if (live.head.sha !== pr.head.sha || live.state !== 'open' || live.draft) {
        core.info('The PR changed while waiting; leaving it to the newer run.');
        return;
    }
    // Someone requested a review by hand while we waited: its status replaced ours.
    const statuses = await github.paginate(github.rest.repos.listCommitStatusesForRef, { owner, repo, ref: pr.head.sha, per_page: 100 });
    const current = statuses.find(s => s.context === 'code-review');
    if (!current || !isWaiting(current.description)) {
        core.info('A review already started on this commit; not requesting another.');
        return;
    }
    // A still-pending team request must be removed first, or requesting it again fires no event.
    await github.rest.pulls.removeRequestedReviewers({ owner, repo, pull_number: pr.number, reviewers: [], team_reviewers: [TEAM] }).catch(() => {});
    await github.rest.pulls.requestReviewers({ owner, repo, pull_number: pr.number, team_reviewers: [TEAM] });
    core.info(`Requested a review from ${TEAM}.`);
}

module.exports = { markAwaiting, requestAfterQuiet, mergesOnlyBase };
