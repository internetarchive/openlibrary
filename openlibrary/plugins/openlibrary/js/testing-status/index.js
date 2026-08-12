/**
 * Progressive enhancement for the /status Testing Environment panel.
 *
 * The panel is rendered server-side by macros/TestingEnvironment.html.jinja and
 * is fully operable without this file: every control is a submit button whose
 * formaction names an endpoint that redirects back to /status. All this adds is
 * doing that round trip with fetch and swapping the result in, so the page
 * doesn't reload. It never builds a row — the template stays the single source
 * of markup.
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
        // Server-rendered they start enabled, so a no-JS click on an empty
        // selection posts nothing and the endpoint bounces straight back.
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

        // The deploy banners are rendered outside the panel, so swapping only
        // the panel would drop them: a failed deploy would come back looking
        // exactly like one that changed nothing.
        const messages = document.querySelector('[data-testing-messages]');
        const incomingMessages = doc.querySelector('[data-testing-messages]');
        if (messages && incomingMessages) {
            messages.replaceChildren(...incomingMessages.childNodes);
        }

        const focused = focusedSelector(this.root);
        this.root.replaceChildren(...incoming.childNodes);
        this.refreshSelection();
        // The control that triggered this update was replaced along with the
        // rest of the panel; put focus back on its successor.
        if (focused) {
            const successor = this.root.querySelector(focused);
            if (successor) successor.focus();
        }
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
     * What a button posts and what to say while it posts, or null to let the
     * browser submit it normally.
     *
     * Every case reads its endpoint from the same formaction the plain form
     * post would use, so the two paths can't disagree about where they go.
     *
     * @param {HTMLButtonElement} button
     * @return {{fields: Object, message: String}|null}
     */
    planFor(button) {
        const action = button.getAttribute('formaction');
        const pr = button.dataset.pr;

        if (button.hasAttribute('data-row-toggle')) {
            const verb = action.endsWith('disable') ? this.strings.disabling : this.strings.enabling;
            return { fields: { prs: [pr] }, message: sprintf(verb, pr) };
        }
        if (button.hasAttribute('data-row-action')) {
            const verb = action.endsWith('remove') ? this.strings.removing : this.strings.updating;
            return { fields: { prs: [pr] }, message: sprintf(verb, pr) };
        }
        if (button.hasAttribute('data-bulk')) {
            const prs = this.selectedPrs();
            if (!prs.length && !button.hasAttribute('data-no-selection')) return null;
            // The button's own label is already translated server-side.
            return { fields: { prs }, message: `${button.textContent.trim()}…` };
        }
        if (button.hasAttribute('data-deploy')) {
            return { fields: {}, message: this.strings.deploying };
        }
        return null;
    }

    /**
     * Attach every listener the panel needs.
     *
     * Delegated from the panel root rather than bound per element: applyUpdate()
     * replaces the panel's contents, which would silently discard listeners
     * bound directly to the buttons inside it.
     */
    bind() {
        this.root.addEventListener('click', (event) => {
            // closest() climbs past the panel, so the match is checked against it.
            const button = event.target.closest('button[formaction]');
            if (!button || !this.root.contains(button)) return;

            const plan = this.planFor(button);
            if (!plan) return;
            event.preventDefault();
            this.runAction(button.getAttribute('formaction'), plan.fields, plan.message);
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
    const active = document.activeElement;
    if (!active || !root.contains(active)) return null;

    const attr = FOCUS_ATTRS.find((name) => active.hasAttribute(name));
    if (!attr) return null;

    // A row control is unique by its PR. Deliberately not keyed on formaction:
    // a toggle's flips to the opposite endpoint in the very markup we're
    // looking it up in. The bulk buttons have no PR and differ only by where
    // they post, so those key on formaction instead.
    if (active.dataset.pr) return `[${attr}][data-pr="${active.dataset.pr}"]`;
    const action = active.getAttribute('formaction');
    return action ? `[${attr}][formaction="${action}"]` : `[${attr}]`;
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
