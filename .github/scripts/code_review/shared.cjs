// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// Helpers used by more than one job of code_review_action.yml.
'use strict';

// Whether the reviewed SHA is still the PR's head. `post` and `status` post nothing if it moved:
// createReview ignores commit_id and anchors to the live head, so the review would land on a commit
// nobody reviewed. The new head gets its own review.
const headIsCurrent = (pinnedHead, liveHead) => {
    return pinnedHead === liveHead;
};

// The blocking-findings count `post` embeds in the review body, so a status can be re-decided
// without re-running the model. null (blocks) when the marker is missing.
const parseReviewMarker = body => {
    const m = /<!-- ol-pr-review-bot f=(\d+) -->/.exec(String(body || ''));
    return m ? Number(m[1]) : null;
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

module.exports = { headIsCurrent, parseReviewMarker, unresolvedThreadCount, filterDiff };
