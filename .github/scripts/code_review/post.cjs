// The `post` job: re-fetches the reviewed diff, runs gate.cjs again, and posts one batched review.
// It publishes nothing the gate rejects, whatever `analyze` uploaded.
'use strict';

const gate = require('./gate.cjs');
const { headIsCurrent } = require('./shared.cjs');

// The review's verdict. Only APPROVE or REQUEST_CHANGES clears a pending review request; COMMENT
// leaves it pending. Findings request changes. A clean review approves only when none of the bot's
// own threads is still open, so it never approves while the status is red; an unknown (null)
// count gives COMMENT. GitHub rejects (422) a verdict on your own PR, so the bot's PRs get COMMENT.
const selectReviewEvent = ({ selfAuthored, findingCount, unresolvedOwnThreads }) => {
    if (selfAuthored) return 'COMMENT';
    if (findingCount > 0) return 'REQUEST_CHANGES';
    if (unresolvedOwnThreads !== 0) return 'COMMENT';
    return 'APPROVE';
};

// A COMMENT on the bot's own PR doesn't clear the team's review request, so `post` removes it.
const shouldDismissTeamRequest = ({ selfAuthored, event }) => {
    return selfAuthored && event === 'COMMENT';
};

// On a re-review, the threads the model listed as fixed (review.resolved) that are still open and
// were started by the bot. An id the model invents, or a human's thread, is never touched.
const threadsToResolve = ({ threads, resolvedIds, botLogin }) => {
    const want = new Set(resolvedIds || []);
    const out = [];
    for (const t of threads || []) {
        if (!t || t.isResolved || !want.has(t.id)) continue;
        const c = t.comments && t.comments.nodes && t.comments.nodes[0];
        if (!c || !c.author || c.author.login !== botLogin) continue;
        out.push(t.id);
    }
    return out;
};

// The commit to credit in the "Fixed in" reply: the newest commit in this run's range that touched
// the thread's file (the fix is usually there), else the reviewed head. rangeShas is newest-first.
const fixedInSha = ({ rangeShas, pathShas, headSha }) => {
    const inRange = new Set(rangeShas || []);
    for (const sha of pathShas || []) if (inRange.has(sha)) return sha;
    return headSha;
};

// The ticket compliance section, as PR-Agent's ticket_markdown_logic (pr_agent/algo/utils.py)
// renders it. Each issue's level is computed from the model's lists, not chosen by the model.
// Only this repo's issues are shown. It does not affect the verdict or the status.
const renderTicketCompliance = (entries, owner, repo) => {
    const prefix = `https://github.com/${owner}/${repo}/issues/`.toLowerCase();
    const bullets = list => list.map(s => `- ${String(s).replace(/\s*\n\s*/g, ' ')}`).join('\n');
    const levels = [];
    let out = '';
    for (const t of entries || []) {
        if (!String(t.ticket_url).toLowerCase().startsWith(prefix)) continue;
        const met = t.fully_compliant_requirements,
            notMet = t.not_compliant_requirements,
            human = t.requires_further_human_verification;
        if (!met.length && !notMet.length && !human.length) continue;
        const level = met.length
            ? notMet.length
                ? 'Partially compliant'
                : human.length
                  ? 'PR Code Verified'
                  : 'Fully compliant'
            : notMet.length
              ? 'Not compliant'
              : 'PR Code Verified';
        levels.push(level);
        out += `\n\n**[#${t.ticket_url.split('/').pop()}](${t.ticket_url}) - ${level}**`;
        if (met.length) out += `\n\nCompliant requirements:\n\n${bullets(met)}`;
        if (notMet.length) out += `\n\nNon-compliant requirements:\n\n${bullets(notMet)}`;
        if (human.length) out += `\n\nRequires further human verification:\n\n${bullets(human)}`;
    }
    if (!levels.length) return '';
    // Overall, as in PR-Agent: any mix of Fully compliant and PR Code Verified passes.
    let mark = '✅';
    if (levels.includes('Not compliant')) mark = levels.every(l => l === 'Not compliant') ? '❌' : '🔶';
    else if (levels.includes('Partially compliant')) mark = '🔶';
    return `\n\n### 🎫 Ticket compliance analysis ${mark}${out}`;
};

async function refetchDiff({ github, context, core, require, process }) {
    const sha = /^[0-9a-f]{40}$/;
    const { BASE_SHA: base, HEAD_SHA: head } = process.env;
    if (!sha.test(base) || !sha.test(head)) {
        core.setFailed('Unexpected review range.');
        return;
    }
    const { data: diff } = await github.rest.repos.compareCommitsWithBasehead({
        owner: context.repo.owner,
        repo: context.repo.repo,
        basehead: `${base}...${head}`,
        headers: { accept: 'application/vnd.github.v3.diff' }
    });
    require('fs').writeFileSync('review.diff', diff);
}

async function validateAndPost({ github, context, core, require, process }) {
    const fs = require('fs');
    const owner = context.repo.owner,
        repo = context.repo.repo;
    const prNumber = Number(process.env.PR);
    const headSha = process.env.HEAD_SHA;
    const inlineKeyIssues = process.env.INLINE_KEY_ISSUES !== 'false';

    // Nothing below runs unless the gate passes.
    let review = null;
    try {
        review = JSON.parse(fs.readFileSync('review.json', 'utf8'));
    } catch (e) {
        review = null;
    }
    const verdict = gate.check(review);
    if (!verdict.publish) {
        // Return without failing: the status job decides pass or fail from analyze's outputs. Log no
        // reason, count or text, because the log is public.
        core.info('Nothing public to post for this commit; the code-review status job decides the gate.');
        return;
    }
    // Everything below renders from the allowlisted copy only.
    review = verdict.clean;

    // Lines a comment can anchor to: the right side (added and context lines) of the diff.
    // GitHub doesn't document what happens with an anchor outside the diff, so findings with one
    // go in the summary instead.
    const anchorable = new Map();
    {
        let file = null,
            newLn = 0;
        for (const raw of fs.readFileSync('review.diff', 'utf8').split('\n')) {
            if (raw.startsWith('+++ ')) {
                const p = raw.slice(4).trim();
                file = p === '/dev/null' ? null : p.replace(/^b\//, '');
                if (file) anchorable.set(file, new Set());
                continue;
            }
            const h = raw.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
            if (h) {
                newLn = Number(h[1]);
                continue;
            }
            if (!file) continue;
            if (raw.startsWith('+') || raw.startsWith(' ')) {
                anchorable.get(file).add(newLn++);
            }
        }
    }

    // Low severity findings are listed as suggestions in the summary, not as threads, which block.
    const inline = [],
        orphaned = [],
        suggestions = [];
    for (const f of review.findings || []) {
        if (f.severity === 'low') {
            suggestions.push(f);
            continue;
        }
        // .pr_agent.toml inline_key_issues = false keeps every finding in the review summary.
        if (!inlineKeyIssues) {
            orphaned.push(f);
            continue;
        }
        const hasAnchor = f.path && f.line;
        const start = f.start_line || f.line;
        const ok =
            hasAnchor &&
            anchorable.has(f.path) &&
            anchorable.get(f.path).has(Number(f.line)) &&
            anchorable.get(f.path).has(Number(start)) &&
            Number(start) <= Number(f.line);
        if (!ok) {
            orphaned.push(f);
            continue;
        }

        let body = `**${(f.severity || 'note').toUpperCase()} · ${gate.dimensions[f.dimension]} — ${f.title}**\n\n${f.body}`;
        // oxlint-disable-next-line eqeqeq -- loose on purpose: null or undefined
        if (f.suggestion != null) {
            // A suggestion must replace exactly start..line or it cannot be applied.
            const want = Number(f.line) - Number(start) + 1;
            const got = String(f.suggestion).split('\n').length;
            if (want === got) body += `\n\n\`\`\`suggestion\n${f.suggestion}\n\`\`\``;
            else core.warning(`Dropped suggestion on ${f.path}:${start}-${f.line} (${got} lines for a ${want}-line range).`);
        }
        const c = { path: f.path, line: Number(f.line), side: 'RIGHT', body };
        if (Number(start) !== Number(f.line)) {
            c.start_line = Number(start);
            c.start_side = 'RIGHT';
        }
        inline.push(c);
    }

    // Summary. Findings without a valid anchor go here rather than on an approximate line.
    const findingCount = inline.length + orphaned.length; // blocking findings only (LOW excluded)
    let summary = review.summary || '';
    // The range comes from analyze's job outputs, set before the model ran.
    const sha = /^[0-9a-f]{40}$/,
        baseSha = process.env.BASE_SHA;
    if (process.env.INCREMENTAL === 'true' && sha.test(baseSha) && sha.test(headSha)) {
        summary = `*Reviewing only the ${baseSha.slice(0, 8)}..${headSha.slice(0, 8)} range — the commits pushed since my last pass.*\n\n${summary}`;
    }

    summary += renderTicketCompliance(review.ticket_compliance, owner, repo);

    // State every dimension, because leaving one out reads the same as having checked it.
    // Security is a fixed line: a review with a security finding never gets this far.
    const count = {};
    for (const f of review.findings) count[f.dimension] = (count[f.dimension] || 0) + 1;
    summary += `\n\n### Dimensions\n\n${Object.entries(gate.dimensions)
        .map(([k, label]) => {
            if (k === 'security') return `- **${label}** — no findings in this range. This is not a security audit.`;
            if (count[k]) return `- **${label}** — ${count[k]} finding${count[k] === 1 ? '' : 's'}`;
            return `- **${label}** — no findings. ${review.dimensions[k].note}`;
        })
        .join('\n')}`;

    if (orphaned.length) {
        summary += `\n\n### ${inlineKeyIssues ? 'Findings without an in-diff anchor' : 'Findings'}\n\n${orphaned
            .map(
                f =>
                    `- **${(f.severity || 'note').toUpperCase()} · ${gate.dimensions[f.dimension]} — ${f.title}**${f.path && anchorable.has(f.path) ? ` (\`${f.path}\`)` : ''}\n  ${String(f.body).replace(/\n/g, '\n  ')}`
            )
            .join('\n\n')}`;
    }
    if (suggestions.length) {
        summary += `\n\n### Suggestions (won't block)\n\n${suggestions
            .map(f => `- **${f.title}**${f.path ? ` (\`${f.path}${f.line ? `:${f.line}` : ''}\`)` : ''}: ${String(f.body).replace(/\n/g, ' ')}`)
            .join('\n')}`;
    }
    // A contributor without write access can't re-request a review, but can comment.
    summary += `\n\n---\n> [!TIP]\n> When you've addressed the feedback and pushed your changes, comment \`@openlibrary-bot review\` on this PR to run a fresh review.`;
    summary += `\n\n> [!NOTE]\n> Automated review by [@openlibrary-bot](https://github.com/internetarchive/openlibrary/blob/master/.github/workflows/code_review.md) on behalf of @mekarpeles. This is **not** an approval or a sign-off, and it does not satisfy a required review.\n\n<!-- ol-pr-review-bot f=${findingCount} -->`;

    // If the head moved since the review, post nothing (see headIsCurrent).
    const { data: livePr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    if (!headIsCurrent(headSha, livePr.head.sha)) {
        core.info(
            `Head moved ${headSha.slice(0, 8)}->${String(livePr.head.sha).slice(0, 8)} since this review was pinned; not posting. The new head earns its own run.`
        );
        return;
    }

    const selfAuthored = (livePr.user && livePr.user.login) === 'openlibrary-bot';

    // Before posting, because it decides the verdict: reply "Fixed in <sha>" on the bot's threads
    // the model judged fixed, resolve them, and count the bot's threads still open. A GraphQL error
    // must not fail the post; it leaves the count null, which means no APPROVE.
    let unresolvedOwnThreads = null;
    try {
        let allThreads = [],
            tCursor = null;
        for (;;) {
            const page = await github.graphql(
                `query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
             repository(owner:$owner,name:$repo){
               pullRequest(number:$pr){
                 reviewThreads(first:100, after:$cursor){
                   nodes { id isResolved isOutdated path line comments(first:1){ nodes { author { login } body } } }
                   pageInfo { hasNextPage endCursor }
                 }
               }
             }
           }`,
                { owner, repo, pr: prNumber, cursor: tCursor }
            );
            const rt = page.repository.pullRequest.reviewThreads;
            allThreads = allThreads.concat(rt.nodes);
            if (!rt.pageInfo.hasNextPage) break;
            tCursor = rt.pageInfo.endCursor;
        }
        const toResolve = threadsToResolve({ threads: allThreads, resolvedIds: review.resolved, botLogin: 'openlibrary-bot' });
        // Commits in the reviewed range, newest first, for the "Fixed in" reply.
        let rangeShas = [];
        if (toResolve.length) {
            try {
                const { data: cmp } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${baseSha}...${headSha}` });
                rangeShas = (cmp.commits || []).map(c => c.sha).reverse();
            } catch (e) {
                core.warning(`Could not list the reviewed commits: ${e.message}`);
            }
        }
        const pathOf = new Map(allThreads.filter(Boolean).map(t => [t.id, t.path]));
        const resolvedOk = new Set();
        for (const id of toResolve) {
            let sha = headSha;
            try {
                const path = pathOf.get(id);
                if (path && rangeShas.length) {
                    const { data: touching } = await github.rest.repos.listCommits({ owner, repo, sha: headSha, path, per_page: 30 });
                    sha = fixedInSha({ rangeShas, pathShas: (touching || []).map(c => c.sha), headSha });
                }
            } catch (e) {
                core.warning(`Could not find the commit that fixed thread ${id}: ${e.message}`);
            }
            try {
                await github.graphql(
                    `mutation($id:ID!,$body:String!){ addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$id, body:$body}){ comment { id } } }`,
                    { id, body: `Fixed in ${sha}.` }
                );
            } catch (e) {
                core.warning(`Could not reply on review thread ${id}: ${e.message}`);
            }
            try {
                await github.graphql(`mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread { id isResolved } } }`, { id });
                resolvedOk.add(id);
            } catch (e) {
                core.warning(`Could not resolve review thread ${id}: ${e.message}`);
            }
        }
        if (resolvedOk.size) core.info(`Resolved ${resolvedOk.size} fixed review thread(s).`);
        // Counted the way the status job counts, limited to the bot's threads. A thread whose
        // resolve failed still counts, so it blocks APPROVE.
        unresolvedOwnThreads = allThreads.filter(t => {
            if (!t || t.isResolved || t.isOutdated || resolvedOk.has(t.id)) return false;
            const c = t.comments && t.comments.nodes && t.comments.nodes[0];
            return !!(c && c.author && c.author.login === 'openlibrary-bot');
        }).length;
    } catch (e) {
        core.warning(`Thread enumeration failed; skipping resolution and not auto-approving: ${e.message}`);
    }

    // A human's open thread doesn't stop APPROVE, though it keeps the status red. The status, not
    // the verdict, is what merging requires.
    let event = selectReviewEvent({ selfAuthored, findingCount, unresolvedOwnThreads });

    // One batched review. POST /pulls/{n}/comments returns 422 `pull_request_review_thread.base`
    // in practice (cli/cli#13358), while the same anchors in a batched review work. If a verdict
    // is rejected with 422 anyway, fall back to COMMENT rather than fail.
    const postReview = ev =>
        github.rest.pulls.createReview({
            owner,
            repo,
            pull_number: prNumber,
            commit_id: headSha,
            event: ev,
            body: summary,
            comments: inline
        });
    let posted;
    try {
        ({ data: posted } = await postReview(event));
    } catch (e) {
        if (event !== 'COMMENT' && e && e.status === 422) {
            core.warning(`Verdict ${event} was rejected (422); posting as COMMENT instead.`);
            event = 'COMMENT';
            ({ data: posted } = await postReview(event));
        } else {
            throw e;
        }
    }

    // This API has returned 2xx without changing anything (pr_autoresponder.md, Step 4), so check.
    const after = await github.paginate(github.rest.pulls.listReviews, {
        owner,
        repo,
        pull_number: prNumber,
        per_page: 100
    });
    if (!after.some(r => r.id === posted.id)) {
        core.setFailed(`createReview returned ${posted.id} but it is not present on the PR.`);
        return;
    }
    core.info(`Posted ${event} review ${posted.id}: ${inline.length} inline, ${orphaned.length} in summary.`);

    // See shouldDismissTeamRequest. Never fails the job.
    if (shouldDismissTeamRequest({ selfAuthored, event })) {
        try {
            await github.rest.pulls.removeRequestedReviewers({
                owner,
                repo,
                pull_number: prNumber,
                reviewers: [],
                team_reviewers: ['openlibrary-agentic-code-reviewer']
            });
            core.info('Dismissed the pending team review request (bot-authored PR, COMMENT posted).');
        } catch (e) {
            core.warning(`Could not dismiss the team review request: ${e.message}`);
        }
    }
}

module.exports = { refetchDiff, validateAndPost, selectReviewEvent, shouldDismissTeamRequest, threadsToResolve, fixedInSha, renderTicketCompliance };
