/**
 * FormAssociatedMixin — makes a Lit component a form-associated custom element
 * (FACE), so it submits with a `<form>`, participates in reset, and is disabled
 * by an ancestor `<fieldset disabled>`, like a native `<input>`.
 *
 * A control rendered in shadow DOM is otherwise invisible to the surrounding
 * form. `ElementInternals` fixes that. Supported on our floor (Safari 16.4+).
 *
 * Consumers must provide a `formValue` getter and call `_syncFormValue()`
 * whenever it changes; `formReset()` is optional. See the example below.
 *
 * @example
 *   export class OlToggle extends FormAssociatedMixin(FocusableHostMixin(LitElement)) {
 *       get formValue() { return this.checked ? this.value : null; }
 *       formReset() { this.checked = this._defaultChecked; }
 *       firstUpdated() { this._syncFormValue(); }
 *       updated(c) { if (c.has('checked') || c.has('value')) this._syncFormValue(); }
 *   }
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
    };

    /** @param {...any} args */
    constructor(...args) {
        super(...args);
        // Absent in some test environments (older jsdom); degrade to
        // "works, just not form-aware" rather than throwing at construction.
        try {
            this._internals = this.attachInternals?.() ?? null;
        } catch {
            this._internals = null;
        }
    }

    /** @returns {ElementInternals|null} */
    get internals() {
        return this._internals;
    }

    /** @returns {HTMLFormElement|null} The form this control belongs to. */
    get form() {
        return this._internals?.form ?? null;
    }

    /** @returns {NodeList|HTMLLabelElement[]} Labels associated with this control. */
    get labels() {
        return this._internals?.labels ?? [];
    }

    /** @returns {ValidityState|null} */
    get validity() {
        return this._internals?.validity ?? null;
    }

    /** @returns {string} */
    get validationMessage() {
        return this._internals?.validationMessage ?? '';
    }

    /** @returns {boolean} Whether this control is a candidate for validation. */
    get willValidate() {
        return this._internals?.willValidate ?? false;
    }

    /** @returns {boolean} True when the control satisfies its constraints. */
    checkValidity() {
        return this._internals?.checkValidity() ?? true;
    }

    /** @returns {boolean} Like {@link checkValidity}, but reports to the user. */
    reportValidity() {
        return this._internals?.reportValidity() ?? true;
    }

    /**
     * Override point. The value(s) to submit with the form.
     *
     * @returns {string|FormData|File|null} A string submits under `name`; a
     *   `FormData` submits multiple entries (you own the keys); `null`
     *   contributes nothing, e.g. an unchecked switch.
     */
    get formValue() {
        return null;
    }

    /**
     * Push the current {@link formValue} into the form. Call after the value
     * changes, and once initially.
     *
     * @returns {void}
     */
    _syncFormValue() {
        this._internals?.setFormValue(this.formValue);
    }

    /**
     * Called by the browser when an ancestor `<fieldset disabled>` disables this
     * control. Mirrored onto `disabled` so visuals and interaction follow.
     *
     * @override
     * @param {boolean} disabled
     * @returns {void}
     */
    formDisabledCallback(disabled) {
        this.disabled = disabled;
    }

    /**
     * Called by the browser on `<form>.reset()`. Delegates to the consumer's
     * optional `formReset()`, then resyncs so the form sees the reset value.
     *
     * @override
     * @returns {void}
     */
    formResetCallback() {
        this.formReset?.();
        this._syncFormValue();
    }

    /**
     * Called by the browser to restore state on history navigation or autofill.
     * Delegates to the consumer's optional `formStateRestore(state, mode)` hook
     * — our own name, not a platform API; no component implements it yet.
     *
     * @override
     * @param {File|string|FormData} state
     * @param {"restore"|"autocomplete"} mode
     * @returns {void}
     */
    formStateRestoreCallback(state, mode) {
        this.formStateRestore?.(state, mode);
        this._syncFormValue();
    }
};
