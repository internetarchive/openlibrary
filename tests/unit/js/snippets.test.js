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
let deleteCalls;

/**
 * Route fetch by URL/method: /api/snippets returns `items`; /search.json returns
 * the `docs` (or an error when `searchOk` is false); a DELETE is recorded and
 * answered per `deleteOk`. Records every call so the test can assert exactly one
 * search request fired, and which deletes ran.
 */
function stubFetch(items, docs, { searchOk = true, deleteOk = true } = {}) {
    apiCalls = [];
    searchCalls = [];
    deleteCalls = [];
    global.fetch = vi.fn(async (url, init = {}) => {
        const u = String(url);
        if (init.method === 'DELETE') {
            deleteCalls.push(u);
            return { ok: deleteOk, status: deleteOk ? 200 : 403, json: async () => ({ deleted: deleteOk }) };
        }
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
let nextId = 1;
const snippet = (ocaid, page = 1, id = nextId++) =>
    ocaid === null
        ? { annotation: 'https://example.org/no-details/here', uri: null, id }
        : { annotation: `${HOST}/details/${ocaid}/page/${page}/mode/2up?ref=ol`, uri: null, id };

const workDoc = (key, title, ia) => ({ key, title, edition_key: ['OLx1M', 'OLx2M'], ia });

function container({ canDelete = false } = {}) {
    const canDeleteAttr = canDelete ? ' data-can-delete="true"' : '';
    document.body.innerHTML =
        `<ul class="js-snippets" data-i18n-empty="None" data-i18n-error="Oops" data-i18n-alt="Page"${canDeleteAttr}` +
        ' data-i18n-delete="Delete snippet" data-i18n-delete-confirm="Sure?"></ul>';
    return document.querySelector('.js-snippets');
}

const cards = () => [...document.querySelectorAll('.snippets-grid__item')];
const buttonsIn = li => li.querySelectorAll('ol-shelf-button');
const captionIn = li => li.querySelector('.snippet-card__title');
const deleteBtnIn = li => li.querySelector('.snippet-card__delete');
/** Let the async click handler's fetch + DOM update settle. */
const flush = () => new Promise(resolve => setTimeout(resolve, 0));

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
    const caption = captionIn(li);
    expect(caption.textContent).toBe('Mack the Life');
    // Clickable, links to the work, and sits above the snippet image.
    expect(caption.getAttribute('href')).toBe('/works/OL1W');
    expect(caption.compareDocumentPosition(li.querySelector('.snippet-card__img')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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
    const item = { id: 1, annotation: 'https://archive.org/details/?ref=ol', uri: null };
    stubFetch([item], []);

    await initSnippets(container());

    const list = cards();
    expect(list).toHaveLength(1);
    expect(searchCalls).toHaveLength(0);
    expect(buttonsIn(list[0])).toHaveLength(0);
    expect(list[0].querySelector('.snippet-card__img')).not.toBeNull();
});

test('rejects a non-http(s) scheme even when the URL contains /details/', async () => {
    // A javascript: URL that would otherwise satisfy the /details/ substring check.
    const item = { annotation: 'javascript:alert(1)//details/x', uri: null };
    stubFetch([item], []);

    await initSnippets(container());

    expect(cards()).toHaveLength(0);
    expect(searchCalls).toHaveLength(0);
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

// ---- admin [x] delete control ----

test('no delete control when the viewer is not an admin (data-can-delete unset)', async () => {
    stubFetch([snippet('macklife0000mack', 1, 42)], [workDoc('/works/OL1W', 'Mack', ['macklife0000mack'])]);

    await initSnippets(container());

    expect(deleteBtnIn(cards()[0])).toBeNull();
});

test('an admin gets an [x] delete control on every card, matched or not', async () => {
    const items = [snippet('macklife0000mack', 1, 42), snippet('ghostocaid00none', 1, 43)];
    stubFetch(items, [workDoc('/works/OL1W', 'Mack', ['macklife0000mack'])]);

    await initSnippets(container({ canDelete: true }));

    const list = cards();
    expect(deleteBtnIn(list[0])).not.toBeNull(); // enriched card
    expect(deleteBtnIn(list[1])).not.toBeNull(); // unmatched card — delete is independent of solr
});

test('clicking [x] DELETEs /snippets/{id} and removes the card on success', async () => {
    window.confirm = vi.fn(() => true);
    stubFetch([snippet('macklife0000mack', 1, 42)], [workDoc('/works/OL1W', 'Mack', ['macklife0000mack'])]);

    await initSnippets(container({ canDelete: true }));
    deleteBtnIn(cards()[0]).click();
    await flush();

    expect(deleteCalls).toEqual(['/snippets/42']);
    expect(cards()).toHaveLength(0);
});

test('a cancelled confirm deletes nothing and keeps the card', async () => {
    window.confirm = vi.fn(() => false);
    stubFetch([snippet('macklife0000mack', 1, 42)], [workDoc('/works/OL1W', 'Mack', ['macklife0000mack'])]);

    await initSnippets(container({ canDelete: true }));
    deleteBtnIn(cards()[0]).click();
    await flush();

    expect(deleteCalls).toEqual([]);
    expect(cards()).toHaveLength(1);
});

test('a failed delete keeps the card so the librarian can retry', async () => {
    window.confirm = vi.fn(() => true);
    stubFetch([snippet('macklife0000mack', 1, 42)], [workDoc('/works/OL1W', 'Mack', ['macklife0000mack'])], {
        deleteOk: false
    });

    await initSnippets(container({ canDelete: true }));
    deleteBtnIn(cards()[0]).click();
    await flush();

    expect(deleteCalls).toEqual(['/snippets/42']);
    expect(cards()).toHaveLength(1);
});

test('the image is served by the snippet image endpoint, keyed by annotation id', async () => {
    stubFetch([{ id: 42, annotation: `${HOST}/details/macklife0000mack/page/3`, uri: null }], []);

    await initSnippets(container());

    const [card] = cards();
    expect(card.querySelector('.snippet-card__img').getAttribute('src')).toBe('/cdn/snippets/42');
    expect(card.querySelector('.snippet-card').getAttribute('href')).toBe(`${HOST}/details/macklife0000mack/page/3`);
});

test('a snippet without an id renders no card', async () => {
    stubFetch([{ annotation: `${HOST}/details/macklife0000mack/page/3`, uri: null }], []);

    await initSnippets(container());

    expect(cards()).toHaveLength(0);
});
