/**
 * Pure, IO-free decision logic for the PR preflight gates.
 *
 * It lives in its own module so it can be unit tested: the entry script
 * (pr_preflight_gates.mjs) reads process.env and calls process.exit at import
 * time, so it cannot be imported in vitest. These functions touch no network,
 * no filesystem, and no argv, so the tests import them directly.
 *
 * Three gates, each a pure function of the PR's own metadata/body:
 *   1. priority     -- the PR must carry a `Priority: N` label.
 *   2. issue-ref    -- the body must reference an issue (bare `#N` or a URL);
 *                      a GitHub "linked"/`Closes` relationship is NOT required.
 *   3. dev-evidence -- a non-staff/non-lead author must show some sign the code
 *                      was actually run in a dev instance. Staff/leads exempt.
 *
 * Gate 3 ERRS TOWARD PASSING: a false "no evidence" on a good PR stalls real
 * work, which is worse than a false "has evidence" on a thin one (a human still
 * reviews and merges every PR). The heuristic is deliberately permissive and
 * its false-positive stance is documented on each matcher below.
 */

/**
 * Staff and leads exempt from the dev-evidence gate (gate 3 only).
 *
 * Compared case-insensitively against the PR author's login. `openlibrary-bot`
 * is included: the fleet's own bot-authored PRs are staff-equivalent.
 *
 * NOTE: this is the ~10th hand-maintained copy of openlibrary's staff/lead
 * allowlist (tracked as drift under issue #13160 -- there is no single source
 * of truth). That drift is tolerable *here specifically* because gate 3 errs
 * toward passing: if a real staffer is missing from this list, their ordinary
 * PR body almost always trips the permissive evidence heuristic anyway, so the
 * worst case is that a staffer's unusually bare PR is asked for evidence it
 * would normally volunteer -- never a hard block. Keep in sync with
 * code_review_action.yml's allowlist when staff change.
 */
export const STAFF_AND_LEADS = ['mekarpeles', 'cdrini', 'hornc', 'scottbarnes', 'seabelis', 'raybb', 'lokesh', 'jimchamp', 'openlibrary-bot'];

// Markdown/HTML image or video embed, or an uploaded attachment. GitHub rewrites
// pasted screenshots/recordings to user-images.githubusercontent.com or to
// github.com/<owner>/<repo>/assets/<id>, so those count even without an extension.
const MEDIA_EMBED_RE = /!\[[^\]]*\]\([^)]+\)|<img\b|<video\b/i;
const MEDIA_LINK_RE = /https?:\/\/[^\s)]+\.(?:png|jpe?g|gif|gifv|webp|svg|bmp|mp4|mov|webm|ogg|avi)\b/i;
// A pasted GitHub attachment (screenshot or drag-dropped video), which carries no
// file extension. GitHub has used three shapes over time, all counted here:
//   - user-images.githubusercontent.com/...        (older pasted images)
//   - github.com/<owner>/<repo>/assets/<id>        (2022-era attachments)
//   - github.com/user-attachments/assets/<uuid>    (current; drag-dropped videos)
// The last is the one a screen recording renders as, so missing it would FAIL the
// single strongest evidence form -- the opposite of err-toward-passing.
const MEDIA_ATTACHMENT_RE = /https?:\/\/(?:user-images\.githubusercontent\.com|github\.com\/(?:user-attachments|[^\s/]+\/[^\s/]+)\/assets)\//i;

// A fenced code block (``` ... ``` or ~~~ ... ~~~) -- pasted output, logs, a
// command transcript. Non-greedy, spans newlines.
const FENCED_CODE_RE = /(?:^|\n)[ \t]*(?:```|~~~)[\s\S]*?(?:```|~~~)/;

// Prose that attests to having run the code. Broad on purpose (err toward
// passing): any one of these phrases is enough. False positives (a PR that
// merely talks about testing without having done it) are the accepted cost.
const TESTIMONIAL_RE =
    /\b(?:tested|testing|i (?:ran|tested|verified|checked)|ran (?:it|this|the|locally|in|on)|run (?:it )?locally|works? (?:locally|as expected|fine|correctly|on)|verified|screenshots?|screencasts?|screen[- ]?recording|manually (?:tested|verified|checked)|smoke[- ]?tested|confirmed (?:locally|working|that|it)|reproduc\w+|dev instance|in dev\b|on (?:my )?local|localhost|127\.0\.0\.1|output (?:below|is|:)|logs? below|exercised|deployed to (?:staging|testing|dev))\b/i;

/**
 * Remove HTML comments (`<!-- ... -->`). The PR template is almost entirely
 * comments, and several of them ("...reproduce/verify...", "post evidence
 * (screenshots)...") contain words the evidence heuristic would otherwise match,
 * so the stock template would pass gate 3 with no real content. new_pr_labeler
 * strips comments before scanning for the same reason.
 *
 * @param {string} s
 * @returns {string}
 */
function stripHtmlComments(s) {
    return s.replace(/<!--[\s\S]*?-->/g, ' ');
}

/**
 * Remove ONLY the stock PR template's own section headers (`### Technical`,
 * `### Testing`, `### Screenshot`/`Screenshots`, `### Stakeholders`). Those are
 * scaffolding, yet two of them ("Testing", "Screenshot") are testimonial
 * vocabulary, so the bare template would otherwise satisfy gate 3.
 *
 * Crucially this does NOT strip arbitrary headers: a contributor whose only
 * testing note is a custom header (`## Tested on localhost, works`) is writing
 * real evidence, and stripping every header would delete it and FALSELY FAIL a
 * good PR -- the err-toward-passing failure this gate must avoid. Prose under a
 * header is on its own line and always survives either way. Code blocks are
 * detected on the comment-stripped (not header-stripped) body, so a `#`-prefixed
 * line inside a fenced block is never lost.
 *
 * @param {string} s
 * @returns {string}
 */
function stripTemplateHeaders(s) {
    return s.replace(/^[ \t]{0,3}#{1,6}[ \t]+(?:Technical|Testing|Screenshots?|Stakeholders)[ \t]*$/gim, ' ');
}

/**
 * True when the given login belongs to a staff member or lead (case-insensitive).
 *
 * @param {string|null|undefined} login
 * @returns {boolean}
 */
export function isStaffOrLead(login) {
    return typeof login === 'string' && STAFF_AND_LEADS.includes(login.toLowerCase());
}

/**
 * Gate 1 -- true when the PR carries any `Priority: N` label.
 *
 * The requirement is only "has a priority", so this accepts any digit: the repo's
 * real labels run `Priority: 0` through `Priority: 4` (confirmed against the live
 * label set), and restricting to 0..2 or 0..3 would FALSELY FAIL a legitimately
 * `Priority: 4` PR. A non-numeric suffix (`Priority: high`) is still rejected.
 *
 * Accepts either the raw payload shape (array of `{name}` objects, as
 * `github.event.pull_request.labels` gives) or a plain array of strings.
 *
 * @param {Array<{name: string}|string>|null|undefined} labels
 * @returns {boolean}
 */
export function hasPriorityLabel(labels) {
    if (!Array.isArray(labels)) {
        return false;
    }
    return labels.some(label => {
        const name = typeof label === 'string' ? label : (label && label.name) || '';
        return /^Priority:\s*\d/.test(name);
    });
}

/**
 * Gate 2 -- true when the body references an issue.
 *
 * Passes on a bare `#N` (the common case) or a full GitHub issues/pull URL. Does
 * NOT require a closing keyword or a real "linked issue" relationship: a mention
 * is enough. A leading `&#` (an HTML entity) is excluded so e.g. `&#39;` is not
 * read as issue 39.
 *
 * @param {string|null|undefined} body
 * @returns {boolean}
 */
export function hasIssueReference(body) {
    if (typeof body !== 'string' || body === '') {
        return false;
    }
    // Scan visible text only: a `#N` or issue URL buried in an HTML comment (e.g. a
    // future template example) is not a reference the author actually made.
    const visible = stripHtmlComments(body);
    const bareRef = /(?:^|[^\w&])#\d+\b/.test(visible);
    const urlRef = /https?:\/\/github\.com\/[^\s/]+\/[^\s/]+\/(?:issues|pull)\/\d+/i.test(visible);
    return bareRef || urlRef;
}

/**
 * Gate 3 -- true when the body shows some indication the code was actually run
 * in a dev instance: a media embed/attachment (screenshot, video), a fenced
 * code block (output/logs), or a written testimonial. Deliberately permissive.
 *
 * This does NOT apply the staff/lead exemption -- that is the caller's job (see
 * evaluatePreflight), so this function stays a pure test of the body alone.
 *
 * @param {string|null|undefined} body
 * @returns {boolean}
 */
export function hasDevRunEvidence(body) {
    if (typeof body !== 'string' || body === '') {
        return false;
    }
    // Strip the template's HTML comments first, so its "...reproduce/verify..." /
    // "post evidence (screenshots)..." hints do not read as the author's evidence.
    const visible = stripHtmlComments(body);
    // Media and code blocks are evidence wherever they appear (a `#`-prefixed line
    // inside a code block must not be lost), so test them on the comment-stripped body.
    if (MEDIA_EMBED_RE.test(visible) || MEDIA_LINK_RE.test(visible) || MEDIA_ATTACHMENT_RE.test(visible) || FENCED_CODE_RE.test(visible)) {
        return true;
    }
    // A written testimonial must be prose the author wrote, not a bare template
    // section header ("### Testing", "### Screenshot"), so drop those first.
    return TESTIMONIAL_RE.test(stripTemplateHeaders(visible));
}

/**
 * Evaluate all three gates for a PR.
 *
 * @param {{labels?: Array<{name: string}|string>, body?: string|null, authorLogin?: string|null}} pr
 * @returns {{passed: boolean, results: Array<{id: string, title: string, ok: boolean, exempt?: boolean, detail: string}>}}
 *          `passed` is true iff every gate is ok. `results` is one row per gate,
 *          in stable order, each with a human-readable `detail`.
 */
export function evaluatePreflight({ labels, body, authorLogin } = {}) {
    const results = [];

    const priorityOk = hasPriorityLabel(labels);
    results.push({
        id: 'priority',
        title: 'Priority label',
        ok: priorityOk,
        detail: priorityOk
            ? 'PR carries a `Priority: N` label.'
            : 'No `Priority: N` label on this PR. It is normally carried over from the ' +
              'linked issue; if it has not been applied yet, add a `Priority:` label and ' +
              'this check re-runs automatically.'
    });

    const issueRefOk = hasIssueReference(body);
    results.push({
        id: 'issue-ref',
        title: 'Issue reference',
        ok: issueRefOk,
        detail: issueRefOk
            ? 'Body references an issue (`#N` or an issue/PR URL).'
            : 'Body references no issue. Add a bare `#NNNN` or a full issue URL ' + '(a `Closes`/linked relationship is not required — a mention is enough).'
    });

    const isExempt = isStaffOrLead(authorLogin);
    const evidenceOk = isExempt || hasDevRunEvidence(body);
    results.push({
        id: 'dev-evidence',
        title: 'Dev-run evidence',
        ok: evidenceOk,
        exempt: isExempt,
        detail: isExempt
            ? `Author @${authorLogin} is staff/lead — dev-run evidence not required.`
            : evidenceOk
              ? 'Body shows the code was run (screenshot/video, output/logs, or a written testimonial).'
              : 'No sign the code was run in a dev instance. Add any one of: a ' +
                'screenshot or screen recording, pasted output/logs in a code block, ' +
                'or a sentence saying you ran/tested it locally.'
    });

    return { passed: results.every(r => r.ok), results };
}
