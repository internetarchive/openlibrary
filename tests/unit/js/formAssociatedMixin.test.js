import { FormAssociatedMixin } from '../../../openlibrary/components/lit/utils/form-associated-mixin.js';

// As in focusableHostMixin.test.js, we test the mixin against a stand-in for
// LitElement: a plain HTMLElement subclass. Real ElementInternals needs a
// browser, so MockBase returns a fake internals object that records
// setFormValue calls — letting us assert the mixin's plumbing deterministically
// in jsdom.
class MockBase extends HTMLElement {
    static shadowRootOptions = { mode: 'open' };

    constructor() {
        super();
        this._fakeInternals = {
            setFormValue: jest.fn(),
            form: { id: 'f' },
            labels: ['label-el'],
        };
    }

    attachInternals() {
        return this._fakeInternals;
    }
}

// A checkbox-shaped consumer (mirrors ol-toggle's contract).
function defineToggleLike(tagName) {
    const cls = class extends FormAssociatedMixin(MockBase) {
        constructor() {
            super();
            this.checked = false;
            this.value = 'on';
            this.disabled = false;
        }
        get formAssociatedValue() {
            return this.checked ? this.value : null;
        }
        formAssociatedReset() {
            this.checked = false;
        }
    };
    customElements.define(tagName, cls);
    return cls;
}

// A multi-select consumer that submits a FormData (mirrors ol-select-popover).
function defineMultiSelectLike(tagName) {
    const cls = class extends FormAssociatedMixin(MockBase) {
        constructor() {
            super();
            this.name = 'langs';
            this.selected = [];
        }
        get formAssociatedValue() {
            if (this.selected.length === 0 || !this.name) return null;
            const data = new FormData();
            for (const v of this.selected) data.append(this.name, v);
            return data;
        }
    };
    customElements.define(tagName, cls);
    return cls;
}

defineToggleLike('face-toggle');
defineMultiSelectLike('face-multiselect');

afterEach(() => {
    document.body.innerHTML = '';
});

describe('FormAssociatedMixin', () => {
    test('marks the element form-associated and declares a reflected name property', () => {
        const Ctor = customElements.get('face-toggle');
        expect(Ctor.formAssociated).toBe(true);
        expect(Ctor.properties.name).toEqual({ type: String, reflect: true });
    });

    test('attaches ElementInternals', () => {
        const el = document.createElement('face-toggle');
        expect(el._internals).toBe(el._fakeInternals);
    });

    test('_syncFormValue pushes null when the control contributes nothing', () => {
        const el = document.createElement('face-toggle');
        el._syncFormValue();
        expect(el._internals.setFormValue).toHaveBeenCalledWith(null);
    });

    test('_syncFormValue pushes the value when checked', () => {
        const el = document.createElement('face-toggle');
        el.checked = true;
        el._syncFormValue();
        expect(el._internals.setFormValue).toHaveBeenLastCalledWith('on');
    });

    test('formResetCallback restores the default value and resyncs', () => {
        const el = document.createElement('face-toggle');
        el.checked = true;
        el.formResetCallback();
        expect(el.checked).toBe(false);
        // After reset the (now unchecked) control contributes nothing.
        expect(el._internals.setFormValue).toHaveBeenLastCalledWith(null);
    });

    test('formDisabledCallback mirrors the browser disabled state onto the host', () => {
        const el = document.createElement('face-toggle');
        el.formDisabledCallback(true);
        expect(el.disabled).toBe(true);
        el.formDisabledCallback(false);
        expect(el.disabled).toBe(false);
    });

    test('delegates form and labels to ElementInternals', () => {
        const el = document.createElement('face-toggle');
        expect(el.form).toEqual({ id: 'f' });
        expect(el.labels).toEqual(['label-el']);
    });

    test('formStateRestoreCallback resyncs so the form drops the pre-restore value', () => {
        const el = document.createElement('face-toggle');
        el.checked = true;
        el.formStateRestoreCallback();
        expect(el._internals.setFormValue).toHaveBeenLastCalledWith('on');
    });

    test('a multi-select submits one repeated entry per value via FormData', () => {
        const el = document.createElement('face-multiselect');
        el.selected = ['en', 'fr'];
        el._syncFormValue();
        const data = el._internals.setFormValue.mock.calls.at(-1)[0];
        expect(data).toBeInstanceOf(FormData);
        expect(data.getAll('langs')).toEqual(['en', 'fr']);
    });

    test('a multi-select contributes nothing when empty', () => {
        const el = document.createElement('face-multiselect');
        el._syncFormValue();
        expect(el._internals.setFormValue).toHaveBeenCalledWith(null);
    });
});
