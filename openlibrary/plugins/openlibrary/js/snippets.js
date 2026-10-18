/**
 * Snippets feed (/snippets).
 *
 * Fetches the most recently shared snippets from /api/snippets and renders a
 * grid of images. Each image is the book page rendered via the "download" host
 * and links to the full "details" page (opened in a new tab). Usernames are
 * intentionally not shown.
 *
 * The cards are then enriched with ONE bulk search.json request for the whole
 * page: every snippet's archive.org id (the "ocaid", the path segment after
 * /details/) is collected and resolved to its Open Library work in a single
 * `ia:(…)` query. Each matched card gains the work title (as a caption) and the
 * standard <ol-shelf-button>, so a reader can shelve / add the book to a list.
 * book-state.js hydrates those buttons (user key + reading state).
 *
 * Note: /api/snippets returns openlibrary_work / openlibrary_edition as null,
 * so the work is resolved client-side from the ocaid rather than read off the
 * annotation. The work doc's edition_key is a flat list of ALL the work's
 * editions and does not identify the edition for a given ocaid, so the shelf
 * button carries the work key only (edition is left unset, not guessed).
 */

const LIMIT = 25;

/** The ocaid is the /details/<id>/ path segment; archive.org ids are limited
 * to this charset, so the pattern both extracts the id and rejects anything
 * that could inject solr query syntax into the `ia:(…)` lookup below. */
const OCAID_RE = /\/details\/([A-Za-z0-9._-]+)/;

/**
 * @param {HTMLElement} container - the <ul class="js-snippets"> element
 */
export async function initSnippets(container) {
    const strings = {
        empty: container.dataset.i18nEmpty || '',
        error: container.dataset.i18nError || '',
        alt: container.dataset.i18nAlt || ''
    };

    let items;
    try {
        const response = await fetch('/api/snippets?sort_by=created_date&order=desc');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        items = (Array.isArray(data) ? data : []).slice(0, LIMIT);
    } catch (error) {
        // eslint-disable-next-line no-console
        console.error('Failed to load snippets:', error);
        container.innerHTML = statusHtml(strings.error);
        container.setAttribute('aria-busy', 'false');
        return;
    }

    const cards = items.map((item, index) => cardHtml(item, index, strings.alt)).filter(Boolean);
    container.innerHTML = cards.length ? cards.join('') : statusHtml(strings.empty);
    container.setAttribute('aria-busy', 'false');
    if (!cards.length) return;

    // Start the shelf-button engine so the buttons we inject below get the
    // reader's key + reading state (it watches the DOM for new buttons).
    import('./book-state').then(module => module.initBookState()).catch(() => {});

    // Enrich the whole page with a single bulk solr lookup.
    await enrichCards(container, items);
}

/**
 * Base card: the snippet image (download host) linking to the details page.
 * Returns '' for rows without a usable details URL.
 */
function cardHtml(item, index, alt) {
    const detailsUrl = item.annotation || item.uri;
    if (!detailsUrl || !detailsUrl.includes('/details/')) return '';
    const imageUrl = detailsUrl.replace('/details/', '/download/');
    return (
        `<li class="snippets-grid__item" data-index="${index}">` +
        `<a class="snippet-card" href="${escapeAttr(detailsUrl)}" target="_blank" rel="noopener noreferrer">` +
        `<img class="snippet-card__img" src="${escapeAttr(imageUrl)}" alt="${escapeAttr(alt)}" loading="lazy">` +
        `</a></li>`
    );
}

/**
 * Resolve every snippet's work in ONE search.json request and decorate each
 * card whose ocaid matched. Snippets with no ocaid, or whose ocaid has no solr
 * match, keep their plain image + link (no caption, no shelf button).
 */
async function enrichCards(container, items) {
    const ocaidByIndex = items.map(ocaidFromItem);
    const ocaids = [...new Set(ocaidByIndex.filter(Boolean))];
    if (!ocaids.length) return;

    const byOcaid = await lookupWorksByOcaid(ocaids);
    if (!byOcaid || !byOcaid.size) return;

    ocaidByIndex.forEach((ocaid, index) => {
        const doc = ocaid && byOcaid.get(ocaid);
        if (doc) decorateCard(container, index, doc);
    });
}

/** The archive.org id for a snippet, from its details URL, or '' if none. */
function ocaidFromItem(item) {
    const detailsUrl = item.annotation || item.uri;
    if (!detailsUrl) return '';
    const match = OCAID_RE.exec(detailsUrl);
    return match ? match[1] : '';
}

/**
 * One bulk `ia:(id OR id …)` lookup for the page. Returns a Map from ocaid to
 * { key, title }. Each result doc's `ia` field lists the ocaids of that work's
 * scans, so a single work can back several snippets; we map every page ocaid
 * the doc covers back to it.
 * @param {string[]} ocaids - unique, already validated by OCAID_RE
 * @returns {Promise<Map<string, {key: string, title: string}>|null>}
 */
async function lookupWorksByOcaid(ocaids) {
    const q = `ia:(${ocaids.join(' OR ')})`;
    try {
        const url = `/search.json?q=${encodeURIComponent(q)}&fields=key,title,edition_key,ia&limit=${ocaids.length}`;
        const response = await fetch(url);
        if (!response.ok) return null;
        const data = await response.json();
        const docs = (data && data.docs) || [];

        const wanted = new Set(ocaids);
        const byOcaid = new Map();
        for (const doc of docs) {
            if (!doc || !doc.key) continue;
            const entry = { key: doc.key, title: doc.title || '' };
            for (const ia of doc.ia || []) {
                if (wanted.has(ia) && !byOcaid.has(ia)) byOcaid.set(ia, entry);
            }
        }
        return byOcaid;
    } catch {
        return null;
    }
}

/**
 * Add a title caption and an <ol-shelf-button> to a card from its resolved work.
 * @param {{key: string, title: string}} doc - the work this snippet resolved to
 */
function decorateCard(container, index, doc) {
    const li = container.querySelector(`.snippets-grid__item[data-index="${index}"]`);
    if (!li) return;

    if (doc.title) {
        const img = li.querySelector('.snippet-card__img');
        if (img) img.alt = doc.title;

        const caption = document.createElement('div');
        caption.className = 'snippet-card__title';
        caption.textContent = doc.title;
        li.appendChild(caption);
    }

    const actions = document.createElement('div');
    actions.className = 'snippet-card__actions';

    // Standard shelf / add-to-list control. No user-key: book-state.js fills in
    // the reader's key and reading state once it's in the DOM. No edition-key:
    // the ocaid's specific edition is not derivable from the bulk query.
    const button = document.createElement('ol-shelf-button');
    button.setAttribute('variant', 'icon');
    button.setAttribute('work-key', doc.key);
    button.setAttribute('book-title', doc.title || '');

    actions.appendChild(button);
    li.appendChild(actions);
}

function statusHtml(message) {
    return `<li class="snippets-grid__status">${escapeHtml(message)}</li>`;
}

function escapeHtml(text) {
    const el = document.createElement('div');
    el.textContent = String(text ?? '');
    return el.innerHTML;
}

// Safe for use inside a double-quoted HTML attribute.
function escapeAttr(text) {
    return escapeHtml(text).replace(/"/g, '&quot;');
}
