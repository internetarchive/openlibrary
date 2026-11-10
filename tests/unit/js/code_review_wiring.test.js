// Coverage for the code-review workflow's STEP wiring that is NOT inside REVIEW_GATE_JS: the
// `buildAdded` diff parser, the `buildBaseIndex` base-tree token index, and `segOf`, all embedded
// inline in the analyze github-script step of code_review_action.yml. The dead-base-check an
// adversarial review caught (a literal grep that missed qualified sink_refs) lived in exactly this
// region, which the REVIEW_GATE_JS unit test cannot reach (it injects a fake ctx). This test
// extracts the real functions from the workflow text and exercises them against real files/diffs.
import { test } from 'vitest';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, mkdtempSync, writeFileSync, mkdirSync, rmSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const fsReal = { readdirSync, readFileSync, existsSync };

const here = dirname(fileURLToPath(import.meta.url));
const YML = join(here, '..', '..', '..', '.github', 'workflows', 'code_review_action.yml');
const ymlLines = readFileSync(YML, 'utf8').split('\n');

// Extract a `const <name> = (…) => { … };` block from the workflow, keyed on the closing line that
// matches the declaration's indentation (so a nested `};` does not truncate it), and eval it. The
// arrow closes over `fs` provided here, exactly as it does in the step.
function extractFn(name) {
    const start = ymlLines.findIndex(l => l.includes(`const ${name} =`));
    assert.ok(start >= 0, `${name} not found in workflow`);
    const indent = ymlLines[start].match(/^(\s*)/)[1];
    const closer = `${indent}};`;
    const body = [ymlLines[start]];
    let end = -1;
    for (let j = start + 1; j < ymlLines.length; j++) {
        body.push(ymlLines[j]);
        if (ymlLines[j] === closer) {
            end = j;
            break;
        }
    }
    assert.ok(end >= 0, `end of ${name} not found`);
    const src = body
        .join('\n')
        .trim()
        .replace(new RegExp(`^const ${name} =\\s*`), '')
        .replace(/;\s*$/, '');
    // eslint-disable-next-line no-new-func
    return new Function('fs', `return (${src});`)(fsReal);
}

const buildAdded = extractFn('buildAdded');
const buildBaseIndex = extractFn('buildBaseIndex');
const segOf = extractFn('segOf');

// ---- buildAdded: pure diff parsing ----
test('buildAdded captures added(+) lines, not context/removed', () => {
    const diff = [
        'diff --git a/f.py b/f.py',
        '--- a/f.py',
        '+++ b/f.py',
        '@@ -5,4 +5,6 @@ def f():',
        ' ctx5',
        ' ctx6',
        '-removed',
        '+added7',
        '+added8',
        ' ctx9',
        ' ctx10'
    ].join('\n');
    assert.deepEqual(
        [...buildAdded(diff).get('f.py')].sort((a, b) => a - b),
        [7, 8]
    );
});
test('buildAdded is not poisoned by a crafted "+++ b/evil.py" ADDED line (F4)', () => {
    const diff = ['diff --git a/r.py b/r.py', '--- a/r.py', '+++ b/r.py', '@@ -1,1 +1,3 @@', ' ctx1', '+real2', '+++ b/evil.py', '+real4'].join('\n');
    const m = buildAdded(diff);
    assert.deepEqual(
        [...m.get('r.py')].sort((a, b) => a - b),
        [2, 3, 4]
    );
    assert.ok(!m.has('evil.py') && !m.has('b/evil.py'), 'no phantom file injected');
});
test('buildAdded keeps later added lines after a "--- "/"+++ " CONTENT pair in a hunk (#4)', () => {
    const diff = ['diff --git a/r.py b/r.py', '--- a/r.py', '+++ b/r.py', '@@ -1,2 +1,3 @@', ' ctx1', '--- removed', '+++ added2', '+added3'].join('\n');
    const m = buildAdded(diff);
    assert.deepEqual(
        [...m.get('r.py')].sort((a, b) => a - b),
        [2, 3]
    );
    assert.ok(!m.has('added2') && !m.has('removed'));
});
test('buildAdded against a REAL git diff', () => {
    const dir = mkdtempSync(join(tmpdir(), 'olcr-git-'));
    try {
        const run = (...a) => execFileSync('git', a, { cwd: dir, stdio: ['ignore', 'pipe', 'ignore'] });
        run('init', '-q');
        run('config', 'user.email', 't@t');
        run('config', 'user.name', 't');
        writeFileSync(join(dir, 'a.py'), 'one\ntwo\nthree\n');
        run('add', 'a.py');
        run('commit', '-qm', 'base');
        writeFileSync(join(dir, 'a.py'), 'one\ntwo\nINSERTED\nthree\n');
        const diff = execFileSync('git', ['diff'], { cwd: dir, encoding: 'utf8' });
        assert.ok([...buildAdded(diff).get('a.py')].includes(3), 'the inserted line 3 is an added line');
    } finally {
        rmSync(dir, { recursive: true, force: true });
    }
});

// ---- segOf: last identifier segment ----
test('segOf resolves the last identifier segment of a qualified/dotted/path ref', () => {
    assert.equal(segOf('openlibrary.core.lending.legacy_fetch'), 'legacy_fetch');
    assert.equal(segOf('self.fetch_url'), 'fetch_url');
    assert.equal(segOf('openlibrary/core/lending.py'), 'py');
    assert.equal(segOf('bare_symbol'), 'bare_symbol');
    assert.equal(segOf(null), null);
});

// ---- buildBaseIndex + the baseHasSymbol lookup composition: real tree walk ----
function baseTree(dir) {
    mkdirSync(join(dir, 'src'), { recursive: true });
    writeFileSync(join(dir, 'src', 'live.py'), 'def legacy_fetch(url):\n    return get(url)\n');
    writeFileSync(join(dir, 'setup.py'), 'setup()\n');
    // The review artifacts + PR-head extraction that sit in the workspace and MUST be excluded.
    mkdirSync(join(dir, 'pr-head', 'src'), { recursive: true });
    writeFileSync(join(dir, 'pr-head', 'src', 'new.py'), 'def pr_only_sink():\n    pass\n');
    writeFileSync(join(dir, 'review.diff'), '+def diff_only_sink():\n+legacy_fetch_in_diff\n');
}
// Replicates the step's baseHasSymbol lookup over a prebuilt token set (the step builds the set
// once at the top of classify; here we build it per test from a temp tree and compose the identical
// lookup). buildBaseIndex takes the root as an argument, so no process.chdir is needed (vitest
// workers forbid it); the path-existence branch is exercised with an absolute ref.
function baseHasSymbol(idx, ref) {
    if (idx.partial) return true; // an incomplete index fails closed -> escalate everything
    if ((ref.includes('/') || /\.[A-Za-z0-9]+$/.test(ref)) && !ref.includes('..') && existsSync(ref)) return true;
    const s = segOf(ref);
    return s ? idx.tokens.has(s) : true;
}
function withBaseTree(fn) {
    const dir = mkdtempSync(join(tmpdir(), 'olcr-base-'));
    try {
        baseTree(dir);
        return fn(buildBaseIndex(dir), dir);
    } finally {
        rmSync(dir, { recursive: true, force: true });
    }
}

test('buildBaseIndex indexes base source tokens; excludes pr-head/ and review artifacts', () => {
    withBaseTree(idx => {
        assert.equal(idx.partial, false);
        assert.ok(idx.tokens.has('legacy_fetch'), 'base source token indexed');
        assert.ok(!idx.tokens.has('pr_only_sink'), 'pr-head/ is excluded');
        assert.ok(!idx.tokens.has('diff_only_sink'), 'review.diff is excluded');
    });
});
test('baseHasSymbol: bare + QUALIFIED sink_ref whose segment is on base -> true (F2)', () => {
    withBaseTree(idx => {
        assert.equal(baseHasSymbol(idx, 'legacy_fetch'), true);
        assert.equal(baseHasSymbol(idx, 'openlibrary.core.lending.legacy_fetch'), true);
    });
});
test('baseHasSymbol: absent symbol -> false; PR-only symbol -> false (not on base)', () => {
    withBaseTree(idx => {
        assert.equal(baseHasSymbol(idx, 'nonexistent_symbol_zzz'), false);
        assert.equal(baseHasSymbol(idx, 'pr_only_sink'), false);
    });
});
test('baseHasSymbol: a file that exists resolves by existence (#3)', () => {
    withBaseTree((idx, dir) => assert.equal(baseHasSymbol(idx, join(dir, 'setup.py')), true));
});
test('buildBaseIndex flags `partial` on a read error -> baseHasSymbol fails CLOSED (escalates)', () => {
    const idx = buildBaseIndex('/no/such/dir/olcr-does-not-exist-zzz');
    assert.equal(idx.partial, true, 'an unreadable root sets partial');
    assert.equal(baseHasSymbol(idx, 'anything_whatsoever'), true, 'partial index escalates every ref');
});
