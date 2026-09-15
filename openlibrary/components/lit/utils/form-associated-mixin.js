/**
 * FormAssociatedMixin — makes a Lit component a form-associated custom element
 * (FACE), so it submits with a `<form>`, participates in reset, and is disabled
 * by an ancestor `<fieldset disabled>`, like a native `<input>`.
 *
 * A control rendered in shadow DOM is otherwise invisible to the surrounding
 * form. `ElementInternals` fixes that. Supported on our floor (Safari 16.4+).
 *
 * Consumers must override `formAssociatedValue` and call `_syncFormValue()`
 * whenever it changes; `formAssociatedReset()` is optional. Both carry the
 * `formAssociated` prefix so they read as this mixin's contract rather than as
 * platform callbacks — the browser-called ones are named `form*Callback`.
 *
 * @example
 *   export class OlToggle extends FormAssociatedMixin(FocusableHostMixin(LitElement)) {
 *       get formAssociatedValue() { return this.checked ? this.value : null; }
 *       formAssociatedReset() { this.checked = this._defaultChecked; }
 *       firstUpdated() { this._syncFormValue(); }
 *       updated(c) { if (c.has('checked') || c.has('value')) this._syncFormValue(); }
 *   }
 *
 * Disabled state: an ancestor `<fieldset disabled>` reports through
 * `formDisabledCallback`, which is kept in `_formDisabled` — separate from the
 * consumer's own `disabled` property. Never write it back into `disabled`: that
 * reflects the `disabled` attribute onto the host, and an attribute-disabled
 * FACE stays disabled after the fieldset is re-enabled (the browser sees no
 * state change, so the callback never fires again). Consumers render and gate
 * on `isDisabled` (either source) and style with `:host(:disabled)`, which the
 * browser keeps in sync with both.
 *
 * @template {new (...args: any[]) => import('lit').LitElement} T
 * @param {T} BaseClass
 * @returns {T} The base class with form participation applied.
 */
export const FormAssociatedMixin = (BaseClass) => class extends BaseClass {
    static formAssociated = true;

    static properties = {
        ...BaseClass.properties,
        /** Read by the browser when creating the form. Must be specified for an element to take part in form submissions. */
        name: { type: String, reflect: true },
        /** Set by the browser via formDisabledCallback (ancestor `<fieldset disabled>`). Not reflected — see the class doc. */
        _formDisabled: { state: true },
    };

    /** @param {...any} args */
    constructor(...args) {
        super(...args);
        // Optional-chained for non-browser contexts where the method is absent;
        // it can't throw here, since this mixin sets formAssociated itself.
        this._internals = this.attachInternals?.() ?? null;
        this._formDisabled = false;
    }

    /**
     * Whether the control is disabled from either source: its own `disabled`
     * property or an ancestor `<fieldset disabled>`. Use this — not `disabled` —
     * to gate interaction and to set `?disabled` on inner controls.
     *
     * @returns {boolean}
     */
    get isDisabled() {
        return Boolean(this.disabled) || this._formDisabled;
    }

    /** @returns {HTMLFormElement|null} The form this control belongs to. */
    get form() {
        return this._internals?.form ?? null;
    }

    /** @returns {NodeList|HTMLLabelElement[]} Labels associated with this control. */
    get labels() {
        return this._internals?.labels ?? [];
    }

    /**
     * Override point. The value(s) to submit with the form.
     *
     * @returns {string|FormData|File|null} A string submits under `name`; a
     *   `FormData` submits multiple entries (you own the keys); `null`
     *   contributes nothing, e.g. an unchecked switch.
     */
    get formAssociatedValue() {
        return null;
    }

    /**
     * Push the current {@link formAssociatedValue} into the form. Call after the
     * value changes, and once initially.
     *
     * @returns {void}
     */
    _syncFormValue() {
        this._internals?.setFormValue(this.formAssociatedValue);
    }

    /**
     * Reflect `disabled` before render rather than after (Lit's default). The
     * browser answers the attribute change with a synchronous
     * `formDisabledCallback`, and a property set that late in an update is
     * dropped — the control would render one state behind.
     *
     * @param {Map<string, unknown>} changed
     * @returns {void}
     */
    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (changed.has('disabled')) this.toggleAttribute('disabled', Boolean(this.disabled));
    }

    /**
     * Called by the browser when the element's form-disabled state changes —
     * an ancestor `<fieldset disabled>` toggled, or the host's own `disabled`
     * attribute did. Recorded separately from `disabled`; see the class doc for
     * why it must not be mirrored back onto that property.
     *
     * @override
     * @param {boolean} disabled
     * @returns {void}
     */
    formDisabledCallback(disabled) {
        this._formDisabled = disabled;
    }

    /**
     * Called by the browser on `<form>.reset()`. Delegates to the consumer's
     * optional `formAssociatedReset()`, then resyncs so the form sees the value.
     *
     * @override
     * @returns {void}
     */
    formResetCallback() {
        this.formAssociatedReset?.();
        this._syncFormValue();
    }

    /**
     * Called by the browser to restore state on history navigation or autofill.
     * Resyncs so the form doesn't hold the pre-restore value.
     *
     * @override
     * @returns {void}
     */
    formStateRestoreCallback() {
        this._syncFormValue();
    }
};
