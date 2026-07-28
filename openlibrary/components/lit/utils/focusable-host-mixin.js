/**
 * FocusableHostMixin — makes a LitElement custom element behave as a single
 * focusable leaf in the document tab order, even when its actual focusable
 * element lives in its shadow DOM.
 *
 * Why this exists
 * ---------------
 * A consumer-level component (e.g. <ol-chip>, <ol-options-popover>) usually
 * renders a <button> inside its shadow root. Two things then go wrong by
 * default for any outer focus trap that doesn't pierce shadow DOM:
 *
 *   1. `querySelectorAll('button, [tabindex]…')` on light DOM doesn't find
 *      the shadow button — the component is invisible to the trap.
 *   2. Calling `host.focus()` focuses the *host*, not the inner button, so
 *      the focus ring lands on nothing visible.
 *
 * This mixin fixes both at once:
 *
 *   - Sets `tabindex="0"` on the host in connectedCallback (only if the
 *     consumer hasn't set one). The host now matches the standard focusable
 *     selector and outer traps discover it.
 *   - Uses `delegatesFocus: true` on the shadow root, so the browser
 *     forwards `host.focus()` to the first focusable inside the shadow root
 *     AND `:focus-visible` fires correctly on the inner element (this is the
 *     reason a manual focus() override is not enough — `:focus-visible` is a
 *     UA heuristic, not a CSS pseudo-class we can opt into).
 *
 * Specifying a non-default focus target
 * -------------------------------------
 * `delegatesFocus` forwards to the first focusable in DOM order. When a
 * component has multiple focusables in its shadow root and the desired
 * target is not the first one, override `_focusTarget`:
 *
 *   get _focusTarget() {
 *       return this.shadowRoot?.querySelector('.my-button');
 *   }
 *
 * Returning `null` (the default) keeps the `delegatesFocus` behavior.
 *
 * @template {new (...args: any[]) => import('lit').LitElement} T
 * @param {T} BaseClass
 */
export const FocusableHostMixin = (BaseClass) => class extends BaseClass {
    static shadowRootOptions = {
        ...BaseClass.shadowRootOptions,
        delegatesFocus: true,
    };

    connectedCallback() {
        super.connectedCallback?.();
        if (!this.hasAttribute('tabindex')) {
            this.setAttribute('tabindex', '0');
        }
    }

    /**
     * Override point. Return the element inside the shadow root that should
     * receive focus when `host.focus()` is called. Return `null` to use the
     * default `delegatesFocus` behavior (focus the first focusable).
     * @returns {HTMLElement|null}
     */
    get _focusTarget() {
        return null;
    }

    /** @override */
    focus(options) {
        const target = this._focusTarget;
        if (target?.focus) target.focus(options);
        else super.focus(options);
    }
};
