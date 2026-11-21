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
// bot's reviews (with superseded ones already left out). heldBackReview returns the first such review,
// so `post` can point at it.
const heldBackReview = reviews => reviews.find(r => r.state !== 'DISMISSED' && heldBackBlocking(r.body)) || null;
const heldBackOpen = reviews => heldBackReview(reviews) !== null;
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

// The parts of a unified diff for the given paths (old or new name). A re-review sees only these.
// Anchors are checked against the whole PR's diff (pr.diff), so a finding can sit on any line the PR
// changed, not only on the files changed since the last review.
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

// Where a comment can go in a unified diff. `lines`: for each file, the right-side lines (added and
// context) a line comment can sit on, with their text for suggestions. A file with no such lines
// (deleted, binary) is still listed: it can take a file-level thread. `firstHunk`: the first line
// of each file's first hunk, the fallback when a file-level thread fails. It is on the new side, or
// on the old side when the file has no new side (deleted or emptied). Line 1 is no fallback: GitHub
// rejects a line outside the diff ("Line could not be resolved").
const diffAnchors = diff => {
    const lines = new Map(),
        firstHunk = new Map();
    let file = null,
        newLn = 0,
        inHunk = false,
        deleted = false;
    for (const raw of String(diff || '').split(/\r?\n/)) {
        const g = /^diff --git a\/(.*) b\/(.*)$/.exec(raw);
        if (g) {
            file = g[2];
            inHunk = false;
            deleted = false;
            if (!lines.has(file)) lines.set(file, new Map());
            continue;
        }
        if (!file) continue;
        if (!inHunk && raw.startsWith('+++ ')) {
            const p = raw.slice(4).trim();
            if (p === '/dev/null') deleted = true;
            else {
                file = p.replace(/^b\//, '');
                if (!lines.has(file)) lines.set(file, new Map());
            }
            continue;
        }
        const h = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(raw);
        if (h) {
            inHunk = true;
            newLn = Number(h[3]);
            const newCount = h[4] === undefined ? 1 : Number(h[4]);
            if (!firstHunk.has(file)) firstHunk.set(file, deleted || newCount === 0 ? { line: Number(h[1]), side: 'LEFT' } : { line: newLn, side: 'RIGHT' });
            continue;
        }
        if (!inHunk || deleted) continue;
        if (raw.startsWith('+') || raw.startsWith(' ')) lines.get(file).set(newLn++, raw.slice(1));
    }
    return { lines, firstHunk };
};

// The thread a finding gets: 'line' when its range is on right-side lines of the PR's diff, 'file'
// when its file is in the diff but the range isn't (or it gives no line), and null when its file
// isn't in the diff. Only findings with a thread block: a finding nobody can reply to or resolve
// would block with no way to clear it, or stop counting silently on the next pass (#14471).
const threadKind = (f, anchors) => {
    if (!f || !f.path || !anchors.lines.has(f.path)) return null;
    const ln = anchors.lines.get(f.path);
    const end = Number(f.line),
        start = Number(f.start_line || f.line);
    if (f.line && ln.has(end) && ln.has(start) && start <= end) return 'line';
    return 'file';
};

module.exports = {
    diffAnchors,
    threadKind,
    headIsCurrent,
    reviewMarker,
    parseReviewMarker,
    heldBackBlocking,
    heldBackOpen,
    heldBackReview,
    verdictFindings,
    unresolvedThreadCount,
    filterDiff,
    supersededMarker,
    supersededCommit
};
