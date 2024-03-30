/**
 * Class for displaying a card for a book, and having it
 * update as it makes requests for information about the book.
 */
const OL_BASE = new URLSearchParams(window.location.search).get('ol_base') || '';

export default class LazyBookCard {
    /**
     * @param {LazyBookCardState} state
     */
    constructor(state) {
        this.state = state;
        /** @type {JQuery} */
        this.ui = null;
    }

    /**
     * Render the HTML
     * @return {JQuery}
     */
    render() {
        this.ui = $(`
          <a class="lazy-book-card">
            <div class="cover">
              <img>
            </div>
            <div class="info">
              <div class="title"></div>
              <div class="byline"></div>
              <div class="identifier"></div>
            </div>
          </a>
        `);

        // Reset state
        const state = this.state;
        this.state = {};
        this.updateState(state);

        return this.ui;
    }

    /**
     * Update the state and the UI
     * @param {LazyBookCardState} newState
     */
    updateState(newState) {
        const oldState = this.state;
        newState = Object.assign({}, oldState, newState);

        if (this.ui) {
            if (oldState.link !== newState.link) {
                this.ui.attr('href', newState.link);
            }

            if (oldState.coverSrc !== newState.coverSrc) {
                this.ui.find('.cover img').attr('src', newState.coverSrc);
            }

            const textFields = ['title', 'byline', 'identifier'];
            for (const field of textFields) {
                if (oldState[field] !== newState[field]) {
                    this.ui.find(`.${field}`).text(newState[field]);
                }
            }

            const classFields = ['loading', 'errored'];
            for (const field of classFields) {
                if (oldState[field] !== newState[field]) {
                    this.ui.toggleClass(field, newState[field]);
                }
            }
        }

        this.state = newState;
    }

    /**
     * @param {string} isbn
     * @return {LazyBookCard}
     */
    static fromISBN(isbn) {
        const cardEl = new LazyBookCard({
            title: isbn,
            loading: true,
            link: `/isbn/${isbn}`,
        });

        fetch(`${OL_BASE}/isbn/${isbn}.json`).then(r => r.json())
            .then(editionRecord => {
                cardEl.updateState({
                    title: editionRecord.title,
                    identifier: isbn,
                    link: editionRecord.key,
                });

                if (editionRecord.covers) {
                    const coverId = editionRecord.covers.find(x => x !== -1);
                    if (coverId) {
                        cardEl.updateState({
                            coverSrc: `https://covers.openlibrary.org/b/id/${coverId}-M.jpg`,
                        });
                    }
                }

                // Split up key, for example /book/00000 becomes 00000.
                const edition_key = editionRecord.key.split('/').pop();

                return fetch(`${OL_BASE}search.json?q=edition_key:${edition_key}&fields=key,author_name`).then(r => r.json())
            }).then(searchRecords => {
                cardEl.updateState({
                    loading: false,
                    byline: searchRecords.docs[0].author_name.join(', '),
                });
            })
            // eslint-disable-next-line no-unused-vars
            .catch(err => cardEl.updateState({loading: false, errored: true}));

        return cardEl;
    }
}

/**
 * @typedef {object} LazyBookCardState
 * @property {string} [coverSrc] url of the cover image
 * @property {string} [link] link when clicking on card
 * @property {string} [title]
 * @property {string} [byline]
 * @property {string} [identifier]
 * @property {boolean} [loading] whether in a loading state
 * @property {boolean} [errored]
 */
