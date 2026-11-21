// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// The `analyze` job's "Gate the analysis before upload" step: runs gate.cjs on the model's
// review.json, replaces the file with what may be uploaded, and sets the outputs `status` reads.
'use strict';

const gate = require('./gate.cjs');
const { diffAnchors, threadKind } = require('./shared.cjs');

async function gateAnalysis({ core, require, process }) {
    const fs = require('node:fs');
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
    // Blocking findings in the published review: not low severity, and with a thread to go on (see
    // threadKind), counted the way `post` sorts them. A finding about no file the PR changes is
    // posted as a note that doesn't block, so it can't block with no thread to clear it (#14471).
    // With inline comments turned off, every finding is in the summary and blocks, as before.
    // Held-back findings are not counted, so the count reveals nothing about them.
    let prDiff = diff;
    try {
        prDiff = fs.readFileSync(`${process.env.GITHUB_WORKSPACE}/pr.diff`, 'utf8');
    } catch (e) {
        prDiff = diff;
    }
    const anchors = diffAnchors(prDiff);
    const inlineKeyIssues = process.env.INLINE_KEY_ISSUES !== 'false';
    const blocks = f => f.severity !== 'low' && (!inlineKeyIssues || threadKind(f, anchors) !== null);
    const pubCount = res.publish ? res.clean.findings.filter(blocks).length : 0;
    core.setOutput('public_findings_count', String(pubCount));
    // About what was not published, `status` gets only these bits: whether the whole review was
    // withheld (it was malformed), whether part of it was held back, and whether what was not
    // published blocks.
    core.setOutput('withheld', res.publish ? 'false' : 'true');
    core.setOutput('held_back', res.publish && res.heldBack ? 'true' : 'false');
    core.setOutput('withheld_blocking', res.blocking ? 'true' : 'false');
    core.info('Gate evaluated; artifact prepared.');
}

// The `analyze` job's "Check the review's format" step, run right after the model and before the
// gate: says whether the gate would withhold review.json in full, so the model gets one try to fix it.
async function checkFormat({ core, require, process }) {
    const fs = require('node:fs');
    let review = null;
    try {
        review = JSON.parse(fs.readFileSync(`${process.env.GITHUB_WORKSPACE}/review.json`, 'utf8'));
    } catch (e) {
        review = null;
    }
    core.setOutput('malformed', gate.check(review, '').publish ? 'false' : 'true');
}

module.exports = { gateAnalysis, checkFormat };
