import { LitElement, html, css, nothing } from 'lit';
import './OlCarousel.js';
import './OlIcon.js';

/**
 * A Lit component that displays a carousel of books with numerically/lexically close
 * Dewey Decimal Classification (DDC) numbers ("shelf-adjacency" browsing).
 *
 * @element ol-nearby-books
 * @prop {String} targetDdc - The normalized ddc_sort value to base the query on
 * @prop {String} workKey - The current work key to exclude from results
 * @prop {String} language - The ISO/MARC language code to filter results (e.g. "eng")
 * @prop {Number} limit - Number of books to fetch in each direction (default: 10)
 */
export class OlNearbyBooks extends LitElement {
    static properties = {
        targetDdc: { type: String, attribute: 'target-ddc' },
        workKey: { type: String, attribute: 'work-key' },
        language: { type: String },
        limit: { type: Number },
        _books: { type: Array, state: true },
        _loading: { type: Boolean, state: true },
        _error: { type: Boolean, state: true },
    };

    static styles = css`
        :host {
            display: block;
            margin-top: 2rem;
            margin-bottom: 2rem;
        }

        :host([hidden]) {
            display: none;
        }

        .nearby-books-container {
            position: relative;
        }

        .nearby-books-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
        }

        .nearby-books-title {
            font-size: 1.5rem;
            font-weight: 700;
            margin: 0;
            color: var(--color-text, #111);
        }

        .nearby-books-subtitle {
            font-size: 0.9rem;
            color: var(--color-text-subtle, #555);
            margin-top: 0.25rem;
        }

        .book-card {
            display: flex;
            flex-direction: column;
            width: 130px;
            text-decoration: none;
            color: inherit;
        }

        .cover-wrapper {
            position: relative;
            width: 130px;
            height: 190px;
            background: #f0f0f0;
            border-radius: 4px;
            overflow: hidden;
            box-shadow: 0 2px 6px rgba(0,0,0,0.12);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .book-card:hover .cover-wrapper {
            transform: translateY(-4px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.18);
        }

        .cover-image {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .fallback-cover {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100%;
            padding: 8px;
            text-align: center;
            box-sizing: border-box;
            background: #e0e6ed;
            color: #333;
        }

        .fallback-title {
            font-size: 0.8rem;
            font-weight: bold;
            line-clamp: 3;
            -webkit-line-clamp: 3;
            display: -webkit-box;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .book-info {
            margin-top: 8px;
        }

        .book-title {
            font-size: 0.85rem;
            font-weight: 600;
            line-height: 1.2;
            margin: 0 0 2px 0;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .book-author {
            font-size: 0.75rem;
            color: var(--color-text-subtle, #666);
            margin: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .ddc-badge {
            font-size: 0.7rem;
            color: var(--color-text-muted, #888);
            margin-top: 2px;
        }
    `;

    constructor() {
        super();
        this.targetDdc = '';
        this.workKey = '';
        this.language = '';
        this.limit = 10;
        this._books = [];
        this._loading = false;
        this._error = false;
    }

    willUpdate(changedProperties) {
        if (
            changedProperties.has('targetDdc') ||
            changedProperties.has('workKey') ||
            changedProperties.has('language')
        ) {
            if (this.targetDdc) {
                this._fetchNearbyBooks();
            } else {
                this._books = [];
            }
        }
    }

    async _fetchNearbyBooks() {
        if (!this.targetDdc) return;

        this._loading = true;
        this._error = false;

        const cleanDdc = this.targetDdc.replace(/"/g, '');
        const cleanWorkKey = this.workKey ? this.workKey.replace(/"/g, '') : '';
        const langFilter = this.language ? `language:${encodeURIComponent(this.language)} AND ` : '';
        const keyFilter = cleanWorkKey ? ` AND -key:"${encodeURIComponent(cleanWorkKey)}"` : '';

        const fields = 'key,title,author_name,cover_i,ddc_sort,ia';

        // Query before (<= targetDdc)
        const beforeUrl = `/search.json?q=${langFilter}ddc_sort:[* TO "${encodeURIComponent(cleanDdc)}"]${keyFilter}&sort=ddc_sort desc&limit=${this.limit}&fields=${fields}`;

        // Query after (>= targetDdc)
        const afterUrl = `/search.json?q=${langFilter}ddc_sort:["${encodeURIComponent(cleanDdc)}" TO *]${keyFilter}&sort=ddc_sort asc&limit=${this.limit}&fields=${fields}`;

        try {
            const [beforeRes, afterRes] = await Promise.all([
                fetch(beforeUrl).then((r) => (r.ok ? r.json() : { docs: [] })),
                fetch(afterUrl).then((r) => (r.ok ? r.json() : { docs: [] })),
            ]);

            const beforeDocs = (beforeRes.docs || []).reverse(); // sort ascending
            const afterDocs = afterRes.docs || [];

            // Combine and deduplicate
            const combinedMap = new Map();
            for (const doc of [...beforeDocs, ...afterDocs]) {
                if (doc.key && !combinedMap.has(doc.key)) {
                    combinedMap.set(doc.key, doc);
                }
            }

            this._books = Array.from(combinedMap.values());
        } catch (err) {
            // eslint-disable-next-line no-console
            console.error('Error fetching nearby books:', err);
            this._error = true;
            this._books = [];
        } finally {
            this._loading = false;
        }
    }

    _getCoverUrl(book) {
        if (book.cover_i && book.cover_i !== -1) {
            return `//covers.openlibrary.org/b/id/${book.cover_i}-M.jpg`;
        }
        if (book.ia && book.ia[0]) {
            return `//covers.openlibrary.org/b/ia/${book.ia[0]}-M.jpg`;
        }
        return null;
    }

    render() {
        if (!this.targetDdc || (!this._loading && this._books.length === 0)) {
            return nothing;
        }

        return html`
            <div class="nearby-books-container">
                <div class="nearby-books-header">
                    <div>
                        <h2 class="nearby-books-title">Nearby Books</h2>
                        <div class="nearby-books-subtitle">
                            Books with similar Dewey Decimal classifications (DDC ${this.targetDdc})
                        </div>
                    </div>
                </div>

                ${this._loading
        ? html`<div class="loading">Loading nearby books...</div>`
        : html`
                          <ol-carousel label="Nearby Books">
                              ${this._books.map((book) => this._renderBookCard(book))}
                          </ol-carousel>
                      `}
            </div>
        `;
    }

    _renderBookCard(book) {
        const coverUrl = this._getCoverUrl(book);
        const authorName = book.author_name ? book.author_name.join(', ') : '';

        return html`
            <a href="${book.key}" class="book-card">
                <div class="cover-wrapper">
                    ${coverUrl
        ? html`<img
                              class="cover-image"
                              src="${coverUrl}"
                              alt="${book.title}"
                              loading="lazy"
                          />`
        : html`
                              <div class="fallback-cover">
                                  <span class="fallback-title">${book.title}</span>
                              </div>
                          `}
                </div>
                <div class="book-info">
                    <h3 class="book-title" title="${book.title}">${book.title}</h3>
                    ${authorName
        ? html`<p class="book-author" title="${authorName}">${authorName}</p>`
        : nothing}
                    ${book.ddc_sort
        ? html`<div class="ddc-badge">DDC: ${book.ddc_sort}</div>`
        : nothing}
                </div>
            </a>
        `;
    }
}

customElements.define('ol-nearby-books', OlNearbyBooks);
