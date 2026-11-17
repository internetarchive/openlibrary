// The disclosure gate: decides what the code review bot may publish. `analyze` runs it before
// uploading the analysis and `post` runs it again before posting.
//
// check(review) withholds anything that is not a well-formed review. On success it returns
// `clean`, a copy with only the fields `post` renders; that copy is what gets uploaded and posted,
// so no unscanned field reaches a public surface. It also returns `findingsTotal` (null when the
// review is malformed) and `blocking`, the one bit the `code-review` status uses for a withheld
// review. `blocking` is false only for a publishable review, or a review withheld by the text scan
// whose findings are all low severity.
'use strict';

module.exports = {
    dimensions: {
        correctness: 'Correctness',
        security: 'Security',
        accessibility: 'Accessibility',
        test_coverage: 'Test coverage',
        styleguide: 'Styleguide'
    },
    severities: ['high', 'medium', 'low'],
    // Backstop for a security concern the model filed under another dimension or wrote into
    // prose. The model's own classification is the main control; this cannot catch every phrasing.
    // A false positive costs a withheld review; a false negative costs a disclosure.
    terms: /\b(secur\w*|vulnerab\w*|exploit\w*|attack\w*|malicious\w*|inject\w*|xss|cross[- ]site|csrf|xsrf|ssrf|rce|remote code|code execution|open[- ]redirect|traversal|privilege\w*|escalat\w* (to|privilege\w*)|(un)?authori[sz]\w*|impersonat\w*|exfiltrat\w*|(auth\w*|permission|access|login|csrf|validation) bypass\w*|bypass\w* (the )?(auth\w*|permission|access|login|csrf|validation)|(credential|secret|password|pii|personal data)s? (are |is )?leak\w*|leak\w* (of )?(the )?(credential|secret|password|pii|personal data|patron|user|reader)\w*|secrets?|credentials?|passwords?|api[- _]?keys?|(auth|access|api|session|csrf|bearer|oauth|refresh)[- _]?tokens?|cve-\d+|ghsa-\w+|deserializ\w*|pickle|shell\s*=\s*true|sql\w* (string|injection)|(concatenat|interpolat|format|substitut)\w* into (the |a )?(sql|query|shell|command)|(missing|no|without( an?)?|lacks?( an?)?) (auth\w*|permission|access|ownership|owner|csrf|host|origin) (check|validation|verification)\w*|without (checking|validating|verifying) the (host|origin|domain|scheme|redirect|owner\w*)|another (patron|user|account|reader)'?s|yaml\.load|httponly|samesite|unsaniti[sz]ed|sanitiz\w*|unescaped|clickjack\w*|denial of service|redos)\b/i,
    // Shapes that are not words, so they cannot sit inside the \b...\b list above.
    patterns:
        /\|\s*safe\b|\beval\s*\(|\bexec\s*\(|\bos\.system\b|\bMarkup\s*\(|x-forwarded-for|rate[- ]limit\w* (is |are )?(missing|absent)|(no|missing|without) rate[- ]limit/i,
    // Credential shapes, independent of the term list: a review must never carry one.
    secrets: /sk-ant-[\w-]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_\w{30,}|\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{6,}|-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    // What GitHub renders as plain text, so the scan sees the words a reader would: decode
    // character references (an unrecognised named one returns null and withholds), drop HTML
    // comments and tags, invisible format characters and combining marks, unwrap markdown
    // links and emphasis/code marks, and split identifiers (snake_case, camelCase) into words.
    // Every regex here is linear: model text is untrusted and can be large.
    entities: {
        amp: '&',
        lt: '<',
        gt: '>',
        quot: '"',
        apos: "'",
        nbsp: ' ',
        mdash: ' ',
        ndash: ' ',
        hellip: ' ',
        copy: ' ',
        reg: ' ',
        times: ' ',
        rarr: ' ',
        larr: ' '
    },
    plain(t) {
        const cp = n => (Number.isInteger(n) && n >= 0 && n <= 0x10ffff ? String.fromCodePoint(n) : ' ');
        let unknown = false;
        t = t
            .normalize('NFKC')
            .replace(/&#x([0-9a-f]{1,8});?/gi, (_, h) => cp(parseInt(h, 16)))
            .replace(/&#(\d{1,10});?/g, (_, d) => cp(Number(d)))
            .replace(/&([a-z][a-z0-9]{0,31});/gi, (_, n) =>
                Object.hasOwn(this.entities, n.toLowerCase()) ? this.entities[n.toLowerCase()] : ((unknown = true), ' ')
            );
        if (unknown) return null;
        // Two readings, both scanned. Tags stripped until none are left, so `sec<b>ret</b>` reads as
        // `secret`; and tags kept, because GitHub shows a tag inside a code span as text and stripping
        // can join or drop words a reader sees. Not an HTML sanitizer: the output is never published.
        let stripped = t;
        for (let prev = null; stripped !== prev;) {
            prev = stripped;
            stripped = stripped.replace(/<!--[\s\S]*?(-->|$)/g, '').replace(/<[^<>]*>/g, '');
        }
        return [stripped, t].map(r =>
            r
                .normalize('NFKD')
                .replace(/[\p{Cf}\p{M}]/gu, '')
                .replace(/\[([^[\]]*)\]\([^()]*\)/g, '$1')
                .replace(/[*`~]/g, '')
                .normalize('NFKC')
        );
    },
    // The same text with identifiers split into words. Scanned in addition to plain(), not
    // instead: splitting would break shapes like HttpOnly or a token's mixed case.
    words(t) {
        return t
            .replace(/_/g, ' ')
            .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
            .replace(/([A-Z])([A-Z][a-z])/g, '$1 $2');
    },
    // Longer published text than this is withheld rather than scanned.
    maxText: 65536,
    // A repository-relative path: no spaces, markdown, absolute paths or `..` segments.
    path: /^(?!.*(^|\/)\.\.(\/|$))[A-Za-z0-9_.][A-Za-z0-9_./-]*$/,
    // A GraphQL node id of an earlier review thread (PRRT_...). Ids only -- never published text.
    threadId: /^[A-Za-z0-9_=-]{1,128}$/,
    // Ticket compliance (code_review.md Step 5): a GitHub issue URL, at most one entry per linked
    // issue (the linked-issues step fetches at most 3), and the published result lists.
    ticketUrl: /^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9._-]+\/issues\/[1-9][0-9]{0,8}$/,
    maxTickets: 3,
    ticketLists: ['fully_compliant_requirements', 'not_compliant_requirements', 'requires_further_human_verification'],
    check(review) {
        try {
            return this.evaluate(review);
        } catch (e) {
            return { publish: false, findingsTotal: null, blocking: true };
        }
    },
    evaluate(review) {
        const no = { publish: false, findingsTotal: null, blocking: true };
        const str = v => typeof v === 'string';
        const absent = v => v === undefined || v === null;
        const line = v => absent(v) || (Number.isInteger(v) && v > 0);
        if (!review || typeof review !== 'object' || Array.isArray(review)) return no;
        const { dimensions: dims, findings } = review;
        if (!str(review.summary) || !Array.isArray(findings) || !dims || typeof dims !== 'object') return no;
        // `resolved`: ids of our earlier review threads the model judged fixed. `post` checks each
        // against the live threads before acting on it.
        if (!absent(review.resolved) && !(Array.isArray(review.resolved) && review.resolved.every(id => str(id) && this.threadId.test(id)))) return no;
        const clean = { summary: review.summary, dimensions: {}, findings: [], resolved: [...new Set(review.resolved || [])] };
        const counts = {};
        for (const f of findings) {
            if (!f || typeof f !== 'object' || !str(f.dimension) || !Object.hasOwn(this.dimensions, f.dimension)) return no;
            if (!this.severities.includes(f.severity) || !str(f.title) || !f.title.trim() || !str(f.body) || !f.body.trim()) return no;
            if (!line(f.line) || !line(f.start_line)) return no;
            if (!absent(f.path) && !(str(f.path) && this.path.test(f.path))) return no;
            if (!absent(f.suggestion) && !str(f.suggestion)) return no;
            counts[f.dimension] = (counts[f.dimension] || 0) + 1;
            const c = { dimension: f.dimension, severity: f.severity, title: f.title, body: f.body };
            for (const k of ['path', 'start_line', 'line', 'suggestion']) if (!absent(f[k])) c[k] = f[k];
            clean.findings.push(c);
        }
        for (const k of Object.keys(this.dimensions)) {
            const d = dims[k],
                n = counts[k] || 0;
            if (!d || typeof d !== 'object' || (d.status !== 'none' && d.status !== 'findings')) return no;
            if ((d.status === 'none') !== (n === 0)) return no;
            // The security note is never published, so it is neither required nor kept.
            if (k !== 'security' && d.status === 'none' && !(str(d.note) && d.note.trim())) return no;
            if (k !== 'security' && !absent(d.note) && !str(d.note)) return no;
            clean.dimensions[k] = k === 'security' ? { status: d.status } : { status: d.status, note: d.note };
        }
        // `ticket_compliance`: PR-Agent's TicketCompliance, one entry per linked issue. The three
        // result lists are published, so they are kept and scanned. `ticket_requirements` is the
        // model's working list and is never published, so it is dropped, and optional because
        // `post` re-checks the clean copy.
        const tc = review.ticket_compliance;
        if (!absent(tc) && !(Array.isArray(tc) && tc.length <= this.maxTickets)) return no;
        const items = v => Array.isArray(v) && v.every(s => str(s) && s.trim());
        clean.ticket_compliance = [];
        for (const t of tc || []) {
            if (!t || typeof t !== 'object' || Array.isArray(t) || !str(t.ticket_url) || !this.ticketUrl.test(t.ticket_url)) return no;
            if (clean.ticket_compliance.some(c => c.ticket_url === t.ticket_url)) return no;
            if (!absent(t.ticket_requirements) && !(items(t.ticket_requirements) && t.ticket_requirements.length)) return no;
            const c = { ticket_url: t.ticket_url };
            for (const k of this.ticketLists) {
                if (!absent(t[k]) && !items(t[k])) return no;
                c[k] = [...(t[k] || [])];
            }
            clean.ticket_compliance.push(c);
        }
        // A review the model itself flagged for security is always blocking.
        if (clean.dimensions.security.status !== 'none') return { publish: false, findingsTotal: clean.findings.length, blocking: true };
        const text = [clean.summary];
        for (const [k, d] of Object.entries(clean.dimensions)) if (k !== 'security') text.push(d.note);
        for (const f of clean.findings) text.push(f.title, f.body, f.suggestion, f.path);
        for (const t of clean.ticket_compliance) {
            text.push(t.ticket_url);
            for (const k of this.ticketLists) text.push(...t[k]);
        }
        // oxlint-disable-next-line eqeqeq -- loose on purpose: null or undefined
        const raw = text.filter(t => t != null).join('\n');
        // Withheld by the text scan below. The findings are still well formed, so they decide
        // `blocking`: a false positive on a review with no blocking findings can still pass.
        const withholdByText = { publish: false, findingsTotal: clean.findings.length, blocking: clean.findings.some(f => f.severity !== 'low') };
        if (raw.length > this.maxText) return withholdByText;
        const readings = this.plain(raw);
        if (readings === null) return withholdByText;
        for (const plain of readings) {
            if (this.secrets.test(plain)) return withholdByText;
            for (const t of [plain, this.words(plain)]) if (this.terms.test(t) || this.patterns.test(t)) return withholdByText;
        }
        return { publish: true, clean, findingsTotal: clean.findings.length, blocking: false };
    }
};
