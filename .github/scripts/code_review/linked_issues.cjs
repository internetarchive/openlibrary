// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// The `analyze` job's "Fetch linked issues" step. Writes two files for the model:
// - pr-description.json: the PR's title and description, so it can check they match the diff.
// - linked-issues.json: the issues the PR links to. Follows PR-Agent's ticket_pr_compliance_check.py:
//   issues referenced in the PR body, then the branch name, then the title; this repo's issues only,
//   no pull requests; title, body, issue type and labels; at most 3 issues of 10,000 characters each.
'use strict';

// Issue numbers referenced in `text`, in order of appearance. Only this repo's issues count.
// Skipped, as in PR-Agent: HTML comments (the PR template's hints), a `#N` that is the whole
// text of a link (the link's target is what counts), a `#N` glued to a word or an `&` (`a#1`,
// `&#123;`), and a bare `#N` of more than 6 digits.
const findIssueNumbers = (text, owner, repo) => {
    const same = (o, r) => o.toLowerCase() === owner.toLowerCase() && r.toLowerCase() === repo.toLowerCase();
    const t = String(text || '')
        .replace(/<!--[\s\S]*?(-->|$)/g, ' ')
        .replace(/\[\s*#\d+\s*\](?=[([])/g, '[]')
        .replace(/(<a\b[^<>]*>)\s*#\d+\s*(<\/a\s*>)/gi, '$1$2');
    const re =
        /(?<![\w@/])https:\/\/github\.com\/([A-Za-z0-9-]+)\/([A-Za-z0-9._-]+)\/issues\/0*([1-9]\d{0,8})(?![\w-]|\/[\w-])|(?<![\w./-])([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\/([A-Za-z0-9._-]+)#(\d{1,9})\b|(?<![\w&])#(\d{1,6})(?!\d)\b/g;
    const out = [];
    for (const m of t.matchAll(re)) {
        let n = null;
        if (m[3]) {
            if (same(m[1], m[2])) n = Number(m[3]);
        } else if (m[6]) {
            if (same(m[4], m[5])) n = Number(m[6]);
        } else n = Number(m[7]);
        if (n > 0 && !out.includes(n)) out.push(n);
    }
    return out;
};
// The issue number a branch name starts with. PR-Agent's default pattern (`123-fix`,
// `feature/123-fix`, not a `2026-11` date) plus this repo's `{issue}/{type}/{slug}` convention.
const branchIssueNumbers = branch => {
    const out = [];
    const b = String(branch || '');
    const ours = /^(\d{1,6})\//.exec(b);
    if (ours) out.push(Number(ours[1]));
    for (const m of b.matchAll(/(?:^|\/)(?!(?:19|20)\d\d-(?:0[1-9]|1[0-2])(?:[-/._]|$))(\d{1,6})(?=-|$)/g)) {
        const n = Number(m[1]);
        if (n > 0 && !out.includes(n)) out.push(n);
    }
    return out;
};

async function fetchLinkedIssues({ github, context, core, require, process }) {
    const fs = require('node:fs');
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const prNumber = Number(process.env.PR);
    // PR-Agent's MAX_GITHUB_TICKETS, MAX_GITHUB_TICKET_LOOKUPS and MAX_TICKET_CHARACTERS.
    const MAX_TICKETS = 3,
        MAX_LOOKUPS = 30,
        MAX_CHARS = 10000;

    // HTML comments are template hints, not content. Dropped to save the budget.
    const clean = text => {
        const t = String(text || '')
            .replace(/<!--[\s\S]*?(-->|$)/g, '')
            .trim();
        return t.length > MAX_CHARS ? `${t.slice(0, MAX_CHARS)}...` : t;
    };

    let pr = null;
    try {
        ({ data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber }));
    } catch (e) {
        core.info(`Could not read the PR (${e.message}) -- reviewing without its description or linked issues.`);
    }
    const description = pr ? { title: String(pr.title || ''), body: clean(pr.body) } : null;
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/pr-description.json`, JSON.stringify(description, null, 2));

    const tickets = [];
    if (process.env.TICKET_ANALYSIS === 'false') core.info('Ticket analysis is turned off in .pr_agent.toml.');
    else if (pr)
        try {
            const candidates = [];
            for (const n of [
                ...findIssueNumbers(pr.body, owner, repo),
                ...branchIssueNumbers(pr.head && pr.head.ref),
                ...findIssueNumbers(pr.title, owner, repo)
            ]) {
                if (!candidates.includes(n)) candidates.push(n);
            }
            const prefix = `https://github.com/${owner}/${repo}/issues/`.toLowerCase();
            for (const n of candidates.slice(0, MAX_LOOKUPS)) {
                if (tickets.length >= MAX_TICKETS) break;
                let issue;
                try {
                    ({ data: issue } = await github.rest.issues.get({ owner, repo, issue_number: n }));
                } catch (e) {
                    core.info(`Could not read #${n} (${e.status || e.message}) -- skipping it.`);
                    continue;
                }
                // A `#N` that is a pull request, or an issue since moved to another repo, is not ticket context.
                if (
                    !issue ||
                    issue.pull_request ||
                    !String(issue.html_url || '')
                        .toLowerCase()
                        .startsWith(prefix)
                )
                    continue;
                const body = clean(issue.body);
                tickets.push({
                    ticket_id: issue.number,
                    ticket_url: `https://github.com/${owner}/${repo}/issues/${issue.number}`,
                    title: String(issue.title || ''),
                    body,
                    type: (issue.type && issue.type.name) || null,
                    labels: (issue.labels || []).map(l => (typeof l === 'string' ? l : l && l.name)).filter(Boolean)
                });
            }
        } catch (e) {
            core.info(`Could not look up linked issues (${e.message}) -- reviewing without them.`);
        }
    fs.writeFileSync(`${process.env.GITHUB_WORKSPACE}/linked-issues.json`, JSON.stringify(tickets, null, 2));
    core.info(`Linked issues for the review: ${tickets.length ? tickets.map(t => `#${t.ticket_id}`).join(', ') : 'none'}.`);
}

module.exports = { fetchLinkedIssues, findIssueNumbers, branchIssueNumbers };
