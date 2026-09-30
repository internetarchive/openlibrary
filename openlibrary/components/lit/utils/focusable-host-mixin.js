/**
 * FocusableHostMixin — for a component whose single focusable element lives in
 * its **own shadow root** (e.g. <ol-toggle>, <ol-chip>). Makes `host.focus()` /
 * clicks / `:focus-visible` behave as if the host were that inner control.
 *
 * Uses `delegatesFocus: true`, which also makes `:focus-visible` fire on the
 * inner element — a `focus()` override alone can't do that.
 *
 * Do NOT add `tabindex` to the host: combined with `delegatesFocus` it produces
 * a double tab stop. Our focus traps find the inner element via the
 * shadow-piercing walker in focus-utils.js. See docs/ai/web-components.md.
 *
 * NOT for: wrappers whose focusable is a slotted / light-DOM child (use a plain
 * LitElement — the trigger is the focusable, e.g. <ol-select-popover> and
 * <ol-options-popover>), or composites that route focus themselves (roving
 * tabindex).
 *
 * @template {new (...args: any[]) => import('lit').LitElement} T
 * @param {T} BaseClass
 * @returns {T} The base class with focus delegation applied.
 */
export const FocusableHostMixin = (BaseClass) => class extends BaseClass {
    static shadowRootOptions = {
        ...BaseClass.shadowRootOptions,
        delegatesFocus: true,
    };

    /**
     * Override point for when the desired target isn't the first focusable in
     * DOM order, which is where `delegatesFocus` would otherwise send focus.
     *
     * @returns {HTMLElement|null} Element to focus, or null to keep the default.
     */
    get _focusTarget() {
        return null;
    }

    /**
     * @override
     * @param {FocusOptions} [options]
     * @returns {void}
     */
    focus(options) {
        const target = this._focusTarget;
        if (target?.focus) target.focus(options);
        else super.focus(options);
    }
};
