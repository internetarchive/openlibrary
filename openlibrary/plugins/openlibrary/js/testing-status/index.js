/**
 * Orchestration controller for the /status Testing Environment table.
 *
 * The table is rendered server-side by macros/TestingEnvironment.html.jinja.
 * Every action posts to the endpoint the markup already names and gets the
 * re-rendered page back, so the template stays the single source of markup
 * and this controller never builds a row.
 */

import { postAction } from './TestingStatusService';
import { sprintf } from '../i18n.js';

/**
 * English source strings and runtime fallback. The macro renders the
 * translated copies into the panel's data-i18n attribute; keep the keys and
 * the English text here in lockstep with it. Its msgids name their
 * placeholders for translators, but what arrives here is always `%s`, filled
 * in by sprintf().
 */
export const DEFAULT_STRINGS = {
    noneSelected: 'None selected',
    selected: '%s selected',
    removing: 'Removing #%s…',
    updating: 'Updating #%s…',
    enabling: 'Enabling #%s…',
    disabling: 'Disabling #%s…',
    deploying: 'Deploying to testing…'
};

/**
 * Attributes that mark a control worth refocusing after an update, most
 * specific first. See focusedSelector().
 */
const FOCUS_ATTRS = ['data-row-toggle', 'data-row-action', 'data-bulk', 'data-deploy'];

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
 * globals so the strings stay attached to the one panel they belong to.
 */
class TestingStatusPanel {
    /**
     * @param {Element} root The [data-testing-env] element.
     */
    constructor(root) {
        this.root = root;
        this.strings = stringsFromElement(root);

        this.bind();
        this.refreshSelection();
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
     * Swap in the panel from a freshly rendered document. The root element
     * itself survives, so the delegated listeners that reference it stay valid.
     *
     * @param {Document} doc Freshly fetched /status document.
     */
    applyUpdate(doc) {
        const incoming = doc.querySelector('[data-testing-env]');
        if (!incoming) return;

        const focused = focusedSelector(this.root);
        this.root.replaceChildren(...incoming.childNodes);
        this.refreshSelection();
        // The control that triggered this update was replaced along with the
        // rest of the panel; put focus back on its successor.
        if (focused) restoreFocus(this.root.querySelector(focused));
    }

    /**
     * Run an action, showing progress and swapping the result back in.
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
            // The server is the source of truth; a reload beats a stale table.
            window.location.reload();
        }
    }

    /**
     * Attach every listener the panel needs.
     *
     * Delegated from the panel root rather than bound per element: applyUpdate()
     * replaces the panel's contents, which would silently discard listeners
     * bound directly to the row buttons inside it.
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
            const rowToggle = event.target.closest('[data-row-toggle]');
            if (!rowToggle) return;

            const { checked } = event.detail;
            const pr = rowToggle.dataset.pr;
            this.runAction(
                checked ? '/status/enable' : '/status/disable',
                { prs: [pr] },
                sprintf(checked ? this.strings.enabling : this.strings.disabling, pr)
            );
        });
    }
}

/**
 * Describe the focused control so it can be found again in the replacement
 * markup. Returns null when focus is outside the panel, or on something the
 * swap doesn't disturb.
 *
 * @param {Element} root
 * @return {String|null} A selector matching the control, e.g.
 *   '[data-row-toggle][data-pr="1234"]'.
 */
function focusedSelector(root) {
    // A shadow-DOM control reports its host here, which is what the selectors
    // below match on anyway.
    const active = document.activeElement;
    if (!active || !root.contains(active)) return null;

    const attr = FOCUS_ATTRS.find((name) => active.hasAttribute(name));
    if (!attr) return null;

    const value = active.getAttribute(attr);
    const pr = active.dataset.pr;
    return `[${attr}${value ? `="${value}"` : ''}]${pr ? `[data-pr="${pr}"]` : ''}`;
}

/**
 * Focus a control in the replacement markup, once it can take focus: a
 * freshly inserted <ol-toggle> delegates focus to a button its first render
 * hasn't produced yet, so focusing it any earlier lands nowhere.
 *
 * @param {Element|null} el
 */
async function restoreFocus(el) {
    if (!el) return;
    // undefined on a plain <button>, which is already focusable.
    await el.updateComplete;
    el.focus();
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
