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
 * the `docs` (flattened, so a workDoc's editions can sit beside single
 * editionDocs; an error when `searchOk` is false); a DELETE is recorded and
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
        if (u.includes('/search/editions.json')) {
            const parsed = new URL(u, 'https://ol.test');
            searchCalls.push(parsed);
            if (!searchOk) return { ok: false, status: 500, json: async () => ({}) };
            return { ok: true, status: 200, json: async () => ({ docs: docs.flat() }) };
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

/** An edition search doc, as search/editions.json returns it. */
const editionDoc = (key, title, ia, workKey = 'OL1W') => ({ key, title, ia, work_key: workKey ? [workKey] : [] });
/** One edition per scan of a work (`/works/OL…W`), each titled like the work. */
const workDoc = (key, title, ia) => ia.map((ocaid, i) => editionDoc(`/books/OL${i}_${ocaid}M`, title, [ocaid], key.split('/').pop()));

const COVERS = 'https://covers.test';

function container({ canDelete = false, coversHost = COVERS } = {}) {
    const canDeleteAttr = canDelete ? ' data-can-delete="true"' : '';
    const coversHostAttr = coversHost ? ` data-covers-host="${coversHost}"` : '';
    document.body.innerHTML =
        `<ul class="js-snippets" data-i18n-empty="None" data-i18n-error="Oops" data-i18n-alt="Page" data-i18n-untitled="Untitled"${canDeleteAttr}${coversHostAttr}` +
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

test('decorates each matched card with the edition title and a work-keyed shelf button', async () => {
    const items = [snippet('macklife0000mack')];
    stubFetch(items, [editionDoc('/books/OL28228056M', 'Mack the Life', ['macklife0000mack'], 'OL1W')]);

    await initSnippets(container());

    const li = cards()[0];
    const caption = captionIn(li);
    expect(caption.textContent).toBe('Mack the Life');
    // Clickable, links to the edition, and sits in the bar under the snippet image.
    expect(caption.getAttribute('href')).toBe('/books/OL28228056M/Mack_the_Life');
    expect(caption.closest('.snippet-card__bar')).not.toBeNull();
    expect(li.querySelector('.snippet-card__img').compareDocumentPosition(caption) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const btn = buttonsIn(li)[0];
    expect(btn.getAttribute('work-key')).toBe('/works/OL1W');
    expect(btn.getAttribute('edition-key')).toBe('OL28228056M');
    expect(btn.getAttribute('book-title')).toBe('Mack the Life');
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
    // HOST is a www-* developer host; readers are sent to archive.org itself.
    expect(card.querySelector('.snippet-card__image-link').getAttribute('href')).toBe('https://archive.org/details/macklife0000mack/page/3');
});

test('the details link keeps hosts other than www-* developer hosts', async () => {
    const annotation = 'https://archive.org/details/macklife0000mack/page/3?text=a+b';
    stubFetch([{ id: 42, annotation, uri: null }], []);

    await initSnippets(container());

    expect(cards()[0].querySelector('.snippet-card__image-link').getAttribute('href')).toBe(annotation);
});

test('a snippet without an id renders no card', async () => {
    stubFetch([{ annotation: `${HOST}/details/macklife0000mack/page/3`, uri: null }], []);

    await initSnippets(container());

    expect(cards()).toHaveLength(0);
});

// ---- edition resolution ----

test('looks up editions, linking the title to the edition and shelving its work', async () => {
    stubFetch([snippet('annakarnina00tols')], [editionDoc('/books/OL24197483M', 'Anna Karénina', ['annakarnina00tols'], 'OL267096W')]);

    await initSnippets(container());

    const [li] = cards();
    expect(captionIn(li).getAttribute('href')).toBe('/books/OL24197483M/Anna_Karénina');
    expect(captionIn(li).textContent).toBe('Anna Karénina');
    const button = buttonsIn(li)[0];
    expect(button.getAttribute('work-key')).toBe('/works/OL267096W');
    expect(button.getAttribute('edition-key')).toBe('OL24197483M');
    expect(searchCalls[0].pathname).toBe('/search/editions.json');
    expect(searchCalls[0].searchParams.get('fields').split(',')).toEqual(expect.arrayContaining(['key', 'title', 'work_key', 'ia']));
});

test('distinct scans of one work each link to their own edition', async () => {
    stubFetch(
        [snippet('annakarnina00tols'), snippet('annakarenina0000coun')],
        [
            editionDoc('/books/OL1M', 'Anna Karénina', ['annakarnina00tols'], 'OL2W'),
            editionDoc('/books/OL2M', 'Anna Karenina', ['annakarenina0000coun'], 'OL2W')
        ]
    );

    await initSnippets(container());

    expect(searchCalls).toHaveLength(1);
    const [first, second] = cards();
    expect(captionIn(first).getAttribute('href')).toBe('/books/OL1M/Anna_Karénina');
    expect(captionIn(second).getAttribute('href')).toBe('/books/OL2M/Anna_Karenina');
});

test('an edition without a work gets its title link but no shelf button', async () => {
    stubFetch([snippet('macklife0000mack')], [editionDoc('/books/OL9M', 'Orphan', ['macklife0000mack'], null)]);

    await initSnippets(container());

    const [li] = cards();
    expect(captionIn(li).getAttribute('href')).toBe('/books/OL9M/Orphan');
    expect(buttonsIn(li)).toHaveLength(0);
});

test('the bar shows the edition cover from the coverstore, linked to the edition', async () => {
    const doc = { ...editionDoc('/books/OL9M', 'Mack the life', ['macklife0000mack']), cover_i: 1234 };
    stubFetch([snippet('macklife0000mack')], [doc]);

    await initSnippets(container());

    const cover = cards()[0].querySelector('.snippet-card__cover');
    expect(cover.getAttribute('href')).toBe('/books/OL9M/Mack_the_life');
    expect(cover.querySelector('img').getAttribute('src')).toBe(`${COVERS}/b/id/1234-M.jpg`);
});

test('no cover image without a cover id or without a coverstore host', async () => {
    const withCover = { ...editionDoc('/books/OL9M', 'Mack', ['macklife0000mack']), cover_i: 1234 };
    stubFetch([snippet('macklife0000mack')], [withCover]);
    await initSnippets(container({ coversHost: '' }));
    expect(cards()[0].querySelector('.snippet-card__cover img')).toBeNull();

    stubFetch([snippet('macklife0000mack')], [editionDoc('/books/OL9M', 'Mack', ['macklife0000mack'])]);
    await initSnippets(container());
    expect(cards()[0].querySelector('.snippet-card__cover img')).toBeNull();
});

test('lists every author, each linked with its name slug', async () => {
    const doc = {
        ...editionDoc('/books/OL9M', 'Collected', ['macklife0000mack']),
        author_key: ['OL1A', 'OL2A'],
        author_name: ['Jane Austen', 'Leo Tolstoy']
    };
    stubFetch([snippet('macklife0000mack')], [doc]);

    await initSnippets(container());

    const authors = cards()[0].querySelector('.snippet-card__authors');
    expect(authors.textContent).toBe('Jane Austen, Leo Tolstoy');
    expect([...authors.querySelectorAll('a')].map(a => a.getAttribute('href'))).toEqual(['/authors/OL1A/Jane_Austen', '/authors/OL2A/Leo_Tolstoy']);
});

test('an untitled edition still gets a named title link', async () => {
    stubFetch([snippet('macklife0000mack')], [editionDoc('/books/OL9M', '', ['macklife0000mack'])]);

    await initSnippets(container());

    const caption = captionIn(cards()[0]);
    expect(caption.textContent).toBe('Untitled');
    expect(caption.getAttribute('href')).toBe('/books/OL9M/untitled');
});

test('the edition link carries the same title slug as the server, so it needs no redirect', async () => {
    const title = `  Who? What: Where/When & "Why" ${'x'.repeat(120)}`;
    stubFetch([snippet('macklife0000mack')], [editionDoc('/books/OL9M', title, ['macklife0000mack'])]);

    await initSnippets(container());

    // core.helpers.urlsafe: runs of unsafe chars -> "_", trimmed, first 100 chars.
    const slug = `Who_What_Where_When_Why_${'x'.repeat(120)}`.slice(0, 100);
    expect(captionIn(cards()[0]).getAttribute('href')).toBe(`/books/OL9M/${slug}`);
});
