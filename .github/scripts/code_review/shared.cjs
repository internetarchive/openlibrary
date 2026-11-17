// Helpers more than one job of code_review_action.yml uses. Before they moved here, each job kept
// its own byte-identical copy; one definition keeps the jobs from drifting apart.
'use strict';

// #14476 D1 -- the reviewed SHA must still be the live head when we post the review (`post`) or the
// status (`status`). createReview re-anchors its comments to the LIVE head and ignores commit_id, so
// if the head moved we post NEITHER: the current head is unreviewed and earns its own run; the
// superseded headSha is harmless -- the ruleset reads the current head.
const headIsCurrent = (pinnedHead, liveHead) => {
    return pinnedHead === liveHead;
};

// #14476 D2 -- read the public findings count back from the review-body marker the post
// job embeds, so an already-reviewed head whose status went missing can be re-decided
// without re-running the model. A legacy review with no `f=` marker -> null -> FAIL CLOSED.
// Used by the range step's state-aware skip and by the status job's repost path.
const parseReviewMarker = body => {
    const m = /<!-- ol-pr-review-bot f=(\d+) -->/.exec(String(body || ''));
    return m ? Number(m[1]) : null;
};

// Feedback resolved: a thread blocks only when it is BOTH unresolved AND not outdated.
// Resolved, outdated (a later push moved the code), or on a dismissed review -> does not
// block. This also counts the bot's own just-posted inline findings, so a review that
// found issues stays red until they are addressed -- which is the intent.
const unresolvedThreadCount = threads => {
    return threads.reduce((n, t) => n + (!t.isResolved && !t.isOutdated ? 1 : 0), 0);
};

module.exports = { headIsCurrent, parseReviewMarker, unresolvedThreadCount };
