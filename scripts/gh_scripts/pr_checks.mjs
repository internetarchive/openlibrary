/**
 * Entry point for the PR checks workflow.
 *
 * Reads the PR's metadata/body from the environment (set from the
 * `pull_request_target` event payload by .github/workflows/pr_checks.yml --
 * never from checked-out PR code), does the one network read the checks need
 * (issue-is-ready's live labels), assembles the five commit statuses, and POSTs
 * each to the PR HEAD commit so each is an independently require-able status
 * context.
 *
 * All decision logic lives in pr_checks_core.mjs (pure, unit-tested). This file
 * is deliberately all IO so the core stays importable in vitest.
 *
 * The orchestrator exits 0 even when a check is `failure`: a failing check is
 * expressed as its POSTED status (red on the PR), not as this job's exit code.
 * The job only reflects infra trouble. Branch protection keys on the posted
 * contexts, not on this workflow's own conclusion.
 *
 * Env:
 *   PR_BODY            the pull request body (may be empty/undefined)
 *   PR_AUTHOR          the pull request author's login
 *   PR_LABELS          JSON array of label objects ([{"name": "..."}]) or names
 *   PR_NUMBER          the pull request number (for logging)
 *   HEAD_SHA           the PR head commit SHA to bind the statuses to
 *   GITHUB_REPOSITORY  `owner/name`
 *   OL_BOT_COMMIT_STATUS_PAT  a token with `statuses:write` (see #14455). Absent -> the
 *                      script runs in dry-run: it computes and prints the statuses
 *                      but posts nothing (the expected interim before the PAT is
 *                      minted, and what the offline unit test exercises).
 *   GITHUB_SERVER_URL / GITHUB_RUN_ID  used to build each status' target_url.
 */
import { appendFileSync } from 'node:fs';
import { buildStatuses, resolveIssueNumber, DEFAULT_REPO } from './pr_checks_core.mjs';

// GitHub Actions sets GITHUB_API_URL (api.github.com on github.com, a different
// host on GHES); honor it rather than hard-coding the host.
const API_BASE = process.env.GITHUB_API_URL || 'https://api.github.com';

main();

async function main() {
    const body = process.env.PR_BODY ?? '';
    const authorLogin = process.env.PR_AUTHOR ?? '';
    const prNumber = process.env.PR_NUMBER ?? '?';
    const headSha = process.env.HEAD_SHA ?? '';
    const repo = process.env.GITHUB_REPOSITORY || DEFAULT_REPO;
    const token = process.env.OL_BOT_COMMIT_STATUS_PAT ?? '';
    const labels = parseLabels(process.env.PR_LABELS);
    const dryRun = token === '' || headSha === '';

    const issue = await resolveIssue(body, repo, token, dryRun);
    const statuses = buildStatuses({ labels, body, authorLogin, issue });

    const targetUrl = buildTargetUrl();
    const lines = [`### PR checks — PR #${prNumber}${dryRun ? ' (dry-run: no PAT, nothing posted)' : ''}`, ''];
    let postFailures = 0;

    for (const status of statuses) {
        const icon = { success: '✅', failure: '❌', error: '⚠️', pending: '⏳' }[status.state] ?? '•';
        lines.push(`- ${icon} \`${status.context}\` → **${status.state}** — ${status.description}`);
        if (dryRun) {
            continue;
        }
        const ok = await postStatus({ repo, sha: headSha, token, targetUrl, ...status });
        if (!ok) {
            postFailures += 1;
        }
    }

    // Posting was attempted (not dry-run) and EVERY post failed -- e.g. a revoked/
    // expired PAT. That is an infra breakage, not a per-check result, so it must be
    // visible rather than a silently-green run.
    const allPostsFailed = !dryRun && statuses.length > 0 && postFailures === statuses.length;

    lines.push('');
    lines.push(
        dryRun
            ? '_Dry-run: set `OL_BOT_COMMIT_STATUS_PAT` (statuses:write) to post these as commit statuses._'
            : postFailures === 0
              ? '_Posted all checks as commit statuses on the PR HEAD._'
              : allPostsFailed
                ? '_ERROR: every status POST failed (PAT revoked/expired, or the API is unreachable) — failing the job to surface it._'
                : `_Posted with ${postFailures} of ${statuses.length} failing; see the log above._`
    );

    const summary = lines.join('\n');
    console.log(summary);
    writeJobSummary(summary);

    // A red CHECK is a posted status, not this job's failure, so exit 0 even when a
    // check is `failure`/`error`, in dry-run, and on a partial post failure -- so a
    // missing PAT (expected pre-#14455) or one flaky POST does not paint the job red
    // and mask the real per-check signal. The ONE exception is a total post failure
    // (above): with nothing posted, a non-zero exit is the only signal left.
    process.exit(allPostsFailed ? 1 : 0);
}

/**
 * Resolve the referenced issue to the shape buildStatuses expects.
 *
 * @returns {Promise<{kind: string, number?: number, labels?: Array}>}
 */
async function resolveIssue(body, repo, token, dryRun) {
    const number = resolveIssueNumber(body, repo);
    if (number === null) {
        return { kind: 'none' };
    }
    if (dryRun) {
        return { kind: 'skipped', number };
    }
    return fetchIssueLabels(repo, number, token);
}

/**
 * Fetch one issue's labels. Classifies the outcome for issue-is-ready:
 *   200 -> {kind:'ok', number, labels}
 *   404 -> {kind:'none'}   (a bogus/foreign number is references-issue's concern,
 *                           not a readiness failure -- defer, don't double-fail)
 *   anything else / throw -> {kind:'error', number}  (transient; not `failure`)
 *
 * @returns {Promise<{kind: string, number?: number, labels?: Array}>}
 */
async function fetchIssueLabels(repo, number, token) {
    try {
        const res = await fetch(`${API_BASE}/repos/${repo}/issues/${number}`, {
            headers: {
                Authorization: `Bearer ${token}`,
                Accept: 'application/vnd.github+json',
                'User-Agent': 'ol-pr-checks',
                'X-GitHub-Api-Version': '2022-11-28'
            }
        });
        if (res.status === 404) {
            return { kind: 'none' };
        }
        if (!res.ok) {
            console.log(`issue-is-ready: GET issues/${number} returned ${res.status}; posting 'error'.`);
            return { kind: 'error', number };
        }
        const data = await res.json();
        return { kind: 'ok', number, labels: Array.isArray(data.labels) ? data.labels : [] };
    } catch (err) {
        console.log(`issue-is-ready: fetch failed (${err.message}); posting 'error'.`);
        return { kind: 'error', number };
    }
}

/**
 * POST one commit status to the HEAD SHA. Best-effort: logs and returns false on
 * any non-2xx or throw, never throws.
 *
 * @returns {Promise<boolean>} true when GitHub accepted the status
 */
async function postStatus({ repo, sha, token, targetUrl, context, state, description }) {
    try {
        const res = await fetch(`${API_BASE}/repos/${repo}/statuses/${sha}`, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${token}`,
                Accept: 'application/vnd.github+json',
                'Content-Type': 'application/json',
                'User-Agent': 'ol-pr-checks',
                'X-GitHub-Api-Version': '2022-11-28'
            },
            body: JSON.stringify({ state, context, description, ...(targetUrl ? { target_url: targetUrl } : {}) })
        });
        if (!res.ok) {
            console.log(`Failed to post ${context}: ${res.status} ${await res.text()}`);
            return false;
        }
        return true;
    } catch (err) {
        console.log(`Failed to post ${context}: ${err.message}`);
        return false;
    }
}

/**
 * The run's URL, used as each status' target_url so a red check links to the log.
 *
 * @returns {string|null}
 */
function buildTargetUrl() {
    const server = process.env.GITHUB_SERVER_URL;
    const repo = process.env.GITHUB_REPOSITORY;
    const runId = process.env.GITHUB_RUN_ID;
    return server && repo && runId ? `${server}/${repo}/actions/runs/${runId}` : null;
}

/**
 * Parse PR_LABELS into an array the core logic accepts. Tolerates missing or
 * malformed JSON by returning [] (treated as "no priority label").
 *
 * @param {string|undefined} raw
 * @returns {Array<{name: string}|string>}
 */
function parseLabels(raw) {
    if (!raw) {
        return [];
    }
    try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        console.log('PR_LABELS was not valid JSON; treating the PR as unlabeled.');
        return [];
    }
}

/**
 * Append markdown to the GitHub Actions job summary when running in CI.
 * No-op (and never throws) when GITHUB_STEP_SUMMARY is unset or unwritable.
 *
 * @param {string} markdown
 */
function writeJobSummary(markdown) {
    const path = process.env.GITHUB_STEP_SUMMARY;
    if (!path) {
        return;
    }
    try {
        appendFileSync(path, `${markdown}\n`);
    } catch (error) {
        console.log(`Could not write job summary: ${error.message}`);
    }
}
