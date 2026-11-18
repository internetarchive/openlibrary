// Tests for the `code-review` status:
//   1. status.cjs's helpers: parseFindings, unresolvedThreadCount and decideStatus.
//   2. The status context is exactly `code-review`, the string the ruleset requires.
//   3. `analyze` never executes PR content. It runs with secrets on fork PRs, so this is what makes
//      pull_request_target safe.
//   4. Every checkout is base-repo code with no credentials kept, and every github-script step
//      runs a module from it.
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
    // A missing count must block: treating it as 0 would pass a review whose only findings have no
    // thread.
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
    // An unknown count must not pass.
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
        // A withheld finding gets a fixed phrase with no count or content.
        { postSucceeded: true, findings: 1, withheld: true, unresolved: 0 },
        { postSucceeded: true, findings: 0, withheld: true, unresolved: 0 },
        { postSucceeded: true, findings: null, withheld: true, unresolved: 0 }
    ]) {
        const { description } = decideStatus(c);
        // One of a small fixed set of templates -- a count plus fixed words, no free text that
        // could carry a finding's content. The withheld-finding template carries NO number.
        assert.match(
            description,
            /^(Review passed; all feedback resolved\.|No clean review for this commit\.|Review findings count unavailable\.|Feedback withheld for maintainer review\.|\d+ findings? to address\.|\d+ unresolved review threads?\.)$/
        );
        // A withheld description must never carry a digit (no count leak).
        if (c.withheld && c.findings) assert.ok(!/\d/.test(description), `withheld description leaked a digit: ${description}`);
    }
});

// ---- Context string: EXACTLY `code-review` (must match the ruleset's required-check string) ----
test('the status job posts commit status context === "code-review" (ruleset-required string)', () => {
    // A rename would make the required check unsatisfiable. Check every `context:` line in the
    // workflow and the modules.
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

// ---- analyze never executes PR content ----
// analyze runs with secrets on fork PRs, so it must treat the PR as data. Only allowlisted actions,
// and no build/install/test/cache command in any `run:`.
const workflow = yaml.load(workflowText);
const analyzeJob = workflow.jobs.analyze;

// Action name = the part before `@`, e.g. `actions/cache` from `actions/cache@<sha>`.
const ALLOWED_ANALYZE_ACTIONS = new Set(['actions/checkout', 'actions/github-script', 'anthropics/claude-code-action', 'actions/upload-artifact']);
// An allowlist, because a blocklist missed `bash pr-head/x.sh`, `./configure`, `source` and `eval`.
// analyze's run steps only fetch and extract the PR head, so only these leading commands are allowed.
const ANALYZE_RUN_ALLOWED_CMDS = new Set(['git', 'mkdir', 'printf', 'tar', 'rm', 'find', 'chmod', 'cd', 'echo', 'true', ':', 'test', '[']);
// Execution hidden in arguments even when the leading command is allowed, e.g. `find ... -exec bash {}`,
// `mkdir "$(sh x)"` or a `./path` / `/abs/path` invocation. find's own `-exec` flag is not matched.
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

// The model has no shell or network. Fail if claude_args ever allows Bash or drops --disallowedTools.
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

// ---- The status always matches the review it describes ----

// ---- The superseded marker: a review of a commit the PR had moved past ----
test('supersededMarker round-trips', () => {
    const { supersededMarker, supersededCommit } = shared;
    const a = 'a'.repeat(40);
    assert.equal(supersededCommit(`x\n${supersededMarker(a)}`), a);
    assert.equal(supersededCommit('x\n<!-- ol-pr-review-bot f=0 -->'), null);
    assert.equal(supersededCommit('<!-- ol-pr-review-bot superseded reviewed=nope -->'), null);
});

// ---- headIsCurrent: the live-head check `post` and `status` share ----
test('D1 headIsCurrent is true only when the pinned reviewed SHA still equals the live head', () => {
    const { headIsCurrent } = shared;
    const a = 'a'.repeat(40),
        b = 'b'.repeat(40);
    assert.equal(headIsCurrent(a, a), true, 'same SHA -> current -> safe to post');
    assert.equal(headIsCurrent(a, b), false, 'head moved -> NOT current -> post neither review nor status');
});
test('D1 the post step guards createReview with a live-head re-fetch (pulls.get)', () => {
    // `post` must re-read the live head and bail before createReview if it moved; createReview would
    // otherwise attach the review to the new head while the status goes on the old one.
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

// ---- Already reviewed: skip only if the present status matches the review's verdict ----
test('#14486 the range resolver is STATE-aware: it compares the present status to the implied verdict', () => {
    // Skip only when the present status matches the verdict the review implies. A stale, contradicting
    // or missing status must lead to a repost.
    const s = range.resolveRange.toString();
    assert.ok(/listCommitStatusesForRef/.test(s), "range step must list the head's commit statuses");
    assert.ok(/reviewThreads/.test(s), 'range step must read live review threads to imply the verdict');
    assert.ok(/expectedState/.test(s), 'range step must compute the implied verdict (expectedState)');
    assert.ok(/\.state === expectedState/.test(s), 'range step must skip ONLY when the present status state matches the verdict');
    assert.ok(/context === 'code-review'/.test(s), 'range step must select the code-review status by context');
    // A presence-only skip left stale statuses in place.
    assert.ok(!/codeReviewStatusPresent/.test(s), 'the presence-only skip (codeReviewStatusPresent) must be removed');
    // analyze must still declare a `repost` output so post can be skipped while status recomputes.
    assert.ok(workflow.jobs.analyze.outputs && 'repost' in workflow.jobs.analyze.outputs, 'analyze must expose a `repost` output');
});
test('#14486 the resolver and the status job share the same verdict helpers (no drift)', () => {
    // range.cjs and status.cjs import the helpers from shared.cjs and keep no copy. The integration
    // test checks that both pick the same review.
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
    // A body without an `f=` count -> null -> the repost fails closed.
    assert.equal(parseReviewMarker('text\n<!-- ol-pr-review-bot -->'), null);
    assert.equal(parseReviewMarker(''), null);
    assert.equal(parseReviewMarker(null), null);
});
test('D2 the post step embeds the findings-count marker in the review body', () => {
    // Without an `f=<count>` marker, a repost cannot reconstruct the count.
    assert.ok(/reviewMarker\(findingCount, heldBackBlocks\)/.test(post.validateAndPost.toString()), 'post must embed the marker in the review body');
});
test('the marker counts a blocking held-back part as one more finding', () => {
    const { reviewMarker, heldBackBlocking, parseReviewMarker } = shared;
    assert.equal(reviewMarker(2, false), '<!-- ol-pr-review-bot f=2 -->');
    assert.equal(reviewMarker(0, true), '<!-- ol-pr-review-bot f=0 h=1 -->');
    assert.equal(parseReviewMarker(reviewMarker(0, true)), 1);
    assert.equal(parseReviewMarker(reviewMarker(2, true)), 3);
    assert.equal(heldBackBlocking(reviewMarker(0, true)), true);
    assert.equal(heldBackBlocking(reviewMarker(0, false)), false);
});

// ---- Withheld reviews: decideStatus, withheldFindings and the gate's findingsTotal ----
test('D3a decideStatus: a withhold with ZERO findings PASSES (the backstop-false-positive case)', () => {
    // A PR that merely trips the security-term backstop but has no real defect must green itself.
    const d = decideStatus({ postSucceeded: true, findings: 0, withheld: true, unresolved: 0 });
    assert.equal(d.pass, true);
    assert.equal(d.state, 'success');
    assert.match(d.description, /passed/i);
});
test('D3a decideStatus: a withhold WITH a finding FAILS with the non-leaky withheld phrase', () => {
    const d = decideStatus({ postSucceeded: true, findings: 1, withheld: true, unresolved: 0 });
    assert.equal(d.pass, false);
    assert.equal(d.state, 'failure');
    assert.equal(d.description, 'Feedback withheld for maintainer review.');
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

// ---- The gate reports a finding count even when it withholds ----
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
            { dimension: 'correctness', severity: 'low', confidence: 8, title: 'a', body: 'b' },
            { dimension: 'correctness', severity: 'low', confidence: 8, title: 'c', body: 'd' }
        ]
    });
    assert.equal(two.publish, true);
    assert.equal(two.findingsTotal, 2);
});
test('gate: the text scan reads markup both with tags stripped and with tags kept', () => {
    const withSummary = summary => !gate.check({ summary, dimensions: cleanDims(), findings: [] }).heldBack;
    assert.equal(withSummary('Rename the sec<b>ret</b> helper.'), false, 'tags stripped: a word split by a tag');
    assert.equal(withSummary('Rename the sec<x<y>>ret helper.'), false, 'tags stripped until none are left');
    assert.equal(withSummary('Label the `<input type="password">` field.'), false, 'tags kept: a tag in a code span is shown as text');
    assert.equal(withSummary('Wrap the <b>helper</b> name in a <code>tag</code>.'), true, 'harmless markup still publishes');
});
test('gate: a finding the text scan holds back blocks only when it is not LOW; the rest is published', () => {
    const dims = cleanDims();
    dims.correctness = { status: 'findings' };
    const withFindings = findings => gate.check({ summary: 'fine', dimensions: dims, findings });
    const low = { dimension: 'correctness', severity: 'low', confidence: 8, title: 'a', body: 'b' };
    const tripped = { ...low, body: 'This query is open to SQL injection.' };
    const lowOnly = withFindings([low, tripped]);
    assert.equal(lowOnly.publish, true);
    assert.equal(lowOnly.heldBack, true);
    assert.equal(lowOnly.blocking, false, 'LOW only -> not blocking');
    assert.deepEqual(lowOnly.clean.findings, [low], 'the other finding is still published');
    assert.equal(withFindings([low, { ...tripped, severity: 'medium' }]).blocking, true, 'a MEDIUM/HIGH held back -> blocking');
});
test('gate: a summary or note the text scan trips is replaced, and the rest is published', () => {
    const dims = cleanDims();
    dims.styleguide = dimNone('Checked the password form.');
    const res = gate.check({ summary: 'This hardens against SQL injection risk.', dimensions: dims, findings: [] });
    assert.equal(res.publish, true);
    assert.equal(res.heldBack, true);
    assert.equal(res.blocking, false, 'no finding was held back -> NON-blocking');
    assert.equal(res.clean.summary, '');
    assert.equal(res.clean.dimensions.styleguide.note, gate.heldBackNote);
    assert.equal(res.clean.dimensions.correctness.note, 'ok');
    assert.equal(gate.check(res.clean).heldBack, false, 'the replacements pass the gate again');
});

// A diff adding lines 10-12 of app.py, with line 9 as context.
const DIFF = 'diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -9,1 +9,4 @@\n x = 1\n+a = 1\n+b = 2\n+c = 3\n';
const sec = f => ({
    dimension: 'security',
    severity: 'high',
    confidence: 8,
    title: 'authz gap',
    body: 'Anyone can edit any list: check the owner.',
    path: 'app.py',
    line: 11,
    ...f
});
const withSecurity = (findings, diff = DIFF) => {
    const dims = cleanDims();
    dims.security = { status: 'findings' };
    return gate.check({ summary: 'review', dimensions: dims, findings }, diff);
};
test('gate: addedLines reads only + lines, past hunk headers and lines that look like headers', () => {
    const added = gate.addedLines(`${DIFF}diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1,2 +1,2 @@\n---- removed\n++++ added\n kept\n`);
    assert.deepEqual([...added.get('app.py')], [10, 11, 12]);
    assert.deepEqual([...added.get('b.py')], [1]);
});
test('SECURITY gate: a concern in existing code is held back and blocks; the rest is published', () => {
    const other = { dimension: 'correctness', severity: 'medium', confidence: 8, title: 'Off by one', body: 'Use <=.' };
    for (const f of [sec({ scope: 'existing' }), sec({ scope: undefined }), sec({ scope: 'existing', severity: 'low', confidence: 2 })]) {
        const dims = cleanDims();
        dims.security = { status: 'findings' };
        dims.correctness = { status: 'findings' };
        const res = gate.check({ summary: 'review', dimensions: dims, findings: [f, other] }, DIFF);
        assert.equal(res.publish, true);
        assert.equal(res.heldBack, true);
        assert.equal(res.blocking, true, 'a held-back security finding always blocks');
        assert.deepEqual(res.clean.findings, [other]);
        assert.deepEqual(res.clean.dimensions.security, { status: 'none' });
        assert.ok(!JSON.stringify(res.clean).includes('owner'), 'nothing of it is kept');
    }
});
test('SECURITY gate: a concern the PR introduces is published when it sits on lines the PR adds', () => {
    const res = withSecurity([sec({ scope: 'introduced', start_line: 10, line: 12 })]);
    assert.equal(res.heldBack, false);
    assert.equal(res.clean.findings.length, 1);
    assert.equal(res.clean.findings[0].scope, 'introduced');
    assert.deepEqual(res.clean.dimensions.security, { status: 'findings' });
    assert.equal(withSecurity([sec({ scope: 'introduced', severity: 'low', confidence: 2 })]).clean.findings[0].severity, 'medium', 'it always blocks');
    // `post` gates the clean copy again, against its own diff.
    assert.equal(gate.check(JSON.parse(JSON.stringify(res.clean)), DIFF).heldBack, false);
});
test('SECURITY gate: an "introduced" concern NOT on lines the PR adds is held back', () => {
    for (const f of [
        sec({ scope: 'introduced', line: 9 }), // a context line
        sec({ scope: 'introduced', start_line: 9, line: 11 }), // starts on a context line
        sec({ scope: 'introduced', line: 40 }), // not in the diff
        sec({ scope: 'introduced', path: 'other.py' }),
        sec({ scope: 'introduced', path: undefined, line: undefined })
    ]) {
        const res = withSecurity([f]);
        assert.equal(res.heldBack, true, JSON.stringify(f));
        assert.equal(res.blocking, true);
        assert.deepEqual(res.clean.findings, []);
    }
    assert.equal(withSecurity([sec({ scope: 'introduced' })], '').heldBack, true, 'no diff -> held back');
});
test('SECURITY gate: an "introduced" concern carrying a credential is held back', () => {
    assert.equal(withSecurity([sec({ scope: 'introduced', body: `Remove ghp_${'a'.repeat(36)}.` })]).heldBack, true);
});
test('gate: a bad scope makes the review unpublishable', () => {
    assert.equal(withSecurity([sec({ scope: 'new' })]).publish, false);
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
    // A withhold is signalled by its own boolean; the count stays 0 so it reveals nothing.
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
    assert.deepEqual([...new Set(checkouts.map(([job]) => job))].sort(), ['analyze', 'decline', 'pending', 'post', 'resolve', 'skipped', 'status']);
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
test('post, resolve, pending and status check out only the scripts, before any step that uses them', () => {
    for (const job of ['post', 'resolve', 'pending', 'status']) {
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
