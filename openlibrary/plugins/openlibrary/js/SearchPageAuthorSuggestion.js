import { deriveAuthors } from './search-modal/authorSuggestion.js';

function docsFromResults(list) {
    return Array.from(list.children)
        .filter(item => item.classList.contains('searchResultItem'))
        .map((item) => {
            const authorLink = item.querySelector('.bookauthor a[href^="/authors/"]');
            const href = authorLink?.getAttribute('href') || '';
            const match = href.match(/^\/authors\/([^/?#]+)/);
            return {
                author_key: match ? [match[1]] : undefined,
                author_name: authorLink?.textContent?.trim() ? [authorLink.textContent.trim()] : undefined,
            };
        });
}

function authorRow(author, authorLabel) {
    const item = document.createElement('li');
    item.className = 'searchResultItem sri--w-main search-page-author-suggestion';

    const link = document.createElement('a');
    link.className = 'search-page-author-suggestion__link';
    link.href = `/authors/${author.key}`;

    const avatar = document.createElement('span');
    avatar.className = 'search-page-author-suggestion__avatar';

    const image = document.createElement('img');
    image.src = `https://covers.openlibrary.org/a/olid/${author.key}-S.jpg?default=false`;
    image.srcset = `https://covers.openlibrary.org/a/olid/${author.key}-M.jpg?default=false 2x`;
    image.alt = '';
    image.loading = 'lazy';
    image.addEventListener('error', () => {
        image.hidden = true;
    });

    const details = document.createElement('span');
    details.className = 'details';

    const title = document.createElement('span');
    title.className = 'resultTitle';

    const heading = document.createElement('h3');
    heading.className = 'booktitle';
    heading.textContent = author.name;

    const label = document.createElement('span');
    label.className = 'bookauthor';
    label.textContent = authorLabel || 'Author';

    avatar.append(image);
    title.append(heading);
    details.append(title, label);
    link.append(avatar, details);
    item.append(link);
    return item;
}

export function initSearchPageAuthorSuggestion(container) {
    if (!container || container.dataset.authorSuggestionAttached === 'true') return;
    const list = container.querySelector('.list-books');
    const query = container.dataset.query || '';
    if (!list || !query.trim()) return;

    const authors = deriveAuthors(docsFromResults(list), query);
    if (!authors.length) return;

    container.dataset.authorSuggestionAttached = 'true';
    list.prepend(...authors.map(author => authorRow(author, container.dataset.authorLabel)));
}
