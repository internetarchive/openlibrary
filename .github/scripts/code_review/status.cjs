// The `status` job: decides the gate and posts the SHA-bound `code-review` commit status. Holds the
// commit-status PAT and runs no model. See the comment above the job in code_review_action.yml.
'use strict';

const { headIsCurrent, parseReviewMarker, unresolvedThreadCount } = require('./shared.cjs');

// Public findings this run, from the analyze job's declared output. FAIL CLOSED: an
// absent output or any non-integer returns null = "unknown", which decideStatus treats
// as BLOCKING -- NOT as 0/clean. Treating absent-as-clean would be a gate bypass:
// orphaned/summary-only findings create no review thread, so threads-only cannot catch
// them (see #13548, 3 of 9). The analyze-gate producer always emits a non-negative
// integer (public findings incl. orphaned) whenever this job runs.
const parseFindings = raw => {
    return /^\d+$/.test((raw ?? '').toString().trim()) ? Number(raw) : null;
};

// #14476 D3a -- a withheld review exposes no inline findings, so its gate verdict arrives
// as the 1-bit WITHHELD_BLOCKING signal instead of a count. Map it to 0/1 for decideStatus,
// FAIL CLOSED (null -> blocks) on anything but the two expected literals.
const withheldFindings = withheldBlocking => {
    if (withheldBlocking === 'true') return 1;
    if (withheldBlocking === 'false') return 0;
    return null;
};

// The decision. Bias to blocking: PASS needs findings KNOWN-to-be-0 (null blocks), zero
// unresolved threads, and a clean post. The description is non-leaky (counts and fixed
// phrases only -- never a finding's content). A public findings count is public by
// construction; it is NOT the withheld-marker we must never read, infer, or surface.
const decideStatus = ({ postSucceeded, findings, withheld, unresolved }) => {
    const pass = postSucceeded && findings === 0 && unresolved === 0;
    let description;
    if (pass) description = 'Review passed; all feedback resolved.';
    else if (!postSucceeded) description = 'No clean review for this commit.';
    else if (findings === null) description = 'Review findings count unavailable.';
    // #14476 D3a -- a WITHHELD blocking finding is reported with a FIXED phrase, byte-identical
    // regardless of count/dimension/severity/location (Locke constraint 1): the status may
    // reveal only that a finding EXISTS, never anything about it. No digit may appear here.
    else if (withheld && findings > 0) description = 'A finding was delivered privately; maintainer review required.';
    // A PUBLISHED finding count is public by construction (the findings are posted inline).
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

    // #14476 D1 -- re-confirm the reviewed SHA is still the live head before posting ANY
    // status. If a push landed since this run pinned headSha, leave headSha without a status:
    // the new head is unreviewed and earns its own run, and we never post on the new head
    // (createCommitStatus below is bound to headSha). This mirrors the post job's guard so the
    // review and the status always describe the same commit.
    // Run-page summary. Counts and the status's fixed wording only: never a withheld review's content or count.
    const range = repost
        ? 'none (re-posting the status of an existing review)'
        : process.env.INCREMENTAL === 'true'
          ? `incremental since ${String(process.env.BASE_SHA).slice(0, 7)}`
          : 'full';
    const writeSummary = rows =>
        core.summary
            .addRaw(`## Code review: #${pr} @ ${headSha.slice(0, 7)}\n\n| | |\n|---|---|\n${rows.map(([k, v]) => `| ${k} | ${v} |`).join('\n')}\n`)
            .write();

    const { data: livePr } = await github.rest.pulls.get({ owner, repo, pull_number: pr });
    if (!headIsCurrent(headSha, livePr.head.sha)) {
        core.info(
            `Head moved ${headSha.slice(0, 8)}->${String(livePr.head.sha).slice(0, 8)} since review; leaving the reviewed SHA without a status. The current head is unreviewed and earns its own run.`
        );
        await writeSummary([
            ['Range', range],
            ['Status', `none: the PR moved to ${String(livePr.head.sha).slice(0, 7)} during the review; request a new one`]
        ]);
        return;
    }

    // Enumerate review threads (GraphQL -- the REST reviews API carries no resolved state).
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

    // Derive the three decideStatus inputs. Two paths:
    //  - NORMAL run: postSucceeded from the post job; findings/withheld from analyze's
    //    finding-driven outputs (published -> the public count; withheld -> the 1-bit signal).
    //  - #14476 D2 REPOST: no model ran. Reconstruct from the existing openlibrary-bot review
    //    on THIS exact head (the status-aware skip routed us here because a review exists but
    //    the status was missing). The marker carries the public findings count; a legacy
    //    review with no marker -> null -> FAIL CLOSED (red), never a fabricated green.
    let postSucceeded, findings, withheld;
    if (repost) {
        const reviews = await github.paginate(github.rest.pulls.listReviews, {
            owner,
            repo,
            pull_number: pr,
            per_page: 100
        });
        const ours = reviews.filter(r => r.user && r.user.login === 'openlibrary-bot' && r.commit_id === headSha && r.body);
        const last = ours.length ? ours[ours.length - 1] : null;
        // oxlint-disable-next-line eqeqeq -- loose on purpose: null or undefined
        postSucceeded = last != null; // a published review exists on this exact head
        withheld = false; // withheld heads post no review, so never reach a repost
        findings = last ? parseReviewMarker(last.body) : null;
    } else if (process.env.WITHHELD === 'true') {
        // Withheld: nothing is posted publicly, so there is no review to confirm; post returned
        // cleanly and the gate's 1-bit verdict decides. postSucceeded means "the withhold ran".
        postSucceeded = process.env.POST_RESULT === 'success';
        withheld = true;
        findings = withheldFindings(process.env.WITHHELD_BLOCKING);
    } else {
        // Published: POST_RESULT == 'success' is NOT proof a review was posted -- post ALSO
        // returns success without posting when its own D1 head-guard fires (head moved). A
        // force-push back to the reviewed SHA would then let the status head-guard pass and green
        // an UNREVIEWED commit. So confirm GROUND TRUTH: a bot review actually exists on THIS
        // exact head (mirrors the repost path). No review on the head -> not a pass. This also
        // fail-closes the residual createReview re-anchor window (a review that landed on a
        // different head is not found here).
        const reviews = await github.paginate(github.rest.pulls.listReviews, {
            owner,
            repo,
            pull_number: pr,
            per_page: 100
        });
        const posted = reviews.some(r => r.user && r.user.login === 'openlibrary-bot' && r.commit_id === headSha);
        postSucceeded = process.env.POST_RESULT === 'success' && posted;
        withheld = false;
        findings = parseFindings(process.env.PUBLIC_FINDINGS_COUNT);
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
        ['Review', repost ? 'existing' : withheld ? 'not posted publicly' : postSucceeded ? 'posted' : 'not posted'],
        ['Findings', withheld ? '—' : (findings ?? 'unknown')],
        ['Unresolved threads', unresolved],
        ['Status', `${d.state}: ${d.description}`]
    ]);
}

module.exports = { postStatus, parseFindings, withheldFindings, decideStatus };
