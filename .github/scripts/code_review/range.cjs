// The `analyze` job's "Resolve review range" step: decides whether this run reviews, re-posts the
// status of an existing review, or skips, and writes the range, diff and settings the model reads.
// Runs before the model, from the BASE checkout.
'use strict';

const { parseReviewMarker, unresolvedThreadCount } = require('./shared.cjs');

async function resolveRange({ github, context, core, require, process }) {
    const fs = require('fs');
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const prNumber =
        context.eventName === 'workflow_dispatch'
            ? Number(context.payload.inputs.pr_number)
            : context.payload.pull_request
              ? context.payload.pull_request.number
              : context.payload.issue.number;

    const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    // Draft check for the automatic paths -- issue_comment's payload has no draft field.
    // A manual dispatch reviews drafts on purpose (see the trigger comment in code_review_action.yml).
    if (pr.draft && context.eventName !== 'workflow_dispatch') {
        core.info(`PR #${prNumber} is a draft -- skipping.`);
        core.setOutput('skip', 'true');
        return;
    }
    if (pr.state !== 'open') {
        core.info(`PR #${prNumber} is ${pr.state} -- skipping.`);
        core.setOutput('skip', 'true');
        return;
    }

    const head = pr.head.sha;

    // Incremental: find the newest review WE submitted and diff from its commit.
    // Epic #13160's cross-cutting rule -- ignore our own bot -- is why we look for our
    // own reviews here rather than any review.
    const reviews = await github.paginate(github.rest.pulls.listReviews, {
        owner,
        repo,
        pull_number: prNumber,
        per_page: 100
    });
    const ours = reviews.filter(r => r.user && r.user.login === 'openlibrary-bot' && r.commit_id);
    const prior = ours.length ? ours[ours.length - 1] : null;

    let base = pr.base.sha,
        incremental = false;
    if (prior && prior.commit_id !== head) {
        // Only trust the prior SHA if it is still reachable AND an ancestor of head; a
        // force-push can leave a commit_id that no longer describes this PR's history,
        // and diffing from it would silently mis-scope the review.
        try {
            const cmp = await github.rest.repos.compareCommitsWithBasehead({
                owner,
                repo,
                basehead: `${prior.commit_id}...${head}`
            });
            if (cmp.data.status === 'ahead' && cmp.data.files && cmp.data.files.length) {
                base = prior.commit_id;
                incremental = true;
            } else {
                core.info(`Prior review commit is ${cmp.data.status} -- falling back to a full review.`);
            }
        } catch (e) {
            core.info(`Could not compare against the prior review commit (${e.message}) -- full review.`);
        }
    } else if (prior && prior.commit_id === head) {
        // #14486 -- STATE-aware skip: skip only when the present `code-review` status MATCHES the
        // verdict this head's existing review implies; absent/stale/contradicting -> idempotent
        // status repost (skip=false, repost=true) and the status job recomputes it. Bound to the
        // resolver-pinned head SHA (#14476 D1). NO model re-run.
        //
        // parseReviewMarker + unresolvedThreadCount come from shared.cjs, the same definitions the
        // status job's repost path uses. The reviewForVerdict selector below must match that path's
        // selection; a drift-pin test runs both against the same inputs and asserts they agree.
        // Last openlibrary-bot review on this head WITH A BODY -- matches the status job's
        // selection. `prior` omits the `&& r.body` filter (it drives the incremental range), so
        // reusing it here could pick a different review and make the two verdicts disagree.
        const onHead = reviews.filter(r => r.user && r.user.login === 'openlibrary-bot' && r.commit_id === head && r.body);
        const reviewForVerdict = onHead.length ? onHead[onHead.length - 1] : null;

        // Live review threads (GraphQL -- REST carries no resolved/outdated state). Fail SAFE on a
        // transient read error -> repost, so a flaky API never leaves a stale status un-corrected
        // (an unset `skip` output would make the status job's `if: skip == 'false'` skip the repost).
        let threads = [],
            cursor = null;
        try {
            for (;;) {
                const page = await github.graphql(
                    `query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
               repository(owner:$owner,name:$repo){
                 pullRequest(number:$pr){
                   reviewThreads(first:100, after:$cursor){
                     nodes { isResolved isOutdated }
                     pageInfo { hasNextPage endCursor }
                   }
                 }
               }
             }`,
                    { owner, repo, pr: prNumber, cursor }
                );
                const rt = page.repository.pullRequest.reviewThreads;
                threads = threads.concat(rt.nodes);
                if (!rt.pageInfo.hasNextPage) break;
                cursor = rt.pageInfo.endCursor;
            }
        } catch (e) {
            core.info(`Could not read review threads (${e.message}) -- routing to a status repost (the status job recomputes the verdict).`);
            core.setOutput('pr', String(prNumber));
            core.setOutput('head_sha', head);
            core.setOutput('skip', 'false');
            core.setOutput('repost', 'true');
            return;
        }

        // PASS needs a bot review with a readable f=0 marker AND zero blocking threads; anything
        // else (unreadable marker -> null, body-less/absent review) fails closed to 'failure'.
        // oxlint-disable-next-line eqeqeq -- loose on purpose: null or undefined
        const postSucceeded = reviewForVerdict != null;
        const findings = reviewForVerdict ? parseReviewMarker(reviewForVerdict.body) : null;
        const unresolved = unresolvedThreadCount(threads);
        const expectedState = postSucceeded && findings === 0 && unresolved === 0 ? 'success' : 'failure';

        // First code-review entry (listCommitStatusesForRef is newest-first); undefined when absent.
        const statuses = await github.paginate(github.rest.repos.listCommitStatusesForRef, {
            owner,
            repo,
            ref: head,
            per_page: 100
        });
        const current = statuses.find(s => s && s.context === 'code-review');
        if (current && current.state === expectedState) {
            core.info(`Already reviewed this exact commit and the code-review status (${current.state}) matches the review verdict -- skipping.`);
            core.setOutput('skip', 'true');
            return;
        }
        core.info(
            `Already reviewed this exact commit but the code-review status (${current ? current.state : 'absent'}) does not match the review verdict (${expectedState}) -- reposting the status.`
        );
        core.setOutput('pr', String(prNumber));
        core.setOutput('head_sha', head);
        core.setOutput('skip', 'false');
        core.setOutput('repost', 'true');
        return;
    }

    const { data: diff } = await github.rest.repos.compareCommitsWithBasehead({
        owner,
        repo,
        basehead: `${base}...${head}`,
        headers: { accept: 'application/vnd.github.v3.diff' }
    });
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/review.diff`, diff);
    // Settings from the BASE checkout's .pr_agent.toml, before the PR head is extracted. The model
    // reads review-config.json. Later steps use these outputs, which the model cannot change.
    const reviewConfig = require(`${process.env.GITHUB_WORKSPACE}/.github/scripts/code_review/config.cjs`);
    const settings = reviewConfig.load(process.env.GITHUB_WORKSPACE, core.info);
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/review-config.json`, JSON.stringify(settings, null, 2));
    core.setOutput('off_dimensions', JSON.stringify(reviewConfig.offDimensions(settings)));
    core.setOutput('inline_key_issues', String(settings.pr_reviewer.inline_key_issues));
    core.setOutput('ticket_analysis', String(settings.pr_reviewer.require_ticket_analysis_review));
    fs.writeFileSync(
        `${process.env.GITHUB_WORKSPACE}/review-range.json`,
        JSON.stringify(
            {
                pr: prNumber,
                base_sha: base,
                head_sha: head,
                incremental,
                prior_review_at: prior ? prior.submitted_at : null
            },
            null,
            2
        )
    );

    // Our own earlier review threads that are still open, for the model to re-check against the
    // PR head (code_review.md Step 4). Outdated threads are included: a fix usually edits the very
    // line a comment sits on, which is what makes GitHub mark it outdated. This file only informs
    // the model; `post` re-reads the live threads and resolves only ids that are still ours and open.
    const ownOpenThreads = (nodes, botLogin) => {
        const out = [];
        for (const t of nodes || []) {
            const c = t && t.comments && t.comments.nodes && t.comments.nodes[0];
            if (!t || !t.id || t.isResolved || !c || !c.author || c.author.login !== botLogin) continue;
            out.push({ id: t.id, path: t.path, line: t.line ?? t.originalLine ?? null, outdated: !!t.isOutdated, comment: String(c.body || '') });
        }
        return out;
    };
    let priorThreads = [];
    try {
        let nodes = [],
            cursor = null;
        for (;;) {
            const page = await github.graphql(
                `query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
             repository(owner:$owner,name:$repo){
               pullRequest(number:$pr){
                 reviewThreads(first:100, after:$cursor){
                   nodes { id isResolved isOutdated path line originalLine comments(first:1){ nodes { author { login } body } } }
                   pageInfo { hasNextPage endCursor }
                 }
               }
             }
           }`,
                { owner, repo, pr: prNumber, cursor }
            );
            const rt = page.repository.pullRequest.reviewThreads;
            nodes = nodes.concat(rt.nodes);
            if (!rt.pageInfo.hasNextPage) break;
            cursor = rt.pageInfo.endCursor;
        }
        priorThreads = ownOpenThreads(nodes, 'openlibrary-bot');
    } catch (e) {
        core.info(`Could not read earlier review threads (${e.message}) -- reviewing without them.`);
    }
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/prior-threads.json`, JSON.stringify(priorThreads, null, 2));

    core.setOutput('pr', String(prNumber));
    core.setOutput('head_sha', head);
    // Job outputs, set before the model runs, are what `post` trusts for the range --
    // not review-range.json, which the model can rewrite.
    core.setOutput('base_sha', base);
    core.setOutput('incremental', String(incremental));
    core.setOutput('skip', 'false');
    core.setOutput('repost', 'false');
    core.info(`PR #${prNumber}: ${incremental ? 'incremental' : 'full'} review, ${base.slice(0, 8)}..${head.slice(0, 8)}`);
}

module.exports = { resolveRange };
