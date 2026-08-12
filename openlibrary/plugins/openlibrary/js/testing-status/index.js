/**
 * Orchestration controller for the /status Testing Environment table.
 *
 * The table is rendered server-side by macros/TestingEnvironment.html.jinja.
 * This controller never builds a row — it patches the volatile cells (PR tags,
 * commit/drift, on-toggle, header status) from a freshly fetched copy of the
 * page, so the template stays the single source of row markup.
 */

import { fetchStatusDocument, postAction } from './TestingStatusService';
import { sprintf } from '../i18n.js';

const POLL_INTERVAL_MS = 20000;
const CLOCK_INTERVAL_MS = 30000;

/**
 * English source strings and runtime fallback. The macro renders the
 * translated copies into the panel's data-i18n attribute; keep the keys and
 * the English text here in lockstep with it. Its msgids name their
 * placeholders for translators, but what arrives here is always `%s`, filled
 * in by sprintf().
 */
export const DEFAULT_STRINGS = {
    justNow: 'just now',
    noneSelected: 'None selected',
    selected: '%s selected',
    synced: 'synced %s',
    removing: 'Removing #%s…',
    updating: 'Updating #%s…',
    enabling: 'Enabling #%s…',
    disabling: 'Disabling #%s…',
    deploying: 'Deploying to testing…'
};

/**
 * @param {Element} el
 * @return {Object} DEFAULT_STRINGS overlaid with the element's translations.
 */
function stringsFromElement(el) {
    try {
        const raw = el.dataset.i18n;
        if (raw) return { ...DEFAULT_STRINGS, ...JSON.parse(raw) };
    } catch {
        // A malformed payload falls back to English rather than blanking the UI.
    }
    return DEFAULT_STRINGS;
}

/**
 * The panel controller. State lives on the instance rather than in module
 * globals so the timers, the formatter and the strings all stay attached to
 * the one panel they belong to.
 */
class TestingStatusPanel {
    /**
     * @param {Element} root The [data-testing-env] element.
     */
    constructor(root) {
        this.root = root;
        this.strings = stringsFromElement(root);
        // One formatter for the panel's lifetime: constructing an Intl object
        // negotiates locales, and this runs once per timestamp per tick.
        this.formatter = new Intl.RelativeTimeFormat(document.documentElement.lang || 'en', { numeric: 'auto' });
        this.pollTimer = null;
        this.lastSyncedAt = null;

        this.bind();
        this.refreshSelection();
        this.renderRelativeTimes();
        this.renderSyncLabel();

        // Keep the relative timestamps honest without polling the server.
        setInterval(() => {
            if (document.hidden) return;
            this.renderRelativeTimes();
            this.renderSyncLabel();
        }, CLOCK_INTERVAL_MS);
    }

    /**
     * Format a timestamp as a coarse relative string ("14 min ago").
     * @param {Date} date
     * @return {String}
     */
    relativeTime(date) {
        const seconds = Math.round((Date.now() - date.getTime()) / 1000);
        if (seconds < 60) return this.strings.justNow;

        const units = [
            ['day', 86400],
            ['hour', 3600],
            ['minute', 60]
        ];
        for (const [unit, secondsPer] of units) {
            if (seconds >= secondsPer) {
                return this.formatter.format(-Math.round(seconds / secondsPer), unit);
            }
        }
        return this.strings.justNow;
    }

    /**
     * Rewrite every <time data-relative-time> to a relative string, keeping the
     * machine-readable value in the title attribute.
     */
    renderRelativeTimes() {
        this.root.querySelectorAll('time[data-relative-time]').forEach((el) => {
            const stamp = el.getAttribute('datetime');
            if (!stamp) return;
            const date = new Date(stamp);
            if (Number.isNaN(date.getTime())) return;
            if (!el.dataset.absolute) {
                el.dataset.absolute = el.textContent.trim();
            }
            setText(el, this.relativeTime(date));
            el.title = el.dataset.absolute;
        });
    }

    renderSyncLabel() {
        const label = this.root.querySelector('[data-sync-label]');
        if (!label) return;
        setText(label, this.lastSyncedAt ? sprintf(this.strings.synced, this.relativeTime(this.lastSyncedAt)) : '');
    }

    /**
     * Show a transient message in the console strip at the foot of the panel.
     * @param {String} message Empty string hides the strip.
     */
    setToast(message) {
        const toast = this.root.querySelector('[data-toast]');
        if (!toast) return;
        toast.textContent = message;
        toast.hidden = !message;
    }

    /** Update the "N selected" label and enable/disable the bulk buttons. */
    refreshSelection() {
        const checked = this.root.querySelectorAll('input[name="prs"]:checked');
        const label = this.root.querySelector('[data-selected-count]');
        if (label) {
            label.textContent = checked.length
                ? sprintf(this.strings.selected, checked.length)
                : this.strings.noneSelected;
        }
        this.root.querySelectorAll('[data-bulk]').forEach((button) => {
            if (button.hasAttribute('data-no-selection')) return;
            button.disabled = checked.length === 0;
        });
    }

    /**
     * @return {String[]} PR numbers of the checked rows.
     */
    selectedPrs() {
        return Array.from(this.root.querySelectorAll('input[name="prs"]:checked')).map((cb) => cb.value);
    }

    /**
     * Patch volatile cells and the deploy section from a freshly fetched
     * document. Falls back to replacing the panel's contents when the set of
     * PRs has changed, since added or removed rows can't be patched in place.
     *
     * Either way the root element itself survives, so the delegated listeners
     * and the timers that reference it stay valid.
     *
     * @param {Document} doc Freshly fetched /status document.
     */
    applyUpdate(doc) {
        const incoming = doc.querySelector('[data-testing-env]');
        if (!incoming) return;

        const liveRows = Array.from(this.root.querySelectorAll('tr[data-pr]'));
        const incomingRows = Array.from(incoming.querySelectorAll('tr[data-pr]'));
        const sameRowSet =
            liveRows.length === incomingRows.length &&
            liveRows.every((row, i) => row.dataset.pr === incomingRows[i].dataset.pr);

        if (sameRowSet) {
            liveRows.forEach((row, i) => patchRow(row, incomingRows[i]));
            // The deploy section is a rendered plan, not a fixed control — its
            // state line, change list and button turn over together, so swap it
            // wholesale rather than patching the button's disabled attribute.
            // data-deploy-key is what the swap keys off: the markup itself can't
            // be compared once the browser has hydrated it and renderRelativeTimes
            // has rewritten its timestamps, and re-rendering on every tick would
            // pull the Deploy button out from under whoever is aiming at it.
            const liveDeploy = this.root.querySelector('[data-deploy-section]');
            const newDeploy = incoming.querySelector('[data-deploy-section]');
            if (liveDeploy && newDeploy && liveDeploy.dataset.deployKey !== newDeploy.dataset.deployKey) {
                liveDeploy.replaceWith(newDeploy);
            }
        } else {
            this.root.replaceChildren(...incoming.childNodes);
            this.refreshSelection();
            // The replacement markup carries the server's defaults, so re-assert
            // the one control whose state lives on this side.
            const autorefresh = this.root.querySelector('[data-autorefresh]');
            if (autorefresh) autorefresh.checked = Boolean(this.pollTimer);
        }

        this.lastSyncedAt = new Date();
        this.renderRelativeTimes();
        this.renderSyncLabel();
    }

    /**
     * Run an action, showing progress and patching the result back in.
     *
     * @param {String} action Endpoint path.
     * @param {Object} fields Form fields.
     * @param {String} message Progress text for the toast.
     */
    async runAction(action, fields, message) {
        this.setToast(message);
        try {
            this.applyUpdate(await postAction(action, fields));
            this.setToast('');
        } catch {
            // The server is the source of truth; a reload beats a half-patched table.
            window.location.reload();
        }
    }

    /** Poll once, ignoring transient failures so a blip doesn't kill the loop. */
    async poll() {
        // A backgrounded tab is still throttled rather than stopped, and each
        // tick costs a full page render server-side.
        if (document.hidden) return;
        try {
            this.applyUpdate(await fetchStatusDocument());
        } catch {
            // Leave the last known good state on screen.
        }
    }

    /**
     * @param {Boolean} enabled
     */
    setPolling(enabled) {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        if (enabled) {
            this.pollTimer = setInterval(() => this.poll(), POLL_INTERVAL_MS);
        }
    }

    /**
     * Attach every listener the panel needs.
     *
     * Delegated from the panel root rather than bound per element: applyUpdate()
     * replaces the contents of the volatile cells, which would silently discard
     * listeners bound directly to the inline row buttons inside them.
     */
    bind() {
        // closest() climbs past the panel, so every match is checked against it.
        const closestIn = (target, selector) => {
            const match = target.closest(selector);
            return match && this.root.contains(match) ? match : null;
        };

        this.root.addEventListener('click', (event) => {
            const rowAction = closestIn(event.target, '[data-row-action]');
            if (rowAction) {
                event.preventDefault();
                const pr = rowAction.dataset.pr;
                const action = rowAction.dataset.rowAction;
                const verb = action.endsWith('remove') ? this.strings.removing : this.strings.updating;
                this.runAction(action, { prs: [pr] }, sprintf(verb, pr));
                return;
            }

            const bulk = closestIn(event.target, '[data-bulk]');
            if (bulk) {
                event.preventDefault();
                const prs = this.selectedPrs();
                if (!prs.length && !bulk.hasAttribute('data-no-selection')) return;
                // The button's own label is already translated server-side.
                this.runAction(bulk.dataset.bulk, { prs }, `${bulk.textContent.trim()}…`);
                return;
            }

            if (closestIn(event.target, '[data-deploy]')) {
                event.preventDefault();
                this.runAction('/status/deploy', {}, this.strings.deploying);
            }
        });

        this.root.addEventListener('change', (event) => {
            const selectAll = event.target.closest('[data-select-all]');
            if (selectAll) {
                this.root.querySelectorAll('input[name="prs"]').forEach((cb) => {
                    cb.checked = selectAll.checked;
                });
            }
            if (selectAll || event.target.matches('input[name="prs"]')) {
                this.refreshSelection();
            }
        });

        this.root.addEventListener('ol-toggle-change', (event) => {
            const { checked } = event.detail;

            if (event.target.matches('[data-autorefresh]')) {
                this.setPolling(checked);
                return;
            }

            const rowToggle = event.target.closest('[data-row-toggle]');
            if (rowToggle) {
                const pr = rowToggle.dataset.pr;
                this.runAction(
                    checked ? '/status/enable' : '/status/disable',
                    { prs: [pr] },
                    sprintf(checked ? this.strings.enabling : this.strings.disabling, pr)
                );
            }
        });

        // Catch up on whatever changed while the tab was in the background.
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.pollTimer) this.poll();
        });
    }
}

/**
 * Write text only when it differs, so a tick over an unchanged panel doesn't
 * dirty layout.
 * @param {Element} el
 * @param {String} text
 */
function setText(el, text) {
    if (el.textContent !== text) el.textContent = text;
}

/**
 * Patch one row's volatile cells from its freshly fetched counterpart.
 *
 * Which cells are volatile is declared by the template, as [data-cell]: the
 * markup and the list of what to repaint stay one thing.
 *
 * Cells are compared before they are written: replacing markup that hasn't
 * changed would tear down and re-upgrade an <ol-toggle> — shadow root, form
 * association and focus with it — on every poll.
 *
 * @param {Element} row Live row.
 * @param {Element} source Same row from the fetched document.
 */
function patchRow(row, source) {
    if (row.className !== source.className) row.className = source.className;

    const sourceCells = indexCells(source);
    row.querySelectorAll('[data-cell]').forEach((target) => {
        const replacement = sourceCells[target.dataset.cell];
        if (!replacement) return;

        // A toggle is state, not markup: flip it in place so the element the
        // user just clicked survives the round trip.
        const toggle = target.querySelector('ol-toggle');
        const newToggle = replacement.querySelector('ol-toggle');
        if (toggle && newToggle) {
            toggle.checked = newToggle.hasAttribute('checked');
            return;
        }

        if (target.innerHTML !== replacement.innerHTML) {
            target.innerHTML = replacement.innerHTML;
        }
    });
}

/**
 * @param {Element} row
 * @return {Object<String, Element>} The row's [data-cell] elements by name.
 */
function indexCells(row) {
    const cells = {};
    row.querySelectorAll('[data-cell]').forEach((cell) => {
        cells[cell.dataset.cell] = cell;
    });
    return cells;
}

/**
 * Entry point. Called from plugins/openlibrary/js/index.js when the panel
 * is present on the page.
 *
 * @param {Element} root The [data-testing-env] element.
 */
export function init(root) {
    new TestingStatusPanel(root);
}
