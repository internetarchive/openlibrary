// The weekly report's `stats` job: collects how the code review bot did, with no model.
// It covers the last `days` days and the same span before it, for a week-over-week comparison,
// writes stats.json for the `report` and `publish` jobs, and checks the alert thresholds.
'use strict';

const BOT = 'openlibrary-bot';
const WORKFLOWS = ['code_review_action.yml', 'code_review_awaiting.yml'];
// A merged PR that touched any of these could have fixed a review bot failure.
const BOT_PATHS = [
    '.github/scripts/code_review',
    '.github/workflows/code_review_action.yml',
    '.github/workflows/code_review_awaiting.yml',
    '.github/workflows/code_review.md'
];

// An issue opens when any of these trips, whatever the model says. Tune them here.
const THRESHOLDS = {
    // Any failed `post` or `resolve` job means a review or a resolve was lost.
    maxPostOrResolveFailures: 0,
    // Share of runs that did real work (not skipped) and failed.
    maxRunFailureRate: 0.05,
    // Median `analyze` job, in seconds.
    maxMedianAnalyzeSeconds: 600,
    // Runs whose model hit its turn limit.
    maxTurnLimitHits: 0,
    // Share of the week's blocking findings nobody acted on (still open, or left open on a merged PR).
    // Only checked once there are at least `minFindingsForRate` findings.
    maxIgnoredFindingRate: 0.6,
    minFindingsForRate: 5
};

// Failure causes, matched against a failed job's error annotations.
const FAILURE_CAUSES = [
    ['turn_limit', /maximum number of turns/i],
    ['line_not_resolved', /Line could not be resolved/i],
    ['not_accessible', /Resource not accessible/i],
    ['rate_limited', /rate limit/i]
];

const DAY = 24 * 60 * 60 * 1000;
const seconds = (a, b) => (a && b ? Math.round((new Date(b) - new Date(a)) / 1000) : null);
const median = xs => {
    const s = xs.filter(x => x !== null).sort((a, b) => a - b);
    if (!s.length) return null;
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2);
};
const max = xs => {
    const s = xs.filter(x => x !== null);
    return s.length ? Math.max(...s) : null;
};
const inWindow = (t, w) => !!t && new Date(t) >= w.start && new Date(t) < w.end;

// The `days` input: an integer from 1 to 31, else 7.
const parseDays = raw => {
    const n = Number(raw);
    return Number.isInteger(n) && n >= 1 && n <= 31 ? n : 7;
};

const windows = (now, days) => {
    const end = new Date(now);
    const start = new Date(end - days * DAY);
    return { current: { start, end }, previous: { start: new Date(start - days * DAY), end: start } };
};

const failureCause = messages => {
    for (const [cause, re] of FAILURE_CAUSES) if (messages.some(m => re.test(m))) return cause;
    return 'other';
};

// runs: [{ workflow, event, conclusion, created_at, updated_at, jobs: [{ name, conclusion, started_at, completed_at, cause }] }]
function summarizeRuns(runs, w) {
    const out = { total: 0, skipped: 0, success: 0, failure: 0, cancelled: 0, by_workflow: {}, jobs: {}, failures: [] };
    for (const r of runs) {
        if (!inWindow(r.created_at, w)) continue;
        out.total++;
        const wf = (out.by_workflow[r.workflow] ||= { total: 0, skipped: 0, success: 0, failure: 0 });
        wf.total++;
        const c = r.conclusion === 'success' || r.conclusion === 'skipped' || r.conclusion === 'cancelled' ? r.conclusion : 'failure';
        out[c]++;
        if (c in wf) wf[c]++;
        for (const j of r.jobs || []) {
            if (j.conclusion === 'skipped') continue;
            const s = (out.jobs[j.name] ||= { count: 0, failed: 0, durations: [] });
            s.count++;
            if (j.conclusion === 'failure') {
                s.failed++;
                out.failures.push({
                    workflow: r.workflow,
                    job: j.name,
                    cause: j.cause || 'other',
                    message: j.message || '',
                    run_url: r.html_url,
                    at: r.created_at
                });
            }
            s.durations.push(seconds(j.started_at, j.completed_at));
        }
    }
    for (const s of Object.values(out.jobs)) {
        s.median_seconds = median(s.durations);
        s.max_seconds = max(s.durations);
        delete s.durations;
    }
    const worked = out.total - out.skipped - out.cancelled;
    out.failure_rate = worked ? +(out.failure / worked).toFixed(3) : 0;
    return out;
}

// "**MEDIUM · Correctness — Title**" -> { severity, dimension, title }
const parseFindingHeader = body => {
    const m = /^\*\*(HIGH|MEDIUM|LOW) · ([^—*]+?) — ([^\n]*?)\*\*/.exec(body || '');
    return m ? { severity: m[1].toLowerCase(), dimension: m[2].trim(), title: m[3].trim() } : null;
};

// What became of one of the bot's threads.
const threadOutcome = (t, pr) => {
    if (t.isResolved) {
        const by = t.resolvedBy && t.resolvedBy.login;
        const body = (t.comments.nodes[0] && t.comments.nodes[0].body) || '';
        if (by === 'github-actions' || by === 'github-actions[bot]' || by === BOT) {
            return /✅ Addressed in/.test(body) ? 'fixed' : /Dismissed:/.test(body) ? 'dismissed' : 'resolved_by_bot';
        }
        return 'resolved_by_person';
    }
    if (pr.merged || pr.state === 'CLOSED') return 'left_open_on_closed_pr';
    if (t.isOutdated) return 'outdated';
    return 'open';
};

const suggestionCount = body => {
    // The status line the review opens with: "**2 findings** · 1 suggestion on `abc1234`".
    const status = /^(?:\*\*[^*\n]+\*\*|[^\n]*?) · (\d+) suggestions? on `[0-9a-f]{7}`/m.exec(body || '');
    if (status) return Number(status[1]);
    // Reviews posted before that line existed: count the bullets of the Suggestions section.
    const m = /### Suggestions \(won't block\)\n\n([\s\S]*?)(\n\n###|\n\n> \[!NOTE\]|\n\n<details>|$)/.exec(body || '');
    return m ? (m[1].match(/^- \*\*/gm) || []).length : 0;
};

// prs: GraphQL pull requests with the bot's reviews and all review threads.
function summarizeReviews(prs, w) {
    const out = {
        reviews: 0,
        prs_reviewed: 0,
        states: {},
        blocking_findings: 0,
        suggestions: 0,
        threads: 0,
        by_dimension: {},
        by_severity: {},
        outcomes: {},
        threads_with_human_reply: 0,
        prs: []
    };
    for (const pr of prs) {
        const reviews = (pr.reviews.nodes || []).filter(r => r.author && r.author.login === BOT && inWindow(r.submittedAt, w));
        const threads = (pr.reviewThreads.nodes || []).filter(t => {
            const c = t.comments.nodes[0];
            return c && c.author && c.author.login === BOT && inWindow(c.createdAt, w) && parseFindingHeader(c.body);
        });
        if (!reviews.length && !threads.length) continue;
        out.prs_reviewed++;
        const row = { number: pr.number, title: pr.title, url: pr.url, state: pr.merged ? 'MERGED' : pr.state, reviews: reviews.length, findings: [] };
        for (const r of reviews) {
            out.reviews++;
            out.states[r.state] = (out.states[r.state] || 0) + 1;
            const f = /<!-- ol-pr-review-bot f=(\d+)(?: h=1)? -->/.exec(r.body || '');
            if (f) out.blocking_findings += Number(f[1]);
            out.suggestions += suggestionCount(r.body);
        }
        for (const t of threads) {
            const first = t.comments.nodes[0];
            const h = parseFindingHeader(first.body);
            const outcome = threadOutcome(t, pr);
            out.threads++;
            out.by_dimension[h.dimension] = (out.by_dimension[h.dimension] || 0) + 1;
            out.by_severity[h.severity] = (out.by_severity[h.severity] || 0) + 1;
            out.outcomes[outcome] = (out.outcomes[outcome] || 0) + 1;
            // Replies are untrusted text; the report job reads them only to judge whether a finding was disputed.
            const reply = t.comments.nodes.slice(1).find(c => c.author && c.author.login !== BOT && !c.author.login.endsWith('[bot]'));
            if (reply) out.threads_with_human_reply++;
            row.findings.push({ ...h, outcome, url: first.url, human_reply: reply ? reply.body.slice(0, 400) : null });
        }
        out.prs.push(row);
    }
    const ignored = (out.outcomes.open || 0) + (out.outcomes.left_open_on_closed_pr || 0);
    const n = k => out.outcomes[k] || 0;
    out.acted_on = n('fixed') + n('dismissed') + n('resolved_by_bot') + n('resolved_by_person') + n('outdated');
    out.ignored = ignored;
    out.ignored_rate = out.threads ? +(ignored / out.threads).toFixed(3) : 0;
    return out;
}

// Failures a merged PR already fixed (`fixed`: failure ids) don't count. A run counts as failed
// while any of its failures is not fixed.
function checkThresholds({ runs, reviews }, t = THRESHOLDS, fixed = new Set()) {
    const alerts = [];
    const failures = runs.failures.filter((f, i) => !fixed.has(f.id === undefined ? i : f.id));
    const fixedRuns = new Set(runs.failures.map(f => f.run_url).filter(u => !failures.some(f => f.run_url === u)));
    const worked = runs.total - runs.skipped - runs.cancelled;
    const failureRate = worked ? (runs.failure - fixedRuns.size) / worked : 0;
    const lost = failures.filter(f => f.job === 'post' || f.job === 'resolve');
    if (lost.length > t.maxPostOrResolveFailures) alerts.push(`${lost.length} \`post\` or \`resolve\` job(s) failed, so reviews or resolves were lost.`);
    if (failureRate > t.maxRunFailureRate) alerts.push(`${(failureRate * 100).toFixed(1)}% of runs failed (threshold ${t.maxRunFailureRate * 100}%).`);
    const analyze = runs.jobs.analyze && runs.jobs.analyze.median_seconds;
    if (analyze > t.maxMedianAnalyzeSeconds)
        alerts.push(`The median \`analyze\` job took ${Math.round(analyze / 60)} min (threshold ${t.maxMedianAnalyzeSeconds / 60} min).`);
    const turns = failures.filter(f => f.cause === 'turn_limit').length;
    if (turns > t.maxTurnLimitHits) alerts.push(`${turns} review(s) hit the model's turn limit.`);
    if (reviews.threads >= t.minFindingsForRate && reviews.ignored_rate > t.maxIgnoredFindingRate) {
        alerts.push(`${(reviews.ignored_rate * 100).toFixed(0)}% of blocking findings were never acted on (threshold ${t.maxIgnoredFindingRate * 100}%).`);
    }
    return alerts;
}

// What a PR changed in the review bot's files, as one diff, cut to `max` characters. PR descriptions
// often don't say which failures a change fixes; the diff does (a removed error message, a new catch).
const MAX_CHANGES = 5000;
const botDiff = files =>
    (files || [])
        .filter(f => BOT_PATHS.some(p => f.filename === p || f.filename.startsWith(`${p}/`)))
        .map(f => `--- ${f.filename}\n${f.patch || '(no textual diff)'}`)
        .join('\n');
const botChanges = (files, max = MAX_CHANGES) => {
    const diff = botDiff(files);
    return diff.length > max ? `${diff.slice(0, max)}\n[cut at ${max} characters]` : diff;
};

// The start of an error message, as it would appear in the code that raised it, or null if too
// short to match on. "Unhandled error: Error: Review not published: ..." -> "Review not published: ...".
const messageKey = message => {
    const key = (message || '').replace(/^(Unhandled error: )?(\w*Error: )?/, '').slice(0, 40);
    return key.length >= 20 ? key : null;
};
// The lines a diff removed.
const removedLines = patch => (patch || '').split('\n').filter(l => l.startsWith('-') && !l.startsWith('---'));

// Each failure gets an `id`, the numbers of the bot PRs merged after it (the only PRs that can be
// credited with fixing it), and `removed_by`: those of them whose diff removed a line containing the
// start of its error message. That is strong evidence the code that failed is gone.
// patches: PR number -> its full diff to the bot's files.
const attachCandidates = (failures, botPrs, patches = new Map()) =>
    failures.map((f, id) => {
        const candidates = botPrs.filter(p => new Date(p.merged_at) > new Date(f.at)).map(p => p.number);
        const key = messageKey(f.message);
        const removedBy = key ? candidates.filter(n => removedLines(patches.get(n)).some(l => l.includes(key))) : [];
        return { id, ...f, candidate_fixes: candidates, removed_by: removedBy };
    });

const PR_QUERY = `query($q:String!,$cursor:String){ search(query:$q, type:ISSUE, first:25, after:$cursor){
  pageInfo { hasNextPage endCursor }
  nodes { ... on PullRequest { number title url state merged
    reviews(last:50){ nodes { author { login } state submittedAt body } }
    reviewThreads(first:100){ nodes { isResolved isOutdated resolvedBy { login }
      comments(first:10){ nodes { author { login } body createdAt url } } } } } } } }`;

async function collect({ github, context, core, require, process }) {
    const { owner, repo } = context.repo;
    const days = parseDays(process.env.DAYS);
    const w = windows(Date.now(), days);
    const since = w.previous.start.toISOString();

    const runs = [];
    for (const workflow of WORKFLOWS) {
        const list = await github.paginate(github.rest.actions.listWorkflowRuns, { owner, repo, workflow_id: workflow, created: `>=${since}`, per_page: 100 });
        for (const r of list) {
            const run = { workflow, event: r.event, conclusion: r.conclusion, created_at: r.created_at, html_url: r.html_url, jobs: [] };
            if (r.conclusion !== 'skipped') {
                const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, { owner, repo, run_id: r.id, per_page: 100 });
                for (const j of jobs) {
                    let cause, message;
                    if (j.conclusion === 'failure') {
                        try {
                            const { data: notes } = await github.rest.checks.listAnnotations({ owner, repo, check_run_id: j.id, per_page: 50 });
                            const messages = notes.map(n => n.message || '');
                            cause = failureCause(messages);
                            // The first error, for matching against fixes. It can quote PR text, so it is untrusted.
                            message = (messages.find(x => /error/i.test(x)) || messages[0] || '').slice(0, 300);
                        } catch (e) {
                            core.warning(`Could not read the annotations of job ${j.id}: ${e.message}`);
                        }
                    }
                    run.jobs.push({ name: j.name, conclusion: j.conclusion, started_at: j.started_at, completed_at: j.completed_at, cause, message });
                }
            }
            runs.push(run);
        }
    }

    const prs = [];
    let cursor = null;
    for (;;) {
        const page = await github.graphql(PR_QUERY, { q: `repo:${owner}/${repo} is:pr updated:>=${since.slice(0, 10)}`, cursor });
        prs.push(...page.search.nodes.filter(n => n && n.number));
        if (!page.search.pageInfo.hasNextPage) break;
        cursor = page.search.pageInfo.endCursor;
    }

    // Merged PRs that touched the review bot, as candidate fixes for the failures.
    const fixes = new Map();
    for (const path of BOT_PATHS) {
        const commits = await github.paginate(github.rest.repos.listCommits, { owner, repo, path, since, per_page: 100 });
        for (const c of commits) {
            const { data: assoc } = await github.rest.repos.listPullRequestsAssociatedWithCommit({ owner, repo, commit_sha: c.sha });
            for (const p of assoc) {
                if (!p.merged_at || fixes.has(p.number)) continue;
                fixes.set(p.number, { number: p.number, title: p.title, url: p.html_url, merged_at: p.merged_at, body: (p.body || '').slice(0, 1500) });
            }
        }
    }
    const patches = new Map();
    for (const p of fixes.values()) {
        try {
            const files = await github.paginate(github.rest.pulls.listFiles, { owner, repo, pull_number: p.number, per_page: 100 });
            patches.set(p.number, botDiff(files));
            p.changes = botChanges(files);
        } catch (e) {
            core.warning(`Could not read the files of #${p.number}: ${e.message}`);
            p.changes = '';
        }
    }

    const current = { runs: summarizeRuns(runs, w.current), reviews: summarizeReviews(prs, w.current) };
    current.runs.failures = attachCandidates(current.runs.failures, [...fixes.values()], patches);
    const previous = { runs: summarizeRuns(runs, w.previous), reviews: summarizeReviews(prs, w.previous) };
    delete previous.reviews.prs;
    previous.runs.failures = previous.runs.failures.length;
    const stats = {
        days,
        window: { start: w.current.start.toISOString(), end: w.current.end.toISOString() },
        thresholds: THRESHOLDS,
        bot_prs: [...fixes.values()].sort((a, b) => a.number - b.number),
        alerts: checkThresholds(current),
        current,
        previous
    };
    require('fs').writeFileSync('stats.json', JSON.stringify(stats, null, 2));
    core.info(`Collected ${current.runs.total} runs and ${current.reviews.reviews} reviews; ${stats.alerts.length} alert(s).`);
}

module.exports = {
    THRESHOLDS,
    attachCandidates,
    botChanges,
    messageKey,
    parseDays,
    windows,
    failureCause,
    summarizeRuns,
    parseFindingHeader,
    threadOutcome,
    suggestionCount,
    summarizeReviews,
    checkThresholds,
    collect
};
