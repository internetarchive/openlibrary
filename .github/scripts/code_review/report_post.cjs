// The weekly report's `publish` job: writes the report to the run summary every time, and opens an
// issue (or comments on the open one) only when something needs attention. It runs no model. The
// model's text is checked and its @-mentions defused; the title, labels and highlights come from here.
'use strict';

const BOT = 'openlibrary-bot';
const TITLE_PREFIX = 'Review bot weekly report';
const LABELS = ['Theme: Bots', 'Needs: Triage'];
const MAX_MARKDOWN = 20000;
const MAX_ITEMS = 5;
const MAX_ITEM = 500;

const str = (x, n) => typeof x === 'string' && x.trim().length > 0 && x.length <= n;

// report.json as the model wrote it, or null if it is missing or not the expected shape.
const parseReport = raw => {
    let r;
    try {
        r = JSON.parse(raw);
    } catch {
        return null;
    }
    if (!r || typeof r !== 'object' || !str(r.markdown, MAX_MARKDOWN) || typeof r.needs_attention !== 'boolean') return null;
    for (const k of ['reasons', 'follow_ups']) {
        if (!Array.isArray(r[k]) || r[k].length > MAX_ITEMS || !r[k].every(x => str(x, MAX_ITEM))) return null;
    }
    return { markdown: r.markdown, needs_attention: r.needs_attention, reasons: r.reasons, follow_ups: r.follow_ups };
};

// So the model's text can't ping a person or team, or close an issue.
const defuse = s => s.replace(/@(?=[A-Za-z0-9_-])/g, '@​').replace(/\b(close[sd]?|fix(e[sd])?|resolve[sd]?)(\s+)#/gi, '$1$3#​');

const fmtSeconds = s => (s === null || s === undefined ? '–' : s >= 90 ? `${Math.round(s / 60)} min` : `${s}s`);
const pct = x => `${Math.round(x * 100)}%`;
const autoResolved = r => ['fixed', 'dismissed', 'resolved_by_bot'].reduce((n, k) => n + (r.reviews.outcomes[k] || 0), 0);

// The few numbers worth a glance, this period against the one before.
const highlights = stats => {
    const c = stats.current,
        p = stats.previous;
    const a = r => (r.runs.jobs.analyze ? r.runs.jobs.analyze.median_seconds : null);
    const rows = [
        ['Reviews posted', c.reviews.reviews, p.reviews.reviews],
        ['PRs reviewed', c.reviews.prs_reviewed, p.reviews.prs_reviewed],
        ['Blocking findings', c.reviews.blocking_findings, p.reviews.blocking_findings],
        ['Suggestions (non-blocking)', c.reviews.suggestions, p.reviews.suggestions],
        ['Findings acted on', `${c.reviews.acted_on} of ${c.reviews.threads}`, `${p.reviews.acted_on} of ${p.reviews.threads}`],
        ['Threads the bot resolved itself', autoResolved(c), autoResolved(p)],
        ['Failed runs', `${c.runs.failure} (${pct(c.runs.failure_rate)})`, `${p.runs.failure} (${pct(p.runs.failure_rate)})`],
        ['Median review time (analyze)', fmtSeconds(a(c)), fmtSeconds(a(p))]
    ];
    return ['| | This period | Previous |', '|---|---|---|', ...rows.map(r => `| ${r.join(' | ')} |`)].join('\n');
};

const fullTables = stats => {
    const c = stats.current;
    const jobs = Object.entries(c.runs.jobs).map(
        ([n, j]) => `| ${n} | ${j.count} | ${j.failed} | ${fmtSeconds(j.median_seconds)} | ${fmtSeconds(j.max_seconds)} |`
    );
    const failures = c.runs.failures.map(f => `- \`${f.job}\` (${f.cause}) in ${f.workflow}: [run](${f.run_url})`);
    const prs = c.reviews.prs.map(
        p =>
            `| [#${p.number}](${p.url}) | ${p.state} | ${p.reviews} | ${p.findings.map(f => `${f.severity} ${f.dimension}: ${f.outcome}`).join('<br>') || '–'} |`
    );
    const counts = o =>
        Object.entries(o)
            .map(([k, v]) => `${k} ${v}`)
            .join(', ') || '–';
    return [
        '### Jobs',
        '| Job | Ran | Failed | Median | Max |',
        '|---|---|---|---|---|',
        ...jobs,
        '',
        '### Failures',
        failures.length ? failures.join('\n') : 'None.',
        '',
        '### Findings',
        `- By type: ${counts(c.reviews.by_dimension)}`,
        `- By severity: ${counts(c.reviews.by_severity)}`,
        `- Outcomes: ${counts(c.reviews.outcomes)}`,
        `- Review states: ${counts(c.reviews.states)}`,
        '',
        '### PRs',
        '| PR | State | Reviews | Findings |',
        '|---|---|---|---|',
        ...prs
    ].join('\n');
};

const period = stats => `${stats.window.start.slice(0, 10)} to ${stats.window.end.slice(0, 10)}`;

function render({ stats, report, runUrl }) {
    const why = stats.alerts.map(a => `- ⚠️ ${a}`);
    if (!report) why.push('- ⚠️ The report job failed or wrote an invalid report, so only the numbers are below.');
    else if (report.needs_attention) why.push(...report.reasons.map(r => `- ${defuse(r)}`));
    const narrative = report ? defuse(report.markdown) : '';
    const followUps = report && report.follow_ups.length ? `\n\n## Suggested follow-ups\n\n${report.follow_ups.map(f => `- ${defuse(f)}`).join('\n')}` : '';
    const open = why.length > 0;
    const head = `How the code review bot did from ${period(stats)}.`;
    const issue = [
        head,
        '\n## Why this opened\n',
        why.join('\n'),
        '\n## Highlights\n',
        highlights(stats),
        narrative ? `\n## Report\n\n${narrative}` : '',
        followUps,
        `\n\nFull stats: [workflow run summary](${runUrl}).`
    ].join('\n');
    const summary = [
        `# ${TITLE_PREFIX}`,
        head,
        open ? `\n**Needs attention:**\n${why.join('\n')}` : '\nNothing needs attention.',
        '\n## Highlights\n',
        highlights(stats),
        narrative ? `\n## Report\n\n${narrative}` : '',
        followUps,
        '\n## Details\n',
        fullTables(stats)
    ].join('\n');
    return { open, issue, summary, title: `${TITLE_PREFIX}: ${period(stats)} needs attention` };
}

async function publish({ github, context, core, require, process }) {
    const fs = require('fs');
    const stats = JSON.parse(fs.readFileSync('stats.json', 'utf8'));
    const report = fs.existsSync('report.json') ? parseReport(fs.readFileSync('report.json', 'utf8')) : null;
    const { open, issue, summary, title } = render({ stats, report, runUrl: process.env.RUN_URL });
    await core.summary.addRaw(summary).write();

    if (!open) return core.info('Nothing needs attention; no issue.');
    if (process.env.EVENT !== 'schedule' && process.env.DRY_RUN !== 'false') return core.info('Dry run: an issue would have opened.');

    const { owner, repo } = context.repo;
    const existing = (
        await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: 'open', creator: BOT, labels: LABELS[0], per_page: 100 })
    ).find(i => !i.pull_request && i.title.startsWith(TITLE_PREFIX));
    if (existing) {
        await github.rest.issues.createComment({ owner, repo, issue_number: existing.number, body: `## ${title}\n\n${issue}` });
        return core.info(`Commented on #${existing.number}.`);
    }
    const { data } = await github.rest.issues.create({ owner, repo, title, body: issue, labels: LABELS });
    core.info(`Opened #${data.number}.`);
}

module.exports = { TITLE_PREFIX, LABELS, parseReport, defuse, highlights, render, publish };
