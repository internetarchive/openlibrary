/**
 * Unit tests for <ol-books-display>: data flow (fetch → cards → user-state
 * overlay), the view toggle, list-view paging, and the logged-in/out branches
 * of the per-book controls. Network is stubbed at `fetch`.
 */
import '../../../openlibrary/components/lit/OlBooksDisplay.js';
import { SHELF } from '../../../openlibrary/components/lit/utils/books-api.js';

function doc(i, overrides = {}) {
    return {
        key: `/works/OL${i}W`,
        title: `Book ${i}`,
        subtitle: null,
        authors: [{ key: `/authors/OL${i}A`, name: `Author ${i}` }],
        cover_url: `https://covers.test/b/id/${i}-M.jpg`,
        edition_key: `OL${i}M`,
        first_publish_year: 2000 + i,
        ratings_average: 4.2,
        ratings_count: 3,
        access: { state: 'borrowable', cta: 'borrow', url: `/borrow/ia/x${i}?ref=ol`, external: false, method: 'get', login_intent: true, ocaid: `x${i}` },
        ...overrides,
    };
}

function page(offset, limit, total) {
    const docs = [];
    for (let i = offset; i < Math.min(offset + limit, total); i++) docs.push(doc(i));
    return { docs, num_found: total, offset, limit };
}

let fetchCalls;

function stubFetch({ total = 45, userState = { shelves: {}, ratings: {} } } = {}) {
    fetchCalls = [];
    global.fetch = jest.fn(async(url, init) => {
        fetchCalls.push({ url, init });
        const u = new URL(url, 'http://localhost');
        let body;
        if (u.pathname === '/books-display.json') {
            body = page(Number(u.searchParams.get('offset')), Number(u.searchParams.get('limit')), total);
        } else if (u.pathname === '/books-display/user-state.json') {
            body = userState;
        } else if (u.pathname.endsWith('/bookshelves.json')) {
            body = { bookshelves_affected: 1 };
        } else {
            body = {};
        }
        return { ok: true, status: 200, json: async() => body };
    });
}

beforeAll(() => {
    // jsdom has no IntersectionObserver; the component falls back to start().
    delete window.IntersectionObserver;
    // ...nor matchMedia, which ol-tooltip reads to detect hover. False keeps
    // the cover tooltips inert.
    window.matchMedia = query => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
    });
    global.ResizeObserver = class { observe() {} disconnect() {} };
    // jsdom's ElementInternals lacks the form-association API the segmented
    // control calls; give it inert stand-ins.
    const proto = window.ElementInternals?.prototype;
    if (proto && !proto.setFormValue) {
        proto.setFormValue = () => {};
        proto.setValidity = () => {};
    }
});

afterEach(() => {
    document.body.innerHTML = '';
});

async function mount(attrs = {}) {
    const el = document.createElement('ol-books-display');
    el.query = 'subject:fiction';
    el.limit = 20;
    el.title = 'Trending';
    el.url = '/search?q=x';
    Object.assign(el, attrs);
    document.body.appendChild(el);
    await el.updateComplete;
    // Let the first fetch + render settle.
    await new Promise(r => setTimeout(r, 0));
    await el.updateComplete;
    await new Promise(r => setTimeout(r, 0));
    await el.updateComplete;
    return el;
}

describe('ol-books-display data flow', () => {
    test('fetches the first page and renders cover cards', async() => {
        stubFetch();
        const el = await mount();
        expect(el.docs).toHaveLength(20);
        expect(el.querySelectorAll('.obd-card')).toHaveLength(20);
        const first = fetchCalls[0].url;
        expect(first).toContain('/books-display.json?');
        expect(first).toContain('q=subject%3Afiction');
        expect(first).toContain('offset=0');
        expect(first).toContain('has_fulltext_only=true');
    });

    test('renders label-free CTA kinds with translated labels', async() => {
        stubFetch();
        const el = await mount({ labels: { borrow: 'Emprunter' } });
        const cta = el.querySelector('.obd-card .obd-cta');
        expect(cta.textContent.trim()).toBe('Emprunter');
        expect(cta.classList.contains('obd-cta--primary')).toBe(true);
        expect(cta.getAttribute('href')).toBe('/borrow/ia/x0?ref=ol');
    });

    test('logged out: borrow CTAs carry the login-intent hook and "+" has no popover', async() => {
        stubFetch();
        const el = await mount();
        expect(el.querySelector('.obd-card .obd-cta').classList.contains('js-login-intent')).toBe(true);
        expect(el.querySelector('ol-book-actions')).toBeNull();
        expect(el.querySelector('.obd-save')).not.toBeNull();
        // No user-state request without a user
        expect(fetchCalls.some(c => c.url.includes('user-state'))).toBe(false);
    });

    test('logged in: overlays shelf state and wraps "+" in ol-book-actions', async() => {
        stubFetch({ userState: { shelves: { OL1W: SHELF.ALREADY_READ }, ratings: { OL1W: 5 } } });
        const el = await mount({ userKey: '/people/tester' });
        const stateCall = fetchCalls.find(c => c.url.includes('user-state'));
        expect(stateCall.url).toContain('work_ids=OL0W%2COL1W');
        const actions = el.querySelectorAll('ol-book-actions');
        expect(actions).toHaveLength(20);
        expect(actions[1].shelf).toBe(SHELF.ALREADY_READ);
        expect(actions[1].rating).toBe(5);
        expect(actions[1].querySelector('.obd-save').classList.contains('obd-save--on')).toBe(true);
        expect(actions[0].querySelector('.obd-save').classList.contains('obd-save--on')).toBe(false);
        expect(el.querySelector('.obd-card .obd-cta').classList.contains('js-login-intent')).toBe(false);
    });

    test('ol-book-state-change updates the card', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        const actions = el.querySelector('ol-book-actions');
        actions.dispatchEvent(new CustomEvent('ol-book-state-change', {
            bubbles: true, composed: true,
            detail: { key: '/works/OL0W', shelf: SHELF.WANT_TO_READ, rating: null },
        }));
        await el.updateComplete;
        expect(el.querySelector('ol-book-actions .obd-save').classList.contains('obd-save--on')).toBe(true);
    });

    test('carousel nearing its end loads the next page', async() => {
        stubFetch({ total: 45 });
        const el = await mount();
        const carousel = el.querySelector('ol-carousel');
        carousel.dispatchEvent(new CustomEvent('ol-carousel-page-change', { detail: { page: 2, totalPages: 3 }, bubbles: true }));
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(el.docs).toHaveLength(40);
        expect(fetchCalls.filter(c => c.url.includes('/books-display.json'))[1].url).toContain('offset=20');
    });

    test('stops paging once every result is loaded', async() => {
        stubFetch({ total: 5 });
        const el = await mount();
        expect(el.hasMore).toBe(false);
        await el.loadMore();
        expect(fetchCalls.filter(c => c.url.includes('/books-display.json'))).toHaveLength(1);
    });

    test('falls back to the wider query when the first is empty', async() => {
        stubFetch({ total: 45 });
        const original = global.fetch;
        global.fetch = jest.fn(async(url, init) => {
            if (url.includes('q=narrow')) return { ok: true, status: 200, json: async() => ({ docs: [], num_found: 0, offset: 0, limit: 20 }) };
            return original(url, init);
        });
        const el = await mount({ query: 'narrow', fallbackQuery: 'subject:fiction' });
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(el.query).toBe('subject:fiction');
        expect(el.docs).toHaveLength(20);
    });

    test('shows the error state with a retry on failure', async() => {
        global.fetch = jest.fn(async() => ({ ok: false, status: 500, json: async() => ({}) }));
        const el = await mount();
        expect(el.querySelector('[role="alert"]').textContent).toContain('load these books');
        expect(el.querySelector('.obd-card')).toBeNull();
    });
});

describe('ol-books-display cover cards', () => {
    test('the cover carries a hover card, and the card text repeats it for touch', async() => {
        stubFetch();
        const el = await mount();
        const card = el.querySelector('.obd-card');
        // The tooltip wraps the cover link only — not the save button.
        const tip = card.querySelector('.obd-cover > ol-tooltip');
        expect(tip.querySelector('.obd-cover__link')).not.toBeNull();
        expect(tip.querySelector('.obd-save')).toBeNull();
        expect(tip.querySelector('[slot="content"]').textContent.replace(/\s+/g, ' ').trim()).toBe('Book 0 (2000) Author 0');
        expect(card.querySelector('.obd-card__heading').textContent.replace(/\s+/g, ' ').trim()).toBe('Book 0 (2000)');
    });

    test('a book with no year shows the title alone', async() => {
        stubFetch();
        const el = await mount({ query: '', books: [doc(1, { first_publish_year: null })] });
        expect(el.querySelector('.obd-card__heading').textContent.trim()).toBe('Book 1');
        expect(el.querySelector('.obd-card__year')).toBeNull();
    });
});

describe('ol-books-display static books', () => {
    test('renders the given books and never fetches', async() => {
        stubFetch();
        const el = await mount({ query: '', books: [doc(1), doc(2), doc(3)] });
        expect(fetchCalls).toHaveLength(0);
        expect(el.querySelectorAll('.obd-card')).toHaveLength(3);
        expect(el.hasMore).toBe(false);
        await el.loadMore();
        expect(fetchCalls).toHaveLength(0);
    });

    test('list view pages through the set without fetching', async() => {
        stubFetch();
        const el = await mount({ query: '', view: 'list', limit: 2, books: [doc(1), doc(2), doc(3)] });
        expect(el.querySelectorAll('.obd-row')).toHaveLength(2);
        el.querySelector('.obd__list-footer .obd__link-btn').click();
        await el.updateComplete;
        expect(el.querySelectorAll('.obd-row')).toHaveLength(3);
        expect(fetchCalls).toHaveLength(0);
    });
});

describe('ol-books-display views', () => {
    test('toggle switches to the list view and back', async() => {
        stubFetch();
        const el = await mount();
        const events = [];
        el.addEventListener('ol-books-display-view-change', e => events.push(e.detail.view));
        el.querySelector('ol-segmented-control').dispatchEvent(new CustomEvent('ol-segmented-control-change', { detail: { value: 'list' } }));
        await el.updateComplete;
        expect(el.view).toBe('list');
        expect(el.getAttribute('view')).toBe('list');
        expect(el.querySelectorAll('.obd-row')).toHaveLength(20);
        expect(el.querySelector('ol-carousel')).toBeNull();
        expect(events).toEqual(['list']);
    });

    test('list rows show byline links, stars, and the year beside the title', async() => {
        stubFetch();
        const el = await mount({ view: 'list' });
        const row = el.querySelector('.obd-row');
        expect(row.querySelector('.obd-row__author a').getAttribute('href')).toBe('/authors/OL0A');
        expect(row.querySelector('.obd-row__author').textContent.replace(/\s+/g, ' ').trim()).toBe('Author 0');
        expect(row.querySelector('.obd-row__rating-text').textContent).toContain('4.2');
        expect(row.querySelector('.obd-row__heading').textContent.replace(/\s+/g, ' ').trim()).toBe('Book 0 (2000)');
    });

    test('list footer: show more fetches and reveals, collapse hides', async() => {
        stubFetch({ total: 45 });
        const el = await mount({ view: 'list' });
        const footerText = () => el.querySelector('.obd__list-footer').textContent.replace(/\s+/g, ' ').trim();
        expect(footerText()).toBe('Show 20 more · See all →');
        el.querySelector('.obd__list-footer .obd__link-btn').click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(el.querySelectorAll('.obd-row')).toHaveLength(40);
        expect(footerText()).toBe('Show 5 more · Collapse · See all →');
        el.scrollIntoView = () => {};
        [...el.querySelectorAll('.obd__list-footer .obd__link-btn')].find(b => b.textContent === 'Collapse').click();
        await el.updateComplete;
        expect(el.querySelectorAll('.obd-row')).toHaveLength(20);
    });

    test('split button main click toggles Want to Read for a signed-in user', async() => {
        stubFetch();
        const el = await mount({ view: 'list', userKey: '/people/tester' });
        const main = el.querySelector('.obd-shelf__main');
        expect(main.textContent.trim()).toBe('Want to Read');
        main.click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        const post = fetchCalls.find(c => c.url.endsWith('/works/OL0W/bookshelves.json'));
        expect(post.init.method).toBe('POST');
        expect(post.init.body.get('bookshelf_id')).toBe(String(SHELF.WANT_TO_READ));
        expect(el.querySelector('.obd-shelf').classList.contains('obd-shelf--on')).toBe(true);
    });
});
