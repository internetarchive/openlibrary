// If you change how the code review bot behaves here, update docs/code-review-bot.md to match.
// Replies to an @openlibrary-bot comment that doesn't start a review, so nobody is left wondering.
// `decline` answers someone who can't ask for a review; `skipped` answers someone who can, when
// there's nothing to review. The text is fixed: only the commenter's login, a commit and the push
// delay from .pr_agent.toml are filled in. Each reply is posted once (see `marker`), so repeated
// comments can't make the bot repeat itself.
'use strict';

const BOT = 'openlibrary-bot';
const DOC = 'https://github.com/internetarchive/openlibrary/blob/master/docs/code-review-bot.md';
const SEE_DOC = `See [how the code review bot works](${DOC}).`;

// A hidden tag on each reply. A reply with the same tag already on the PR means don't post again.
const marker = (kind, key) => `<!-- ol-review-bot-reply ${kind} ${key} -->`;

// When the bot reviews again after pushes, in the words of a sentence, or null when it doesn't.
const pushRule = settings =>
    settings.github_action_config.handle_push_trigger
        ? `${settings.openlibrary_reviewer.push_review_delay_minutes} minutes after new commits stop arriving`
        : null;

const declineText = ({ login, settings }) => {
    const again = pushRule(settings);
    return [
        `Hi @${login}, I can only start a review when this PR's author or an Open Library maintainer asks.`,
        `You usually don't need to: I review new PRs${again ? `, and review again ${again}` : ''}. ${SEE_DOC}`
    ].join('\n\n');
};

// reason: the `skip_reason` output of range.cjs.
const skippedText = ({ reason, sha, settings }) => {
    if (reason === 'draft')
        return `This PR is a draft, so I won't review it yet. Mark it ready for review, then ask again if a review doesn't start. ${SEE_DOC}`;
    if (reason === 'closed') return `This PR is closed, so I won't review it. ${SEE_DOC}`;
    if (reason === 'reviewed') {
        const again = pushRule(settings);
        const next = again ? `Push new commits and I'll review them ${again}.` : 'Push new commits, then ask again.';
        return `I've already reviewed this commit (\`${String(sha).slice(0, 7)}\`) and its \`code-review\` check is up to date, so there's nothing new to review. ${next} ${SEE_DOC}`;
    }
    return null;
};

// Posts body + tag on the PR unless the bot already posted that tag there. Returns whether it posted.
async function postOnce({ github, owner, repo, issue_number, body, tag }) {
    const comments = await github.paginate(github.rest.issues.listComments, { owner, repo, issue_number, per_page: 100 });
    if (comments.some(c => c.user && c.user.login === BOT && (c.body || '').includes(tag))) return false;
    await github.rest.issues.createComment({ owner, repo, issue_number, body: `${body}\n\n${tag}` });
    return true;
}

const loadSettings = (require, process, core) =>
    require(`${process.env.GITHUB_WORKSPACE}/.github/scripts/code_review/config.cjs`).load(process.env.GITHUB_WORKSPACE, core.info);

async function replyDecline({ github, context, core, require, process }) {
    const { owner, repo } = context.repo;
    const login = context.payload.comment.user.login;
    const body = declineText({ login, settings: loadSettings(require, process, core) });
    const posted = await postOnce({ github, owner, repo, issue_number: context.payload.issue.number, body, tag: marker('decline', login) });
    core.info(posted ? `Told ${login} who can ask for a review.` : `Already told ${login} on this PR.`);
}

async function replySkipped({ github, context, core, require, process }) {
    const { owner, repo } = context.repo;
    const reason = process.env.SKIP_REASON;
    const sha = process.env.SKIP_SHA || '';
    const body = skippedText({ reason, sha, settings: loadSettings(require, process, core) });
    if (!body) return core.info(`No reply for skip reason "${reason}".`);
    const posted = await postOnce({ github, owner, repo, issue_number: context.payload.issue.number, body, tag: marker(reason, sha || 'pr') });
    core.info(posted ? `Explained the skip (${reason}).` : `Already explained this skip (${reason}).`);
}

module.exports = { marker, declineText, skippedText, postOnce, replyDecline, replySkipped };
