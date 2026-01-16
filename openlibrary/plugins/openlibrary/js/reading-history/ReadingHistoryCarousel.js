// Carousel component for displaying reading history on My Books page

import { ReadingHistory } from './ReadingHistory';
import { htmlquote } from '../jsdef.js';

const DEFAULT_LIMIT = 50;
const LAZY_LOAD_THRESHOLD = 5; // lazy load images after first 5
const TITLE_TRUNCATE_LENGTH = 70;
const AUTHOR_TRUNCATE_LENGTH = 30;

// Get coverstore URL - check config first, fallback to default
function getCoverstoreUrl() {
    if (typeof window !== 'undefined' && window.CONFIGS && window.CONFIGS.OL_BASE_COVERS) {
        const base = window.CONFIGS.OL_BASE_COVERS;
        return base.startsWith('http') ? base : `https://${base}`;
    }
    return 'https://covers.openlibrary.org';
}

export class ReadingHistoryCarousel {
    constructor(container) {
        this.container = container;
        this.apiEndpoint = '/reading-history';
        this.coverstoreUrl = getCoverstoreUrl();
    }

    // Load and display the carousel
    async init() {
        if (!ReadingHistory.isAvailable()) {
            return;
        }

        const editionIds = ReadingHistory.getEditionIds(DEFAULT_LIMIT);

        if (editionIds.length === 0) {
            return; // nothing to show
        }

        try {
            const books = await this.fetchBooks(editionIds);
            if (books && books.length > 0) {
                this.renderCarousel(books);
            }
        } catch {
            // Silently fail - reading history is a nice-to-have feature
            // Error could be due to network issues, API problems, etc.
        }
    }

    // Fetch book data from API
    async fetchBooks(editionIds) {
        const url = `${this.apiEndpoint}?edition_ids=${editionIds.join(',')}&limit=${DEFAULT_LIMIT}`;
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`API request failed: ${response.status}`);
        }

        const data = await response.json();
        return data.docs || [];
    }

    // Render the carousel HTML and initialize it
    renderCarousel(books) {
        const config = {
            booksPerBreakpoint: [4, 4, 4, 3, 2, 1], // compact layout
            analyticsCategory: 'BookCarousel',
            carouselKey: 'reading-history',
            loadMore: null
        };

        // Build HTML for all book cards
        const bookCards = books.map((book, index) => {
            const lazy = index > LAZY_LOAD_THRESHOLD;
            return this.renderBookCard(book, lazy);
        }).join('');

        // Get i18n string for "Reading History" if available
        const readingHistoryLabel = (typeof window !== 'undefined' && window._)
            ? window._('Reading History')
            : 'Reading History';

        const carouselHtml = `
            <div class="carousel-section">
                <div class="carousel-section-header">
                    <h2 class="home-h2">
                        <a name="reading-history" href="#reading-history">${htmlquote(readingHistoryLabel)} (${books.length})</a>
                    </h2>
                </div>
                <div class="carousel-container carousel-container-decorated">
                    <div class="carousel carousel--compact carousel--progressively-enhanced"
                         data-config='${JSON.stringify(config)}'>
                        ${bookCards}
                    </div>
                </div>
            </div>
        `;

        this.container.innerHTML = carouselHtml;

        // Initialize the carousel component
        const carouselElement = this.container.querySelector('.carousel--progressively-enhanced');
        if (carouselElement) {
            import('../carousel').then(module => {
                module.initialzeCarousels([carouselElement]);
            });
        }
    }

    // Render HTML for a single book card
    renderBookCard(book, lazy = false) {
        const key = book.key || '';
        const title = book.title || '';
        const coverId = book.cover_i || book.cover_id || null;
        const coverEditionKey = book.cover_edition_key || '';
        const authorNames = (book.author_name || []).join(', ') || '';
        const editionKey = book.edition_key || key.split('/').pop() || '';

        // Escape user data to prevent XSS
        const safeTitle = htmlquote(title);
        const safeAuthorNames = htmlquote(authorNames);
        const safeTitleAttr = safeTitle + (safeAuthorNames ? ` by ${safeAuthorNames}` : '');

        // Build cover image URL
        let coverUrl = '';
        if (coverId) {
            coverUrl = `${this.coverstoreUrl}/b/id/${coverId}-M.jpg`;
        } else if (coverEditionKey) {
            coverUrl = `${this.coverstoreUrl}/b/olid/${coverEditionKey}-M.jpg`;
        }

        // Build link to book page
        const bookUrl = key ? `/${key.split('/').slice(1).join('/')}` : '#';

        // Analytics tracking
        const analyticsAttr = editionKey
            ? `data-ol-link-track="ReadingHistoryCarousel|BookClick|${htmlquote(editionKey)}"`
            : '';

        const lazyAttr = lazy ? `data-lazy="${coverUrl}" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="` : `src="${coverUrl}"`;

        return `
            <div class="book">
                <div class="book-cover">
                    <a href="${bookUrl}" title="${safeTitleAttr}" ${analyticsAttr}>
                        ${coverUrl ? `
                            <img class="bookcover" ${lazyAttr}
                                 alt="${safeTitle}"
                                 title="${safeTitleAttr}" />
                        ` : `
                            <div class="carousel__item__blankcover" title="${safeTitle}">
                                <div class="carousel__item__blankcover--title">${htmlquote(this.truncate(title, TITLE_TRUNCATE_LENGTH))}</div>
                                ${authorNames ? `<div class="carousel__item__blankcover--authors">${htmlquote(this.truncate(authorNames, AUTHOR_TRUNCATE_LENGTH))}</div>` : ''}
                            </div>
                        `}
                    </a>
                </div>
            </div>
        `;
    }

    // Truncate text if it's too long
    truncate(str, maxLength) {
        if (!str || str.length <= maxLength) {
            return str;
        }
        return `${str.substring(0, maxLength - 3)}...`;
    }
}

