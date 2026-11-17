// The `resolve` job: resolves the review threads `post` listed, and does nothing else.
// It runs with the job's GITHUB_TOKEN. resolveReviewThread needs Contents: write, which we won't give
// the bot's PAT (#14533), so this job holds it only for the few seconds it runs.
// Its one input is a JSON list of thread ids; anything else is rejected before any API call.
'use strict';

// GitHub's node id for a pull request review thread.
const THREAD_ID = /^PRRT_[A-Za-z0-9_-]{1,100}$/;
// More than a PR could plausibly need resolving in one review.
const MAX_THREADS = 100;

// The ids to resolve, deduplicated, or null if the input is anything but a short list of thread ids.
const parseThreadIds = raw => {
    let ids;
    try {
        ids = JSON.parse(raw);
    } catch {
        return null;
    }
    if (!Array.isArray(ids) || ids.length > MAX_THREADS) return null;
    if (!ids.every(id => typeof id === 'string' && THREAD_ID.test(id))) return null;
    return [...new Set(ids)];
};

async function resolveThreads({ github, core, process }) {
    const ids = parseThreadIds(process.env.THREAD_IDS);
    if (!ids) {
        core.setFailed('THREAD_IDS is not a JSON list of review thread ids; resolving nothing.');
        return;
    }
    let failed = 0;
    for (const id of ids) {
        try {
            await github.graphql('mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread { id isResolved } } }', { id });
        } catch (e) {
            failed++;
            core.warning(`Could not resolve review thread ${id}: ${e.message}`);
        }
    }
    core.info(`Resolved ${ids.length - failed} of ${ids.length} review thread(s).`);
    // An unresolved thread keeps the code-review status red; failing here makes the reason visible.
    if (failed) core.setFailed(`${failed} review thread(s) could not be resolved.`);
}

module.exports = { parseThreadIds, resolveThreads };
