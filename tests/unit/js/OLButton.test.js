/**
 * <ol-button> rendering contract: it paints a real <button> / <a> in its own
 * shadow root, projects the author's label through a slot, mirrors host ARIA
 * onto the inner control, and forwards submit/reset to the enclosing form via
 * ElementInternals. jsdom has no layout, so appearance (variants, shapes,
 * elevation) is CSS-only and verified in the browser / design page.
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

    test('type="submit" calls the form\'s requestSubmit(); type="reset" resets it', async() => {
        const form = document.createElement('form');
        document.body.appendChild(form);
        const submit = await mount({ type: 'submit' }, 'Go', form);
        // Point the fake internals at the form, as the browser would.
        submit._internals.form = { requestSubmit: jest.fn(), reset: jest.fn() };
        control(submit).click();
        expect(submit._internals.form.requestSubmit).toHaveBeenCalledTimes(1);

        const reset = await mount({ type: 'reset' }, 'Clear', form);
        reset._internals.form = { requestSubmit: jest.fn(), reset: jest.fn() };
        control(reset).click();
        expect(reset._internals.form.reset).toHaveBeenCalledTimes(1);
        expect(reset._internals.form.requestSubmit).not.toHaveBeenCalled();
    });

    test('type="button" does not touch the form', async() => {
        const el = await mount({}, 'Noop');
        el._internals.form = { requestSubmit: jest.fn(), reset: jest.fn() };
        control(el).click();
        expect(el._internals.form.requestSubmit).not.toHaveBeenCalled();
        expect(el._internals.form.reset).not.toHaveBeenCalled();
    });

    test('formDisabledCallback mirrors to the disabled property', async() => {
        const el = await mount();
        el.formDisabledCallback(true);
        await el.updateComplete;
        expect(el.disabled).toBe(true);
        expect(control(el).disabled).toBe(true);
    });
});
