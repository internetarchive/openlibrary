/**
 * FocusableHostMixin — for a component whose single focusable element lives in
 * its **own shadow root** (e.g. <ol-toggle>, <ol-chip>, <ol-options-popover>'s
 * shadow trigger). Makes `host.focus()` / clicks / `:focus-visible` behave as
 * if the host were that inner control.
 *
 * Uses `delegatesFocus: true` on the shadow root, so the browser forwards
 * `host.focus()` to the first focusable inside the shadow root AND
 * `:focus-visible` fires correctly on the inner element (a manual focus()
 * override alone can't do the latter — `:focus-visible` is a UA heuristic, not
 * a CSS pseudo-class we can opt into).
 *
 * Do NOT add `tabindex` to the host. The inner native focusable already
 * participates in the document tab order on its own, and a host `tabindex`
 * combined with `delegatesFocus` produces a double tab stop (host, then inner)
 * in native sequential navigation. Our manual focus traps (OlDialog/OlPopover)
 * find the inner focusable via the shadow-piercing walker in focus-utils.js
 * (`getTabbableElements`/`getTabbableFromSlot`), so they don't need the host to
 * be discoverable either. See docs/ai/focus-tabbing.md.
 *
 * NOT for: wrappers whose focusable is a slotted / light-DOM child (use a plain
 * LitElement — the trigger is the focusable, e.g. <ol-select-popover>), or
 * composites that route focus themselves (roving tabindex).
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
