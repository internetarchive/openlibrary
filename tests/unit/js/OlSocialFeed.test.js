/**
 * Unit tests for <ol-social-feed>:
 * - Renders feed activity items (actor handle, verb, book cover, title, time)
 * - Follow button state and toggle
 * - Showcase controls (paging, refresh)
 * - Handling of empty feed and error states
 */
import '../../../openlibrary/components/lit/OlSocialFeed.js';

const MOCK_ACTIVITY = [
    {
        type: 'shelf_change',
        username: 'ada_reader',
        patron_url: '/people/ada_reader',
        avatar_url: '/people/ada_reader/avatar',
        created: new Date(Date.now() - 3600 * 1000).toISOString(),
        label: 'added to Want to Read',
        shelf_url: '/people/ada_reader/books/want-to-read',
        work: {
            key: '/works/OL123W',
            title: 'Dune',
            author: 'Frank Herbert',
            cover_id: 101010
        }
    },
    {
        type: 'shelf_change',
        username: 'mek_reader',
        patron_url: '/people/mek_reader',
        avatar_url: '/people/mek_reader/avatar',
        created: new Date(Date.now() - 7200 * 1000).toISOString(),
        label: 'is Currently Reading',
        shelf_url: '/people/mek_reader/books/currently-reading',
        work: {
            key: '/works/OL456W',
            title: 'Foundation',
            author: 'Isaac Asimov',
            cover_id: 202020
        }
    }
];

beforeAll(() => {
    window.matchMedia = query => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {}
    });
});

beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
            scope: 'public',
            following: false,
            page: 1,
            activity: MOCK_ACTIVITY
        })
    });
});

afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
});

async function mount(attrs = {}) {
    const el = document.createElement('ol-social-feed');
    Object.assign(el, attrs);
    document.body.appendChild(el);
    await el.updateComplete;
    // Allow any async _load() promise to resolve and re-render
    await new Promise(resolve => setTimeout(resolve, 10));
    await el.updateComplete;
    return el;
}

const q = (el, selector) => el.renderRoot.querySelector(selector);
const qAll = (el, selector) => el.renderRoot.querySelectorAll(selector);

describe('ol-social-feed rendering', () => {
    test('renders cards for each activity item', async () => {
        const el = await mount({ apiUrl: '/api/internal/activity/feed.json' });
        const cards = qAll(el, '.card');
        expect(cards.length).toBe(2);

        const firstCard = cards[0];
        expect(firstCard.querySelector('.handle').textContent.trim()).toBe('ada_reader');
        expect(firstCard.querySelector('.verb').textContent.trim()).toBe('added to Want to Read');
        expect(firstCard.querySelector('.title').textContent.trim()).toBe('Dune');
        expect(firstCard.querySelector('.byline').textContent).toContain('Frank Herbert');

        const coverImg = firstCard.querySelector('.cover img');
        expect(coverImg.getAttribute('src')).toBe('https://covers.openlibrary.org/b/id/101010-M.jpg');
    });

    test('follow button initializes in unfollowed state and toggles on click', async () => {
        const el = await mount({ viewerUsername: 'current_patron' });
        const followBtn = q(el, '.follow');
        expect(followBtn.getAttribute('aria-pressed')).toBe('false');
        expect(followBtn.textContent.trim()).toBe('Follow');

        followBtn.click();
        await el.updateComplete;

        expect(followBtn.getAttribute('aria-pressed')).toBe('true');
        expect(followBtn.textContent.trim()).toBe('Following');
    });

    test('showcase variant renders paging controls and handles page navigation', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                scope: 'public',
                following: false,
                page: 1,
                activity: [
                    ...MOCK_ACTIVITY,
                    {
                        type: 'shelf_change',
                        username: 'third_reader',
                        patron_url: '/people/third_reader',
                        avatar_url: '/people/third_reader/avatar',
                        created: new Date().toISOString(),
                        label: 'shelved recently',
                        work: { key: '/works/OL789W', title: 'Neuromancer', author: 'William Gibson' }
                    }
                ]
            })
        });

        const el = await mount({ variant: 11, controls: true });
        const controls = q(el, '.controls');
        expect(controls).not.toBeNull();

        const prevBtn = q(el, '.ctl--prev');
        expect(prevBtn).not.toBeNull();
        expect(prevBtn.textContent).toContain('Newer');
        expect(prevBtn.disabled).toBe(true);

        const olderBtn = q(el, '.ctl--next');
        expect(olderBtn).not.toBeNull();
        expect(olderBtn.textContent).toContain('Older');
        expect(olderBtn.disabled).toBe(false);

        olderBtn.click();
        await el.updateComplete;
        expect(el._page).toBe(2);
    });

    test('renders empty state message when activity is empty', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                scope: 'public',
                following: false,
                page: 1,
                activity: []
            })
        });

        const el = await mount();
        const state = q(el, '.state');
        expect(state).not.toBeNull();
        expect(state.textContent).toContain('No recent activity yet');
    });

    test('gracefully renders works from trending/now.json format', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                query: '/trending/now',
                works: [
                    {
                        key: '/works/OL999W',
                        title: 'Trending Masterpiece',
                        author_name: ['Great Author'],
                        author_key: ['OL999A'],
                        cover_i: 99999
                    }
                ]
            })
        });

        const el = await mount({ apiUrl: '/trending/now.json' });
        const cards = qAll(el, '.card');
        expect(cards.length).toBe(1);
        expect(cards[0].querySelector('.title').textContent.trim()).toBe('Trending Masterpiece');
        expect(cards[0].querySelector('.byline').textContent).toContain('Great Author');
        expect(cards[0].querySelector('.handle').textContent.trim()).toBe('community');
    });
});
