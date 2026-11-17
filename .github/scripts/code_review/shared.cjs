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

// True when `sha` is already on the base branch, so a merge of it only brings base changes in.
const inBaseBranch = async ({ github, owner, repo, sha, baseRef }) => {
    const { data: cmp } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${sha}...${baseRef}` });
    return cmp.status === 'ahead' || cmp.status === 'identical';
};

// The parts of a unified diff for the given paths. A renamed file is kept if either name matches.
const filterDiff = (diff, paths) => {
    const want = new Set(paths);
    const blocks = String(diff).split(/^(?=diff --git )/m);
    return blocks
        .filter(block => {
            if (!block.startsWith('diff --git ')) return false;
            const names = [];
            const header = /^diff --git a\/(.+) b\/(.+)$/m.exec(block);
            if (header) names.push(header[1], header[2]);
            for (const m of block.matchAll(/^(?:--- a\/|\+\+\+ b\/|rename from |rename to )(.+)$/gm)) names.push(m[1]);
            return names.some(n => want.has(n));
        })
        .join('');
};

module.exports = { headIsCurrent, parseReviewMarker, unresolvedThreadCount, inBaseBranch, filterDiff };
