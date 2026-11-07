import { readFileSync } from 'node:fs';
import path from 'node:path';

// These tests exercise the ACTUAL logic deployed in the workflow, not a copy. The pure
// decision objects (FORK_GATE_JS, TRIAGE_JS) are `({ ... })` block scalars under `env:` in
// .github/workflows/code_review_action.yml -- the same text the workflow `eval`s at run time.
// We extract each block verbatim and eval it, so a drift between test and deployment is
// impossible: edit the workflow and these tests see the edit.
const workflowPath = path.join(__dirname, '../../../.github/workflows/code_review_action.yml');
const workflow = readFileSync(workflowPath, 'utf8');

// Pull a `  KEY: |` YAML block scalar out of the workflow and dedent it to valid JS.
function extractBlock(yaml, key) {
    const lines = yaml.split('\n');
    const idx = lines.findIndex(l => new RegExp(`^(\\s*)${key}:\\s*\\|\\s*$`).test(l));
    if (idx < 0) throw new Error(`block ${key} not found in workflow`);
    const keyIndent = lines[idx].match(/^(\s*)/)[1].length;
    const body = [];
    for (let i = idx + 1; i < lines.length; i++) {
        const line = lines[i];
        if (line.trim() === '') {
            body.push('');
            continue;
        }
        if (line.match(/^(\s*)/)[1].length <= keyIndent) break;
        body.push(line);
    }
    const indents = body.filter(l => l.trim()).map(l => l.match(/^(\s*)/)[1].length);
    const min = Math.min(...indents);
    return body.map(l => l.slice(min)).join('\n');
}

function evalBlock(key) {
    // The block is an `({ ... })` expression; `return` it from a fresh function scope.
    return new Function(`return ${extractBlock(workflow, key)}`)();
}

const forkGate = evalBlock('FORK_GATE_JS');
const triage = evalBlock('TRIAGE_JS');

describe('FORK_GATE_JS.decide (fork-path abuse controls)', () => {
    const base = { mergedPrCount: 3, runsToday: 0, perAuthorPerDay: 5, globalToday: 0, globalPerDay: 100 };

    it('admits an author with >=1 merged PR under both limits', () => {
        expect(forkGate.decide(base)).toEqual({ block: false });
    });

    it('blocks a brand-new account (0 merged PRs) -- it keeps the manual staff gate', () => {
        expect(forkGate.decide({ ...base, mergedPrCount: 0 }).block).toBe(true);
    });

    it('is a strict threshold: exactly 1 merged PR admits, 0 blocks', () => {
        expect(forkGate.decide({ ...base, mergedPrCount: 1 }).block).toBe(false);
        expect(forkGate.decide({ ...base, mergedPrCount: 0 }).block).toBe(true);
    });

    it('blocks at the per-author/day cap (not always-true, not always-false)', () => {
        expect(forkGate.decide({ ...base, runsToday: 4 }).block).toBe(false); // 4 < 5
        expect(forkGate.decide({ ...base, runsToday: 5 }).block).toBe(true); // 5 not < 5
        expect(forkGate.decide({ ...base, runsToday: 9 }).block).toBe(true);
    });

    it('blocks at the global/day backstop even for an eligible author under their own cap', () => {
        expect(forkGate.decide({ ...base, globalToday: 99 }).block).toBe(false);
        expect(forkGate.decide({ ...base, globalToday: 100 }).block).toBe(true);
    });

    it('fails CLOSED: the error sentinels (0 merged / runsToday==cap / globalToday==cap) all block', () => {
        expect(forkGate.decide({ ...base, mergedPrCount: 0 }).block).toBe(true);
        expect(forkGate.decide({ ...base, runsToday: 5 }).block).toBe(true);
        expect(forkGate.decide({ ...base, globalToday: 100 }).block).toBe(true);
    });
});

describe('FORK_GATE_JS.tally (per-author / global run counting)', () => {
    const opts = { author: 'alice', currentRunId: 999, workflowName: 'Code Review Action' };
    const run = (id, login, name = 'Code Review Action') => ({ id, name, actor: { login } });

    it("counts this workflow's runs per-author and globally, excluding the current run", () => {
        const runs = [
            run(1, 'alice'),
            run(2, 'alice'),
            run(3, 'bob'),
            run(999, 'alice') // the current run -- excluded
        ];
        expect(forkGate.tally(runs, opts)).toEqual({ globalToday: 3, runsToday: 2 });
    });

    it('ignores runs from OTHER workflows sharing the Actions API page', () => {
        const runs = [run(1, 'alice'), run(2, 'alice', 'Some Other Workflow')];
        expect(forkGate.tally(runs, opts)).toEqual({ globalToday: 1, runsToday: 1 });
    });

    it('is empty-safe (no runs today)', () => {
        expect(forkGate.tally([], opts)).toEqual({ globalToday: 0, runsToday: 0 });
        expect(forkGate.tally(undefined, opts)).toEqual({ globalToday: 0, runsToday: 0 });
    });

    it('tolerates a run with no actor without miscounting the author tally', () => {
        const runs = [run(1, 'alice'), { id: 2, name: 'Code Review Action' }];
        expect(forkGate.tally(runs, opts)).toEqual({ globalToday: 2, runsToday: 1 });
    });
});

describe('TRIAGE_JS.decide (triage-label decision)', () => {
    it('is clean -> no label when review is clean and CI is green', () => {
        expect(triage.decide({ withheld: false, findingsCount: 0, ciRed: false }).needsChanges).toBe(false);
    });

    it('needs changes on actionable findings', () => {
        expect(triage.decide({ withheld: false, findingsCount: 1, ciRed: false }).needsChanges).toBe(true);
    });

    it('needs changes on a red CI check even with a clean review', () => {
        expect(triage.decide({ withheld: false, findingsCount: 0, ciRed: true }).needsChanges).toBe(true);
    });

    it('needs changes on a withheld review', () => {
        expect(triage.decide({ withheld: true, findingsCount: 0, ciRed: false }).needsChanges).toBe(true);
    });

    // --- The security assertion (#14210 item 6). A withheld review -- which may be a
    // suppressed security finding -- must be INDISTINGUISHABLE, by the label decision, from
    // an ordinary has-findings PR. Same boolean, and NO extra key that could leak the reason.
    it('NON-DISCLOSURE: a withheld review yields the exact same decision as a has-findings PR', () => {
        const withheld = triage.decide({ withheld: true, findingsCount: 0, ciRed: false });
        const findings = triage.decide({ withheld: false, findingsCount: 1, ciRed: false });
        expect(withheld).toEqual(findings);
    });

    it('NON-DISCLOSURE: the decision exposes only { needsChanges } -- no security/withheld/reason tell', () => {
        for (const input of [
            { withheld: true, findingsCount: 0, ciRed: false },
            { withheld: false, findingsCount: 2, ciRed: false },
            { withheld: false, findingsCount: 0, ciRed: true }
        ]) {
            expect(Object.keys(triage.decide(input)).sort()).toEqual(['needsChanges']);
        }
    });
});

describe('TRIAGE_JS.ciRed (CI state re-derivation)', () => {
    const notOurs = () => false;

    it('is red on a concluded failing check-run', () => {
        expect(
            triage.ciRed({
                checkRuns: [{ status: 'completed', conclusion: 'failure', details_url: 'x' }],
                statuses: [],
                ours: notOurs
            })
        ).toBe(true);
    });

    it('is NOT red while a check is still pending (review may finish before CI)', () => {
        expect(
            triage.ciRed({
                checkRuns: [{ status: 'in_progress', conclusion: null, details_url: 'x' }],
                statuses: [],
                ours: notOurs
            })
        ).toBe(false);
    });

    it('is NOT red on success/neutral/skipped conclusions', () => {
        for (const conclusion of ['success', 'neutral', 'skipped']) {
            expect(
                triage.ciRed({
                    checkRuns: [{ status: 'completed', conclusion, details_url: 'x' }],
                    statuses: [],
                    ours: notOurs
                })
            ).toBe(false);
        }
    });

    it("ignores this workflow's OWN run so the review action never red-flags itself", () => {
        const ours = c => c.details_url.includes('/runs/999/');
        expect(
            triage.ciRed({
                checkRuns: [{ status: 'completed', conclusion: 'failure', details_url: 'https://github.com/o/r/actions/runs/999/job/1' }],
                statuses: [],
                ours
            })
        ).toBe(false);
    });

    it('reads legacy commit statuses: failure/error are red, pending is not', () => {
        expect(triage.ciRed({ checkRuns: [], statuses: [{ state: 'failure' }], ours: notOurs })).toBe(true);
        expect(triage.ciRed({ checkRuns: [], statuses: [{ state: 'error' }], ours: notOurs })).toBe(true);
        expect(triage.ciRed({ checkRuns: [], statuses: [{ state: 'pending' }], ours: notOurs })).toBe(false);
        expect(triage.ciRed({ checkRuns: [], statuses: [{ state: 'success' }], ours: notOurs })).toBe(false);
    });

    it('handles empty/missing inputs as not-red', () => {
        expect(triage.ciRed({ checkRuns: [], statuses: [], ours: notOurs })).toBe(false);
        expect(triage.ciRed({ ours: notOurs })).toBe(false);
    });
});

describe('TRIAGE_JS.lastLabelerIsBot (do not clobber a human-set shared label)', () => {
    const bots = ['github-actions[bot]', 'openlibrary-bot'];

    it('true when a bot added the label most recently', () => {
        expect(triage.lastLabelerIsBot([{ actor: 'github-actions[bot]', added: true }], bots)).toBe(true);
        expect(triage.lastLabelerIsBot([{ actor: 'openlibrary-bot', added: true }], bots)).toBe(true);
    });

    it("false when a human added the label (never strip a human's copy)", () => {
        expect(triage.lastLabelerIsBot([{ actor: 'somehuman', added: true }], bots)).toBe(false);
    });

    it('false when a human added it AFTER a bot did', () => {
        expect(
            triage.lastLabelerIsBot(
                [
                    { actor: 'github-actions[bot]', added: true },
                    { actor: 'somehuman', added: true }
                ],
                bots
            )
        ).toBe(false);
    });

    it('false when the most recent event removed the label', () => {
        expect(
            triage.lastLabelerIsBot(
                [
                    { actor: 'github-actions[bot]', added: true },
                    { actor: 'github-actions[bot]', added: false }
                ],
                bots
            )
        ).toBe(false);
    });

    it('false on empty/missing history', () => {
        expect(triage.lastLabelerIsBot([], bots)).toBe(false);
        expect(triage.lastLabelerIsBot(undefined, bots)).toBe(false);
    });
});

describe('workflow structure: security guards pinned against drift', () => {
    const analyzeIf = (() => {
        // The analyze job `if:` block, from `if: >` up to `permissions:`.
        const m = workflow.match(/\n {4}if: >\n([\s\S]*?)\n {4}permissions:/);
        if (!m) throw new Error('analyze if-block not found');
        return m[1];
    })();

    it('adds a pull_request_target fork path', () => {
        expect(analyzeIf).toContain("github.event_name == 'pull_request_target'");
    });

    it('the fork path is guarded to forks ONLY (head repo != base repo)', () => {
        expect(analyzeIf).toContain('github.event.pull_request.head.repo.full_name != github.repository');
    });

    it('the same-repo pull_request path still requires head repo == base repo (no double review)', () => {
        expect(analyzeIf).toContain('github.event.pull_request.head.repo.full_name == github.repository');
    });

    it('the fork path still skips drafts', () => {
        // Both automatic PR paths carry the not-draft guard.
        expect((analyzeIf.match(/!github\.event\.pull_request\.draft/g) || []).length).toBeGreaterThanOrEqual(2);
    });

    it('the issue_comment staff allowlist is left intact', () => {
        expect(analyzeIf).toContain("github.event_name == 'issue_comment'");
        expect(analyzeIf).toContain('fromJSON(');
    });

    it("token containment: the model OAuth token appears exactly once, in analyze's Review step", () => {
        const occurrences = (workflow.match(/OL_BOT_CLAUDE_OAUTH_TOKEN/g) || []).length;
        expect(occurrences).toBe(1);
        // It sits inside the claude_code_oauth_token line, with egress tools disallowed nearby.
        expect(workflow).toContain('claude_code_oauth_token: ${{ secrets.OL_BOT_CLAUDE_OAUTH_TOKEN }}');
        expect(workflow).toContain('--disallowedTools "Bash WebFetch WebSearch"');
    });

    it('analyze holds NO write scope except the OIDC id-token exception, and NO review PAT', () => {
        const m = workflow.match(/\n {2}analyze:\n[\s\S]*?\n {4}permissions:\n([\s\S]*?)\n {4}outputs:/);
        expect(m).toBeTruthy();
        const perms = m[1];
        // id-token: write is the documented OIDC exception (#13604); nothing else may be write.
        const writeScopes = [...perms.matchAll(/^\s*([a-z-]+):\s*write/gm)].map(x => x[1]);
        expect(writeScopes).toEqual(['id-token']);
        // The review PAT must live only in `post`, never in `analyze`.
        const analyzeBlock = workflow.match(/\n {2}analyze:\n([\s\S]*?)\n {2}post:/)[1];
        expect(analyzeBlock).not.toContain('OL_BOT_REVIEW_PAT');
    });

    it('the forkgate step runs only for pull_request_target and before the model', () => {
        expect(workflow).toMatch(/id: forkgate\n\s*if: github\.event_name == 'pull_request_target'/);
        // range (and so the model + post) is gated on the forkgate decision.
        expect(workflow).toMatch(/if: steps\.forkgate\.outputs\.block != 'true'\n\s*id: range/);
    });

    it('the triage label step runs always() and is the one label definition', () => {
        expect(workflow).toMatch(/name: Apply triage label[\s\S]*?if: always\(\)/);
        expect((workflow.match(/TRIAGE_LABEL: "Needs: Submitter Input"/g) || []).length).toBe(1);
    });
});
