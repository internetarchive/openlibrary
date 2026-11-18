// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// Helpers used by more than one job of code_review_action.yml.
'use strict';

// Whether the reviewed SHA is still the PR's head. If it moved, `post` posts the review on the commit
// it read, as a superseded COMMENT, and `status` posts no verdict: the new head gets its own review.
// createReview does record the commit_id it is given (checked on #14554), but nothing relies on
// that: see supersededCommit.
const headIsCurrent = (pinnedHead, liveHead) => {
    return pinnedHead === liveHead;
};

// The blocking-findings count `post` embeds in the review body, so a status can be re-decided
// without re-running the model. ` h=1` means part of the review was held back and that part blocks;
// it counts as one more finding. null (blocks) when the marker is missing.
const reviewMarker = (findings, heldBackBlocking) => `<!-- ol-pr-review-bot f=${findings}${heldBackBlocking ? ' h=1' : ''} -->`;
const MARKER = /<!-- ol-pr-review-bot f=(\d+)( h=1)? -->/;
const parseReviewMarker = body => {
    const m = MARKER.exec(String(body || ''));
    return m ? Number(m[1]) + (m[2] ? 1 : 0) : null;
};
const heldBackBlocking = body => {
    const m = MARKER.exec(String(body || ''));
    return Boolean(m && m[2]);
};
// A blocking held-back part keeps the PR blocked across later reviews, which may cover other files,
// until a maintainer has looked and dismissed the review that held it back. These read that from the
// bot's reviews (with superseded ones already left out).
const heldBackOpen = reviews => reviews.some(r => r.state !== 'DISMISSED' && heldBackBlocking(r.body));
// The findings a review's marker counts toward the verdict: its own, plus the held-back part unless
// a maintainer dismissed the review.
const verdictFindings = review => {
    const n = parseReviewMarker(review.body);
    return n !== null && review.state === 'DISMISSED' && heldBackBlocking(review.body) ? n - 1 : n;
};

// A review `post` made of a commit the PR had already moved past (see post.cjs). It is feedback on
// that commit, never a verdict on the PR: range and status leave it out entirely, so it never counts
// as a commit's review or verdict, whatever commit GitHub records it on. The marker names the commit
// it read, for people and the weekly report.
const supersededMarker = sha => `<!-- ol-pr-review-bot superseded reviewed=${sha} -->`;
const supersededCommit = body => {
    const m = /<!-- ol-pr-review-bot superseded reviewed=([0-9a-f]{40}) -->/.exec(String(body || ''));
    return m ? m[1] : null;
};
// Threads that block the status: unresolved and not outdated. This includes the bot's own
// just-posted findings, so a review with findings stays red until they are addressed.
const unresolvedThreadCount = threads => {
    return threads.reduce((n, t) => n + (!t.isResolved && !t.isOutdated ? 1 : 0), 0);
};

// The parts of a unified diff for the given paths (old or new name). A re-review sees only these,
// and `post` validates anchors against the same cut.
const filterDiff = (diff, paths) => {
    const want = new Set(paths);
    return String(diff)
        .split(/^(?=diff --git )/m)
        .filter(part => {
            const m = /^diff --git a\/(.*) b\/(.*)\n/.exec(part);
            return m && (want.has(m[1]) || want.has(m[2]));
        })
        .join('');
};

module.exports = {
    headIsCurrent,
    reviewMarker,
    parseReviewMarker,
    heldBackBlocking,
    heldBackOpen,
    verdictFindings,
    unresolvedThreadCount,
    filterDiff,
    supersededMarker,
    supersededCommit
};
