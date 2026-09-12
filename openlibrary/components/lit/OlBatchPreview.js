import { LitElement, html, css, nothing } from 'lit';
import { translate } from './utils/labels.js';
import { DEFAULT_LABELS } from './workbench-labels.js';
import { api, olid } from '../../plugins/openlibrary/js/librarians/api.js';
import './OlDialog.js';
import './OLButton.js';
import './OlIcon.js';
import './OlBookCover.js';

const LEVEL_ORDER = { block: 0, warn: 1, info: 2, ok: 3 };
const LEVEL_ICON = { block: 'octagon-alert', warn: 'triangle-alert', info: 'info' };

/**
 * The preview → apply → undo dialog every batch action goes through.
 *
 * `show({ action, items, params, records, title })` runs a dry run against
 * POST /librarians/batch.json and renders what would change and what the
 * checks found. Blocks must be acknowledged (super-librarians only) before
 * Apply is enabled; librarians get Request instead, which files the batch in
 * the merge queue. After apply, the dialog shows the result and an Undo that
 * reverts the batch as a unit.
 *
 * `show({ mode: 'checks', action, items, href })` is the lighter form for the
 * merge pages, which happen elsewhere: it shows the checks and a Continue link.
 *
 * @element ol-batch-preview
 *
 * @prop {Boolean} canApply - Whether the viewer is a super-librarian
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-batch-applied - detail: { batch_id, action, status, keys }
 * @fires ol-batch-reverted - detail: { batch_id }
 */
export class OlBatchPreview extends LitElement {
    static properties = {
        canApply: { type: Boolean, attribute: 'can-apply' },
        labels: { type: Object },
        _open: { state: true },
        _request: { state: true },
        _preview: { state: true },
        _result: { state: true },
        _error: { state: true },
        _busy: { state: true },
        _overrides: { state: true },
        _comment: { state: true },
        _reverted: { state: true },
    };

    static styles = css`
        :host { display: contents; font-family: var(--font-family-body); }
        .body { display: grid; gap: var(--spacing-md); font-size: var(--font-size-body-small); color: var(--color-text); }
        .summary { flex: 1; min-width: 0; font-size: var(--font-size-label-medium); color: var(--color-text-muted); }
        .mode { color: var(--color-text-secondary); font-size: var(--font-size-label-medium); }
        h4 { margin: 0 0 var(--spacing-2xs); font-size: var(--font-size-body-medium); font-weight: var(--font-weight-semibold); color: var(--color-text); }
        /* Records as a ledger: one row per record, the survivor tinted. */
        .ledger { border: var(--border-width) solid var(--color-border-muted); border-radius: var(--border-radius-md); overflow: hidden; }
        .ledger .row { display: grid; grid-template-columns: 30px minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr); gap: var(--spacing-md); align-items: center; padding: var(--spacing-sm) var(--spacing-md); border-top: var(--border-width) solid var(--color-border-muted); }
        .ledger .row:first-child { border-top: 0; }
        .ledger .row[data-survivor] { background: var(--color-control-selected-bg); }
        .ledger ol-book-cover { width: 30px; }
        .ledger .t { display: flex; align-items: center; gap: var(--spacing-sm); min-width: 0; }
        .ledger .t a { font-weight: var(--font-weight-medium); color: inherit; text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .ledger .t a:hover { text-decoration: underline; }
        .ledger .s, .ledger .m { color: var(--color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
        .ledger .survives { flex: none; font-size: var(--font-size-label-small); font-weight: var(--font-weight-semibold); text-transform: uppercase; letter-spacing: 0.05em; padding: 0 var(--spacing-xs); border-radius: var(--border-radius-sm); background: var(--color-chip-neutral-bg); color: var(--color-chip-neutral-fg); }
        .ledger .more { display: block; color: var(--color-text-secondary); }
        /* Findings: one ruled list; the icon colour says block, warning or note. */
        .findings { margin: 0; padding: 0; list-style: none; }
        .finding { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: var(--spacing-sm); align-items: start; padding: var(--spacing-sm) 0; border-top: var(--border-width) solid var(--color-border-muted); }
        .finding:last-child { border-bottom: var(--border-width) solid var(--color-border-muted); }
        .finding ol-icon { margin-top: 1px; color: var(--color-text-secondary); }
        .finding[data-level="block"] ol-icon { color: var(--color-error-fg); }
        .finding[data-level="warn"] ol-icon { color: var(--color-warning-fg); }
        .finding[data-level="info"] { color: var(--color-text-secondary); }
        .finding p { margin: 0; }
        .finding .ev { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); margin-top: var(--spacing-3xs); font-size: var(--font-size-label-medium); }
        .finding label { display: inline-flex; gap: var(--spacing-xs); align-items: center; margin-top: var(--spacing-2xs); font-size: var(--font-size-label-medium); color: var(--color-text-secondary); cursor: pointer; }
        .changes { max-height: 40vh; overflow: auto; border: var(--border-width) solid var(--color-border-muted); border-radius: var(--border-radius-md); }
        table { border-collapse: collapse; width: 100%; font-size: var(--font-size-label-medium); }
        th, td { text-align: left; vertical-align: top; padding: var(--spacing-xs) var(--spacing-sm); border-bottom: var(--border-width) solid var(--color-border-muted); }
        th { position: sticky; top: 0; background: var(--color-surface-sunken); font-weight: var(--font-weight-semibold); color: var(--color-text-secondary); }
        tr:last-child td { border-bottom: 0; }
        td.k { font-family: var(--font-family-mono); white-space: nowrap; }
        .from { color: var(--color-text-muted); text-decoration: line-through; }
        .to { color: var(--color-text); }
        .arrow { color: var(--color-text-muted); padding: 0 var(--spacing-2xs); }
        textarea { width: 100%; box-sizing: border-box; font: inherit; font-size: 16px; padding: var(--spacing-xs); border: var(--border-input); border-radius: var(--border-radius-input); resize: vertical; min-height: 44px; }
        textarea:focus-visible { outline: none; border: var(--border-input-focused); box-shadow: var(--box-shadow-focus); }
        @media (hover: hover) and (pointer: fine) { textarea { font-size: var(--font-size-body-medium); } }
        .footer { display: flex; gap: var(--spacing-xs); justify-content: flex-end; align-items: center; flex-wrap: wrap; }
        .result { display: grid; gap: var(--spacing-xs); padding: var(--spacing-sm) var(--spacing-md); border-radius: var(--border-radius-md); background: var(--color-success-bg); border: var(--border-width) solid var(--color-success-border); }
        .result.requested { background: var(--color-info-bg); border-color: var(--color-info-border); }
        .result.reverted { background: var(--color-surface-sunken); border-color: var(--color-border-muted); }
        .error { padding: var(--spacing-sm) var(--spacing-md); border-radius: var(--border-radius-md); background: var(--color-error-bg); border: var(--border-width) solid var(--color-error-border); color: var(--color-error-fg); }
        .muted { color: var(--color-text-muted); }
        a { color: var(--color-link); }
    `;

    constructor() {
        super();
        this.canApply = false;
        this.labels = {};
        this._open = false;
        this._request = null;
        this._preview = null;
        this._result = null;
        this._error = null;
        this._busy = false;
        this._overrides = new Set();
        this._comment = '';
        this._reverted = false;
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /** Open the dialog for a batch (or, with mode 'checks', for a merge page). */
    async show(request) {
        this._request = request;
        this._preview = null;
        this._result = null;
        this._error = null;
        this._reverted = false;
        this._overrides = new Set();
        this._comment = '';
        this._open = true;
        await this.updateComplete;
        this.renderRoot.querySelector('ol-dialog').open = true;
        return this.runPreview();
    }

    close() {
        this._open = false;
        const dialog = this.renderRoot.querySelector('ol-dialog');
        if (dialog) dialog.open = false;
    }

    async runPreview() {
        const r = this._request;
        if (!r) return;
        this._busy = true;
        this._error = null;
        try {
            if (r.mode === 'checks') {
                const c = await api.checks(r.action, r.items.map((it) => it.key));
                this._preview = { warnings: c.warnings, changes: [], summary: r.summary || '', mode: 'checks', can_apply: true, label: r.label || r.action };
            } else {
                this._preview = await api.batch({ action: r.action, items: r.items, params: r.params || {}, dry_run: true });
            }
        } catch (e) {
            this._error = e.message;
        } finally {
            this._busy = false;
        }
    }

    get blocks() {
        return (this._preview?.warnings || []).filter((w) => w.level === 'block');
    }

    get canProceed() {
        if (!this._preview || this._busy) return false;
        if (this._preview.mode === 'checks') return true;
        const unacknowledged = this.blocks.some((w) => !this._overrides.has(w.code));
        if (unacknowledged) return false;
        return this._preview.docs_touched > 0 || this._request.action === 'flag';
    }

    async apply() {
        const r = this._request;
        const revisions = this._preview.revisions || {};
        const items = r.items.map((it) => {
            const key = this._preview.resolved?.[it.key] || it.key;
            return { key: it.key, expected_revision: revisions[key] ?? it.expected_revision ?? null };
        });
        this._busy = true;
        this._error = null;
        try {
            this._result = await api.batch({
                action: r.action,
                items,
                params: r.params || {},
                dry_run: false,
                overrides: [...this._overrides],
                comment: this._comment || null,
            });
            const keys = Object.keys(this._result.revisions || {}).concat(this._result.creates || []);
            this.dispatchEvent(new CustomEvent('ol-batch-applied', {
                bubbles: true,
                composed: true,
                detail: { batch_id: this._result.batch_id, action: r.action, status: this._result.status, keys },
            }));
        } catch (e) {
            this._error = e.status === 409 && e.detail?.stale ? this.t('conflict') : this.t('failed', { error: e.message });
        } finally {
            this._busy = false;
        }
    }

    async revert() {
        if (!this._result?.batch_id) return;
        this._busy = true;
        try {
            await api.batchRevert(this._result.batch_id);
            this._reverted = true;
            this.dispatchEvent(new CustomEvent('ol-batch-reverted', { bubbles: true, composed: true, detail: { batch_id: this._result.batch_id } }));
        } catch (e) {
            this._error = this.t('failed', { error: e.message });
        } finally {
            this._busy = false;
        }
    }

    toggleOverride(code, on) {
        const next = new Set(this._overrides);
        if (on) next.add(code); else next.delete(code);
        this._overrides = next;
    }

    fmt(v) {
        if (v === null || v === undefined || v === '') return '—';
        if (Array.isArray(v)) return v.map((x) => (typeof x === 'object' ? (x.key || JSON.stringify(x)) : String(x))).join(', ') || '—';
        if (typeof v === 'object') return v.key || JSON.stringify(v);
        return String(v);
    }

    /** Records the batch touches, as passed by the caller; empty for callers that only send keys. */
    get records() {
        return (this._request?.records || []).filter((r) => r && r.key);
    }

    /** The record that survives a merge: the plan's target, or the merge page's default (first). */
    get survivorKey() {
        if (this._preview?.target) return this._preview.target;
        if (this._preview?.mode === 'checks' && this._request?.action?.startsWith('merge')) return this.records[0]?.key;
        return null;
    }

    cardLines(r) {
        const n = (count, key) => (Number.isFinite(count) ? this.t(key, { count }) : '');
        const by = [...new Set((r.authors || []).map((a) => (typeof a === 'string' ? a : a?.name || '')))].filter(Boolean).join(', ');
        if (r.type === 'edition') return [by, [r.year, (r.publishers || [])[0], r.isbn].filter(Boolean).join(' · ')];
        if (r.type === 'author') return [r.dates || '', n(r.work_count, 'workCount')];
        return [by, [r.year, n(r.edition_count, 'editionCount')].filter(Boolean).join(' · ')];
    }

    /** The records as a ledger: one row each, the survivor tinted, so a long merge still scans. */
    renderRecords() {
        const records = this.records;
        if (!records.length) return nothing;
        const survivor = this.survivorKey;
        const shown = records.slice(0, 12);
        return html`
            <div class="ledger" role="table">
                ${shown.map((r) => {
        const title = r.title || olid(r.key);
        const [sub, meta] = this.cardLines(r);
        return html`
                    <div class="row" role="row" ?data-survivor=${r.key === survivor}>
                        <ol-book-cover size="small" src=${r.cover || ''} book-title=${title}></ol-book-cover>
                        <div class="t" role="cell">
                            <a href=${r.key} target="_blank" rel="noopener">${title}</a>
                            ${r.key === survivor ? html`<span class="survives">${this.t('survives')}</span>` : nothing}
                        </div>
                        <div class="s" role="cell" title=${sub}>${sub || nothing}</div>
                        <div class="m" role="cell">${meta || nothing}</div>
                    </div>`;
    })}
                ${records.length > shown.length ? html`<div class="row more">${this.t('moreRecords', { count: records.length - shown.length })}</div>` : nothing}
            </div>`;
    }

    renderWarning(w) {
        const overridable = (w.level === 'block' && this.canApply) || w.level === 'warn';
        const isChecks = this._preview?.mode === 'checks';
        const shown = new Set(this.records.map((r) => r.key));
        const evidence = (w.evidence || []).filter((e) => !shown.has(e));
        const level = w.level === 'block' || w.level === 'warn' ? w.level : 'info';
        return html`
            <li class="finding" data-level=${level}>
                <ol-icon name=${LEVEL_ICON[level]} size="sm" aria-label=${this.t(level === 'info' ? 'info' : level)}></ol-icon>
                <div>
                    <p>${w.key ? html`<a href=${w.key} target="_blank" rel="noopener">${olid(w.key)}</a> · ` : nothing}${w.text}</p>
                    ${evidence.length ? html`<div class="ev">${evidence.map((e) => html`<a href=${e} target="_blank" rel="noopener">${e.replace(/^https?:\/\/(www\.)?/, '').slice(0, 40)}</a>`)}</div>` : nothing}
                    ${overridable && !isChecks && !this._result ? html`
                        <label><input type="checkbox" .checked=${this._overrides.has(w.code)} @change=${(e) => this.toggleOverride(w.code, e.target.checked)}> ${this.t('override')}</label>
                    ` : nothing}
                </div>
            </li>`;
    }

    // One ruled list, blocks first, then warnings, then notes; the icon and its
    // colour carry the level, so a dozen findings still read as one list.
    renderWarnings() {
        const all = [...(this._preview?.warnings || [])].sort((a, b) => (LEVEL_ORDER[a.level] ?? 9) - (LEVEL_ORDER[b.level] ?? 9));
        if (!all.length) return nothing;
        return html`<ul class="findings">${all.map((w) => this.renderWarning(w))}</ul>`;
    }

    renderChanges() {
        const changes = this._preview?.changes || [];
        if (!changes.length) return html`<p class="muted">${this.t('noChanges')}</p>`;
        return html`
            <div class="changes">
                <table>
                    <thead><tr><th>${this.t('record')}</th><th>${this.t('field')}</th><th>${this.t('changes')}</th></tr></thead>
                    <tbody>
                        ${changes.slice(0, 400).map((c) => html`
                            <tr>
                                <td class="k"><a href=${c.key} target="_blank" rel="noopener">${olid(c.key)}</a></td>
                                <td>${c.field}</td>
                                <td><span class="from">${this.fmt(c.from)}</span><span class="arrow">→</span><span class="to">${this.fmt(c.to)}${c.to_key ? html` <span class="muted">(${olid(c.to_key)})</span>` : nothing}</span></td>
                            </tr>`)}
                        ${changes.length > 400 ? html`<tr><td colspan="3" class="muted">${this.t('more', { count: changes.length - 400 })}</td></tr>` : nothing}
                    </tbody>
                </table>
            </div>`;
    }

    renderResult() {
        const r = this._result;
        if (this._reverted) return html`<div class="result reverted"><strong>${this.t('undone')}</strong></div>`;
        if (r.status === 'requested') {
            return html`<div class="result requested"><strong>${this.t('requested')}</strong><span>#${r.batch_id} · <a href="/merges?mode=open">${this.t('batches')}</a></span></div>`;
        }
        return html`
            <div class="result">
                <strong>${this.t('applied')} · ${r.applied} ${r.failed ? html`· ${r.failed} failed` : nothing}</strong>
                <span>${this.t('solrLag')}</span>
                <span class="muted">#${r.batch_id} · ${r.summary || ''}</span>
            </div>`;
    }

    render() {
        if (!this._open) return nothing;
        const p = this._preview;
        const r = this._request || {};
        const isChecks = p?.mode === 'checks';
        const proceedLabel = isChecks ? this.t('open') : (p?.mode === 'request' ? this.t('request') : this.t('apply'));
        return html`
            <ol-dialog label=${r.title || p?.label || this.t('preview')} width="large" fullscreen-on-mobile @ol-after-close=${() => { this._open = false; }}>
                <div class="body" aria-busy=${this._busy ? 'true' : 'false'}>
                    ${this.renderRecords()}
                    ${p && !isChecks && p.mode === 'request' ? html`<span class="mode">${this.t('reviewNote')}</span>` : nothing}
                    ${this._error ? html`<div class="error" role="alert">${this._error}</div>` : nothing}
                    ${this._busy && !p ? html`<p class="muted">${this.t('working')}</p>` : nothing}
                    ${this._result ? this.renderResult() : nothing}
                    ${this.renderWarnings()}
                    ${p && !isChecks && !this._result ? html`<div><h4>${this.t('changes')}</h4>${this.renderChanges()}</div>` : nothing}
                    ${p && !isChecks && !this._result ? html`
                        <label><span class="mode">${this.t('comment')}</span>
                            <textarea rows="2" .value=${this._comment} @input=${(e) => { this._comment = e.target.value; }}></textarea>
                        </label>` : nothing}
                </div>
                <div slot="footer" class="footer">
                    ${p?.summary ? html`<span class="summary">${p.summary}</span>` : nothing}
                    ${this._result && !this._reverted && this._result.status === 'applied' ? html`
                        <ol-button variant="secondary" ?loading=${this._busy} @click=${this.revert}><ol-icon slot="icon-start" name="undo"></ol-icon>${this.t('undo')}</ol-button>` : nothing}
                    <ol-button variant="ghost" @click=${this.close}>${this._result ? this.t('close') : this.t('cancel')}</ol-button>
                    ${!this._result ? (isChecks
        ? html`<ol-button variant="primary" href=${r.href} target="_blank" rel="noopener" ?disabled=${!this.canProceed}>${proceedLabel}</ol-button>`
        : html`<ol-button variant="primary" ?disabled=${!this.canProceed} ?loading=${this._busy} @click=${this.apply}>${proceedLabel}</ol-button>`) : nothing}
                </div>
            </ol-dialog>`;
    }
}

customElements.define('ol-batch-preview', OlBatchPreview);
