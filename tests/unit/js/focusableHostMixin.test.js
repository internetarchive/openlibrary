import { FocusableHostMixin } from '../../../openlibrary/components/lit/utils/focusable-host-mixin.js';

// We test the mixin against a stand-in for LitElement: a plain HTMLElement
// subclass that satisfies the parts of the contract the mixin reads from
// (`shadowRootOptions`, `connectedCallback`, `focus`). This keeps the test
// independent of a Lit transform in Jest.
class MockBase extends HTMLElement {
    static shadowRootOptions = { mode: 'open' };

    constructor() {
        super();
        this.attachShadow(this.constructor.shadowRootOptions);
    }
}

// Each test scenario gets its own tag, since `customElements.define` is
// global and one-shot per name.
function defineFocusableElement(tagName, { renderHTML = '', focusTargetSelector = null } = {}) {
    const cls = class extends FocusableHostMixin(MockBase) {
        connectedCallback() {
            // Real consumers extend LitElement (which defines connectedCallback);
            // MockBase is a bare HTMLElement, so guard the super call.
            super.connectedCallback?.();
            if (!this.shadowRoot.innerHTML) this.shadowRoot.innerHTML = renderHTML;
        }
        get _focusTarget() {
            return focusTargetSelector
                ? this.shadowRoot.querySelector(focusTargetSelector)
                : null;
        }
    };
    customElements.define(tagName, cls);
    return cls;
}

defineFocusableElement('mixin-test-default', {
    renderHTML: '<button class="trigger">trigger</button><button class="other">other</button>',
});

defineFocusableElement('mixin-test-with-target', {
    renderHTML: '<button class="trigger">trigger</button><button class="other">other</button>',
    focusTargetSelector: '.trigger',
});

afterEach(() => {
    document.body.innerHTML = '';
});

describe('FocusableHostMixin', () => {
    test('does NOT add a host tabindex (avoids the delegatesFocus double tab stop)', () => {
        // The inner native focusable is tabbable on its own, and our focus
        // traps find it via the shadow-piercing walker — so the host must not
        // be a second tab stop. See docs/ai/web-components.md (Focus and Shadow DOM).
        const el = document.createElement('mixin-test-default');
        document.body.appendChild(el);

        expect(el.hasAttribute('tabindex')).toBe(false);
    });

    test('leaves a consumer-provided tabindex untouched', () => {
        const el = document.createElement('mixin-test-default');
        el.setAttribute('tabindex', '-1');
        document.body.appendChild(el);

        expect(el.getAttribute('tabindex')).toBe('-1');
    });

    test('exposes shadowRootOptions with delegatesFocus: true and preserves base options', () => {
        const Ctor = customElements.get('mixin-test-default');
        expect(Ctor.shadowRootOptions.delegatesFocus).toBe(true);
        // Carries the base's mode forward — important guard against a
        // future refactor that clobbers other options.
        expect(Ctor.shadowRootOptions.mode).toBe('open');
    });

    test('focus() forwards to _focusTarget when the override returns an element', () => {
        const el = document.createElement('mixin-test-with-target');
        document.body.appendChild(el);

        const trigger = el.shadowRoot.querySelector('.trigger');
        const spy = jest.spyOn(trigger, 'focus');

        el.focus({ preventScroll: true });

        expect(spy).toHaveBeenCalledTimes(1);
        expect(spy).toHaveBeenCalledWith({ preventScroll: true });
    });

    test('focus() falls back to HTMLElement.focus when _focusTarget is null', () => {
        const el = document.createElement('mixin-test-default');
        document.body.appendChild(el);

        const trigger = el.shadowRoot.querySelector('.trigger');
        const other = el.shadowRoot.querySelector('.other');
        const triggerSpy = jest.spyOn(trigger, 'focus');
        const otherSpy = jest.spyOn(other, 'focus');

        expect(() => el.focus()).not.toThrow();
        // We don't programmatically focus a specific inner element — that's
        // the delegatesFocus opt-in's job at the browser layer (untestable
        // in jsdom; verified above via the shadowRootOptions assertion).
        expect(triggerSpy).not.toHaveBeenCalled();
        expect(otherSpy).not.toHaveBeenCalled();
    });
});
