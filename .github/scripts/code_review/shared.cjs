// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// Helpers used by more than one job of code_review_action.yml.
'use strict';

// Whether the reviewed SHA is still the PR's head. If it moved, `post` posts the review on the commit
// it read, as a superseded COMMENT, and `status` posts no verdict: the new head gets its own review.
// createReview does record the commit_id it is given (checked on #14554), but nothing relies on
// that alone: see supersededCommit.
const headIsCurrent = (pinnedHead, liveHead) => {
    return pinnedHead === liveHead;
};

// The blocking-findings count `post` embeds in the review body, so a status can be re-decided
// without re-running the model. null (blocks) when the marker is missing.
const parseReviewMarker = body => {
    const m = /<!-- ol-pr-review-bot f=(\d+) -->/.exec(String(body || ''));
    return m ? Number(m[1]) : null;
};

// A review `post` made of a commit the PR had already moved past (see post.cjs). It is feedback on
// that commit, never a verdict on the PR, so nothing reuses it as one. The marker also names the
// commit it read, so the next review starts from there whatever commit GitHub records it on.
const supersededMarker = sha => `<!-- ol-pr-review-bot superseded reviewed=${sha} -->`;
const supersededCommit = body => {
    const m = /<!-- ol-pr-review-bot superseded reviewed=([0-9a-f]{40}) -->/.exec(String(body || ''));
    return m ? m[1] : null;
};
// The commit a bot review covers.
const reviewedCommit = r => supersededCommit(r.body) || r.commit_id;

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

module.exports = { headIsCurrent, parseReviewMarker, unresolvedThreadCount, filterDiff, supersededMarker, supersededCommit, reviewedCommit };
