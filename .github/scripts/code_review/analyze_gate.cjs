// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// The `analyze` job's "Gate the analysis before upload" step: runs gate.cjs on the model's
// review.json, replaces the file with what may be uploaded, and sets the outputs `status` reads.
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
    // The diff the model read. A security finding is published only on lines it adds.
    let diff = '';
    try {
        diff = fs.readFileSync(`${process.env.GITHUB_WORKSPACE}/review.diff`, 'utf8');
    } catch (e) {
        diff = '';
    }
    const res = gate.check(review, diff);
    // Drop findings in dimensions .pr_agent.toml turned off. After the gate, so a security
    // concern filed under one of them still withholds the review.
    if (res.publish) {
        for (const d of JSON.parse(process.env.OFF_DIMENSIONS || '[]')) {
            res.clean.findings = res.clean.findings.filter(f => f.dimension !== d);
            res.clean.dimensions[d] = { status: 'none', note: 'Not reviewed (turned off in .pr_agent.toml).' };
        }
    }
    fs.writeFileSync(file, JSON.stringify(res.publish ? res.clean : { withheld: true }));
    // Blocking findings in the published review; low severity ones are suggestions. This includes
    // findings with no line to anchor to, which get no review thread. Held-back findings are not
    // counted, so the count reveals nothing about them.
    // Known gap (#14471): a re-review counts only its own range, so an unanchored finding from an
    // earlier pass stops counting once a later pass finds nothing. Human review covers that.
    const pubCount = res.publish ? res.clean.findings.filter(f => f.severity !== 'low').length : 0;
    core.setOutput('public_findings_count', String(pubCount));
    // About what was not published, `status` gets only these bits: whether the whole review was
    // withheld (it was malformed), whether part of it was held back, and whether what was not
    // published blocks.
    core.setOutput('withheld', res.publish ? 'false' : 'true');
    core.setOutput('held_back', res.publish && res.heldBack ? 'true' : 'false');
    core.setOutput('withheld_blocking', res.blocking ? 'true' : 'false');
    core.info('Gate evaluated; artifact prepared.');
}

module.exports = { gateAnalysis };