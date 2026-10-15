/**
 * Snippets feed (/snippets).
 *
 * Fetches the most recently shared snippets from /api/snippets and renders a
 * grid of images. Each image is the book page rendered via the "download" host
 * and links to the full "details" page (opened in a new tab). Usernames are
 * intentionally not shown.
 *
 * Each card is then progressively enriched: a search.json lookup (by edition,
 * falling back to work) supplies the work title and work key, which lets us drop
 * in the standard <ol-shelf-button> so a reader can shelve / add the book to a
 * list. book-state.js hydrates those buttons (user key + reading state).
 */

const LIMIT = 25;

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

    // Progressively enrich each card with a title + shelf button.
    items.forEach((item, index) => decorateCard(container, index, item));
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
 * Look up the work (title + key) for a snippet and, if found, add a title
 * caption and an <ol-shelf-button> to its card.
 */
async function decorateCard(container, index, item) {
    const li = container.querySelector(`.snippets-grid__item[data-index="${index}"]`);
    if (!li) return;

    const doc = await lookupWork(item);
    if (!doc || !doc.key) return;

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
    // the reader's key and reading state once it's in the DOM.
    const button = document.createElement('ol-shelf-button');
    button.setAttribute('variant', 'icon');
    button.setAttribute('work-key', doc.key);
    if (item.openlibrary_edition) {
        button.setAttribute('edition-key', olid(item.openlibrary_edition));
    }
    button.setAttribute('book-title', doc.title || '');

    actions.appendChild(button);
    li.appendChild(actions);
}

/**
 * Resolve a snippet's work via search.json, preferring the edition.
 * @returns {Promise<{key: string, title: string}|null>}
 */
async function lookupWork(item) {
    const edition = item.openlibrary_edition ? olid(item.openlibrary_edition) : '';
    const work = item.openlibrary_work ? olid(item.openlibrary_work) : '';

    let q;
    if (edition) q = `edition_key:${edition}`;
    else if (work) q = `key:/works/${work}`;
    else return null;

    try {
        const url = `/search.json?q=${encodeURIComponent(q)}&fields=key,title&limit=1`;
        const response = await fetch(url);
        if (!response.ok) return null;
        const data = await response.json();
        const doc = data && data.docs && data.docs[0];
        return doc && doc.key ? { key: doc.key, title: doc.title || '' } : null;
    } catch {
        return null;
    }
}

/** Reduce "/works/OL1W", "/books/OL1M", or "OL1M" to the bare OLID. */
function olid(value) {
    return String(value).trim().split('/').pop();
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
