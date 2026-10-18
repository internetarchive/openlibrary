/**
 * snippets.js: the /snippets feed renders a card per snippet, then enriches the
 * whole page with ONE bulk `ia:(…)` search.json request keyed on the ocaid in
 * each snippet's details URL. Matched cards get a title caption and a work-keyed
 * <ol-shelf-button>; unmatched or ocaid-less snippets degrade to image + link.
 */
import { initSnippets } from '../../../openlibrary/plugins/openlibrary/js/snippets.js';

// The shelf-button engine is exercised in book-state.test.js; stub it so this
// test sees only the search.json request snippets.js itself makes.
vi.mock('../../../openlibrary/plugins/openlibrary/js/book-state.js', () => ({
    initBookState: vi.fn()
}));

let apiCalls;
let searchCalls;

/**
 * Route fetch by URL: /api/snippets returns `items`; /search.json returns the
 * `docs` (or an error when `searchOk` is false). Records every call so the test
 * can assert exactly one search request fired.
 */
function stubFetch(items, docs, { searchOk = true } = {}) {
    apiCalls = [];
    searchCalls = [];
    global.fetch = vi.fn(async url => {
        const u = String(url);
        if (u.includes('/api/snippets')) {
            apiCalls.push(u);
            return { ok: true, status: 200, json: async () => items };
        }
        if (u.includes('/search.json')) {
            searchCalls.push(new URL(u, 'https://ol.test'));
            if (!searchOk) return { ok: false, status: 500, json: async () => ({}) };
            return { ok: true, status: 200, json: async () => ({ docs }) };
        }
        throw new Error(`unexpected fetch ${u}`);
    });
}

const HOST = 'https://www-drini.archive.org';
const snippet = (ocaid, page = 1) =>
    ocaid === null
        ? { annotation: 'https://example.org/no-details/here', uri: null }
        : { annotation: `${HOST}/details/${ocaid}/page/${page}/mode/2up?ref=ol`, uri: null };

const workDoc = (key, title, ia) => ({ key, title, edition_key: ['OLx1M', 'OLx2M'], ia });

function container() {
    document.body.innerHTML = '<ul class="js-snippets" data-i18n-empty="None" data-i18n-error="Oops" data-i18n-alt="Page"></ul>';
    return document.querySelector('.js-snippets');
}

const cards = () => [...document.querySelectorAll('.snippets-grid__item')];
const buttonsIn = li => li.querySelectorAll('ol-shelf-button');
const captionIn = li => li.querySelector('.snippet-card__title');

afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = '';
});

test('issues exactly ONE search.json request for a page of several snippets', async () => {
    const items = [snippet('macklife0000mack'), snippet('annakarnina00tols')];
    const docs = [
        workDoc('/works/OL1W', 'Mack the Life', ['macklife0000mack', 'macklife0000mack_s3e6']),
        workDoc('/works/OL2W', 'Anna Karenina', ['annakarnina00tols', 'annakarenina0000coun'])
    ];
    stubFetch(items, docs);

    await initSnippets(container());

    expect(searchCalls).toHaveLength(1);
    const q = searchCalls[0].searchParams.get('q');
    expect(q).toBe('ia:(macklife0000mack OR annakarnina00tols)');
    expect(searchCalls[0].searchParams.get('fields')).toContain('ia');
});

test('decorates each matched card with the work title and a work-keyed shelf button', async () => {
    const items = [snippet('macklife0000mack')];
    stubFetch(items, [workDoc('/works/OL1W', 'Mack the Life', ['macklife0000mack'])]);

    await initSnippets(container());

    const li = cards()[0];
    expect(captionIn(li).textContent).toBe('Mack the Life');
    const btn = buttonsIn(li)[0];
    expect(btn.getAttribute('work-key')).toBe('/works/OL1W');
    expect(btn.getAttribute('book-title')).toBe('Mack the Life');
    // Edition is not derivable from the bulk query — it must not be faked.
    expect(btn.hasAttribute('edition-key')).toBe(false);
});

test('dedupes a repeated ocaid: two snippets, one query term, both decorated', async () => {
    const items = [snippet('annakarnina00tols', 5), snippet('annakarnina00tols', 9)];
    stubFetch(items, [workDoc('/works/OL2W', 'Anna Karenina', ['annakarnina00tols'])]);

    await initSnippets(container());

    expect(searchCalls[0].searchParams.get('q')).toBe('ia:(annakarnina00tols)');
    const list = cards();
    expect(buttonsIn(list[0])[0].getAttribute('work-key')).toBe('/works/OL2W');
    expect(buttonsIn(list[1])[0].getAttribute('work-key')).toBe('/works/OL2W');
});

test('maps distinct ocaids that belong to the same work back to one doc', async () => {
    const items = [snippet('annakarnina00tols'), snippet('annakarenina0000coun')];
    // A single work doc whose `ia` covers both ocaids.
    stubFetch(items, [workDoc('/works/OL2W', 'Anna Karenina', ['annakarnina00tols', 'annakarenina0000coun'])]);

    await initSnippets(container());

    const list = cards();
    expect(buttonsIn(list[0])[0].getAttribute('work-key')).toBe('/works/OL2W');
    expect(buttonsIn(list[1])[0].getAttribute('work-key')).toBe('/works/OL2W');
});

test('a snippet whose ocaid has no solr match degrades to image + link, no button', async () => {
    const items = [snippet('macklife0000mack'), snippet('ghostocaid00none')];
    stubFetch(items, [workDoc('/works/OL1W', 'Mack the Life', ['macklife0000mack'])]);

    await initSnippets(container());

    const list = cards();
    expect(buttonsIn(list[0])).toHaveLength(1);
    expect(buttonsIn(list[1])).toHaveLength(0);
    expect(captionIn(list[1])).toBeNull();
    // Still a usable card: the linked image survives.
    expect(list[1].querySelector('.snippet-card__img')).not.toBeNull();
});

test('skips the search entirely when no snippet has a usable ocaid', async () => {
    stubFetch([snippet(null)], []);

    await initSnippets(container());

    expect(apiCalls).toHaveLength(1);
    expect(searchCalls).toHaveLength(0);
    // No /details/ URL → no card rendered, and no crash.
    expect(cards()).toHaveLength(0);
});

test('a card that renders but yields no ocaid fires no search (guards the empty ia:() query)', async () => {
    // Contains /details/ (so cardHtml renders a card) but no id follows it, so
    // ocaidFromItem returns ''. This is the path that exercises the
    // `if (!ocaids.length) return` guard — without it an `ia:()` request fires.
    const item = { annotation: 'https://archive.org/details/?ref=ol', uri: null };
    stubFetch([item], []);

    await initSnippets(container());

    const list = cards();
    expect(list).toHaveLength(1);
    expect(searchCalls).toHaveLength(0);
    expect(buttonsIn(list[0])).toHaveLength(0);
    expect(list[0].querySelector('.snippet-card__img')).not.toBeNull();
});

test('a failed search.json leaves plain cards, no shelf buttons, no throw', async () => {
    const items = [snippet('macklife0000mack')];
    stubFetch(items, [], { searchOk: false });

    await initSnippets(container());

    const li = cards()[0];
    expect(buttonsIn(li)).toHaveLength(0);
    expect(captionIn(li)).toBeNull();
    expect(li.querySelector('.snippet-card__img')).not.toBeNull();
});
