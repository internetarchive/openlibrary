// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// The `status` job: decides and posts the `code-review` commit status for the reviewed SHA. The pass
// rule is in decideStatus and in the comment above the job in code_review_action.yml.
'use strict';

const { headIsCurrent, verdictFindings, heldBackOpen, unresolvedThreadCount, supersededCommit } = require('./shared.cjs');

// The public findings count from `analyze`. null (blocks) unless it is a non-negative integer:
// findings with no anchor in the diff have no thread, so the thread count alone can't catch them.
const parseFindings = raw => {
    return /^\d+$/.test((raw ?? '').toString().trim()) ? Number(raw) : null;
};

// What wasn't published arrives as one bit instead of a count. null (blocks) on anything else.
const withheldFindings = withheldBlocking => {
    if (withheldBlocking === 'true') return 1;
    if (withheldBlocking === 'false') return 0;
    return null;
};

// Pass needs a clean post, a findings count known to be 0, and no unresolved threads. The
// description holds only counts and fixed phrases, never a finding's content.
const decideStatus = ({ postSucceeded, findings, withheld, unresolved }) => {
    const pass = postSucceeded && findings === 0 && unresolved === 0;
    let description;
    if (pass) description = 'Review passed; all feedback resolved.';
    else if (!postSucceeded) description = 'No clean review for this commit.';
    else if (findings === null) description = 'Review findings count unavailable.';
    // Feedback that wasn't published gets one fixed phrase with no number: the status may reveal
    // only that some exists. Nothing sends it anywhere, so don't say it was delivered.
    else if (withheld && findings > 0) description = 'Feedback withheld for maintainer review.';
    // Published findings are already public, so their count is too.
    else if (findings > 0) description = `${findings} finding${findings === 1 ? '' : 's'} to address.`;
    else description = `${unresolved} unresolved review thread${unresolved === 1 ? '' : 's'}.`;
    return { pass, state: pass ? 'success' : 'failure', description };
};

async function postStatus({ github, context, core, process }) {
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const pr = Number(process.env.PR);
    const headSha = process.env.HEAD_SHA;
    const repost = process.env.REPOST === 'true';
    if (!/^[0-9a-f]{40}$/.test(headSha)) {
        core.setFailed('Unexpected head sha.');
        return;
    }

    // Run-page summary. Counts and the status's fixed wording only: never a withheld review's content or count.
    const range = repost
        ? 'none (re-posting the status of an existing review)'
        : process.env.INCREMENTAL === 'true'
          ? 'incremental: files changed since the last review'
          : 'full';
    const writeSummary = rows =>
        core.summary
            .addRaw(`## Code review: #${pr} @ ${headSha.slice(0, 7)}\n\n| | |\n|---|---|\n${rows.map(([k, v]) => `| ${k} | ${v} |`).join('\n')}\n`)
            .write();

    // If the head moved since the review, post no status (see headIsCurrent).
    const { data: livePr } = await github.rest.pulls.get({ owner, repo, pull_number: pr });
    if (!headIsCurrent(headSha, livePr.head.sha)) {
        core.info(
            `Head moved ${headSha.slice(0, 8)}->${String(livePr.head.sha).slice(0, 8)} since review; marking the reviewed SHA superseded. The current head is unreviewed and earns its own run.`
        );
        // Replaces "Review in progress", which would otherwise stay on this commit. Still pending: it was never reviewed.
        await github.rest.repos.createCommitStatus({
            owner,
            repo,
            sha: headSha,
            context: 'code-review',
            state: 'pending',
            target_url: process.env.RUN_URL,
            description: `Superseded by ${String(livePr.head.sha).slice(0, 7)}: the PR changed during the review.`
        });
        await writeSummary([
            ['Range', range],
            ['Status', `pending: superseded by ${String(livePr.head.sha).slice(0, 7)}, which gets its own review`]
        ]);
        return;
    }

    // GraphQL, because REST has no resolved/outdated state.
    let threads = [],
        cursor = null;
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
            { owner, repo, pr, cursor }
        );
        const rt = page.repository.pullRequest.reviewThreads;
        threads = threads.concat(rt.nodes);
        if (!rt.pageInfo.hasNextPage) break;
        cursor = rt.pageInfo.endCursor;
    }
    const unresolved = unresolvedThreadCount(threads);

    // On a repost no model ran: read the verdict back from the bot's last review on this head, or
    // on VERDICT_SHA when the commits since that review only merged the base branch.
    let postSucceeded, findings, withheld;
    const reviews = await github.paginate(github.rest.pulls.listReviews, {
        owner,
        repo,
        pull_number: pr,
        per_page: 100
    });
    // The bot's reviews, without superseded ones, which are never a verdict (see shared.cjs).
    const ours = reviews.filter(r => r.user && r.user.login === 'openlibrary-bot' && r.body && !supersededCommit(r.body));
    if (repost) {
        const verdictSha = process.env.VERDICT_SHA || headSha;
        const onSha = ours.filter(r => r.commit_id === verdictSha);
        const last = onSha.length ? onSha[onSha.length - 1] : null;
        // oxlint-disable-next-line eqeqeq -- loose on purpose: null or undefined
        postSucceeded = last != null;
        withheld = false;
        findings = last ? verdictFindings(last) : null;
    } else if (process.env.WITHHELD === 'true') {
        // Withheld in full (the review was malformed). Nothing was posted, so there is no review to
        // confirm. postSucceeded means `post` ran cleanly.
        postSucceeded = process.env.POST_RESULT === 'success';
        withheld = true;
        findings = withheldFindings(process.env.WITHHELD_BLOCKING);
    } else {
        // When the head moved, `post` posts only a superseded review, which is no verdict. If the head
        // then moved back to this SHA, the head check above would pass, so confirm a real bot review
        // exists on it.
        const posted = ours.some(r => r.commit_id === headSha);
        postSucceeded = process.env.POST_RESULT === 'success' && posted;
        findings = parseFindings(process.env.PUBLIC_FINDINGS_COUNT);
        // Part of the review was held back: its one blocking bit counts as one more finding.
        if (process.env.HELD_BACK === 'true') {
            const held = withheldFindings(process.env.WITHHELD_BLOCKING);
            withheld = held === 1;
            findings = findings === null || held === null ? null : findings + held;
        } else {
            withheld = false;
        }
    }

    // A blocking part held back from any earlier review still blocks, until a maintainer dismisses it.
    if (heldBackOpen(ours)) {
        withheld = true;
        if (findings === 0) findings = 1;
    }
    const d = decideStatus({ postSucceeded, findings, withheld, unresolved });
    await github.rest.repos.createCommitStatus({
        owner,
        repo,
        sha: headSha,
        context: 'code-review',
        state: d.state,
        target_url: process.env.RUN_URL,
        description: d.description
    });
    core.info(
        `code-review=${d.state} on ${headSha.slice(0, 8)} (repost=${repost}, post=${process.env.POST_RESULT}, withheld=${withheld}, findings=${findings}, unresolved=${unresolved}).`
    );
    await writeSummary([
        ['Range', range],
        [
            'Review',
            repost
                ? 'existing'
                : process.env.WITHHELD === 'true'
                  ? 'not posted publicly'
                  : postSucceeded
                    ? process.env.HELD_BACK === 'true'
                        ? 'posted, with part held back'
                        : 'posted'
                    : 'not posted'
        ],
        ['Findings', withheld ? '—' : (findings ?? 'unknown')],
        ['Unresolved threads', unresolved],
        ['Status', `${d.state}: ${d.description}`]
    ]);
}

module.exports = { postStatus, parseFindings, withheldFindings, decideStatus };