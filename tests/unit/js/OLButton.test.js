/**
 * <ol-button> rendering contract: it paints a real <button> / <a> in its own
 * shadow root, projects the author's label through a slot, mirrors host ARIA
 * onto the inner control, and acts on the enclosing form through a hidden
 * light-DOM proxy <button>. jsdom has no layout, so appearance (variants,
 * shapes, elevation) is CSS-only and verified in the browser / design page.
 * jsdom also has no <fieldset disabled> → formDisabledCallback plumbing and no
 * implicit submission (Enter in a text field); those live in
 * tests/e2e/ol-button-form.spec.ts.
 */
import '../../../openlibrary/components/lit/OLButton.js';

// jsdom has no attachInternals; give every ol-button a fake so the form
// plumbing can be asserted deterministically. Installed before any element is
// constructed (the constructor calls attachInternals?.()).
let fakeInternals;
beforeAll(() => {
    HTMLElement.prototype.attachInternals = function() {
        fakeInternals = { form: null };
        return fakeInternals;
    };
});
afterAll(() => {
    delete HTMLElement.prototype.attachInternals;
});

async function mount(attrs = {}, label = 'Label', parent = document.body) {
    const el = document.createElement('ol-button');
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    el.textContent = label;
    parent.appendChild(el);
    await el.updateComplete;
    return el;
}

const control = (el) => el.shadowRoot.querySelector('.control');
const proxy = (el) => el.querySelector(':scope > button');
// Click forwarding is deferred past event dispatch (setTimeout 0).
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function mountInForm(attrs, label = 'Go') {
    const form = document.createElement('form');
    document.body.appendChild(form);
    const submits = [];
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        submits.push(e);
    });
    const el = await mount(attrs, label, form);
    return { form, el, submits };
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('OLButton', () => {
    test('renders a <button> in its shadow root and slots the label', async() => {
        const el = await mount();
        expect(el.shadowRoot).not.toBeNull();
        // Nothing rendered into light DOM — the author's text stays put.
        expect(el.childNodes).toHaveLength(1);
        expect(el.textContent).toBe('Label');
        const btn = control(el);
        expect(btn.tagName).toBe('BUTTON');
        expect(btn.getAttribute('part')).toBe('control');
        const label = el.shadowRoot.querySelector('.label');
        expect(label.getAttribute('part')).toBe('label');
        const slot = label.querySelector('slot:not([name])');
        expect(slot.assignedNodes()[0].textContent).toBe('Label');
    });

    test('preserves node identity of slotted content', async() => {
        const el = document.createElement('ol-button');
        const span = document.createElement('span');
        span.textContent = 'One';
        el.appendChild(span);
        document.body.appendChild(el);
        await el.updateComplete;
        span.textContent = 'Two';
        const slot = el.shadowRoot.querySelector('slot:not([name])');
        expect(slot.assignedElements()[0]).toBe(span);
        expect(el.textContent).toBe('Two');
    });

    test('projects icon-start / icon-end into named slots inside the label', async() => {
        const el = document.createElement('ol-button');
        const start = document.createElement('svg');
        start.setAttribute('slot', 'icon-start');
        const end = document.createElement('svg');
        end.setAttribute('slot', 'icon-end');
        el.append(start, 'Label', end);
        document.body.appendChild(el);
        await el.updateComplete;
        const label = el.shadowRoot.querySelector('.label');
        const slots = [...label.querySelectorAll('slot')].map((sl) => sl.name);
        expect(slots).toEqual(['icon-start', '', 'icon-end']);
        expect(label.querySelector('slot[name="icon-start"]').assignedElements()[0]).toBe(start);
        expect(label.querySelector('slot[name="icon-end"]').assignedElements()[0]).toBe(end);
    });

    test('renders an <a> when href is set, passing link attributes through', async() => {
        const el = await mount({ href: '/borrow/OL1M', target: '_blank', rel: 'noopener', download: 'x.pdf' });
        const a = control(el);
        expect(a.tagName).toBe('A');
        expect(a.getAttribute('href')).toBe('/borrow/OL1M');
        expect(a.getAttribute('target')).toBe('_blank');
        expect(a.getAttribute('rel')).toBe('noopener');
        expect(a.getAttribute('download')).toBe('x.pdf');
        expect(a.hasAttribute('aria-disabled')).toBe(false);
    });

    test('a disabled link drops its href and sets aria-disabled', async() => {
        const el = await mount({ href: '/x', disabled: '' });
        const a = control(el);
        expect(a.hasAttribute('href')).toBe(false);
        expect(a.getAttribute('aria-disabled')).toBe('true');
    });

    test('a loading link is also inert and reports aria-busy', async() => {
        const el = await mount({ href: '/x', loading: '' });
        const a = control(el);
        expect(a.hasAttribute('href')).toBe(false);
        expect(a.getAttribute('aria-disabled')).toBe('true');
        expect(a.getAttribute('aria-busy')).toBe('true');
    });

    test('toggling href swaps between <a> and <button>', async() => {
        const el = await mount();
        el.href = '/x';
        await el.updateComplete;
        expect(control(el).tagName).toBe('A');
        el.href = undefined;
        await el.updateComplete;
        expect(control(el).tagName).toBe('BUTTON');
    });

    test('mirrors aria-label / aria-haspopup / aria-expanded onto the control', async() => {
        const el = await mount({ 'aria-label': 'Save', 'aria-haspopup': 'dialog', 'aria-expanded': 'true' });
        const btn = control(el);
        expect(btn.getAttribute('aria-label')).toBe('Save');
        expect(btn.getAttribute('aria-haspopup')).toBe('dialog');
        expect(btn.getAttribute('aria-expanded')).toBe('true');
    });

    test('is form-associated and delegates focus', () => {
        const Ctor = customElements.get('ol-button');
        expect(Ctor.formAssociated).toBe(true);
        expect(Ctor.shadowRootOptions.delegatesFocus).toBe(true);
    });

    describe('form proxy', () => {
        test('type="submit" keeps one hidden, unslotted native submit button in light DOM', async() => {
            const el = await mount({ type: 'submit', name: 'action', value: 'save' });
            const p = proxy(el);
            expect(p).not.toBeNull();
            expect(el.querySelectorAll('button')).toHaveLength(1);
            expect(p.type).toBe('submit');
            expect(p.hidden).toBe(true);
            expect(p.assignedSlot).toBeNull();
            expect(p.getAttribute('aria-hidden')).toBe('true');
            expect(p.tabIndex).toBe(-1);
            expect(p.name).toBe('action');
            expect(p.value).toBe('save');
            // The visible label is untouched.
            expect(el.textContent).toBe('Label');
        });

        test('mirrors form* attributes and disabled/loading onto the proxy', async() => {
            const el = await mount({ type: 'submit', formaction: '/save', formmethod: 'post', formnovalidate: '', formtarget: '_blank' });
            const p = proxy(el);
            expect(p.getAttribute('formaction')).toBe('/save');
            expect(p.getAttribute('formmethod')).toBe('post');
            expect(p.hasAttribute('formnovalidate')).toBe(true);
            expect(p.getAttribute('formtarget')).toBe('_blank');
            expect(p.disabled).toBe(false);
            el.disabled = true;
            await el.updateComplete;
            expect(p.disabled).toBe(true);
            el.disabled = false;
            el.loading = true;
            await el.updateComplete;
            expect(p.disabled).toBe(true);
            el.loading = false;
            el.removeAttribute('formaction');
            await el.updateComplete;
            expect(p.disabled).toBe(false);
            expect(p.hasAttribute('formaction')).toBe(false);
        });

        test('type="button" and links have no proxy; it follows type/href changes', async() => {
            const el = await mount();
            expect(proxy(el)).toBeNull();
            el.type = 'submit';
            await el.updateComplete;
            expect(proxy(el)).not.toBeNull();
            el.href = '/x';
            await el.updateComplete;
            expect(proxy(el)).toBeNull();
            el.href = undefined;
            el.type = 'reset';
            await el.updateComplete;
            expect(proxy(el).type).toBe('reset');
            el.type = 'button';
            await el.updateComplete;
            expect(proxy(el)).toBeNull();
        });

        test('restores the proxy if a consumer replaces the light DOM', async() => {
            const el = await mount({ type: 'submit' });
            el.textContent = 'New label';
            expect(proxy(el)).toBeNull();
            await Promise.resolve(); // MutationObserver callbacks are microtasks
            expect(proxy(el)).not.toBeNull();
            expect(el.textContent).toBe('New label');
        });

        test('form* properties reach the proxy, not just attributes', async() => {
            const el = await mount({ type: 'submit' });
            el.formAction = '/save';
            el.formMethod = 'post';
            el.formNoValidate = true;
            el.formTarget = '_blank';
            await el.updateComplete;
            const p = proxy(el);
            expect(p.getAttribute('formaction')).toBe('/save');
            expect(p.getAttribute('formmethod')).toBe('post');
            expect(p.hasAttribute('formnovalidate')).toBe(true);
            expect(p.getAttribute('formtarget')).toBe('_blank');
            el.formNoValidate = false;
            await el.updateComplete;
            expect(p.hasAttribute('formnovalidate')).toBe(false);
        });
    });

    describe('form submission', () => {
        test('type="submit" submits with the proxy as submitter, carrying name/value', async() => {
            const { form, el, submits } = await mountInForm({ type: 'submit', name: 'action', value: 'save' });
            control(el).click();
            expect(submits).toHaveLength(0); // deferred past dispatch
            await flush();
            expect(submits).toHaveLength(1);
            expect(submits[0].submitter).toBe(proxy(el));
            expect(submits[0].submitter.closest('ol-button')).toBe(el);
            expect(new FormData(form, submits[0].submitter).get('action')).toBe('save');
        });

        test('type="reset" resets the form', async() => {
            const { form, el } = await mountInForm({ type: 'reset' }, 'Clear');
            const input = document.createElement('input');
            input.name = 'q';
            form.prepend(input);
            input.value = 'typed';
            control(el).click();
            await flush();
            expect(input.value).toBe('');
        });

        test('type="button" does not touch the form', async() => {
            const { el, submits } = await mountInForm({}, 'Noop');
            control(el).click();
            await flush();
            expect(submits).toHaveLength(0);
        });

        test('preventDefault() on the host or an ancestor cancels the submit, like a native button', async() => {
            const { form, el, submits } = await mountInForm({ type: 'submit' });
            const cancel = (e) => e.preventDefault();
            form.addEventListener('click', cancel);
            control(el).click();
            await flush();
            expect(submits).toHaveLength(0);
            form.removeEventListener('click', cancel);

            el.addEventListener('click', cancel);
            control(el).click();
            await flush();
            expect(submits).toHaveLength(0);
            el.removeEventListener('click', cancel);

            control(el).click();
            await flush();
            expect(submits).toHaveLength(1);
        });

        test('does not submit while disabled or loading', async() => {
            const { el, submits } = await mountInForm({ type: 'submit', disabled: '' });
            control(el).click();
            await flush();
            el.disabled = false;
            el.loading = true;
            await el.updateComplete;
            control(el).click();
            await flush();
            expect(submits).toHaveLength(0);
        });

        test('falls back to internals.form.requestSubmit() when the proxy has no form owner', async() => {
            // e.g. the button is inside another component's shadow root and the
            // form is outside — the proxy can't associate, ElementInternals can.
            const el = await mount({ type: 'submit' });
            const fakeForm = { requestSubmit: jest.fn(), reset: jest.fn() };
            el._internals.form = fakeForm;
            control(el).click();
            await flush();
            expect(fakeForm.requestSubmit).toHaveBeenCalledTimes(1);
            expect(fakeForm.requestSubmit).toHaveBeenCalledWith();
        });
    });

    test('formDisabledCallback disables the control without reflecting a disabled attribute', async() => {
        const el = await mount({ type: 'submit' });
        el.formDisabledCallback(true);
        await el.updateComplete;
        expect(el.disabled).toBe(false);
        expect(el.hasAttribute('disabled')).toBe(false);
        expect(el.isDisabled).toBe(true);
        expect(control(el).disabled).toBe(true);
        expect(proxy(el).disabled).toBe(true);
        el.formDisabledCallback(false);
        await el.updateComplete;
        expect(control(el).disabled).toBe(false);
        expect(proxy(el).disabled).toBe(false);
    });
});
