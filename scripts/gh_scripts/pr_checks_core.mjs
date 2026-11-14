/**
 * Pure, IO-free decision logic for the PR checks.
 *
 * Each check is posted to the PR's HEAD commit as its OWN named commit status
 * (GitHub Commit Statuses API), so each is independently require-able in branch
 * protection. GitHub groups required status contexts by the segment before `/`,
 * so every context here shares a single swappable prefix (see CHECK_PREFIX).
 *
 * This module is the testable core: it touches no network, filesystem, or argv.
 * The entry script (pr_checks.mjs) gathers inputs from the event payload, does
 * the one network read (issue-is-ready's live labels), calls buildStatuses, and
 * POSTs the results. These functions are imported directly in vitest.
 *
 * The five checks, each a pure function of the PR's own metadata/body (plus, for
 * issue-is-ready, the referenced issue's live labels, fetched by the caller):
 *   priority         -- the PR must carry a `Priority: N` label.
 *   references-issue -- the body must reference an issue (bare `#N` or a URL).
 *   issue-is-ready   -- the referenced issue must NOT be labeled
 *                       `Not Ready for Work!`.
 *   passes-pr-template -- the body must follow the PR template (its sections
 *                       present, and the substantive ones filled in).
 *   ran-the-code     -- a non-staff/non-lead author must show some sign the code
 *                       was run in a dev instance. Staff/leads exempt.
 *
 * Two checks carry deliberately soft semantics; the rest are strict:
 *   - ran-the-code ERRS TOWARD PASSING. A false "no evidence" on a good PR stalls
 *     real work, which is worse than a false "has evidence" on a thin one (a human
 *     still reviews and merges every PR). Its heuristic is permissive by design.
 *   - issue-is-ready never posts `failure` for something it cannot determine: a
 *     missing in-repo reference (references-issue owns that) posts `success`, and a
 *     transient live-read error posts `error`. NOTE: GitHub counts a required
 *     context satisfied only on `success`, so a *required* issue-is-ready still
 *     blocks a merge on an `error` -- but every PR event (push/edit/label) re-runs
 *     it, so any later activity clears a transient error to green.
 * passes-pr-template is strict and structural by contrast: no exemption, and the
 * staff/err-toward-passing semantics of ran-the-code are deliberately kept OUT of
 * it so a "sections present/filled" check stays clean and predictable.
 */

/**
 * The single prefix every check's status context shares. GitHub required-status
 * grouping keys on the segment before `/`, and Mek may pick `pr` over `check`;
 * changing this one constant renames all five contexts at once.
 */
export const CHECK_PREFIX = 'check';

/** Stable suffixes for the five checks. The context is `${CHECK_PREFIX}/${name}`. */
export const CHECK = {
    priority: 'priority',
    referencesIssue: 'references-issue',
    issueIsReady: 'issue-is-ready',
    passesTemplate: 'passes-pr-template',
    ranTheCode: 'ran-the-code'
};

/**
 * Build the full status context for a check suffix.
 *
 * @param {string} name one of the CHECK values
 * @returns {string} e.g. `check/priority`
 */
export function contextFor(name) {
    return `${CHECK_PREFIX}/${name}`;
}

/** The issue label that marks an issue as not-yet-ready to be worked on. */
export const NOT_READY_LABEL = 'Not Ready for Work!';

/** The repo these checks run for; same-repo issue references are resolvable. */
export const DEFAULT_REPO = 'internetarchive/openlibrary';

/**
 * Staff and leads exempt from the ran-the-code check (that check only).
 *
 * Compared case-insensitively against the PR author's login. `openlibrary-bot`
 * is included: the fleet's own bot-authored PRs are staff-equivalent.
 *
 * NOTE: this is the ~10th hand-maintained copy of openlibrary's staff/lead
 * allowlist (tracked as drift under issue #13160 -- there is no single source of
 * truth). That drift is tolerable *here specifically* because ran-the-code errs
 * toward passing: if a real staffer is missing from this list, their ordinary PR
 * body almost always trips the permissive evidence heuristic anyway, so the worst
 * case is that a staffer's unusually bare PR is asked for evidence it would
 * normally volunteer -- never a hard block. Keep in sync with
 * code_review_action.yml's allowlist when staff change.
 */
export const STAFF_AND_LEADS = ['mekarpeles', 'cdrini', 'hornc', 'scottbarnes', 'seabelis', 'raybb', 'lokesh', 'jimchamp', 'openlibrary-bot'];

/** The PR template's section headers, in order. */
export const TEMPLATE_SECTIONS = ['Technical', 'Testing', 'Screenshot', 'Stakeholders'];

/**
 * Which template sections must actually be FILLED (not merely present).
 *
 * Technical and Testing are the substantive sections every PR should speak to.
 * Screenshot is conditional ("If this PR touches UI...") so requiring it filled
 * would falsely fail backend PRs; Stakeholders is a courtesy @-tag. Both are
 * therefore presence-only. This set is the single knob for how strict the
 * template check is.
 */
export const REQUIRED_FILLED_SECTIONS = ['Technical', 'Testing'];

// --- shared text helpers -------------------------------------------------

/**
 * Remove HTML comments (`<!-- ... -->`). The PR template is almost entirely
 * comments, several of which contain words ("...reproduce/verify...", "post
 * evidence (screenshots)...") the evidence heuristic would otherwise match, and a
 * `#N` inside a comment is not a reference the author actually made. new_pr_labeler
 * strips comments before scanning for the same reason.
 *
 * @param {string} s
 * @returns {string}
 */
function stripHtmlComments(s) {
    return s.replace(/<!--[\s\S]*?-->/g, ' ');
}

/**
 * Remove HTML comments AND fenced code blocks (``` ... ``` / ~~~ ... ~~~). Used
 * where we scan for the author's REAL intent -- an issue reference, or template
 * structure -- so that a `#1234` or a `### Testing` merely QUOTED inside a pasted
 * log or example does not read as a genuine reference/section. (ran-the-code is
 * the opposite: there a code block IS evidence, so it uses stripHtmlComments and
 * keeps fences.)
 *
 * @param {string} s
 * @returns {string}
 */
function stripCommentsAndFences(s) {
    return stripHtmlComments(s)
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/~~~[\s\S]*?~~~/g, ' ');
}

/**
 * Remove ONLY the stock PR template's own section headers (`### Technical`,
 * `### Testing`, `### Screenshot`/`Screenshots`, `### Stakeholders`), so the bare
 * template's "Testing"/"Screenshot" scaffolding does not read as a testimonial.
 * It deliberately does NOT strip arbitrary headers: a contributor whose only
 * testing note is a custom header (`## Tested on localhost, works`) is writing
 * real evidence that must survive.
 *
 * @param {string} s
 * @returns {string}
 */
function stripTemplateHeaders(s) {
    return s.replace(/^[ \t]{0,3}#{1,6}[ \t]+(?:Technical|Testing|Screenshots?|Stakeholders)[ \t]*$/gim, ' ');
}

// --- priority ------------------------------------------------------------

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
// passing): any one of these phrases is enough. False positives (a PR that merely
// talks about testing without having done it) are the accepted cost.
const TESTIMONIAL_RE =
    /\b(?:tested|testing|i (?:ran|tested|verified|checked)|ran (?:it|this|the|locally|in|on)|run (?:it )?locally|works? (?:locally|as expected|fine|correctly|on)|verified|screenshots?|screencasts?|screen[- ]?recording|manually (?:tested|verified|checked)|smoke[- ]?tested|confirmed (?:locally|working|that|it)|reproduc\w+|dev instance|in dev\b|on (?:my )?local|localhost|127\.0\.0\.1|output (?:below|is|:)|logs? below|exercised|deployed to (?:staging|testing|dev))\b/i;

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
 * priority -- true when the PR carries any `Priority: N` label.
 *
 * Accepts any digit: the repo's real labels run `Priority: 0` through
 * `Priority: 4`, and restricting the range would falsely fail a legitimately
 * `Priority: 4` PR. A non-numeric suffix (`Priority: high`) is still rejected.
 * Accepts either the raw payload shape (array of `{name}`) or an array of strings.
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
 * references-issue -- true when the body references an issue.
 *
 * Passes on a bare `#N` or a full GitHub issues/pull URL. Does NOT require a
 * closing keyword or a real "linked issue" relationship: a mention is enough. A
 * leading `&#` (an HTML entity) is excluded so `&#39;` is not read as issue 39.
 *
 * @param {string|null|undefined} body
 * @returns {boolean}
 */
export function hasIssueReference(body) {
    if (typeof body !== 'string' || body === '') {
        return false;
    }
    const visible = stripCommentsAndFences(body);
    // `#N` only counts at a start/whitespace/`(` boundary, the way GitHub itself
    // autolinks it. This excludes a URL anchor (`.../#42`, where `/` precedes it)
    // and an HTML entity (`&#39;`), neither of which is an issue reference.
    const bareRef = /(?:^|[\s(])#\d+\b/.test(visible);
    const urlRef = /https?:\/\/github\.com\/[^\s/]+\/[^\s/]+\/(?:issues|pull)\/\d+/i.test(visible);
    return bareRef || urlRef;
}

/**
 * Resolve the first SAME-REPO issue number the body references, or null.
 *
 * Only same-repo references are resolvable: a bare `#N`, or a URL whose
 * owner/repo matches `repo`. A cross-repo URL is intentionally ignored (its
 * readiness is not this repo's to police), yielding null -> issue-is-ready then
 * defers rather than failing. HTML comments are stripped first.
 *
 * @param {string|null|undefined} body
 * @param {string} [repo] `owner/name`
 * @returns {number|null}
 */
export function resolveIssueNumber(body, repo = DEFAULT_REPO) {
    if (typeof body !== 'string' || body === '') {
        return null;
    }
    const visible = stripCommentsAndFences(body);
    const bare = visible.match(/(?:^|[\s(])#(\d+)\b/);
    if (bare) {
        return Number(bare[1]);
    }
    const escaped = repo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const url = visible.match(new RegExp(`https?://github\\.com/${escaped}/(?:issues|pull)/(\\d+)`, 'i'));
    return url ? Number(url[1]) : null;
}

/**
 * issue-is-ready (pure half) -- true when the referenced issue's labels do NOT
 * include `Not Ready for Work!`. The caller fetches the labels; this only judges.
 *
 * @param {Array<{name: string}|string>|null|undefined} issueLabels
 * @returns {boolean}
 */
export function isIssueReady(issueLabels) {
    if (!Array.isArray(issueLabels)) {
        return true;
    }
    return !issueLabels.some(label => {
        const name = typeof label === 'string' ? label : (label && label.name) || '';
        return name.trim() === NOT_READY_LABEL;
    });
}

/**
 * Scan a (comment-stripped) body for ATX headers that are NOT inside a fenced
 * code block. A `### Testing` merely quoted inside ``` ... ``` is example text,
 * not real template structure, so it must neither satisfy nor split a section.
 *
 * @param {string} strippedBody body with HTML comments already removed
 * @returns {{lines: string[], headers: Array<{level: number, idx: number, text: string}>}}
 */
function scanHeaders(strippedBody) {
    const lines = strippedBody.split('\n');
    const headers = [];
    let inFence = false;
    for (let i = 0; i < lines.length; i++) {
        if (/^[ \t]{0,3}(?:```|~~~)/.test(lines[i])) {
            inFence = !inFence;
            continue;
        }
        if (inFence) {
            continue;
        }
        const m = lines[i].match(/^[ \t]{0,3}(#{1,6})[ \t]+\S/);
        if (m) {
            headers.push({ level: m[1].length, idx: i, text: lines[i] });
        }
    }
    return { lines, headers };
}

/**
 * True when a header line is the given template section's header. `Screenshots?`
 * tolerates the singular/plural the template uses; `\b` stops it matching a longer
 * word ("Technicalities").
 *
 * @param {string} headerText
 * @param {string} section
 * @returns {boolean}
 */
function isSectionHeader(headerText, section) {
    return new RegExp(`^[ \\t]{0,3}#{1,6}[ \\t]+${section}s?\\b`, 'i').test(headerText);
}

/**
 * passes-pr-template -- the body follows the PR template: every template section
 * header is present (outside code fences), and each REQUIRED_FILLED_SECTIONS
 * section has real content under it. A section runs until the next header at the
 * SAME-OR-SHALLOWER level, or the next template section header -- so an author's
 * deeper sub-heading (`#### Approach`) stays part of the section rather than
 * ending it, while a sibling template header always bounds it. Fenced code under a
 * section counts as content. Strict and structural: no exemption, no
 * err-toward-passing.
 *
 * @param {string|null|undefined} body
 * @returns {{ok: boolean, missing: string[], empty: string[]}}
 */
export function evaluateTemplate(body) {
    const stripped = typeof body === 'string' ? stripHtmlComments(body) : '';
    const { lines, headers } = scanHeaders(stripped);
    const indexOf = {};
    for (const section of TEMPLATE_SECTIONS) {
        const hi = headers.findIndex(h => isSectionHeader(h.text, section));
        if (hi !== -1) {
            indexOf[section] = hi;
        }
    }
    const missing = TEMPLATE_SECTIONS.filter(s => !(s in indexOf));
    const empty = REQUIRED_FILLED_SECTIONS.filter(s => {
        if (!(s in indexOf)) {
            return false; // a missing header is reported as missing, not empty
        }
        const h = headers[indexOf[s]];
        let end = lines.length;
        for (let j = indexOf[s] + 1; j < headers.length; j++) {
            const isTemplateHeader = TEMPLATE_SECTIONS.some(t => isSectionHeader(headers[j].text, t));
            if (headers[j].level <= h.level || isTemplateHeader) {
                end = headers[j].idx;
                break;
            }
        }
        return (
            lines
                .slice(h.idx + 1, end)
                .join('\n')
                .trim() === ''
        );
    });
    return { ok: missing.length === 0 && empty.length === 0, missing, empty };
}

/**
 * ran-the-code (body heuristic) -- true when the body shows some sign the code
 * was actually run: a media embed/attachment, a fenced code block (output/logs),
 * or a written testimonial. Deliberately permissive. Does NOT apply the staff
 * exemption -- that is the caller's job (see buildStatuses).
 *
 * @param {string|null|undefined} body
 * @returns {boolean}
 */
export function hasDevRunEvidence(body) {
    if (typeof body !== 'string' || body === '') {
        return false;
    }
    const visible = stripHtmlComments(body);
    if (MEDIA_EMBED_RE.test(visible) || MEDIA_LINK_RE.test(visible) || MEDIA_ATTACHMENT_RE.test(visible) || FENCED_CODE_RE.test(visible)) {
        return true;
    }
    return TESTIMONIAL_RE.test(stripTemplateHeaders(visible));
}

// --- status assembly -----------------------------------------------------

/**
 * Clamp a description to GitHub's 140-char commit-status limit.
 *
 * @param {string} s
 * @returns {string}
 */
export function clamp(s) {
    return s.length <= 140 ? s : `${s.slice(0, 137)}...`;
}

/**
 * Assemble the five commit-status descriptors for a PR, in stable order.
 *
 * Pure: the caller resolves `issue` (the one network read) and passes the result
 * in. Each returned row is `{context, state, description}`, where `state` is a
 * GitHub commit-status state (`success` | `failure` | `error` | `pending`).
 *
 * issue-is-ready reads `issue`:
 *   {kind:'none'}            -> success, deferring the no-issue case to
 *                              references-issue (never double-fails it).
 *   {kind:'ok', number, labels} -> success/failure on the live labels.
 *   {kind:'error', number?}  -> `error` (transient; not the PR's fault).
 *   {kind:'skipped', number} -> `pending` (dry-run, no PAT; never posted).
 *
 * @param {{labels?: Array, body?: string|null, authorLogin?: string|null,
 *          issue?: {kind: string, number?: number, labels?: Array}}} input
 * @returns {Array<{context: string, state: string, description: string}>}
 */
export function buildStatuses({ labels, body, authorLogin, issue = { kind: 'none' } } = {}) {
    const rows = [];

    const priorityOk = hasPriorityLabel(labels);
    rows.push({
        context: contextFor(CHECK.priority),
        state: priorityOk ? 'success' : 'failure',
        description: priorityOk ? 'Has a Priority label.' : 'Add a `Priority: N` label (carried from the linked issue, or set it).'
    });

    const issueRefOk = hasIssueReference(body);
    rows.push({
        context: contextFor(CHECK.referencesIssue),
        state: issueRefOk ? 'success' : 'failure',
        description: issueRefOk ? 'Body references an issue.' : 'Reference an issue in the body: a bare `#NNNN` or a full issue URL.'
    });

    rows.push(issueReadyRow(issue));

    const template = evaluateTemplate(body);
    rows.push({
        context: contextFor(CHECK.passesTemplate),
        state: template.ok ? 'success' : 'failure',
        description: template.ok ? 'PR body follows the template.' : templateDetail(template)
    });

    const exempt = isStaffOrLead(authorLogin);
    const evidenceOk = exempt || hasDevRunEvidence(body);
    rows.push({
        context: contextFor(CHECK.ranTheCode),
        state: evidenceOk ? 'success' : 'failure',
        description: exempt
            ? `@${authorLogin} is staff/lead; evidence not required.`
            : evidenceOk
              ? 'Body shows the code was run.'
              : 'Show you ran it: a screenshot/recording, output in a code block, or "tested locally".'
    });

    return rows.map(r => ({ ...r, description: clamp(r.description) }));
}

/**
 * The issue-is-ready row for a resolved issue outcome.
 *
 * @param {{kind: string, number?: number, labels?: Array}} issue
 * @returns {{context: string, state: string, description: string}}
 */
function issueReadyRow(issue) {
    const context = contextFor(CHECK.issueIsReady);
    switch (issue.kind) {
        case 'ok': {
            const ready = isIssueReady(issue.labels);
            return {
                context,
                state: ready ? 'success' : 'failure',
                description: ready
                    ? `Referenced issue #${issue.number} is ready for work.`
                    : `Issue #${issue.number} is labeled "${NOT_READY_LABEL}" -- not ready to work on yet.`
            };
        }
        case 'error':
            return {
                context,
                state: 'error',
                description: `Could not read issue ${issue.number ? `#${issue.number}` : ''} labels (transient); it will re-run.`
            };
        case 'skipped':
            return {
                context,
                state: 'pending',
                description: `Dry-run: PAT not configured; readiness of #${issue.number} not checked.`
            };
        case 'none':
        default:
            return {
                context,
                state: 'success',
                description: 'No in-repo issue referenced; readiness not applicable (see references-issue).'
            };
    }
}

/**
 * Human detail for a failing template evaluation.
 *
 * @param {{missing: string[], empty: string[]}} t
 * @returns {string}
 */
function templateDetail(t) {
    const parts = [];
    if (t.missing.length) {
        parts.push(`missing section(s): ${t.missing.join(', ')}`);
    }
    if (t.empty.length) {
        parts.push(`fill in: ${t.empty.join(', ')}`);
    }
    return `PR body does not follow the template -- ${parts.join('; ')}.`;
}
