/**
 * FormAssociatedMixin — turns a Lit component into a real form control (a
 * "form-associated custom element", FACE) so it submits with a `<form>`,
 * participates in reset, and carries default ARIA semantics — the same way a
 * native `<input>`/`<select>` would.
 *
 * Why: a control rendered in shadow DOM (e.g. <ol-toggle>'s switch, the radios
 * inside <ol-options-popover>) is invisible to the surrounding form — the form
 * never sees its value. FACE fixes that via `ElementInternals`: the element
 * declares `static formAssociated = true`, grabs `this.attachInternals()`, and
 * calls `internals.setFormValue(...)` whenever its value changes. The browser
 * then submits that value under the element's `name`, fires
 * `formResetCallback` on `<form>.reset()`, and disables the control inside a
 * disabled `<fieldset>`. Broadly supported on our floor (Safari 16.4+).
 *
 * What a consumer must provide:
 *   1. `get formValue()` — the value(s) to submit. Return a string (single
 *      value, submitted under `name`), a `FormData` (multiple entries, for a
 *      multi-select — you own the keys), a `File`, or `null` to contribute
 *      nothing (e.g. an unchecked switch).
 *   2. A call to `this._syncFormValue()` whenever that value changes — the
 *      simplest place is `firstUpdated()` (initial value) plus `updated()`
 *      (subsequent changes), or directly in the change handler.
 *   3. Optionally `formReset()` — restore the control's default value on
 *      `<form>.reset()`. Capture the default once on connect.
 *
 * `name` is provided by this mixin (reflected, like a native control).
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
 */
export const FormAssociatedMixin = (BaseClass) => class extends BaseClass {
    static formAssociated = true;

    static properties = {
        ...BaseClass.properties,
        name: { type: String, reflect: true },
    };

    constructor(...args) {
        super(...args);
        // attachInternals() throws if the element isn't form-associated and is
        // absent in some test environments (older jsdom). Guard so an
        // unsupported environment degrades to "works, just not form-aware"
        // rather than throwing at construction.
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

    // ── Standard form-control reflection (delegated to ElementInternals) ──
    get form() {
        return this._internals?.form ?? null;
    }

    get labels() {
        return this._internals?.labels ?? [];
    }

    get validity() {
        return this._internals?.validity ?? null;
    }

    get validationMessage() {
        return this._internals?.validationMessage ?? '';
    }

    get willValidate() {
        return this._internals?.willValidate ?? false;
    }

    checkValidity() {
        return this._internals?.checkValidity() ?? true;
    }

    reportValidity() {
        return this._internals?.reportValidity() ?? true;
    }

    /**
     * Override point. The value(s) to submit with the form: a string, a
     * `FormData` (multi-value), a `File`, or `null` to contribute nothing.
     * @returns {string|FormData|File|null}
     */
    get formValue() {
        return null;
    }

    /**
     * Push the current {@link formValue} into the form. Call after the
     * component's value changes (and once initially).
     */
    _syncFormValue() {
        this._internals?.setFormValue(this.formValue);
    }

    // The browser calls this when the control is disabled by an ancestor
    // <fieldset disabled>. Mirror it onto the component's own `disabled` so its
    // visuals and interaction follow.
    formDisabledCallback(disabled) {
        this.disabled = disabled;
    }

    // <form>.reset(): restore the default value (consumer's formReset), then
    // resync so the form sees the reset value immediately.
    formResetCallback() {
        this.formReset?.();
        this._syncFormValue();
    }

    // Browser state restoration (history nav / autofill). Optional consumer hook.
    formStateRestoreCallback(state, mode) {
        this.formStateRestore?.(state, mode);
        this._syncFormValue();
    }
};
