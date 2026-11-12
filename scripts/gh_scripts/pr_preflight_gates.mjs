/**
 * Entry point for the PR preflight gates CI check.
 *
 * Reads the PR's metadata/body from the environment (set from the
 * `pull_request` event payload by .github/workflows/pr_preflight.yml -- never
 * from checked-out PR code), evaluates the three gates, writes a per-gate
 * breakdown to the GitHub job summary and the log, and exits non-zero if any
 * required gate fails so the check-run bound to this HEAD commit goes red.
 *
 * All decision logic lives in pr_preflight_gates_core.mjs (pure, unit-tested).
 * This file is deliberately all IO so the core stays importable in vitest.
 *
 * Env:
 *   PR_BODY     the pull request body (may be empty/undefined)
 *   PR_AUTHOR   the pull request author's login
 *   PR_LABELS   JSON array of label objects ([{"name": "..."}]) or names
 *   PR_NUMBER   the pull request number (for logging only)
 */
import { appendFileSync } from 'node:fs';
import { evaluatePreflight } from './pr_preflight_gates_core.mjs';

main();

function main() {
    const body = process.env.PR_BODY ?? '';
    const authorLogin = process.env.PR_AUTHOR ?? '';
    const prNumber = process.env.PR_NUMBER ?? '?';
    const labels = parseLabels(process.env.PR_LABELS);

    const { passed, results } = evaluatePreflight({ labels, body, authorLogin });

    const lines = [`### PR preflight gates — PR #${prNumber}`, ''];
    for (const r of results) {
        const icon = r.ok ? '✅' : '❌';
        const tag = r.exempt ? ' _(exempt)_' : '';
        lines.push(`- ${icon} **${r.title}**${tag}: ${r.detail}`);
    }
    lines.push('');
    lines.push(
        passed
            ? '**All preflight gates passed.**'
            : '**One or more preflight gates failed.** This is a lightweight, text-only check ' +
                  'on the PR description/labels — fix the items marked ❌ above and it re-runs automatically.'
    );
    const summary = lines.join('\n');

    console.log(summary);
    writeJobSummary(summary);

    process.exit(passed ? 0 : 1);
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
