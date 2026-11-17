// The `pending` job: reacts to the @-mention that asked for a review, and marks the head
// `code-review=pending` while the review runs. Runs no model.
'use strict';

async function reactToComment({ github, context, core }) {
    try {
        await github.rest.reactions.createForIssueComment({
            owner: context.repo.owner,
            repo: context.repo.repo,
            comment_id: context.payload.comment.id,
            content: 'eyes'
        });
    } catch (e) {
        core.warning(`Could not react to the review request comment: ${e.message}`);
    }
}

async function markPending({ github, context, core, process }) {
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const prNumber =
        context.eventName === 'workflow_dispatch'
            ? Number(context.payload.inputs.pr_number)
            : context.payload.pull_request
              ? context.payload.pull_request.number
              : context.payload.issue.number;

    const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    if ((pr.draft && context.eventName !== 'workflow_dispatch') || pr.state !== 'open') return;
    const head = pr.head.sha;

    const statuses = await github.paginate(github.rest.repos.listCommitStatusesForRef, {
        owner,
        repo,
        ref: head,
        per_page: 100
    });
    if (statuses.some(s => s.context === 'code-review')) return;

    await github.rest.repos.createCommitStatus({
        owner,
        repo,
        sha: head,
        context: 'code-review',
        state: 'pending',
        target_url: process.env.RUN_URL,
        description: 'Review in progress.'
    });
    core.setOutput('pr', String(prNumber));
    core.setOutput('head_sha', head);
}

module.exports = { reactToComment, markPending };
