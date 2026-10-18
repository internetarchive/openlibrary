/**
 * contribute.js inline task page: picking languages adds chips, Save posts the chosen codes, and on success
 * the card leaves Needs review for Done with both tab counts kept in step.
 */
import { init } from '../../../openlibrary/plugins/openlibrary/js/contribute.js';

// A minimal stand-in so customElements.whenDefined('ol-options-popover') resolves under jsdom; the picker's
// behaviour is driven in the test by dispatching its change event, not by the real component.
if (!customElements.get('ol-options-popover')) {
    customElements.define('ol-options-popover', class extends HTMLElement {});
}

const LANGS = [
    { value: 'eng', label: 'English' },
    { value: 'fre', label: 'French' }
];

function page({ todo = 1, done = 0 } = {}) {
    const cards = Array.from(
        { length: todo },
        (_, i) => `
        <li class="contrib-card" data-card data-olid="OL${i + 1}M">
            <div class="contrib-card__editor" data-editor>
                <ul class="contrib-chips" data-chips></ul>
                <div class="contrib-card__pickrow">
                    <ol-options-popover data-lang-picker></ol-options-popover>
                    <button data-save>Save</button>
                </div>
                <p data-error data-msg-empty="Choose at least one language." data-msg-failed="Could not save." hidden></p>
            </div>
        </li>`
    ).join('');
    document.body.innerHTML = `
        <div class="contrib-inline" data-inline-tasks data-field="languages" data-msg-history="History">
            <script type="application/json" data-inline-items>${JSON.stringify(LANGS)}</script>
            <button data-tab="todo" aria-selected="true">Needs review <span data-count-todo>${todo}</span></button>
            <button data-tab="done" aria-selected="false" tabindex="-1">Done <span data-count-done>${done}</span></button>
            <section data-panel="todo"><ul data-todo-list>${cards}</ul><div data-todo-empty ${todo ? 'hidden' : ''}></div></section>
            <section data-panel="done" hidden><ul data-done-list></ul><div data-done-empty ${done ? 'hidden' : ''}></div></section>
        </div>`;
    return document.querySelector('[data-inline-tasks]');
}

const pick = (card, code) =>
    card.querySelector('[data-lang-picker]').dispatchEvent(new CustomEvent('ol-options-popover-change', { detail: { selected: code } }));
const chips = card => [...card.querySelectorAll('[data-chips] [data-code]')].map(c => c.dataset.code);
const tick = () => new Promise(r => setTimeout(r, 0));

function stubFetch(result, { ok = true } = {}) {
    const posts = [];
    global.fetch = vi.fn(async (url, init) => {
        posts.push({ url: String(url), body: JSON.parse(init.body) });
        return { ok, json: async () => result };
    });
    return posts;
}

test('picking a language adds a chip; the same language is not added twice', () => {
    const card = page().querySelector('[data-card]');
    init();
    pick(card, 'eng');
    expect(chips(card)).toEqual(['eng']);
    pick(card, 'eng');
    expect(chips(card)).toEqual(['eng']);
});

test('a chip can be removed', () => {
    const card = page().querySelector('[data-card]');
    init();
    pick(card, 'eng');
    card.querySelector('[data-chips] .contrib-chip__remove').click();
    expect(chips(card)).toEqual([]);
});

test('saving with no language chosen posts nothing and shows the empty message', async () => {
    const posts = stubFetch({ ok: true });
    const card = page().querySelector('[data-card]');
    init();
    card.querySelector('[data-save]').click();
    await tick();
    expect(posts).toHaveLength(0);
    const error = card.querySelector('[data-error]');
    expect(error.hidden).toBe(false);
    expect(error.textContent).toBe('Choose at least one language.');
});

test('saving several languages posts their codes and moves the card to Done', async () => {
    const root = page({ todo: 1, done: 0 });
    const card = root.querySelector('[data-card]');
    const posts = stubFetch({ ok: true, olid: 'OL1M', title: 'A Book', value: 'English, French', history_url: '/books/OL1M?m=history' });
    init();
    pick(card, 'eng');
    pick(card, 'fre');
    card.querySelector('[data-save]').click();
    await tick();

    expect(posts[0].url).toContain('/tasks/languages');
    expect(posts[0].body).toEqual({ olid: 'OL1M', value: 'eng,fre' });
    // Left Needs review, arrived in Done.
    expect(root.querySelectorAll('[data-todo-list] [data-card]')).toHaveLength(0);
    const doneCard = root.querySelector('[data-done-list] [data-done-olid="OL1M"]');
    expect(doneCard).not.toBeNull();
    expect(doneCard.textContent).toContain('English, French');
    expect(root.querySelector('[data-count-todo]').textContent).toBe('0');
    expect(root.querySelector('[data-count-done]').textContent).toBe('1');
    expect(root.querySelector('[data-todo-empty]').hidden).toBe(false);
});

test('a server error keeps the card in Needs review and shows the message', async () => {
    const root = page();
    const card = root.querySelector('[data-card]');
    stubFetch({ ok: false, error: 'Pick a language from the list.' });
    init();
    pick(card, 'eng');
    card.querySelector('[data-save]').click();
    await tick();
    expect(root.querySelectorAll('[data-todo-list] [data-card]')).toHaveLength(1);
    expect(card.querySelector('[data-error]').textContent).toBe('Pick a language from the list.');
});

test('clicking the Done tab reveals its panel', () => {
    const root = page();
    init();
    root.querySelector('[data-tab="done"]').click();
    expect(root.querySelector('[data-panel="done"]').hidden).toBe(false);
    expect(root.querySelector('[data-panel="todo"]').hidden).toBe(true);
});
