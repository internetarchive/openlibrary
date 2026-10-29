/**
 * Snippets feed (/snippets).
 *
 * Fetches the most recently shared snippets from /api/snippets and renders a
 * grid of images. Each image is the book page (fetched server-side by
 * /cdn/snippets/<id> from the "download" host) and links to the full
 * "details" page (opened in a new tab). Usernames are intentionally not shown.
 *
 * The cards are then enriched with ONE bulk search/editions.json request for
 * the whole page: every snippet's archive.org id (the "ocaid", the path segment
 * after /details/) is collected and resolved to the Open Library edition
 * scanned as it in a single `ia:(…)` query. Each matched card gains a bar
 * under its image with the edition's cover, title and authors, and the
 * standard <ol-shelf-button> for its work, so a reader can shelve / add the
 * book to a list. book-state.js hydrates those buttons (user key + reading
 * state).
 *
 * Note: /api/snippets returns openlibrary_work / openlibrary_edition as null,
 * so the book is resolved client-side from the ocaid rather than read off the
 * annotation.
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
        alt: container.dataset.i18nAlt || '',
        untitled: container.dataset.i18nUntitled || 'Untitled',
        delete: container.dataset.i18nDelete || 'Delete snippet',
        deleteConfirm: container.dataset.i18nDeleteConfirm || 'Delete this snippet? This cannot be undone.'
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

    // Admins/super-librarians get a delete control on every card (the server
    // sets data-can-delete only for them; the DELETE endpoint re-checks the
    // role, so this is UI convenience, not the security boundary).
    if (container.dataset.canDelete === 'true') {
        addDeleteControls(container, strings);
    }

    // Enrich the whole page with a single bulk solr lookup.
    await enrichCards(container, items, strings);
}

/**
 * Add an [x] delete control to every card that carries a snippet id. Shown only
 * to super-librarians (gated by the caller). Deletes via the FastAPI endpoint,
 * which re-checks the role server-side.
 */
function addDeleteControls(container, strings) {
    const cards = container.querySelectorAll('.snippets-grid__item[data-snippet-id]');
    cards.forEach(li => {
        const id = li.dataset.snippetId;
        if (!id) return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'snippet-card__delete';
        button.setAttribute('aria-label', strings.delete);
        button.title = strings.delete;
        button.textContent = '×'; // ×
        button.addEventListener('click', () => deleteSnippet(li, id, strings));
        li.appendChild(button);
    });
}

/**
 * Delete one snippet by id, then drop its card. On failure the card stays so the
 * librarian can retry; the endpoint is the real authority on who may delete.
 */
async function deleteSnippet(li, id, strings) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(strings.deleteConfirm)) return;
    try {
        const response = await fetch(`/snippets/${encodeURIComponent(id)}`, {
            method: 'DELETE',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (response.ok) {
            li.remove();
        } else {
            // eslint-disable-next-line no-console
            console.error(`Failed to delete snippet ${id}: HTTP ${response.status}`);
        }
    } catch (error) {
        // eslint-disable-next-line no-console
        console.error(`Failed to delete snippet ${id}:`, error);
    }
}

/**
 * Base card: the snippet image (served by /cdn/snippets/<id>) linking to the
 * details page. Returns '' for rows without an id or a usable details URL.
 */
function cardHtml(item, index, alt) {
    const detailsUrl = item.annotation || item.uri;
    // Only render genuine http(s) links, so a non-http scheme (e.g. javascript:)
    // can never reach the card's href/src even if it contains "/details/".
    if (item.id === null || item.id === undefined) return '';
    if (!detailsUrl || !/^https?:\/\//i.test(detailsUrl) || !detailsUrl.includes('/details/')) return '';
    const imageUrl = `/cdn/snippets/${encodeURIComponent(item.id)}`;
    // The snippet id also lets an admin delete the card (see addDeleteControls).
    const idAttr = ` data-snippet-id="${escapeAttr(item.id)}"`;
    return (
        `<li class="snippets-grid__item snippet-card" data-index="${index}"${idAttr}>` +
        `<a class="snippet-card__image-link" href="${escapeAttr(publicDetailsUrl(detailsUrl))}" target="_blank" rel="noopener noreferrer">` +
        `<img class="snippet-card__img" src="${escapeAttr(imageUrl)}" alt="${escapeAttr(alt)}" loading="lazy">` +
        `</a></li>`
    );
}

/** www-<name>.archive.org hosts are developers' environments; readers go to archive.org. */
const DEV_ARCHIVE_HOST_RE = /^www-[^.]+\.archive\.org$/i;

/** A snippet's details URL, on archive.org itself rather than a www-* host. */
function publicDetailsUrl(detailsUrl) {
    let url;
    try {
        url = new URL(detailsUrl);
    } catch {
        return detailsUrl;
    }
    if (DEV_ARCHIVE_HOST_RE.test(url.hostname)) url.hostname = 'archive.org';
    return url.href;
}

/**
 * Resolve every snippet's edition in ONE search/editions.json request and
 * decorate each card whose ocaid matched. Snippets with no ocaid, or whose
 * ocaid has no solr match, keep their plain image + link (no caption, no shelf
 * button).
 */
async function enrichCards(container, items, strings) {
    const ocaidByIndex = items.map(ocaidFromItem);
    const ocaids = [...new Set(ocaidByIndex.filter(Boolean))];
    if (!ocaids.length) return;

    const byOcaid = await lookupEditionsByOcaid(ocaids);
    if (!byOcaid || !byOcaid.size) return;

    const coversHost = container.dataset.coversHost || '';
    ocaidByIndex.forEach((ocaid, index) => {
        const edition = ocaid && byOcaid.get(ocaid);
        if (edition) decorateCard(container, index, edition, coversHost, strings);
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
 * @typedef {object} SnippetEdition
 * @property {string} key - "/books/OL…M"
 * @property {string} title
 * @property {string} workKey - "/works/OL…W", or '' if the edition has none
 * @property {string[]} authorKeys
 * @property {string[]} authorNames
 * @property {number|null} coverId
 */

/**
 * One bulk `ia:(id OR id …)` edition search for the page. Returns a Map from
 * ocaid to the edition scanned as it. An edition's `ia` lists the ocaids of
 * its scans, so one edition can back several snippets.
 * @param {string[]} ocaids - unique, already validated by OCAID_RE
 * @returns {Promise<Map<string, SnippetEdition>|null>}
 */
async function lookupEditionsByOcaid(ocaids) {
    const q = `ia:(${ocaids.join(' OR ')})`;
    const fields = 'key,title,work_key,ia,author_key,author_name,cover_i';
    try {
        // Rarely, one scan is attached to several editions; leave room for them.
        const url = `/search/editions.json?q=${encodeURIComponent(q)}&fields=${fields}&limit=${ocaids.length * 2}`;
        const response = await fetch(url);
        if (!response.ok) return null;
        const data = await response.json();
        const docs = (data && data.docs) || [];

        const wanted = new Set(ocaids);
        const byOcaid = new Map();
        for (const doc of docs) {
            if (!doc || !doc.key) continue;
            const workKey = (doc.work_key || [])[0];
            const edition = {
                key: doc.key,
                title: doc.title || '',
                workKey: workKey ? `/works/${workKey}` : '',
                authorKeys: doc.author_key || [],
                authorNames: doc.author_name || [],
                coverId: doc.cover_i || null
            };
            for (const ia of doc.ia || []) {
                if (wanted.has(ia) && !byOcaid.has(ia)) byOcaid.set(ia, edition);
            }
        }
        return byOcaid;
    } catch {
        return null;
    }
}

/**
 * Add the bar under a card's image: the edition's cover, its title and authors,
 * and an <ol-shelf-button> for its work on the right.
 * @param {SnippetEdition} edition
 * @param {string} coversHost - the coverstore's origin; covers are skipped without it
 */
function decorateCard(container, index, edition, coversHost, strings) {
    const li = container.querySelector(`.snippets-grid__item[data-index="${index}"]`);
    if (!li) return;

    const editionUrl = `${edition.key}/${urlsafe(edition.title || 'untitled')}`;
    const displayTitle = edition.title || strings.untitled;
    if (edition.title) {
        const img = li.querySelector('.snippet-card__img');
        if (img) img.alt = edition.title;
    }

    const bar = document.createElement('div');
    bar.className = 'snippet-card__bar';

    const coverLink = document.createElement('a');
    coverLink.className = 'snippet-card__cover';
    coverLink.href = editionUrl;
    coverLink.tabIndex = -1; // the title link goes to the same place
    coverLink.setAttribute('aria-hidden', 'true');
    if (edition.coverId && coversHost) {
        const cover = document.createElement('img');
        cover.src = `${coversHost}/b/id/${edition.coverId}-M.jpg`;
        cover.alt = '';
        cover.loading = 'lazy';
        coverLink.appendChild(cover);
    }
    bar.appendChild(coverLink);

    const meta = document.createElement('div');
    meta.className = 'snippet-card__meta';
    const title = document.createElement('a');
    title.className = 'snippet-card__title';
    title.href = editionUrl;
    title.textContent = displayTitle;
    meta.appendChild(title);
    if (edition.authorNames.length) {
        const authors = document.createElement('div');
        authors.className = 'snippet-card__authors';
        edition.authorNames.forEach((name, i) => {
            if (i) authors.appendChild(document.createTextNode(', '));
            const key = edition.authorKeys[i];
            const author = document.createElement(key ? 'a' : 'span');
            if (key) author.href = `/authors/${key}/${urlsafe(name || 'unnamed')}`;
            author.textContent = name;
            authors.appendChild(author);
        });
        meta.appendChild(authors);
    }
    bar.appendChild(meta);

    // Shelving acts on a work, so an edition without one gets no button.
    if (edition.workKey) {
        const actions = document.createElement('div');
        actions.className = 'snippet-card__actions';

        // Standard shelf / add-to-list control. No user-key: book-state.js fills
        // in the reader's key and reading state once it's in the DOM.
        const button = document.createElement('ol-shelf-button');
        button.setAttribute('variant', 'outline');
        button.setAttribute('work-key', edition.workKey);
        button.setAttribute('edition-key', edition.key.split('/').pop());
        button.setAttribute('book-title', displayTitle);
        actions.appendChild(button);
        bar.appendChild(actions);
    }

    li.querySelector('.snippet-card__image-link').after(bar);
}

/** Runs of the chars RFC 2396 calls unsafe in a path; see urlsafe(). */
const UNSAFE_PATH_CHARS_RE = /[;/?:@&=+$,<>#%"{}|\\^[\]` \n\r]+/g;

/**
 * The title slug Open Library puts after a key ("/books/OL…M/<slug>"); the
 * same as core.helpers.urlsafe, so links skip the redirect to the canonical
 * URL.
 */
function urlsafe(title) {
    const slug = title.replace(UNSAFE_PATH_CHARS_RE, '_').replace(/^_+|_+$/g, '');
    return Array.from(slug).slice(0, 100).join('');
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
