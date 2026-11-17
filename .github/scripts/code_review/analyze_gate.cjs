// The `analyze` job's "Gate the analysis before upload" step: runs the disclosure gate (gate.cjs) on
// the model's review.json and replaces it with what may be uploaded. Sets the outputs the `status`
// job decides from.
'use strict';

const gate = require('./gate.cjs');

async function gateAnalysis({ core, require, process }) {
    const fs = require('fs');
    const file = `${process.env.GITHUB_WORKSPACE}/review.json`;
    let review = null;
    try {
        review = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch (e) {
        review = null;
    }
    // Upload the gate's allowlisted copy, never the model's file. Same log line either way:
    // the run log is public, and a difference would say which.
    const res = gate.check(review);
    // Drop findings in dimensions .pr_agent.toml turned off. After the gate, so a security
    // concern filed under one of them still withholds the review.
    if (res.publish) {
        for (const d of JSON.parse(process.env.OFF_DIMENSIONS || '[]')) {
            res.clean.findings = res.clean.findings.filter(f => f.dimension !== d);
            res.clean.dimensions[d] = { status: 'none', note: 'Not reviewed (turned off in .pr_agent.toml).' };
        }
    }
    fs.writeFileSync(file, JSON.stringify(res.publish ? res.clean : { withheld: true }));
    // Count of PUBLIC findings this run, for the `code-review` status decision (issue B.2).
    // On publish it is the allowlisted findings length (includes orphaned/summary-only
    // findings, which create no review thread -- so the status's thread check alone cannot
    // catch them; this count is exactly that guard). On a withhold it is 0: the count is
    // PUBLIC by construction and a withheld review exposes nothing, so 0 never signals
    // "a review was withheld". #14476 D3a: a withhold is NO LONGER an automatic block -- the
    // status is finding-driven. The `withheld` + 1-bit `withheld_blocking` outputs below (NOT
    // this count) carry the withhold verdict: the status job blocks only when a blocking
    // finding exists, so a backstop false-positive with 0 findings greens itself. (post now
    // returns cleanly on a withhold rather than failing -- do NOT restore a setFailed there,
    // or you re-break the green path; the status job is the sole gate decider.)
    //
    // KNOWN GAP (#14471, accepted for v1): this count is scoped to THIS run's review, and a
    // re-review is INCREMENTAL (only the diff since our last pass). An orphaned/summary-only
    // finding from a PRIOR run creates no thread, so once a later incremental run returns 0
    // the status can go green with that finding unaddressed. v1 ships with this because the
    // `code-review` status is a required FLOOR (an automated review ran clean-ish), NOT a
    // CEILING (good to merge) -- it is "not an approval" and is paired with human review, who
    // stays in the loop for exactly this case. Fast-follow #14471: count over the full PR.
    // LOW findings are suggestions: they don't count toward the status.
    const pubCount = res.publish ? res.clean.findings.filter(f => f.severity !== 'low').length : 0;
    core.setOutput('public_findings_count', String(pubCount));
    // #14476 D3a -- the SHA-bound status is finding-driven, not withhold-driven. The PUBLIC
    // count above keeps its documented "0 on every withhold" invariant, so no finding count
    // ever leaks. The only new signal is two booleans: `withheld` (was the public copy
    // withheld) and `withheld_blocking` (does a BLOCKING finding exist -- the 1-bit verdict
    // the gate computed trusted-side, fail-closed). Never a count, dimension, severity,
    // location or text. A withhold with withheld_blocking=false greens itself; true -> blocks.
    core.setOutput('withheld', res.publish ? 'false' : 'true');
    core.setOutput('withheld_blocking', res.publish ? 'false' : res.blocking ? 'true' : 'false');
    core.info('Gate evaluated; artifact prepared.');
}

module.exports = { gateAnalysis };
