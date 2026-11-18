// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// The `post` job: re-fetches the reviewed diff, runs gate.cjs again, and posts one batched review.
// It publishes nothing the gate rejects, whatever `analyze` uploaded.
'use strict';

const gate = require('./gate.cjs');
const { filterDiff, headIsCurrent, supersededMarker, supersededCommit, reviewMarker, heldBackOpen } = require('./shared.cjs');

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

// The commit to credit in the "Addressed in" note: the newest commit in this run's range that touched
// the thread's file (the fix is usually there), else the reviewed head. rangeShas is newest-first.
const fixedInSha = ({ rangeShas, pathShas, headSha }) => {
    const inRange = new Set(rangeShas || []);
    for (const sha of pathShas || []) if (inRange.has(sha)) return sha;
    return headSha;
};

// The collapsed "Prompt for AI agents" block under a finding, for a reader to paste into a coding
// agent. Only the gate's clean fields: no PR text, which could carry instructions for that agent.
const agentPrompt = (f, inThread) => {
    const where = f.path ? ` At \`${f.path}\`${f.line ? `, line \`${f.line}\`` : ''}:` : '';
    const reply = inThread ? 'reply in its thread with the reason and resolve the thread' : 'say why in a comment on the PR';
    const text = `Check if this issue is valid — if so, understand the root cause and fix it. If it isn't valid or won't be fixed in this PR, ${reply}.${where}\n\n<comment>${f.title}\n\n${f.body}</comment>`;
    // A fence longer than any run of backticks inside, so the text can't close it.
    const fence = '`'.repeat(Math.max(3, ...(text.match(/`+/g) || []).map(run => run.length + 1)));
    return `\n\n<details>\n<summary>Prompt for AI agents</summary>\n\n${fence}text\n${text}\n${fence}\n\n</details>`;
};

// ` · `path:line`` after a finding's title in the summary, when it has a path.
const location = f => (f.path ? ` · \`${f.path}${f.line ? `:${f.line}` : ''}\`` : '');

// One collapsed "Prompt for AI agents" block in the summary covering every published finding, in
// the shape Cubic uses, so a reader can hand them all to a coding agent at once. Gate fields only.
const combinedAgentPrompt = findings => {
    if (!findings.length) return '';
    const byFile = new Map();
    for (const f of findings) {
        const key = f.path || '';
        if (!byFile.has(key)) byFile.set(key, []);
        byFile.get(key).push(f);
    }
    const item = f => `<item${f.line ? ` location="${f.line}"` : ''}>${f.title}: ${String(f.body).replace(/\s*\n\s*/g, ' ')}</item>`;
    const files = [...byFile].map(([path, fs]) => (path ? `<file name="${path}">\n${fs.map(item).join('\n')}\n</file>` : fs.map(item).join('\n')));
    const text = `Check if each issue is valid — if so, understand the root cause and fix it. If one isn't valid or won't be fixed in this PR, say why in its thread, or in a comment on the PR if it has none.\n\n${files.join('\n\n')}`;
    // A fence longer than any run of backticks inside, so the text can't close it.
    const fence = '`'.repeat(Math.max(3, ...(text.match(/`+/g) || []).map(run => run.length + 1)));
    return `\n\n<details>\n<summary>Prompt for AI agents (${findings.length} open item${findings.length === 1 ? '' : 's'})</summary>\n\n${fence}text\n${text}\n${fence}\n\n</details>`;
};

// The line a re-review's summary opens with: what happened to the bot's earlier threads.
const threadStateLine = ({ addressed, dismissed, open }) => {
    const parts = [];
    if (addressed) parts.push(`${addressed} addressed`);
    if (dismissed) parts.push(`${dismissed} dismissed`);
    if (open) parts.push(`${open} still open`);
    if (!parts.length) return '';
    return `${open ? '' : '✅ '}Earlier findings: ${parts.join(', ')}.`;
};

// The ticket compliance section, as PR-Agent's ticket_markdown_logic (pr_agent/algo/utils.py)
// renders it. Each issue's level is computed from the model's lists, not chosen by the model.
// Only this repo's issues are shown. It does not affect the verdict or the status.
const MARKS = { 'Fully compliant': '✅', 'PR Code Verified': '✅', 'Partially compliant': '🔶', 'Not compliant': '❌' };
const renderTicketCompliance = (entries, owner, repo) => {
    const prefix = `https://github.com/${owner}/${repo}/issues/`.toLowerCase();
    const bullets = list => list.map(s => `- ${String(s).replace(/\s*\n\s*/g, ' ')}`).join('\n');
    const levels = [],
        heads = [];
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
        const n = t.ticket_url.split('/').pop();
        heads.push(`#${n} ${MARKS[level]}`);
        out += `\n\n**[#${n}](${t.ticket_url}) - ${level}**`;
        if (met.length) out += `\n\nCompliant requirements:\n\n${bullets(met)}`;
        if (notMet.length) out += `\n\nNon-compliant requirements:\n\n${bullets(notMet)}`;
        if (human.length) out += `\n\nRequires further human verification:\n\n${bullets(human)}`;
    }
    if (!levels.length) return '';
    // Overall, as in PR-Agent: any mix of Fully compliant and PR Code Verified passes.
    let mark = '✅';
    if (levels.includes('Not compliant')) mark = levels.every(l => l === 'Not compliant') ? '❌' : '🔶';
    else if (levels.includes('Partially compliant')) mark = '🔶';
    // Collapsed: one line names each issue and its level, the requirements are folded underneath.
    return `\n\n<details>\n<summary>🎫 Linked issues ${mark}: ${heads.join(' · ')}</summary>${out}\n\n</details>`;
};

async function refetchDiff({ github, context, core, require, process }) {
    const sha = /^[0-9a-f]{40}$/;
    const { BASE_SHA: base, HEAD_SHA: head, FILES: files } = process.env;
    let paths = null;
    try {
        paths = files ? JSON.parse(files) : null;
    } catch (e) {
        paths = undefined;
    }
    const pathsOk = paths === null || (Array.isArray(paths) && paths.every(p => typeof p === 'string'));
    if (!sha.test(base) || !sha.test(head) || !pathsOk) {
        core.setFailed('Unexpected review range.');
        return;
    }
    const { data: diff } = await github.rest.repos.compareCommitsWithBasehead({
        owner: context.repo.owner,
        repo: context.repo.repo,
        basehead: `${base}...${head}`,
        headers: { accept: 'application/vnd.github.v3.diff' }
    });
    // A re-review covers only the files analyze listed, before the model ran.
    require('fs').writeFileSync('review.diff', paths ? filterDiff(diff, paths) : diff);
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
    const verdict = gate.check(review, fs.readFileSync('review.diff', 'utf8'));
    if (!verdict.publish) {
        // Return without failing: the status job decides pass or fail from analyze's outputs. Log no
        // reason, count or text, because the log is public.
        core.info('Nothing public to post for this commit; the code-review status job decides the gate.');
        return;
    }
    // analyze already took out anything held back, so the gate must hold back nothing more. If it
    // would (this diff differs from analyze's), post nothing: `status` doesn't know about it.
    if (verdict.heldBack) {
        core.setFailed('The review did not pass the gate again; not posting.');
        return;
    }
    // Everything below renders from the allowlisted copy only.
    review = verdict.clean;
    // From analyze's gate: whether part of the review was held back, and whether that part blocks.
    const heldBack = process.env.HELD_BACK === 'true';
    const heldBackBlocks = heldBack && process.env.WITHHELD_BLOCKING === 'true';

    // Lines a comment can anchor to: the right side (added and context lines) of the diff.
    // GitHub doesn't document what happens with an anchor outside the diff, so findings with one
    // go in the summary instead.
    const anchorable = new Map();
    {
        let file = null,
            newLn = 0;
        for (const raw of fs.readFileSync('review.diff', 'utf8').split(/\r?\n/)) {
            if (raw.startsWith('+++ ')) {
                const p = raw.slice(4).trim();
                file = p === '/dev/null' ? null : p.replace(/^b\//, '');
                if (file) anchorable.set(file, new Map());
                continue;
            }
            const h = raw.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
            if (h) {
                newLn = Number(h[1]);
                continue;
            }
            if (!file) continue;
            if (raw.startsWith('+') || raw.startsWith(' ')) {
                anchorable.get(file).set(newLn++, raw.slice(1));
            }
        }
    }

    // Low severity findings are listed as suggestions in the summary, not as threads, which block.
    const inline = [],
        inlineFindings = [],
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
            // A suggestion must replace exactly start..line, and change something, or it is no use.
            const want = Number(f.line) - Number(start) + 1;
            const got = String(f.suggestion).split('\n').length;
            const current = Array.from({ length: want }, (_, i) => anchorable.get(f.path).get(Number(start) + i)).join('\n');
            // Longer than any backtick run inside, so the suggestion can't close the fence.
            const fence = '`'.repeat(Math.max(2, ...(f.suggestion.match(/`+/g) || []).map(r => r.length)) + 1);
            if (want !== got) core.warning(`Dropped suggestion on ${f.path}:${start}-${f.line} (${got} lines for a ${want}-line range).`);
            else if (f.suggestion === current) core.warning(`Dropped suggestion on ${f.path}:${start}-${f.line} (no change).`);
            else body += `\n\n${fence}suggestion\n${f.suggestion}\n${fence}`;
        }
        body += agentPrompt(f, true);
        const c = { path: f.path, line: Number(f.line), side: 'RIGHT', body };
        if (Number(start) !== Number(f.line)) {
            c.start_line = Number(start);
            c.start_side = 'RIGHT';
        }
        inline.push(c);
        inlineFindings.push(f);
    }

    // Summary. Findings without a valid anchor go here rather than on an approximate line.
    const findingCount = inline.length + orphaned.length; // blocking findings only (LOW excluded)
    const baseSha = process.env.BASE_SHA;
    // Set once the earlier threads are handled; the summary opens with it.
    let stateLine = '';
    // Set when the PR moved on during the review; the summary opens with it.
    let supersededLine = '';
    // A function, so a rejected post can render it again with every finding in the summary.
    const renderSummary = () => {
        // Short, like the other review bots: a status line, the findings that have no inline thread,
        // one agent prompt for everything open, and a one-line footer. What the PR does is the
        // author's to say, so the model's summary appears only when it has something else to add.
        const short = headSha.slice(0, 7);
        const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
        const blocking = inline.length + orphaned.length;
        let status;
        if (!blocking && !suggestions.length) status = heldBack ? `**No published findings** on \`${short}\`.` : `**No issues found** on \`${short}\`.`;
        else {
            const counts = [
                blocking ? `**${plural(blocking, 'finding')}**` : '**No blocking findings**',
                suggestions.length && plural(suggestions.length, 'suggestion')
            ];
            status = `${counts.filter(Boolean).join(' · ')} on \`${short}\``;
        }
        const lines = [supersededLine, status, stateLine];
        // The range comes from analyze's job outputs, set before the model ran.
        if (process.env.INCREMENTAL === 'true') lines.push('*Re-reviewed only the files changed since my last review, skipping merges of the base branch.*');
        if (review.summary && review.summary.trim()) lines.push(review.summary.trim());
        let summary = lines.filter(Boolean).join('\n\n');

        // Fixed text only: no count, and nothing about what was held back or why.
        if (heldBack) {
            summary += heldBackBlocks
                ? '\n\n> [!IMPORTANT]\n> Part of this review was held back because it may be security-sensitive. A maintainer needs to look at this PR before it can merge.'
                : '\n\n> [!NOTE]\n> Part of this review was held back because it may be security-sensitive. None of it blocks this PR.';
        }

        if (orphaned.length) {
            summary += `\n\n### ${inlineKeyIssues ? 'Findings without an in-diff anchor' : 'Findings'}\n\n${orphaned
                .map(
                    f =>
                        `- **${(f.severity || 'note').toUpperCase()} · ${gate.dimensions[f.dimension]} — ${f.title}**${location(f)}\n  ${String(f.body).replace(/\n/g, '\n  ')}`
                )
                .join('\n\n')}`;
        }
        if (suggestions.length) {
            summary += `\n\n### Suggestions (won't block)\n\n${suggestions.map(f => `- **${f.title}**${location(f)}\n  ${String(f.body).replace(/\n/g, ' ')}`).join('\n\n')}`;
        }
        // After a rejected post the inline findings have moved into `orphaned`, so count them once.
        summary += combinedAgentPrompt([...(inline.length ? inlineFindings : []), ...orphaned, ...suggestions]);

        summary += renderTicketCompliance(review.ticket_compliance, owner, repo);

        // One small line instead of callouts. Comments and re-requests are in the doc: most authors
        // just push, and a push gets its own review.
        const minutes = process.env.PUSH_REVIEW_MINUTES;
        const footer = [
            'Automated review: not an approval or a security audit',
            '[How this bot works](https://github.com/internetarchive/openlibrary/blob/master/docs/code-review-bot.md)'
        ];
        if (/^\d+$/.test(minutes || '')) footer.push(`Reviews new pushes after ${minutes} minutes`);
        summary += `\n\n<sub>${footer.join(' · ')}</sub>\n\n${reviewMarker(findingCount, heldBackBlocks)}`;
        if (supersededLine) summary += `\n${supersededMarker(headSha)}`;
        return summary;
    };
    // If the head moved during the review, the review is still real feedback on the commit it read, so
    // post it there, but only as a COMMENT: it must not approve or block a PR whose newest commit it
    // never saw. It also leaves the bot's earlier threads alone; the new head's review re-checks them,
    // and covers everything this review did (see supersededCommit, and range.cjs).
    const { data: livePr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    const superseded = !headIsCurrent(headSha, livePr.head.sha);
    if (superseded) {
        // After a force-push the reviewed commit may no longer be in the PR, and a review can't be
        // posted on it. Then post nothing, as before: the new head gets its own review regardless.
        let inHistory = false;
        try {
            const { data: cmp } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${headSha}...${livePr.head.sha}` });
            inHistory = cmp.status === 'ahead';
        } catch (e) {
            core.info(`Could not compare ${headSha.slice(0, 8)} with the new head (${e.message}).`);
        }
        if (!inHistory) {
            core.info(
                `Head moved ${headSha.slice(0, 8)}->${String(livePr.head.sha).slice(0, 8)} and the reviewed commit is no longer in the PR (force-push); not posting. The new head gets its own review.`
            );
            return;
        }
        const reviewed = headSha.slice(0, 7),
            live = String(livePr.head.sha).slice(0, 7);
        core.info(`Head moved ${headSha.slice(0, 8)}->${String(livePr.head.sha).slice(0, 8)} during the review; posting it on ${reviewed} as a comment.`);
        supersededLine = `*This review is of \`${reviewed}\`. \`${live}\` was pushed while it ran, so it neither approves nor blocks, and \`${live}\` gets its own review.*`;
    }

    const selfAuthored = (livePr.user && livePr.user.login) === 'openlibrary-bot';

    // Before posting, because it decides the verdict: pick the bot's threads the model judged fixed or
    // dismissed for the resolve job, noting why on the thread's first comment, and count the bot's threads still
    // open. A GraphQL error must not fail the post; it leaves the count null, which means no APPROVE.
    let unresolvedOwnThreads = null;
    const toResolveIds = [];
    const noteEdits = [];
    if (!superseded) {
        try {
            let allThreads = [],
                tCursor = null;
            for (;;) {
                const page = await github.graphql(
                    `query($owner:String!,$repo:String!,$pr:Int!,$cursor:String){
             repository(owner:$owner,name:$repo){
               pullRequest(number:$pr){
                 reviewThreads(first:100, after:$cursor){
                   nodes { id isResolved isOutdated path line comments(first:1){ nodes { id author { login } body } } }
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
            // A thread listed as both counts as fixed.
            const toDismiss = threadsToResolve({ threads: allThreads, resolvedIds: review.dismissed, botLogin: 'openlibrary-bot' }).filter(
                id => !toResolve.includes(id)
            );
            // Commits in the reviewed range, newest first, for the "Addressed in" note.
            let rangeShas = [];
            if (toResolve.length) {
                try {
                    const { data: cmp } = await github.rest.repos.compareCommitsWithBasehead({ owner, repo, basehead: `${baseSha}...${headSha}` });
                    rangeShas = (cmp.commits || []).map(c => c.sha).reverse();
                } catch (e) {
                    core.warning(`Could not list the reviewed commits: ${e.message}`);
                }
            }
            const byId = new Map(allThreads.filter(Boolean).map(t => [t.id, t]));
            let addressed = 0,
                dismissed = 0;
            for (const id of [...toResolve, ...toDismiss]) {
                const fixed = toResolve.includes(id);
                let note = 'Dismissed: a reply below shows this does not apply.';
                if (fixed) {
                    let sha = headSha;
                    try {
                        const path = byId.get(id).path;
                        if (path && rangeShas.length) {
                            const { data: touching } = await github.rest.repos.listCommits({ owner, repo, sha: headSha, path, per_page: 30 });
                            sha = fixedInSha({ rangeShas, pathShas: (touching || []).map(c => c.sha), headSha });
                        }
                    } catch (e) {
                        core.warning(`Could not find the commit that fixed thread ${id}: ${e.message}`);
                    }
                    note = `✅ Addressed in [\`${sha.slice(0, 7)}\`](https://github.com/${owner}/${repo}/commit/${sha})`;
                }
                // Noted on the bot's comment rather than as a reply, once the review is posted.
                const first = byId.get(id).comments.nodes[0];
                noteEdits.push({ threadId: id, commentId: first.id, body: `${first.body}\n\n${note}` });
                toResolveIds.push(id);
                if (fixed) addressed++;
                else dismissed++;
            }
            // The `resolve` job resolves these after this job ends. This job's tokens can't (#14533).
            if (toResolveIds.length) core.info(`Handing ${addressed} fixed and ${dismissed} dismissed review thread(s) to the resolve job.`);
            // Counted the way the status job counts, limited to the bot's threads, as if the resolve
            // job succeeds. If it fails, the status job still sees the thread open and stays red.
            unresolvedOwnThreads = allThreads.filter(t => {
                if (!t || t.isResolved || t.isOutdated || toResolveIds.includes(t.id)) return false;
                const c = t.comments && t.comments.nodes && t.comments.nodes[0];
                return !!(c && c.author && c.author.login === 'openlibrary-bot');
            }).length;
            stateLine = threadStateLine({ addressed, dismissed, open: unresolvedOwnThreads });
        } catch (e) {
            core.warning(`Thread enumeration failed; resolving no threads and not auto-approving: ${e.message}`);
        }
    }

    // A human's open thread doesn't stop APPROVE, though it keeps the status red. The status, not
    // the verdict, is what merging requires.
    // Never approve while a blocking part is held back, from this review or an earlier one a
    // maintainer hasn't dismissed: count it as one more finding.
    let blocked = heldBackBlocks;
    if (!blocked && !superseded) {
        const earlier = await github.paginate(github.rest.pulls.listReviews, { owner, repo, pull_number: prNumber, per_page: 100 });
        blocked = heldBackOpen(earlier.filter(r => r.user && r.user.login === 'openlibrary-bot' && r.body && !supersededCommit(r.body)));
    }
    let event = superseded ? 'COMMENT' : selectReviewEvent({ selfAuthored, findingCount: findingCount + (blocked ? 1 : 0), unresolvedOwnThreads });
    let summary = renderSummary();

    // One batched review. POST /pulls/{n}/comments returns 422 `pull_request_review_thread.base`
    // in practice (cli/cli#13358), while the same anchors in a batched review work. On a 422,
    // first move the inline comments into the summary (GitHub rejects a line it can't find in the
    // PR's diff), then fall back from a verdict to COMMENT, rather than fail and lose the review.
    const postReview = () =>
        github.rest.pulls.createReview({
            owner,
            repo,
            pull_number: prNumber,
            commit_id: headSha,
            event,
            body: summary,
            comments: inline
        });
    let posted;
    for (;;) {
        try {
            ({ data: posted } = await postReview());
            break;
        } catch (e) {
            if (!e || e.status !== 422) throw e;
            if (inline.length) {
                core.warning(`The review was rejected (422: ${e.message}); posting it again with the inline comments in the summary.`);
                orphaned.push(...inlineFindings);
                inline.length = 0;
                summary = renderSummary();
            } else if (event !== 'COMMENT') {
                core.warning(`Verdict ${event} was rejected (422); posting as COMMENT instead.`);
                event = 'COMMENT';
            } else {
                throw e;
            }
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
    // Only once the review is up, so a failed post leaves the threads and their comments as they were.
    // A failed edit still hands the thread on.
    for (const { threadId, commentId, body } of noteEdits) {
        try {
            await github.graphql(
                `mutation($id:ID!,$body:String!){ updatePullRequestReviewComment(input:{pullRequestReviewCommentId:$id, body:$body}){ pullRequestReviewComment { id } } }`,
                { id: commentId, body }
            );
        } catch (e) {
            core.warning(`Could not edit the comment on review thread ${threadId}: ${e.message}`);
        }
    }
    core.setOutput('resolve_thread_ids', JSON.stringify(toResolveIds));

    // See shouldDismissTeamRequest. Never fails the job. A superseded review leaves the request for the new head.
    if (!superseded && shouldDismissTeamRequest({ selfAuthored, event })) {
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

module.exports = {
    refetchDiff,
    validateAndPost,
    selectReviewEvent,
    shouldDismissTeamRequest,
    threadsToResolve,
    fixedInSha,
    renderTicketCompliance,
    agentPrompt,
    threadStateLine
};
