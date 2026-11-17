// The `post` job: re-fetches the reviewed diff, runs the disclosure gate (gate.cjs) again as the
// enforcer, and posts one batched review. Holds the review PAT and runs no model.
'use strict';

const gate = require('./gate.cjs');
const { headIsCurrent } = require('./shared.cjs');

// #14487 PART A -- the verdict. GitHub clears a reviewer's pending request ONLY on APPROVE
// or REQUEST_CHANGES; a COMMENT never does, so the bot's team request sat pending forever
// (#14450). Post a real verdict driven by the SAME signal the status job uses on the published
// path -- review.findings.length (== analyze's public_findings_count): >0 blocking ->
// REQUEST_CHANGES. A clean run APPROVEs ONLY when no finding of OUR OWN is still unresolved
// (unresolvedOwnThreads === 0), so the verdict never says APPROVE while the code-review status
// is still red on a standing bot finding; any surviving (or unknown) thread -> COMMENT.
// EXCEPTION -- self-review: GitHub returns 422 for approving/requesting-changes on your OWN PR,
// so a bot-authored (same-repo) PR falls back to COMMENT (its loop is driven by forge off the
// submitted review and by the status check, not the reviewer pill).
const selectReviewEvent = ({ selfAuthored, findingCount, unresolvedOwnThreads }) => {
    if (selfAuthored) return 'COMMENT';
    if (findingCount > 0) return 'REQUEST_CHANGES';
    // Do NOT auto-APPROVE while any of our OWN prior findings is still unresolved -- or while the
    // thread state is unknown (null, e.g. enumeration failed): APPROVE would then contradict a
    // red code-review status. Exactly 0 surviving own threads is required to approve.
    if (unresolvedOwnThreads !== 0) return 'COMMENT';
    return 'APPROVE';
};

// #14487 PART A.2 -- clearing the pending pill on a BOT-AUTHORED PR. A contributor PR's pill is
// cleared by the APPROVE/REQUEST_CHANGES verdict itself. A bot-authored PR can only post COMMENT
// (self-review 422), which never clears the team request -- so after a real COMMENT post we must
// explicitly dismiss the team request (removeRequestedReviewers) or the pill sits pending forever
// (live proof: #14450). Only on a self-authored PR that actually posted a COMMENT -- never on a
// contributor verdict, and never on skip/withhold/failed/head-moved (those return before the post).
const shouldDismissTeamRequest = ({ selfAuthored, event }) => {
    return selfAuthored && event === 'COMMENT';
};

// #14487 PART B -- on a re-review, select OUR OWN open review threads the model judged fixed.
// The model re-checks every earlier thread against the PR head (code_review.md Step 4) and lists
// the fixed ones' ids in review.resolved. That replaced a "finding not re-reported on a
// re-examined line" heuristic, which never resolved a thread whose fix landed on other lines
// (#14515: a comment saying "the sibling strings have the same bug" stayed open after they were
// fixed, so the PR got COMMENT instead of APPROVE and a red status). GUARDS: only a live,
// unresolved thread whose first comment is the bot's -- an id the model invents, or a human's
// thread, is never touched. The reply is fixed text, so no model prose reaches it.
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

// Ticket compliance section (code_review.md Step 5), rendered as PR-Agent's
// ticket_markdown_logic does (pr_agent/algo/utils.py): a level per issue computed here from
// the model's lists, not chosen by the model, and an overall level. Only this repo's issues
// are shown. Informational: it does not change the verdict or the code-review status.
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

    // --- The disclosure gate. Nothing below this block runs unless it passes.
    let review = null;
    try {
        review = JSON.parse(fs.readFileSync('review.json', 'utf8'));
    } catch (e) {
        review = null;
    }
    const verdict = gate.check(review);
    if (!verdict.publish) {
        // #14476 D3a -- nothing PUBLIC to post for this commit (withheld or empty). Exit
        // CLEANLY, not failed: this job still publishes nothing (the enforcer property is
        // intact), but a withhold is no longer a hard job failure. The SHA-bound `code-review`
        // status job is the sole gate decider and derives pass/fail from analyze's
        // finding-driven outputs (withheld + the 1-bit withheld_blocking), so a backstop
        // false-positive with zero findings can green while a real finding still blocks.
        // No reason, count or text in the log (the log is public).
        core.info('Nothing public to post for this commit; the code-review status job decides the gate.');
        return;
    }
    // Everything below renders from the allowlisted copy only.
    review = verdict.clean;

    // --- Anchorable lines: RIGHT-side (added + context) lines of the reviewed diff.
    // GitHub documents no behaviour for an out-of-diff anchor, and this API surface is
    // already known to no-op silently here, so we drop bad anchors rather than find out.
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

    // LOW findings become a non-blocking suggestions list in the summary, not threads (threads block).
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

    // --- Summary body. Findings with no honest in-diff anchor live here rather than
    // being pinned to an approximate line: on a real review of #13548, 3 of 9 findings
    // proved themselves in files the diff never touched.
    const findingCount = inline.length + orphaned.length; // blocking findings only (LOW excluded)
    let summary = review.summary || '';
    // The range comes from analyze's job outputs, set before the model ran.
    const sha = /^[0-9a-f]{40}$/,
        baseSha = process.env.BASE_SHA;
    if (process.env.INCREMENTAL === 'true' && sha.test(baseSha) && sha.test(headSha)) {
        summary = `*Reviewing only the ${baseSha.slice(0, 8)}..${headSha.slice(0, 8)} range — the commits pushed since my last pass.*\n\n${summary}`;
    }

    // --- Ticket compliance against the linked issues (empty when there are none).
    summary += renderTicketCompliance(review.ticket_compliance, owner, repo);

    // --- Every dimension, stated. Silence on one reads identically to having checked it.
    // Security is a fixed line: a review that reaches this point has none by construction.
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
    // #14484: tell the contributor -- who may have no write access and cannot use the
    // "re-request review" button -- exactly how to re-run the review after pushing fixes.
    // A plain instruction so a stranger needs no prior knowledge of the magic comment.
    summary += `\n\n---\n> [!TIP]\n> When you've addressed the feedback and pushed your changes, comment \`@openlibrary-bot review\` on this PR to run a fresh review.`;
    summary += `\n\n> [!NOTE]\n> Automated review by [@openlibrary-bot](https://github.com/internetarchive/openlibrary/blob/master/.github/workflows/code_review.md) on behalf of @mekarpeles. This is **not** an approval or a sign-off, and it does not satisfy a required review.\n\n<!-- ol-pr-review-bot f=${findingCount} -->`;

    // #14476 D1 -- review + status must describe the SAME commit. createReview re-anchors its
    // inline comments to the PR's LIVE head at post time (it ignores commit_id), so if a push
    // landed since this run pinned headSha, posting now attaches the review to a commit this
    // run did NOT review, while the status job binds headSha -> the stranded head (observed on
    // #14475 ae775e7d: two reviews, no status). If the head has moved, post NEITHER: the new
    // head is unreviewed and correctly earns its own run (a required status it has not yet
    // satisfied). The superseded headSha is left as-is -- the ruleset reads the current head.
    const { data: livePr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    if (!headIsCurrent(headSha, livePr.head.sha)) {
        core.info(
            `Head moved ${headSha.slice(0, 8)}->${String(livePr.head.sha).slice(0, 8)} since this review was pinned; not posting. The new head earns its own run.`
        );
        return;
    }

    // --- #14487: the PR author (authoritative, from the live-head re-fetch above) and the published
    // finding count -- the SAME signal the status job reads on the published path.
    const selfAuthored = (livePr.user && livePr.user.login) === 'openlibrary-bot';

    // --- #14487 PART B (runs BEFORE the post, because it gates the verdict): enumerate the review
    // threads, reply "Fixed in <sha>" on and resolve our OWN threads the model judged fixed
    // (threadsToResolve -- never a blind resolve-all), and count our OWN threads that remain unresolved. The whole block
    // is wrapped: a transient GraphQL failure must never fail a post that otherwise succeeds -- it
    // leaves unresolvedOwnThreads unknown (null), which selectReviewEvent treats as "do not APPROVE".
    let unresolvedOwnThreads = null; // null = unknown -> fail safe (no auto-approve)
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
        // Our own threads still unresolved-and-not-outdated AFTER resolution -- the exact shape the
        // status job counts, restricted to the bot's own finding threads. Only a SUCCESSFULLY resolved
        // thread is excluded, so a failed resolve keeps the PR from auto-approving.
        unresolvedOwnThreads = allThreads.filter(t => {
            if (!t || t.isResolved || t.isOutdated || resolvedOk.has(t.id)) return false;
            const c = t.comments && t.comments.nodes && t.comments.nodes[0];
            return !!(c && c.author && c.author.login === 'openlibrary-bot');
        }).length;
    } catch (e) {
        core.warning(`Thread enumeration failed; skipping resolution and not auto-approving: ${e.message}`);
    }

    // --- #14487 PART A: pick the verdict now that thread state is known. selfAuthored -> COMMENT
    // (self-review 422); findings>0 -> REQUEST_CHANGES; clean AND no surviving own thread -> APPROVE;
    // otherwise COMMENT. The APPROVE gate is scoped to the bot's OWN findings -- it never approves
    // over a standing bot finding. A purely-human open thread can still leave the status red while
    // the bot approves (cosmetic): by design the pill tracks the bot's findings, and the all-author
    // `code-review` status (which counts human threads too) stays the merge authority.
    let event = selectReviewEvent({ selfAuthored, findingCount, unresolvedOwnThreads });

    // --- One batched review. The per-comment endpoint (POST /pulls/{n}/comments) is
    // documented but returns 422 `pull_request_review_thread.base` in practice
    // (cli/cli#13358); the batched payload with identical anchors succeeds. commit_id is
    // headSha, now re-confirmed as the live head, so the review and the status agree.
    // #14487: a self-review verdict is a 422 -- selfAuthored already routes those to COMMENT; this
    // try/catch is the belt-and-suspenders degrade so an UNEXPECTED 422 can never fail the post job
    // (it posts a COMMENT instead; the code-review status check remains the merge gate).
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

    // --- Verify. Step 4 of pr_autoresponder.md documents this API surface returning
    // 2xx while changing nothing, so confirm rather than trusting the status code.
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

    // --- #14487 PART A.2: on a bot-authored PR the COMMENT above does not clear the pending team
    // request, so dismiss it explicitly (only after a verified real post). Never fails the job.
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
