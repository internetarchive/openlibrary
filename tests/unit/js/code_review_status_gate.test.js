// Unit tests for the CODE-REVIEW STATUS gate (#14453). Covers three things that must not drift:
//   1. The three pure helpers the `status` job's step uses (.github/scripts/code_review/status.cjs
//      and shared.cjs); this test imports the module that ships, so tested logic == deployed logic:
//        - parseFindings(raw)                 -- the env->findings derivation, FAIL CLOSED on absent
//        - unresolvedThreadCount(threads)     -- threads that are unresolved AND not outdated
//        - decideStatus({postSucceeded,...})  -- the pass/fail + state + non-leaky description
//      (The public-findings COUNT is produced INSIDE this workflow's analyze-gate step -- the
//      `public_findings_count` output -- and consumed here via parseFindings, which blocks when absent.)
//   2. The posted commit-status context string is EXACTLY `code-review` (the branch-protection
//      ruleset requires that string; a drift makes the required gate unsatisfiable -> every PR blocked).
//   3. The ANALYZE-EXECUTION INVARIANT: the `analyze` job (which runs with secrets on untrusted fork
//      PRs under pull_request_target) must NEVER execute PR content -- no build/install/test/cache/
//      cloud-auth/language-setup step. This is the load-bearing control that makes pull_request_target
//      safe here, so a CI test fails the build if analyze gains a disallowed action or run command.
//   4. Every checkout is of base-repo code (never a PR-head ref) and leaves no credentials behind, and
//      every github-script step runs a module from that checkout.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import yaml from 'js-yaml';

const here = dirname(fileURLToPath(import.meta.url));
const WF = join(here, '..', '..', '..', '.github', 'workflows');
const SCRIPTS = join(here, '..', '..', '..', '.github', 'scripts', 'code_review');
const workflowText = readFileSync(join(WF, 'code_review_action.yml'), 'utf8');
const load = createRequire(import.meta.url);
const shared = load(join(SCRIPTS, 'shared.cjs'));
const status = load(join(SCRIPTS, 'status.cjs'));
const range = load(join(SCRIPTS, 'range.cjs'));
const post = load(join(SCRIPTS, 'post.cjs'));
const source = file => readFileSync(join(SCRIPTS, file), 'utf8');

const { parseFindings, decideStatus } = status;
const { unresolvedThreadCount } = shared;

// ---- parseFindings: the env->findings derivation. FAIL CLOSED (absent/garbage -> null, blocks) ----
test('parseFindings returns the integer for a well-formed non-negative count', () => {
    assert.equal(parseFindings('0'), 0);
    assert.equal(parseFindings('3'), 3);
    assert.equal(parseFindings(' 7 '), 7);
});
test('parseFindings returns null (=> blocks) for absent or malformed input -- NOT 0', () => {
    // This is the H1 fail-closed guard: before the #14451 producer lands, or on a skip path, the
    // output is absent. null -> decideStatus blocks. Treating absent as 0/clean would let a review
    // with only orphaned (summary-only, un-threaded) findings pass. Each of these MUST be null.
    for (const raw of ['', undefined, null, 'abc', '-1', '3.5', '1e2', 'NaN', '0x3', ' ']) {
        assert.equal(parseFindings(raw), null, `expected null for ${JSON.stringify(raw)}`);
    }
});

// ---- unresolvedThreadCount: GitHub's own isResolved/isOutdated are authoritative ----
test('unresolvedThreadCount counts only threads that are unresolved AND not outdated', () => {
    const threads = [
        { isResolved: false, isOutdated: false }, // blocks
        { isResolved: true, isOutdated: false }, // resolved -> ok
        { isResolved: false, isOutdated: true }, // outdated by a later push -> ok
        { isResolved: true, isOutdated: true }, // ok
        { isResolved: false, isOutdated: false } // blocks
    ];
    assert.equal(unresolvedThreadCount(threads), 2);
    assert.equal(unresolvedThreadCount([]), 0);
});

// ---- decideStatus: PASS = posted-clean AND fully-resolved; bias to blocking; non-leaky text ----
test('decideStatus PASSES only when posted, zero public findings, zero unresolved', () => {
    const d = decideStatus({ postSucceeded: true, findings: 0, unresolved: 0 });
    assert.equal(d.pass, true);
    assert.equal(d.state, 'success');
    assert.match(d.description, /passed/i);
});
test('decideStatus FAILS when the review did not post cleanly (greenlight-a)', () => {
    const d = decideStatus({ postSucceeded: false, findings: 0, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
    assert.equal(d.description, 'No clean review for this commit.');
});
test('decideStatus FAILS when this pass posted public findings (singular/plural)', () => {
    const one = decideStatus({ postSucceeded: true, findings: 1, unresolved: 0 });
    assert.equal(one.state, 'failure');
    assert.equal(one.description, '1 finding to address.');
    const many = decideStatus({ postSucceeded: true, findings: 4, unresolved: 0 });
    assert.equal(many.description, '4 findings to address.');
});
test('decideStatus FAILS when prior feedback is unresolved, even with a clean pass (singular/plural)', () => {
    const one = decideStatus({ postSucceeded: true, findings: 0, unresolved: 1 });
    assert.equal(one.state, 'failure');
    assert.equal(one.description, '1 unresolved review thread.');
    const many = decideStatus({ postSucceeded: true, findings: 0, unresolved: 3 });
    assert.equal(many.description, '3 unresolved review threads.');
});
test('decideStatus FAILS CLOSED when the findings count is unavailable (null), even with zero unresolved', () => {
    // H1: an unknown count must NOT pass. null is what parseFindings returns when the producer
    // output is absent -- a review could have orphaned/summary-only findings we cannot see.
    const d = decideStatus({ postSucceeded: true, findings: null, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
    assert.equal(d.description, 'Review findings count unavailable.');
});
test('decideStatus never leaks finding content -- description is counts and fixed phrases only', () => {
    for (const c of [
        { postSucceeded: true, findings: 0, unresolved: 0 },
        { postSucceeded: false, findings: 0, unresolved: 0 },
        { postSucceeded: true, findings: 2, unresolved: 0 },
        { postSucceeded: true, findings: 0, unresolved: 2 },
        { postSucceeded: true, findings: null, unresolved: 0 },
        // Withheld paths (D3a): the one describing a withheld finding must be a FIXED phrase with
        // no count and no content -- the only thing a withheld status may reveal is that a finding
        // exists (the accepted one-bit leak), never how many, where, or what.
        { postSucceeded: true, findings: 1, withheld: true, unresolved: 0 },
        { postSucceeded: true, findings: 0, withheld: true, unresolved: 0 },
        { postSucceeded: true, findings: null, withheld: true, unresolved: 0 }
    ]) {
        const { description } = decideStatus(c);
        // One of a small fixed set of templates -- a count plus fixed words, no free text that
        // could carry a finding's content. The withheld-finding template carries NO number.
        assert.match(
            description,
            /^(Review passed; all feedback resolved\.|No clean review for this commit\.|Review findings count unavailable\.|A finding was delivered privately; maintainer review required\.|\d+ findings? to address\.|\d+ unresolved review threads?\.)$/
        );
        // A withheld description must never carry a digit (no count leak).
        if (c.withheld && c.findings) assert.ok(!/\d/.test(description), `withheld description leaked a digit: ${description}`);
    }
});

// ---- Context string: EXACTLY `code-review` (must match the ruleset's required-check string) ----
test('the status job posts commit status context === "code-review" (ruleset-required string)', () => {
    // A rename makes the required gate unsatisfiable (ruleset requires a string nothing posts) or
    // unenforcing. Pin the single source of truth: the createCommitStatus `context:` line, in the
    // workflow and in every code review module.
    const files = readdirSync(SCRIPTS).filter(f => f.endsWith('.cjs'));
    const contextLines = [workflowText, ...files.map(source)].flatMap(t => t.split('\n')).filter(l => /^\s*context:\s*/.test(l));
    assert.ok(contextLines.length >= 1, 'expected at least one `context:` line in the code review scripts');
    for (const line of contextLines) {
        assert.match(line, /^\s*context:\s*'code-review',?\s*$/, `status context must be exactly 'code-review', got: ${line.trim()}`);
    }
});

test('pending fires on the same triggers as analyze, and status runs whenever pending posted', () => {
    assert.equal(workflow.jobs.pending.if, workflow.jobs.analyze.if);
    assert.ok(workflow.jobs.status.needs.includes('pending'));
    assert.match(workflow.jobs.status.if, /needs\.pending\.outputs\.head_sha != ''/);
});

// ---- ANALYZE-EXECUTION INVARIANT: analyze never executes PR content (the pull_request_target belt) ----
// analyze runs with secrets on untrusted fork PRs. Its safety rests entirely on "reads the diff as
// data, never runs it." This asserts that structurally: only an allowlist of actions, and no
// build/install/test/cache command in any `run:`. Fails the build the moment analyze gains a
// cache/cloud/setup/exec step -- the #1 regression risk Locke flagged for pull_request_target.
const workflow = yaml.load(workflowText);
const analyzeJob = workflow.jobs.analyze;

// Action name = the part before `@`, e.g. `actions/cache` from `actions/cache@<sha>`.
const ALLOWED_ANALYZE_ACTIONS = new Set(['actions/checkout', 'actions/github-script', 'anthropics/claude-code-action', 'actions/upload-artifact']);
// ALLOWLIST (not a blocklist -- adversarial review found a blocklist porous: `bash pr-head/x.sh`,
// `./configure`, `source`, `eval` all slipped a keyword blocklist). analyze's run steps may ONLY
// fetch + inertly extract the PR head, so only these leading commands are permitted. Anything else
// (a shell, interpreter, build tool, or executing a path) means analyze might run fork content.
const ANALYZE_RUN_ALLOWED_CMDS = new Set(['git', 'mkdir', 'printf', 'tar', 'rm', 'find', 'chmod', 'cd', 'echo', 'true', ':', 'test', '[']);
// Belt for execution hidden in args/substitutions even when the leading command is allowed, e.g.
// `find ... -exec bash {}` or `mkdir "$(sh x)"` or a `./path` / `/abs/path` invocation. `-exec`
// (find's own flag, hyphen-prefixed) is deliberately NOT matched.
const EXEC_SHAPE =
    /(?<![-\w])(bash|sh|zsh|ksh|dash|source|eval|exec|xargs|env|ruby|perl|php|node|nodejs|python[0-9.]*|dotnet|java|gradlew|make|cmake|configure|awk|sed)(?![\w])|(?:^|[\s|&;(])\.{0,2}\/[\w.]/m;

// Drop full-line comments (so a `;` or `/` inside a comment is never read as a command/path).
const codeOnly = run =>
    run
        .split('\n')
        .map(l => l.trim())
        .filter(l => l && !l.startsWith('#'))
        .join('\n');

// Leading command of each pipeline segment of a `run:` block. Pure VAR=value assignment segments
// (value may be a quoted string or a $(...) substitution with spaces, e.g. ATTR="$(git ...)")
// contribute no command and are dropped FIRST; a leading inline env-assignment prefix
// (FOO=bar cmd ...) is then stripped so the real command is checked.
const PURE_ASSIGN = /^[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|\$\([^)]*\)|\S*)$/;
const leadingCommands = run =>
    codeOnly(run)
        .split(/\n|&&|\|\||\||;/)
        .map(seg => seg.trim())
        .filter(Boolean)
        .filter(seg => !PURE_ASSIGN.test(seg))
        .map(seg => seg.replace(/^(?:[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|\S+)\s+)+/, ''))
        .filter(Boolean)
        .map(seg => seg.split(/\s+/)[0]);

test('analyze job uses only allowlisted actions (no cache/cloud/setup -> no fork-code execution)', () => {
    const used = (analyzeJob.steps || []).filter(s => s.uses).map(s => s.uses.split('@')[0]);
    assert.ok(used.length > 0, 'expected analyze to have `uses:` steps');
    for (const name of used) {
        assert.ok(
            ALLOWED_ANALYZE_ACTIONS.has(name),
            `analyze uses a non-allowlisted action "${name}" -- if this is a cache/cloud/setup ` +
                `action it can execute or poison fork content under pull_request_target. If the addition ` +
                `is genuinely safe, extend ALLOWED_ANALYZE_ACTIONS deliberately and re-justify the banner invariant.`
        );
    }
});

test('analyze run steps invoke only allowlisted commands (no shell/interpreter/build/./path -> no fork-code exec)', () => {
    for (const step of analyzeJob.steps || []) {
        if (typeof step.run !== 'string') continue;
        for (const cmd of leadingCommands(step.run)) {
            assert.ok(
                ANALYZE_RUN_ALLOWED_CMDS.has(cmd),
                `analyze run step leads with non-allowlisted command "${cmd}" -- it could execute or parse ` +
                    `fork content. analyze may only fetch + inertly extract the PR head. Step:\n${step.run}`
            );
        }
        assert.ok(
            !EXEC_SHAPE.test(codeOnly(step.run)),
            `analyze run step contains an execution shape (shell/interpreter/./path) that could run fork content:\n${step.run}`
        );
    }
});

// The model's shell+network are OFF -- this is the actual injection->exec barrier under
// pull_request_target, and the adversarial review flagged it was unasserted. Pin it so flipping
// claude_args to allow Bash (or dropping --disallowedTools) fails CI.
test('the Review (model) step keeps Bash/WebFetch/WebSearch disabled and does not allow a shell', () => {
    const review = (analyzeJob.steps || []).find(s => (s.uses || '').includes('claude-code-action'));
    assert.ok(review, 'expected a claude-code-action Review step in analyze');
    const args = String((review.with && review.with.claude_args) || '');
    const disallowed = args.match(/--disallowedTools\s+"([^"]*)"/);
    assert.ok(disallowed, 'Review step must pass --disallowedTools (the model must have no shell/network)');
    for (const tool of ['Bash', 'WebFetch', 'WebSearch']) {
        assert.ok(new RegExp(`\\b${tool}\\b`).test(disallowed[1]), `--disallowedTools must include ${tool}`);
    }
    const allowed = (args.match(/--allowedTools\s+"([^"]*)"/) || ['', ''])[1];
    assert.ok(!/\bBash\b/.test(allowed), 'Review step must not re-enable Bash via --allowedTools');
});

test('analyze job holds no PAT and no write permission (the no-write half of the split)', () => {
    const text = JSON.stringify(analyzeJob);
    // No PAT secret referenced anywhere in the analyze job (OAuth model token + GITHUB_TOKEN only).
    assert.ok(!/secrets\.OL_BOT_\w*PAT/.test(text), 'analyze must not reference any OL_BOT_*PAT secret -- PATs live only in post/status.');
    // Permissions are read-only (id-token:write is the OIDC exception, not repo write).
    const perms = analyzeJob.permissions || {};
    for (const [scope, level] of Object.entries(perms)) {
        if (scope === 'id-token') continue; // OIDC token exchange only; not repo write
        assert.notEqual(level, 'write', `analyze must not hold write scope "${scope}: write".`);
    }
});

// ============================================================================================
// #14476 -- make the code-review merge check RELIABLE on every PR. Three defects, red-first.
//   D1  review + status must describe the SAME commit (post NEITHER if the head moved mid-run).
//   D2  "already reviewed this SHA" must never mean "no status": a reviewed head with no
//       code-review status gets the status re-posted (idempotent, from the review-body marker).
//   D3a status is finding-driven, not withhold-driven: a withhold with 0 findings -> success;
//       any finding (public or withheld) -> failure with a NON-LEAKY description; absent -> closed.
// Each helper below is imported from the shipped module, so tested logic == deployed logic.
// ============================================================================================

// ---- D1: headIsCurrent -- the live-head guard shared by `post` and `status` ----
test('D1 headIsCurrent is true only when the pinned reviewed SHA still equals the live head', () => {
    const { headIsCurrent } = shared;
    const a = 'a'.repeat(40),
        b = 'b'.repeat(40);
    assert.equal(headIsCurrent(a, a), true, 'same SHA -> current -> safe to post');
    assert.equal(headIsCurrent(a, b), false, 'head moved -> NOT current -> post neither review nor status');
});
test('D1 the post step guards createReview with a live-head re-fetch (pulls.get)', () => {
    // The post job must re-read the live head and bail before createReview when it moved -- otherwise
    // createReview re-anchors the review to the new head while the status binds the old one (the
    // ae775e7d strand). Structural: a pulls.get and a headIsCurrent guard precede createReview.
    const postScript = post.validateAndPost.toString();
    assert.ok(/pulls\.get/.test(postScript), 'post must re-fetch the live head (pulls.get) before posting');
    assert.ok(/headIsCurrent\(/.test(postScript), 'post must guard the review with a headIsCurrent() call');
    // The guard (pulls.get + headIsCurrent call) must precede the createReview API call. Use the
    // qualified call strings so a mention of "createReview" in a comment cannot satisfy the order.
    assert.ok(postScript.indexOf('pulls.get') < postScript.indexOf('pulls.createReview'), 'the live-head re-fetch must precede pulls.createReview');
    assert.ok(postScript.indexOf('headIsCurrent(') < postScript.indexOf('pulls.createReview'), 'the head guard must precede pulls.createReview');
});
test('D1 the status step guards createCommitStatus with a live-head re-fetch', () => {
    const s = status.postStatus.toString();
    assert.ok(/pulls\.get/.test(s), 'status must re-fetch the live head (pulls.get) before posting the status');
    assert.ok(/headIsCurrent\(/.test(s), 'status must guard createCommitStatus with a headIsCurrent() call');
    assert.ok(s.indexOf('pulls.get') < s.indexOf('repos.createCommitStatus'), 'the live-head re-fetch must precede repos.createCommitStatus');
    assert.ok(s.indexOf('headIsCurrent(') < s.indexOf('repos.createCommitStatus'), 'the head guard must precede repos.createCommitStatus');
});

// ---- D2/#14486: STATE-aware skip -- compare the present status STATE to the review's verdict ----
test('#14486 the range resolver is STATE-aware: it compares the present status to the implied verdict', () => {
    // The already-reviewed skip must be STATE-aware, not merely presence-aware (the #14486 bug): it may
    // skip only when the present `code-review` status STATE matches the verdict the review implies for
    // this head; a stale/contradicting/absent status must route to a repost, never strand the head red.
    const s = range.resolveRange.toString();
    assert.ok(/listCommitStatusesForRef/.test(s), "range step must list the head's commit statuses");
    assert.ok(/reviewThreads/.test(s), 'range step must read live review threads to imply the verdict');
    assert.ok(/expectedState/.test(s), 'range step must compute the implied verdict (expectedState)');
    assert.ok(/\.state === expectedState/.test(s), 'range step must skip ONLY when the present status state matches the verdict');
    assert.ok(/context === 'code-review'/.test(s), 'range step must select the code-review status by context');
    // The old presence-only gate must be gone -- a mere-presence skip is the stale-status bug.
    assert.ok(!/codeReviewStatusPresent/.test(s), 'the presence-only skip (codeReviewStatusPresent) must be removed');
    // analyze must still declare a `repost` output so post can be skipped while status recomputes.
    assert.ok(workflow.jobs.analyze.outputs && 'repost' in workflow.jobs.analyze.outputs, 'analyze must expose a `repost` output');
});
test('#14486 the resolver and the status job share the same verdict helpers (no drift)', () => {
    // Both the resolver (expectedState) and the status repost (decideStatus) read the review-body marker
    // and count unresolved threads. Both import the ONE definition in shared.cjs and define no copy of
    // their own. A behavioural drift pin (which also covers the review selection) lives in the
    // integration test.
    for (const file of ['range.cjs', 'status.cjs']) {
        const src = source(file);
        assert.match(
            src,
            /\{[^}]*\bparseReviewMarker\b[^}]*\bunresolvedThreadCount\b[^}]*\} = require\('\.\/shared\.cjs'\)/,
            `${file} imports the shared helpers`
        );
        assert.doesNotMatch(src, /const (parseReviewMarker|unresolvedThreadCount) =/, `${file} keeps no copy of its own`);
    }
    const { parseReviewMarker } = shared;
    assert.equal(parseReviewMarker('text\n<!-- ol-pr-review-bot f=0 -->'), 0);
    assert.equal(parseReviewMarker('text\n<!-- ol-pr-review-bot -->'), null, 'legacy marker -> null -> fail closed');
    assert.equal(unresolvedThreadCount([{ isResolved: false, isOutdated: false }]), 1, 'unresolved + current -> blocks');
    assert.equal(
        unresolvedThreadCount([
            { isResolved: true, isOutdated: false },
            { isResolved: false, isOutdated: true }
        ]),
        0,
        'resolved or outdated -> does not block'
    );
});
test('D2 parseReviewMarker reads the public findings count from the review-body marker', () => {
    const { parseReviewMarker } = shared;
    assert.equal(parseReviewMarker('text\n<!-- ol-pr-review-bot f=0 -->'), 0);
    assert.equal(parseReviewMarker('text\n<!-- ol-pr-review-bot f=3 -->'), 3);
    // A legacy review body with the old marker (no f=) -> null -> the repost FAILS CLOSED (red),
    // never a fabricated green on a count we cannot read.
    assert.equal(parseReviewMarker('text\n<!-- ol-pr-review-bot -->'), null);
    assert.equal(parseReviewMarker(''), null);
    assert.equal(parseReviewMarker(null), null);
});
test('D2 the post step embeds the findings-count marker in the review body', () => {
    // Without an `f=<count>` marker in the posted body, a later status repost cannot reconstruct the
    // count and would strand the head. The marker is the public findings count (public by construction).
    assert.ok(/ol-pr-review-bot f=\$\{/.test(post.validateAndPost.toString()), 'post must embed `<!-- ol-pr-review-bot f=${...} -->` in the review body');
});

// ---- D3a: decideStatus withheld paths + withheldFindings + gate findingsTotal ----
test('D3a decideStatus: a withhold with ZERO findings PASSES (the backstop-false-positive case)', () => {
    // A PR that merely trips the security-term backstop but has no real defect must green itself.
    const d = decideStatus({ postSucceeded: true, findings: 0, withheld: true, unresolved: 0 });
    assert.equal(d.pass, true);
    assert.equal(d.state, 'success');
    assert.match(d.description, /passed/i);
});
test('D3a decideStatus: a withhold WITH a finding FAILS with the non-leaky private-delivery phrase', () => {
    const d = decideStatus({ postSucceeded: true, findings: 1, withheld: true, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
    assert.equal(d.description, 'A finding was delivered privately; maintainer review required.');
    assert.ok(!/\d/.test(d.description), 'the withheld description must carry no count');
});
test('D3a decideStatus: an unknown finding count on a withheld review FAILS CLOSED', () => {
    const d = decideStatus({ postSucceeded: true, findings: null, withheld: true, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
});
test('D3a withheldFindings maps the one-bit blocking signal to 0/1, fail-closed on unknown', () => {
    const { withheldFindings } = status;
    assert.equal(withheldFindings('true'), 1, 'a blocking withheld finding -> counts as >0 -> failure');
    assert.equal(withheldFindings('false'), 0, 'no blocking withheld finding -> 0 -> success');
    assert.equal(withheldFindings(''), null, 'absent -> null -> fail closed');
    assert.equal(withheldFindings(undefined), null);
    assert.equal(withheldFindings('garbage'), null, 'anything but true/false -> fail closed');
});

// ---- D3a: the pre-publication gate reports a trustworthy finding COUNT even when it withholds ----
// Both jobs run this exact module, so the test exercises the shipped gate (tested logic == deployed logic).
const gate = load(join(SCRIPTS, 'gate.cjs'));
const dimNone = note => ({ status: 'none', note });
const cleanDims = () => ({
    correctness: dimNone('ok'),
    security: dimNone('ok'),
    accessibility: dimNone('ok'),
    test_coverage: dimNone('ok'),
    styleguide: dimNone('ok')
});
test('D3a gate: a clean publishable review reports findingsTotal (0 and N) and blocking=false', () => {
    const empty = gate.check({ summary: 'fine', dimensions: cleanDims(), findings: [] });
    assert.equal(empty.publish, true);
    assert.equal(empty.findingsTotal, 0, 'a clean review has a KNOWN count of 0');
    assert.equal(empty.blocking, false);

    const dims = cleanDims();
    dims.correctness = { status: 'findings' };
    const two = gate.check({
        summary: 'has findings',
        dimensions: dims,
        findings: [
            { dimension: 'correctness', severity: 'low', title: 'a', body: 'b' },
            { dimension: 'correctness', severity: 'low', title: 'c', body: 'd' }
        ]
    });
    assert.equal(two.publish, true);
    assert.equal(two.findingsTotal, 2);
});
test('gate: a backstop withhold blocks only on a non-LOW finding', () => {
    const dims = cleanDims();
    dims.correctness = { status: 'findings' };
    const withFindings = findings => gate.check({ summary: 'This hardens against SQL injection risk.', dimensions: dims, findings });
    const low = { dimension: 'correctness', severity: 'low', title: 'a', body: 'b' };
    assert.equal(withFindings([low]).blocking, false, 'LOW only -> not blocking');
    assert.equal(withFindings([low, { ...low, severity: 'medium' }]).blocking, true, 'any MEDIUM/HIGH -> blocking');
});
test('D3a gate: a withhold triggered by the backstop with 0 findings is NON-blocking (-> success)', () => {
    // Summary mentions a security term so the text backstop withholds the public copy, but the MODEL
    // classified security=none and filed no finding. This is the ONLY greenable withheld case
    // (Locke constraint 3): pure backstop-vocabulary trip, model-structurally-zero findings.
    const res = gate.check({ summary: 'This hardens against SQL injection risk.', dimensions: cleanDims(), findings: [] });
    assert.equal(res.publish, false, 'backstop term in the summary withholds the public text');
    assert.equal(res.findingsTotal, 0, 'but the model found nothing');
    assert.equal(res.blocking, false, '-> NON-blocking -> status greens itself');
});
test('D3a gate (Locke constraint 3): a MODEL security-classification is blocking regardless of count', () => {
    // A withhold caused by the model's OWN security classification must be blocking even though the
    // public findings count stays 0 -- never greenable, no matter what the structured array parses to.
    const dims = cleanDims();
    dims.security = { status: 'findings' };
    const res = gate.check({
        summary: 'review',
        dimensions: dims,
        findings: [{ dimension: 'security', severity: 'high', title: 'authz gap', body: 'missing owner check' }]
    });
    assert.equal(res.publish, false, 'a security finding is never published');
    assert.equal(res.blocking, true, 'model-classified security -> BLOCKING -> failure');
    assert.ok(res.findingsTotal > 0);
});
test('D3a gate: a structurally malformed review is UNKNOWN and FAILS CLOSED (blocking=true)', () => {
    for (const bad of [null, 'nope', { summary: 5 }, { summary: 'x', dimensions: {}, findings: 'no' }]) {
        const res = gate.check(bad);
        assert.equal(res.publish, false);
        assert.equal(res.findingsTotal, null, `malformed review must yield an UNKNOWN count: ${JSON.stringify(bad)}`);
        assert.equal(res.blocking, true, 'ambiguity is always blocking');
    }
});
test('D3a analyze emits withheld + withheld_blocking outputs, and public_findings_count stays 0 on withhold', () => {
    // The 1-bit disclosure signal is a dedicated boolean; the COUNT output keeps its documented
    // "0 on every withhold" invariant so no count ever leaks (Locke Q2).
    const outs = workflow.jobs.analyze.outputs || {};
    assert.ok('withheld' in outs, 'analyze must expose `withheld`');
    assert.ok('withheld_blocking' in outs, 'analyze must expose the 1-bit `withheld_blocking`');
    // The gate step must NOT emit the withheld finding count anywhere (count stays 0 on withhold).
    assert.ok(
        /res\.publish \? res\.clean\.findings\.filter\(f => f\.severity !== 'low'\)\.length : 0/.test(source('analyze_gate.cjs').replace(/\n/g, ' ')),
        'public_findings_count must remain `0` on a withhold (no count leak)'
    );
});

// ---- Checkouts: base-repo code only, no credentials left behind ----
// Under pull_request_target every job runs with secrets, so a checkout of the PR head would put fork
// code where a github-script step `require`s it. post, pending and status hold PATs.
test('every checkout is github.sha (never a PR-head ref or a stale base.sha) with persist-credentials: false', () => {
    const checkouts = Object.entries(workflow.jobs).flatMap(([job, j]) =>
        (j.steps || []).filter(s => (s.uses || '').startsWith('actions/checkout@')).map(s => [job, s.with || {}])
    );
    assert.deepEqual([...new Set(checkouts.map(([job]) => job))].sort(), ['analyze', 'pending', 'post', 'status']);
    for (const [job, w] of checkouts) {
        assert.equal(w['persist-credentials'], false, `${job}: checkout must set persist-credentials: false`);
        assert.equal(w.repository, undefined, `${job}: checkout must be of this repo, not the PR's fork`);
        const ref = String(w.ref || '');
        assert.doesNotMatch(ref, /head|merge|refs\/pull|pull_request\.number|github\.ref\b/i, `${job}: checkout must not use a PR-head ref (got ${ref})`);
        // github.sha is the commit this workflow was loaded from. pull_request.base.sha is stale on a PR
        // not pushed since master moved, so it can lack the scripts the steps require.
        assert.equal(ref, '${{ github.sha }}', `${job}: checkout must use github.sha (got ${ref})`);
    }
});
test('post, pending and status check out only the scripts, before any step that uses them', () => {
    for (const job of ['post', 'pending', 'status']) {
        const steps = workflow.jobs[job].steps;
        assert.ok((steps[0].uses || '').startsWith('actions/checkout@'), `${job}: the checkout is the first step`);
        assert.equal(steps[0].with['sparse-checkout'], '/.github/scripts/');
        assert.equal(steps[0].with['sparse-checkout-cone-mode'], false);
    }
});
test('every github-script step runs a code review module from the base checkout, never from pr-head/', () => {
    for (const [job, j] of Object.entries(workflow.jobs)) {
        for (const s of j.steps || []) {
            if (!(s.uses || '').startsWith('actions/github-script@')) continue;
            const m = /require\(`\$\{process\.env\.GITHUB_WORKSPACE\}\/\.github\/scripts\/code_review\/(\w+\.cjs)`\)/.exec(s.with.script);
            assert.ok(m, `${job} / ${s.name}: script must require a module from .github/scripts/code_review`);
            assert.doesNotMatch(s.with.script, /pr-head/);
            const fn = /await (\w+)\(\{/.exec(s.with.script);
            assert.ok(fn, `${job} / ${s.name}: script must call the module's function`);
            assert.equal(typeof load(join(SCRIPTS, m[1]))[fn[1]], 'function', `${m[1]} must export ${fn[1]}`);
        }
    }
});
