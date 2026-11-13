/** GitHub I/O for the Good First Issue flow; no requests run at import time. */
import { decideGfiAction, findIssueReferences, getLinkedIssueMetadata } from './new_pr_labeler_core.mjs';

const MARKER = '<!-- ol-bot -->';
const sameName = (a, b) => a.toLowerCase() === b.toLowerCase();

/** Handles only the first closing reference, independently of PR lead assignment. */
export async function handleGfiPr(octokit, fullRepoName, prNumber, prBody, authorAssociation) {
    const [owner, repo] = fullRepoName.split('/');
    const base = { owner, repo, headers: { 'X-GitHub-Api-Version': '2022-11-28' } };
    const { data: pr } = await octokit.request('GET /repos/{owner}/{repo}/pulls/{pull_number}', { ...base, pull_number: prNumber });
    pr.author_association ??= authorAssociation;
    // The body may have been edited while this workflow was queued.
    const reference = findIssueReferences(pr.body === undefined ? prBody : pr.body, fullRepoName).find(ref => ref.kind === 'closing');
    if (!reference) return { action: 'skip', reason: 'no closing reference' };
    // Re-read the issue rather than relying on metadata fetched by the lead step.
    const issueParams = { ...base, issue_number: reference.number };
    const { data: issue } = await octokit.request('GET /repos/{owner}/{repo}/issues/{issue_number}', issueParams);
    const input = { pr, issue, kind: reference.kind };
    const initial = decideGfiAction(input);
    if (initial.action === 'skip' && initial.reason !== 'comments not fetched') return initial;

    // paginate rejects if ANY page fails: never interpret an unread page as no comment.
    const issueComments = await octokit.paginate('GET /repos/{owner}/{repo}/issues/{issue_number}/comments', { ...issueParams, per_page: 100 });
    const decision = decideGfiAction({ ...input, hasCommented: issueComments.some(comment => sameName(comment.user.login, pr.user.login)) });
    const author = pr.user.login;
    const { leadName } = getLinkedIssueMetadata({ data: issue });
    const taggedLead = leadName ? ` or tag @${leadName}` : '';
    let body;
    let target;
    let comments;
    if (decision.action === 'assign') {
        body = `🤖 Assigned to @${author} automatically: they opened #${prNumber} after commenting here. (This is a Good First Issue, so nobody has to assign it by hand.)`;
        target = reference.number;
        comments = issueComments;
    } else {
        target = prNumber;
        comments = await octokit.paginate('GET /repos/{owner}/{repo}/issues/{issue_number}/comments', { ...base, issue_number: prNumber, per_page: 100 });
        if (decision.reason === 'duplicate') {
            const assignee = issue.assignees[0].login;
            body = `Hi @${author} — thanks for the PR! **#${reference.number}** is already assigned to @${assignee}, so this looks like a duplicate and we've closed it to avoid two people doing the same work. (Good First Issues are assigned to the first person who opens a ready, non-draft PR after commenting on the issue.)

If you think that's wrong, or you'd like to pick it up if @${assignee} steps back, leave a comment on #${reference.number}${leadName ? ` and tag @${leadName}` : ''} — we'll help from there.`;
        } else {
            body = `Hi @${author} — thanks for putting this together, and sorry for the bump! 👋

For **Good First Issues** we ask contributors to leave a quick comment on the issue (**#${reference.number}**) before opening a PR. Two reasons: it lets other contributors know the issue is taken, and GitHub won't let us assign an issue to anyone who hasn't commented on it — so without the comment we can't tell who's working on what.

We couldn't find a comment from you on **#${reference.number}**, so this PR has been closed for now. It's easy to pick back up:

1. Leave a comment on #${reference.number} saying you'd like to work on it.
2. Reopen this pull request — or open a new one if GitHub won't let you reopen.

That comment is the only thing missing, and we'll take it from there. If you think we got this wrong, reply here${taggedLead} and we'll sort it out.`;
        }
    }
    const commentKey = `<!-- gfi:${reference.number}:${decision.reason} -->`;
    body = `${body}\n\n${MARKER}\n${commentKey}`;
    const alreadyCommented = comments.some(
        comment =>
            comment.body.includes(MARKER) &&
            comment.body.includes(commentKey) &&
            (sameName(comment.user.login, 'openlibrary-bot') || /\[bot\]$/i.test(comment.user.login))
    );
    if (decision.action === 'assign') {
        const { data } = await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/assignees', { ...issueParams, assignees: [author] });
        if (!data.assignees.some(user => sameName(user.login, author))) throw new Error(`GitHub did not assign @${author} to #${reference.number}`);
    }
    if (!alreadyCommented) await octokit.request('POST /repos/{owner}/{repo}/issues/{issue_number}/comments', { ...base, issue_number: target, body });
    if (decision.action === 'close')
        await octokit.request('PATCH /repos/{owner}/{repo}/pulls/{pull_number}', { ...base, pull_number: prNumber, state: 'closed' });
    return decision;
}
