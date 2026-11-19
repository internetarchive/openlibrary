/**
 * Browser-mode tests for <ol-autocomplete>: a real form, real focus and the
 * real top layer, with only the network stubbed.
 */
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { userEvent } from 'vitest/browser';
import { render } from 'vitest-browser-lit';
import { html } from 'lit';
import '../../openlibrary/components/lit/OlAutocomplete.js';

const NAMES = [
    { value: 'Penguin Books', count: 1051 },
    { value: 'Penguin', count: 19 }
];

/** What the stubbed endpoint answers, by the text asked about. */
let answers;
let asked;

beforeEach(() => {
    answers = { peng: NAMES };
    asked = [];
    vi.stubGlobal(
        'fetch',
        vi.fn(async url => {
            const q = new URL(url, location.href).searchParams.get('q');
            asked.push(q);
            return new Response(JSON.stringify(answers[q] ?? []), { headers: { 'Content-Type': 'application/json' } });
        })
    );
});

afterEach(() => vi.unstubAllGlobals());

function mount() {
    const submitted = [];
    render(html`
        <form
            @submit=${event => {
                event.preventDefault();
                submitted.push(new FormData(event.target).get('publisher'));
            }}
        >
            <label for="publisher">Publisher</label>
            <ol-autocomplete
                id="publisher"
                name="publisher"
                src="/publishers/_autocomplete"
                label-new="Add “{value}” as a new publisher"
                label-similar="Did you mean"
                hint-new="No other book uses this name."
            ></ol-autocomplete>
            <button type="submit">Save</button>
        </form>
    `);
    const el = document.querySelector('ol-autocomplete');
    return {
        el,
        submitted,
        input: () => el.shadowRoot.querySelector('input'),
        rows: () => [...el.shadowRoot.querySelectorAll('[role="option"]')].map(row => row.textContent.replace(/\s+/g, ' ').trim()),
        hint: () => el.shadowRoot.querySelector('.hint')?.textContent ?? null
    };
}

async function type(el, text) {
    await el.updateComplete;
    el.focus();
    await userEvent.keyboard(text);
}

test('typing lists the names in use with their counts, under the field', async () => {
    const { el, input, rows } = mount();
    await type(el, 'peng');
    await expect.poll(rows).toEqual(['Penguin Books 1,051', 'Penguin 19', 'Add “peng” as a new publisher']);

    expect(input().getAttribute('aria-expanded')).toBe('true');
    // Named by the <label for> that points at the host.
    expect(input().getAttribute('aria-label')).toBe('Publisher');
    const panel = el.shadowRoot.querySelector('.panel').getBoundingClientRect();
    const field = input().getBoundingClientRect();
    expect(panel.top).toBeGreaterThanOrEqual(field.bottom);
    expect(panel.width).toBeCloseTo(field.width, 0);
});

test('under a short field the list is wider than the field and stays in the viewport', async () => {
    const { el, rows } = mount();
    el.style.width = '120px';
    el.style.marginInlineStart = 'calc(100vw - 140px)';
    await type(el, 'peng');
    await expect.poll(() => rows().length).toBe(3);
    const panel = el.shadowRoot.querySelector('.panel').getBoundingClientRect();
    expect(panel.width).toBeGreaterThan(300);
    expect(panel.right).toBeLessThanOrEqual(window.innerWidth);
});

test('one letter asks for nothing, and only the last keystroke is asked about', async () => {
    const { el, rows } = mount();
    await type(el, 'p');
    await new Promise(resolve => setTimeout(resolve, 300));
    expect(asked).toEqual([]);
    await userEvent.keyboard('eng');
    await expect.poll(rows).toHaveLength(3);
    expect(asked).toEqual(['peng']);
});

test('the arrow keys and Enter pick a name without submitting the form', async () => {
    const { el, input, rows, submitted, hint } = mount();
    const picked = [];
    el.addEventListener('ol-autocomplete-select', event => picked.push(event.detail));
    await type(el, 'peng');
    await expect.poll(rows).toHaveLength(3);

    await userEvent.keyboard('{ArrowDown}{ArrowDown}');
    const active = input().getAttribute('aria-activedescendant');
    expect(el.shadowRoot.getElementById(active).textContent).toContain('Penguin');
    await userEvent.keyboard('{Enter}');

    expect(el.value).toBe('Penguin');
    expect(picked).toEqual([{ value: 'Penguin', isNew: false }]);
    expect(submitted).toEqual([]);
    expect(input().getAttribute('aria-expanded')).toBe('false');
    // A picked name is a known one.
    expect(el.isNew).toBe(false);
    expect(hint()).toBeNull();
});

test('Enter with no row picked submits the form with the typed text', async () => {
    const { el, rows, submitted } = mount();
    await type(el, 'peng');
    await expect.poll(rows).toHaveLength(3);
    await userEvent.keyboard('{Enter}');
    expect(submitted).toEqual(['peng']);
});

test('text that matches no name is kept and called new once the list closes', async () => {
    const { el, rows, hint } = mount();
    await type(el, 'peng');
    await expect.poll(rows).toHaveLength(3);
    expect(el.isNew).toBe(true);
    // While the list is open its own row says so.
    expect(hint()).toBeNull();

    await userEvent.keyboard('{Escape}');
    await el.updateComplete;
    expect(rows()).toHaveLength(3);
    expect(el.shadowRoot.querySelector('input').getAttribute('aria-expanded')).toBe('false');
    expect(hint()).toBe('No other book uses this name.');
    expect(el.value).toBe('peng');
});

test('a name typed in another case is not new', async () => {
    answers['penguin books'] = NAMES;
    const { el, rows } = mount();
    await type(el, 'penguin books');
    await expect.poll(rows).toEqual(['Penguin Books 1,051', 'Penguin 19']);
    expect(el.isNew).toBe(false);
});

test('near misses are offered under their own heading', async () => {
    answers.pengiun = [{ value: 'Penguin', count: 19, similar: true }];
    const { el, rows } = mount();
    await type(el, 'pengiun');
    await expect.poll(rows).toEqual(['Penguin 19', 'Add “pengiun” as a new publisher']);
    expect(el.shadowRoot.querySelector('.heading').textContent).toBe('Did you mean');
    expect(el.isNew).toBe(true);
});

test('a failed request leaves a plain text field', async () => {
    fetch.mockRejectedValueOnce(new Error('offline'));
    const { el, rows, submitted } = mount();
    await type(el, 'peng');
    await new Promise(resolve => setTimeout(resolve, 300));
    expect(rows()).toEqual([]);
    expect(el.isNew).toBe(false);
    await userEvent.keyboard('{Enter}');
    expect(submitted).toEqual(['peng']);
});
