/**
 * book-state.js: labels and the reader's key reach every button, state is
 * fetched in one batch for the buttons the server left without it, and a
 * change on one button lands on every button for that work.
 */
import '../../../openlibrary/components/lit/OlShelfButton.js';
import { BATCH_SIZE, hydrate, initBookState, readLabels, resetBookState } from '../../../openlibrary/plugins/openlibrary/js/book-state.js';

let calls;

function stubFetch(works = {}, { status = 200 } = {}) {
    calls = [];
    global.fetch = jest.fn(async(url) => {
        calls.push(new URL(String(url)));
        return { ok: status < 400, status, json: async() => ({ user_key: '/people/tester', works }) };
    });
}

const LABELS = { wantToRead: 'Quiero leer', save: 'Guardar %(title)s' };

function page({ userKey = '/people/tester', labels = LABELS, buttons = '' } = {}) {
    if (userKey) document.body.dataset.userKey = userKey;
    else delete document.body.dataset.userKey;
    document.body.innerHTML = `
        ${labels ? `<input type="hidden" name="shelf-button-i18n-strings" value='${JSON.stringify(labels)}'>` : ''}
        ${buttons}
    `;
}

const button = (workKey, attrs = '') => `<ol-shelf-button work-key="${workKey}" book-title="A book" ${attrs}></ol-shelf-button>`;
const all = () => [...document.querySelectorAll('ol-shelf-button')];
const tick = () => new Promise(r => setTimeout(r, 0));

beforeAll(() => {
    window.matchMedia = query => ({
        matches: false, media: query,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {},
    });
    global.ResizeObserver = class { observe() {} disconnect() {} };
});

afterEach(() => {
    resetBookState();
    document.body.innerHTML = '';
    delete document.body.dataset.userKey;
});

describe('readLabels', () => {
    test('parses the hidden input site/body.html renders', () => {
        page();
        expect(readLabels()).toEqual(LABELS);
    });

    test('is null without one, or with a broken one', () => {
        page({ labels: null });
        expect(readLabels()).toBeNull();
        document.body.innerHTML = '<input type="hidden" name="shelf-button-i18n-strings" value="{not json">';
        expect(readLabels()).toBeNull();
    });
});

describe('hydrate', () => {
    test('hands every button its labels and the reader\'s key', async() => {
        stubFetch();
        page({ buttons: button('/works/OL1W') + button('/works/OL2W', 'user-key="/people/other" data-hydrated') });
        await hydrate();
        const [carousel, row] = all();
        expect(carousel.labels).toEqual(LABELS);
        expect(row.labels).toEqual(LABELS);
        expect(carousel.userKey).toBe('/people/tester');
        // A key the server rendered is the server's to set.
        expect(row.userKey).toBe('/people/other');
    });

    test('fetches state once, for the buttons the server left without it, and applies it', async() => {
        stubFetch({
            OL1W: { shelf: 2, rating: 4, read_date: null, event_id: null },
            OL3W: { shelf: null, rating: null, read_date: null, event_id: null },
        });
        page({
            buttons: [
                button('/works/OL1W'),
                button('/works/OL1W'), // the same work twice on a page
                button('/works/OL2W', 'data-hydrated shelf="1"'),
                button('/works/OL3W'),
            ].join(''),
        });
        await hydrate();
        expect(calls).toHaveLength(1);
        expect(calls[0].pathname).toBe('/partials/ReadingState.json');
        expect(calls[0].searchParams.get('work_ids')).toBe('OL1W,OL3W');
        const [a, b, row, c] = all();
        expect([a.shelf, a.rating]).toEqual([2, 4]);
        expect([b.shelf, b.rating]).toEqual([2, 4]);
        expect(row.shelf).toBe(1);
        expect(c.shelf).toBeNull();
        expect(all().every(el => el.hasAttribute('data-hydrated'))).toBe(true);

        // A second pass has nothing left to ask for.
        await hydrate();
        expect(calls).toHaveLength(1);
    });

    test('signed out, applies labels and never asks for state', async() => {
        stubFetch();
        page({ userKey: '', buttons: button('/works/OL1W') });
        await hydrate();
        expect(calls).toHaveLength(0);
        expect(all()[0].labels).toEqual(LABELS);
        expect(all()[0].userKey).toBe('');
    });

    test('asks in batches the server accepts', async() => {
        stubFetch();
        const buttons = Array.from({ length: BATCH_SIZE + 1 }, (_, i) => button(`/works/OL${i + 1}W`)).join('');
        page({ buttons });
        await hydrate();
        expect(calls).toHaveLength(2);
        expect(calls[0].searchParams.get('work_ids').split(',')).toHaveLength(BATCH_SIZE);
        expect(calls[1].searchParams.get('work_ids')).toBe(`OL${BATCH_SIZE + 1}W`);
    });

    test('a failed request is retried on the next pass', async() => {
        stubFetch({}, { status: 500 });
        page({ buttons: button('/works/OL1W') });
        await hydrate();
        expect(calls).toHaveLength(1);
        expect(all()[0].hasAttribute('data-hydrated')).toBe(false);
        stubFetch({ OL1W: { shelf: 1, rating: null, read_date: null, event_id: null } });
        await hydrate();
        expect(calls).toHaveLength(1);
        expect(all()[0].shelf).toBe(1);
    });
});

describe('initBookState', () => {
    test('a shelf change on one button reaches every button for that work', async() => {
        stubFetch();
        page({ buttons: button('/works/OL1W', 'data-hydrated') + button('/works/OL1W', 'data-hydrated') + button('/works/OL2W', 'data-hydrated') });
        initBookState();
        await hydrate();
        const [a, b, other] = all();
        b.readDate = '2026-08';
        b.eventId = 7;
        a.dispatchEvent(new CustomEvent('ol-book-state-change', {
            bubbles: true, composed: true, detail: { key: '/works/OL1W', shelf: 3, rating: 5 },
        }));
        expect([a.shelf, a.rating, b.shelf, b.rating]).toEqual([3, 5, 3, 5]);
        expect(other.shelf).toBeNull();
        expect(b.readDate).toBe('2026-08');

        // Off the shelf takes the finish date with it.
        a.dispatchEvent(new CustomEvent('ol-book-state-change', {
            bubbles: true, composed: true, detail: { key: '/works/OL1W', shelf: null, rating: 5 },
        }));
        expect([b.shelf, b.readDate, b.eventId]).toEqual([null, null, null]);
    });

    test('a saved finish date reaches every button for that work', async() => {
        stubFetch();
        page({ buttons: button('/works/OL1W', 'data-hydrated') + button('/works/OL1W', 'data-hydrated') });
        initBookState();
        const [a, b] = all();
        a.dispatchEvent(new CustomEvent('ol-book-check-in', {
            bubbles: true, composed: true, detail: { key: '/works/OL1W', date: '2026-09-08', eventId: 42 },
        }));
        expect([b.readDate, b.eventId]).toEqual(['2026-09-08', 42]);
    });

    test('buttons that arrive later (a lazy carousel) are hydrated too', async() => {
        stubFetch({ OL9W: { shelf: 4, rating: null, read_date: null, event_id: null } });
        page({ buttons: '' });
        initBookState();
        await tick();
        expect(calls).toHaveLength(0);
        const carousel = document.createElement('div');
        carousel.innerHTML = button('/works/OL9W');
        document.body.appendChild(carousel);
        await tick(); // the observer's coalescing timeout
        await tick(); // the fetch
        expect(calls).toHaveLength(1);
        const late = all()[0];
        expect(late.labels).toEqual(LABELS);
        expect(late.userKey).toBe('/people/tester');
        expect(late.shelf).toBe(4);
    });
});
