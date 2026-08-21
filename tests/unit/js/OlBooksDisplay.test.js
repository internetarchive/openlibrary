/**
 * Unit tests for <ol-books-display>: data flow (fetch → cards → user-state
 * overlay), the view toggle, grid- and list-view paging, and the logged-in/out branches
 * of the per-book controls. Network is stubbed at `fetch`.
 *
 * The component renders into its shadow root, so queries for its own markup go
 * through `el.renderRoot`. Anything it hands to a child component (the save
 * button slotted into <ol-book-actions>, the tooltip's content) is a light
 * child of that child and is reached from it directly.
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
    document.cookie = 'pending_action=; path=/; max-age=0';
});

/** The `pending_action` cookie the CTA writes for a logged-out visitor. */
function pendingAction() {
    const match = document.cookie.match(/(?:^|; )pending_action=([^;]*)/);
    return match ? JSON.parse(decodeURIComponent(match[1])) : null;
}

async function mount(attrs = {}) {
    const el = document.createElement('ol-books-display');
    el.query = 'subject:fiction';
    el.limit = 20;
    el.heading = 'Trending';
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
        expect(el.renderRoot.querySelectorAll('.obd-card')).toHaveLength(20);
        const first = fetchCalls[0].url;
        expect(first).toContain('/books-display.json?');
        expect(first).toContain('q=subject%3Afiction');
        expect(first).toContain('offset=0');
        expect(first).toContain('has_fulltext_only=true');
    });

    test('renders label-free CTA kinds with translated labels', async() => {
        stubFetch();
        const el = await mount({ labels: { borrow: 'Emprunter' } });
        const cta = el.renderRoot.querySelector('.obd-card__cta');
        expect(cta.textContent.trim()).toBe('Emprunter');
        expect(cta.getAttribute('variant')).toBe('primary');
        expect(cta.getAttribute('href')).toBe('/borrow/ia/x0?ref=ol');
    });

    test('logged out: a borrow CTA queues the pending action and "+" has no popover', async() => {
        stubFetch();
        const el = await mount();
        const cta = el.renderRoot.querySelector('.obd-card__cta');
        // Still an ordinary link to the borrow URL — only the cookie is ours.
        cta.addEventListener('click', e => e.preventDefault());
        cta.click();
        expect(pendingAction()).toEqual({ name: 'Book 0', url: '/books/OL0M', action: 'Borrow', type: 'book' });
        expect(el.renderRoot.querySelector('ol-book-actions')).toBeNull();
        expect(el.renderRoot.querySelector('.obd-save')).not.toBeNull();
        // No user-state request without a user
        expect(fetchCalls.some(c => c.url.includes('user-state'))).toBe(false);
    });

    test('logged in: overlays shelf state and wraps "+" in ol-book-actions', async() => {
        stubFetch({ userState: { shelves: { OL1W: SHELF.ALREADY_READ }, ratings: { OL1W: 5 } } });
        const el = await mount({ userKey: '/people/tester' });
        const stateCall = fetchCalls.find(c => c.url.includes('user-state'));
        expect(stateCall.url).toContain('work_ids=OL0W%2COL1W');
        const actions = el.renderRoot.querySelectorAll('ol-book-actions');
        expect(actions).toHaveLength(20);
        expect(actions[1].shelf).toBe(SHELF.ALREADY_READ);
        expect(actions[1].rating).toBe(5);
        expect(actions[1].querySelector('.obd-save').classList.contains('obd-save--on')).toBe(true);
        expect(actions[0].querySelector('.obd-save').classList.contains('obd-save--on')).toBe(false);
        const cta = el.renderRoot.querySelector('.obd-card__cta');
        cta.addEventListener('click', e => e.preventDefault());
        cta.click();
        expect(pendingAction()).toBeNull();
    });

    test('ol-book-state-change updates the card', async() => {
        stubFetch();
        const el = await mount({ userKey: '/people/tester' });
        const actions = el.renderRoot.querySelector('ol-book-actions');
        actions.dispatchEvent(new CustomEvent('ol-book-state-change', {
            bubbles: true, composed: true,
            detail: { key: '/works/OL0W', shelf: SHELF.WANT_TO_READ, rating: null },
        }));
        await el.updateComplete;
        expect(el.renderRoot.querySelector('ol-book-actions .obd-save').classList.contains('obd-save--on')).toBe(true);
    });

    test('carousel nearing its end loads the next page', async() => {
        stubFetch({ total: 45 });
        const el = await mount();
        const carousel = el.renderRoot.querySelector('ol-carousel');
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
        expect(el.renderRoot.querySelector('[role="alert"]').textContent).toContain('load these books');
        expect(el.renderRoot.querySelector('.obd-card')).toBeNull();
    });
});

describe('ol-books-display cover cards', () => {
    test('the cover carries a hover card, and the card text repeats it for touch', async() => {
        stubFetch();
        const el = await mount();
        const card = el.renderRoot.querySelector('.obd-card');
        // The tooltip wraps the cover link only — not the save button.
        const tip = card.querySelector('.obd-cover > ol-tooltip');
        expect(tip.querySelector('.obd-cover__link')).not.toBeNull();
        expect(tip.querySelector('.obd-save')).toBeNull();
        expect(tip.querySelector('[slot="content"]').textContent.replace(/\s+/g, ' ').trim()).toBe('Book 0 (2000) Author 0');
        expect(card.querySelector('.obd-card__heading').textContent.replace(/\s+/g, ' ').trim()).toBe('Book 0 (2000)');
    });

    test('an unavailable book shows a disabled CTA with no link', async() => {
        stubFetch();
        const el = await mount({ query: '', books: [doc(1, { access: { cta: 'checked_out', url: null, login_intent: false } })] });
        const cta = el.renderRoot.querySelector('.obd-card__cta');
        expect(cta.textContent.trim()).toBe('Checked Out');
        expect(cta.getAttribute('variant')).toBe('secondary');
        expect(cta.hasAttribute('disabled')).toBe(true);
        expect(cta.hasAttribute('href')).toBe(false);
    });

    test('a book with no year shows the title alone', async() => {
        stubFetch();
        const el = await mount({ query: '', books: [doc(1, { first_publish_year: null })] });
        expect(el.renderRoot.querySelector('.obd-card__heading').textContent.trim()).toBe('Book 1');
        expect(el.renderRoot.querySelector('.obd-card__year')).toBeNull();
    });
});

describe('ol-books-display static books', () => {
    test('renders the given books and never fetches', async() => {
        stubFetch();
        const el = await mount({ query: '', books: [doc(1), doc(2), doc(3)] });
        expect(fetchCalls).toHaveLength(0);
        expect(el.renderRoot.querySelectorAll('.obd-card')).toHaveLength(3);
        expect(el.hasMore).toBe(false);
        await el.loadMore();
        expect(fetchCalls).toHaveLength(0);
    });

    test('list view pages through the set without fetching', async() => {
        stubFetch();
        const el = await mount({ query: '', view: 'list', limit: 2, books: [doc(1), doc(2), doc(3)] });
        expect(el.renderRoot.querySelectorAll('.obd-row')).toHaveLength(2);
        el.renderRoot.querySelector('.obd__list-footer .obd__link-btn').click();
        await el.updateComplete;
        expect(el.renderRoot.querySelectorAll('.obd-row')).toHaveLength(3);
        expect(fetchCalls).toHaveLength(0);
    });
});

describe('ol-books-display views', () => {
    test('toggle switches between the list and grid views', async() => {
        stubFetch();
        const el = await mount();
        const events = [];
        el.addEventListener('ol-books-display-view-change', e => events.push(e.detail.view));
        el.renderRoot.querySelector('ol-segmented-control').dispatchEvent(new CustomEvent('ol-segmented-control-change', { detail: { value: 'list' } }));
        await el.updateComplete;
        expect(el.view).toBe('list');
        expect(el.getAttribute('view')).toBe('list');
        expect(el.renderRoot.querySelectorAll('.obd-row')).toHaveLength(20);
        expect(el.renderRoot.querySelector('ol-carousel')).toBeNull();
        el.renderRoot.querySelector('ol-segmented-control').dispatchEvent(new CustomEvent('ol-segmented-control-change', { detail: { value: 'grid' } }));
        await el.updateComplete;
        expect(el.view).toBe('grid');
        expect(el.renderRoot.querySelectorAll('.obd__grid-item')).toHaveLength(20);
        expect(el.renderRoot.querySelector('.obd-row')).toBeNull();
        expect(events).toEqual(['list', 'grid']);
    });

    test('views limits the switcher to the named views, in order', async() => {
        stubFetch();
        const el = await mount({ views: 'list,carousel' });
        const segments = [...el.renderRoot.querySelectorAll('ol-segment')].map(s => s.getAttribute('value'));
        expect(segments).toEqual(['list', 'carousel']);
        // A view left out stays unreachable.
        el.renderRoot.querySelector('ol-segmented-control').dispatchEvent(new CustomEvent('ol-segmented-control-change', { detail: { value: 'grid' } }));
        await el.updateComplete;
        expect(el.view).toBe('carousel');
    });

    test('a view the instance doesn\'t offer falls back to the first one it does', async() => {
        stubFetch();
        const el = await mount({ views: 'grid,list' });
        expect(el.view).toBe('grid');
        expect(el.getAttribute('view')).toBe('grid');
        expect(el.renderRoot.querySelectorAll('.obd__grid-item')).toHaveLength(20);
    });

    test('a single view drops the switcher', async() => {
        stubFetch();
        const el = await mount({ views: 'grid' });
        expect(el.renderRoot.querySelector('ol-segmented-control')).toBeNull();
        expect(el.view).toBe('grid');
        expect(el.renderRoot.querySelectorAll('.obd__grid-item')).toHaveLength(20);
    });

    test('an unrecognized views list falls back to all three', async() => {
        stubFetch();
        const el = await mount({ views: 'shelf', view: 'list' });
        const segments = [...el.renderRoot.querySelectorAll('ol-segment')].map(s => s.getAttribute('value'));
        expect(segments).toEqual(['carousel', 'grid', 'list']);
        expect(el.view).toBe('list');
    });

    test('list rows show byline links, stars, and the year beside the title', async() => {
        stubFetch();
        const el = await mount({ view: 'list' });
        const row = el.renderRoot.querySelector('.obd-row');
        expect(row.querySelector('.obd-row__author a').getAttribute('href')).toBe('/authors/OL0A');
        expect(row.querySelector('.obd-row__author').textContent.replace(/\s+/g, ' ').trim()).toBe('Author 0');
        expect(row.querySelector('.obd-row__rating-text').textContent).toContain('4.2');
        expect(row.querySelector('.obd-row__heading').textContent.replace(/\s+/g, ' ').trim()).toBe('Book 0 (2000)');
    });

    test('list footer: show more fetches and reveals, collapse hides', async() => {
        stubFetch({ total: 45 });
        const el = await mount({ view: 'list' });
        const footerText = () => el.renderRoot.querySelector('.obd__list-footer').textContent.replace(/\s+/g, ' ').trim();
        expect(footerText()).toBe('Show 20 more · See all →');
        el.renderRoot.querySelector('.obd__list-footer .obd__link-btn').click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(el.renderRoot.querySelectorAll('.obd-row')).toHaveLength(40);
        expect(footerText()).toBe('Show 5 more · Collapse · See all →');
        el.scrollIntoView = () => {};
        [...el.renderRoot.querySelectorAll('.obd__list-footer .obd__link-btn')].find(b => b.textContent === 'Collapse').click();
        await el.updateComplete;
        expect(el.renderRoot.querySelectorAll('.obd-row')).toHaveLength(20);
    });

    test('grid view renders the carousel view\'s cards in rows, not a carousel', async() => {
        stubFetch();
        const el = await mount({ view: 'grid' });
        expect(el.renderRoot.querySelector('ol-carousel')).toBeNull();
        const items = el.renderRoot.querySelectorAll('.obd__grid-item');
        expect(items).toHaveLength(20);
        // Same card the carousel slots: cover, corner save button, CTA.
        const card = items[0].querySelector('.obd-card');
        expect(card.querySelector('.obd-cover__img').getAttribute('src')).toBe('https://covers.test/b/id/0-M.jpg');
        expect(card.querySelector('.obd-save')).not.toBeNull();
        expect(card.querySelector('.obd-card__cta').textContent.trim()).toBe('Borrow');
    });

    test('grid footer: show more fetches and reveals, collapse hides', async() => {
        stubFetch({ total: 45 });
        const el = await mount({ view: 'grid' });
        const footerText = () => el.renderRoot.querySelector('.obd__list-footer').textContent.replace(/\s+/g, ' ').trim();
        expect(footerText()).toBe('Show 20 more · See all →');
        el.renderRoot.querySelector('.obd__list-footer .obd__link-btn').click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        expect(el.renderRoot.querySelectorAll('.obd__grid-item')).toHaveLength(40);
        expect(footerText()).toBe('Show 5 more · Collapse · See all →');
        el.scrollIntoView = () => {};
        [...el.renderRoot.querySelectorAll('.obd__list-footer .obd__link-btn')].find(b => b.textContent === 'Collapse').click();
        await el.updateComplete;
        expect(el.renderRoot.querySelectorAll('.obd__grid-item')).toHaveLength(20);
    });

    test('split button main click toggles Want to Read for a signed-in user', async() => {
        stubFetch();
        const el = await mount({ view: 'list', userKey: '/people/tester' });
        const main = el.renderRoot.querySelector('.obd-shelf__main');
        expect(main.textContent.trim()).toBe('Want to Read');
        main.click();
        await new Promise(r => setTimeout(r, 0));
        await el.updateComplete;
        const post = fetchCalls.find(c => c.url.endsWith('/works/OL0W/bookshelves.json'));
        expect(post.init.method).toBe('POST');
        expect(post.init.body.get('bookshelf_id')).toBe(String(SHELF.WANT_TO_READ));
        expect(el.renderRoot.querySelector('.obd-shelf').classList.contains('obd-shelf--on')).toBe(true);
    });
});
