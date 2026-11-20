// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// The `analyze` job's "Resolve review range" step: decides whether this run reviews, re-posts the
// status of an existing review, or skips, and writes the range, diff and settings the model reads.
'use strict';

const { filterDiff, verdictFindings, heldBackOpen, unresolvedThreadCount, supersededCommit } = require('./shared.cjs');

// The paths to review once files identical to the base branch's tip are left out, or null to
// change nothing: when no file matches, or GitHub's lists are cut short (300 files in a compare, a
// truncated tree). `files` is the re-review's list, or null for the whole PR. A file matches when
// its blob in the PR equals the base branch's, or the PR deletes a file the base branch lacks.
async function withoutFilesOnBase({ github, owner, repo, baseRef, base, head, files, core }) {
    try {
        const { data: cmp } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${base}...${head}` });
        const changed = (cmp && cmp.files) || [];
        if (!changed.length || changed.length >= 300) return null;
        const { data: tree } = await github.rest.git.getTree({ owner, repo, tree_sha: baseRef, recursive: 'true' });
        if (!tree || tree.truncated || !Array.isArray(tree.tree)) return null;
        const onBase = new Map(tree.tree.map(e => [e.path, e.sha]));
        const same = f => (f.status === 'removed' ? !onBase.has(f.filename) : onBase.get(f.filename) === f.sha);
        const kept = new Set();
        for (const f of changed) {
            if (same(f)) continue;
            kept.add(f.filename);
            if (f.previous_filename) kept.add(f.previous_filename);
        }
        const all = new Set(changed.flatMap(f => [f.filename, f.previous_filename].filter(Boolean)));
        // A path outside the compare's list (shouldn't happen) is kept rather than dropped.
        const out = (files || [...all]).filter(p => kept.has(p) || !all.has(p)).sort();
        const dropped = changed.length - changed.filter(f => !same(f)).length;
        if (!dropped) return null;
        core.info(`Leaving out ${dropped} file(s) that already match ${baseRef}.`);
        return out;
    } catch (e) {
        core.info(`Could not compare the PR's files with ${baseRef} (${e.message}) -- reviewing them all.`);
        return null;
    }
}

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
    // issue_comment's payload has no draft field, so check here. A manual dispatch reviews drafts.
    if (pr.draft && context.eventName !== 'workflow_dispatch') {
        core.info(`PR #${prNumber} is a draft -- skipping.`);
        core.setOutput('skip', 'true');
        core.setOutput('skip_reason', 'draft');
        return;
    }
    if (pr.state !== 'open') {
        core.info(`PR #${prNumber} is ${pr.state} -- skipping.`);
        core.setOutput('skip', 'true');
        core.setOutput('skip_reason', 'closed');
        return;
    }

    const head = pr.head.sha;

    // Incremental: only the files changed since the bot's newest review.
    const reviews = await github.paginate(github.rest.pulls.listReviews, {
        owner,
        repo,
        pull_number: prNumber,
        per_page: 100
    });
    // Superseded reviews (see shared.cjs) are left out: the next review starts from the last review
    // that was not overtaken, so it covers everything a superseded one saw, including findings that
    // never became threads, and a commit whose only review was superseded still gets reviewed.
    const ours = reviews.filter(r => r.user && r.user.login === 'openlibrary-bot' && r.commit_id && !supersededCommit(r.body));
    const prior = ours.length ? ours[ours.length - 1] : null;
    const priorSha = prior ? prior.commit_id : null;

    let base = pr.base.sha,
        incremental = false,
        files = null;
    if (prior && priorSha !== head) {
        // Use the prior SHA only if it is an ancestor of head. After a force-push it may not be,
        // and diffing from it would review the wrong changes.
        try {
            const { data: since } = await github.rest.repos.compareCommitsWithBasehead({
                owner,
                repo,
                basehead: `${priorSha}...${head}`
            });
            if (since.status === 'ahead' && since.files && since.files.length) {
                // The PR's own commits and its merge base, as GitHub's PR diff has them.
                const { data: own } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${pr.base.ref}...${head}` });
                if (since.total_commits > since.commits.length || own.total_commits > own.commits.length) throw new Error('too many commits');
                const ownShas = new Set(own.commits.map(c => c.sha));
                // The author's commits since the last review. Commits from the base branch are not PR
                // commits, and a merge whose second parent is not a PR commit only merges the base in.
                const ownSince = since.commits.filter(c => ownShas.has(c.sha));
                const isBaseMerge = c => c.parents.length === 2 && !ownShas.has(c.parents[1].sha);
                const authored = ownSince.filter(c => !isBaseMerge(c));
                // GitHub lists at most 300 files per commit or compare; past that, review everything.
                const filesOf = list => {
                    if ((list || []).length >= 300) throw new Error('too many files in one commit');
                    return list || [];
                };
                const touched = new Set();
                const add = f => {
                    touched.add(f.filename);
                    if (f.previous_filename) touched.add(f.previous_filename);
                };
                for (const c of authored) {
                    const { data: commit } = await github.rest.repos.getCommit({ owner, repo, ref: c.sha });
                    filesOf(commit.files).forEach(add);
                }
                // A base merge can carry hand-resolved conflicts. Those files differ from both parents:
                // they are in the merge's diff against the PR side and against the base side.
                for (const m of ownSince.filter(isBaseMerge)) {
                    const { data: commit } = await github.rest.repos.getCommit({ owner, repo, ref: m.sha });
                    const { data: vsBase } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${m.parents[1].sha}...${m.sha}` });
                    const fromBase = new Set(filesOf(vsBase.files).map(f => f.filename));
                    filesOf(commit.files)
                        .filter(f => fromBase.has(f.filename))
                        .forEach(add);
                }
                if (!touched.size) {
                    // Nothing new to review: `status` carries the last review's verdict, no model runs.
                    core.info('Only base branch merges since the last review -- reposting its verdict.');
                    core.setOutput('pr', String(prNumber));
                    core.setOutput('head_sha', head);
                    core.setOutput('verdict_sha', prior.commit_id);
                    core.setOutput('skip', 'false');
                    core.setOutput('repost', 'true');
                    return;
                }
                // Review the PR's diff, limited to those files, so every line the model can comment on
                // is in the PR's diff.
                base = own.merge_base_commit.sha;
                files = [...touched].sort();
                incremental = true;
            } else {
                core.info(`Prior review commit is ${since.status} -- falling back to a full review.`);
            }
        } catch (e) {
            core.info(`Could not compare against the prior review commit (${e.message}) -- full review.`);
        }
    } else if (prior && priorSha === head) {
        // Already reviewed. Skip only if the current `code-review` status matches the verdict the
        // existing review implies; otherwise re-post the status without running the model.
        // This must pick the same review as status.cjs's repost path (the last bot review on this
        // head with a body); a test checks the two agree. `prior` has no body filter, so it can differ.
        const onHead = ours.filter(r => r.commit_id === head && r.body);
        const reviewForVerdict = onHead.length ? onHead[onHead.length - 1] : null;

        // GraphQL, because REST has no resolved/outdated state. On an error, re-post: the status
        // job recomputes the verdict itself, so a flaky read can't leave a stale status in place.
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

        // The same pass rule as status.cjs's decideStatus.
        // oxlint-disable-next-line eqeqeq -- loose on purpose: null or undefined
        const postSucceeded = reviewForVerdict != null;
        let findings = reviewForVerdict ? verdictFindings(reviewForVerdict) : null;
        if (findings === 0 && heldBackOpen(ours)) findings = 1;
        const unresolved = unresolvedThreadCount(threads);
        const expectedState = postSucceeded && findings === 0 && unresolved === 0 ? 'success' : 'failure';

        // listCommitStatusesForRef is newest first.
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
            // Not head_sha: the status job reads that, and must not run for a skip.
            core.setOutput('skip_reason', 'reviewed');
            core.setOutput('skip_sha', head);
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

    // A file the PR leaves exactly as it is on the base branch adds nothing to review, however the
    // history got it there: master's changes committed by hand instead of merged, or a stacked PR
    // whose parent was squash-merged. #14495 was reviewed with 169 such files. Leave them out,
    // through the same file list a re-review uses. Best effort: on any doubt, review as before.
    const narrowed = await withoutFilesOnBase({ github, owner, repo, baseRef: pr.base.ref, base, head, files, core });
    if (narrowed && !narrowed.length && prior) {
        // Nothing the PR changes differs from the base branch any more: carry the last verdict.
        core.info('Every file the PR changes already matches the base branch -- reposting the last verdict.');
        core.setOutput('pr', String(prNumber));
        core.setOutput('head_sha', head);
        core.setOutput('verdict_sha', prior.commit_id);
        core.setOutput('skip', 'false');
        core.setOutput('repost', 'true');
        return;
    }
    if (narrowed && narrowed.length) files = narrowed;

    const { data: diff } = await github.rest.repos.compareCommitsWithBasehead({
        owner,
        repo,
        basehead: `${base}...${head}`,
        headers: { accept: 'application/vnd.github.v3.diff' }
    });
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/review.diff`, files ? filterDiff(diff, files) : diff);
    // The whole PR's diff, which a finding may anchor to. `post` fetches the same diff again.
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/pr.diff`, diff);
    // Settings from the base checkout's .pr_agent.toml, so a PR can't change them. Later steps use
    // these outputs, which the model cannot change; the model reads review-config.json.
    const reviewConfig = require(`${process.env.GITHUB_WORKSPACE}/.github/scripts/code_review/config.cjs`);
    const settings = reviewConfig.load(process.env.GITHUB_WORKSPACE, core.info);
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/review-config.json`, JSON.stringify(settings, null, 2));
    core.setOutput('off_dimensions', JSON.stringify(reviewConfig.offDimensions(settings)));
    core.setOutput('inline_key_issues', String(settings.pr_reviewer.inline_key_issues));
    core.setOutput('ticket_analysis', String(settings.pr_reviewer.require_ticket_analysis_review));
    // Empty when push reviews are off. `post` words the review's tip from it.
    const pushReviews = settings.github_action_config.handle_push_trigger;
    core.setOutput('push_review_minutes', pushReviews ? String(settings.openlibrary_reviewer.push_review_delay_minutes) : '');
    fs.writeFileSync(
        `${process.env.GITHUB_WORKSPACE}/review-range.json`,
        JSON.stringify(
            {
                pr: prNumber,
                base_sha: base,
                head_sha: head,
                incremental,
                prior_review_sha: incremental ? priorSha : null,
                prior_review_at: prior ? prior.submitted_at : null,
                files
            },
            null,
            2
        )
    );

    // The bot's earlier threads that are still open, for the model to re-check. Outdated ones are
    // included: a fix usually edits the commented line, which is what makes a thread outdated.
    // `post` re-reads the live threads before choosing any to resolve. `replies` are the PR author's
    // and maintainers' answers, so the model can weigh them; other people can't get a finding dismissed.
    const canAnswer = r => r.author.login === pr.user?.login || ['OWNER', 'MEMBER', 'COLLABORATOR'].includes(r.authorAssociation);
    const ownOpenThreads = (nodes, botLogin) => {
        const out = [];
        for (const t of nodes || []) {
            const [c, ...rest] = (t && t.comments && t.comments.nodes) || [];
            if (!t || !t.id || t.isResolved || !c || !c.author || c.author.login !== botLogin) continue;
            const replies = rest
                .filter(r => r && r.author && r.author.login !== botLogin && canAnswer(r))
                .map(r => ({ author: r.author.login, body: String(r.body || '').slice(0, 2000) }));
            out.push({ id: t.id, path: t.path, line: t.line ?? t.originalLine ?? null, outdated: !!t.isOutdated, comment: String(c.body || ''), replies });
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
                   nodes { id isResolved isOutdated path line originalLine comments(first:10){ nodes { author { login } authorAssociation body } } }
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
    // `post` takes the range from these outputs, not from review-range.json, which the model can rewrite.
    core.setOutput('base_sha', base);
    core.setOutput('incremental', String(incremental));
    core.setOutput('files', files ? JSON.stringify(files) : '');
    core.setOutput('skip', 'false');
    core.setOutput('repost', 'false');
    core.info(`PR #${prNumber}: ${incremental ? `incremental review of ${files.length} file(s)` : 'full review'}, ${base.slice(0, 8)}..${head.slice(0, 8)}`);
}

module.exports = { resolveRange };
