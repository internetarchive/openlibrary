import { initSearchPageAuthorSuggestion } from '../../../openlibrary/plugins/openlibrary/js/SearchPageAuthorSuggestion';

function renderSearchResults(query) {
    document.body.innerHTML = `
        <div id="searchResults" data-query="${query}" data-author-label="Author">
            <ul class="list-books">
                <li class="searchResultItem sri--w-main">
                    <span class="bookauthor">
                        <a href="/authors/OL1A/Octavia_E_Butler">Octavia E. Butler</a>
                    </span>
                </li>
                <li class="searchResultItem sri--w-main">
                    <span class="bookauthor">
                        <a href="/authors/OL2A/Someone_Else">Someone Else</a>
                    </span>
                </li>
            </ul>
        </div>
    `;
    return document.getElementById('searchResults');
}

describe('initSearchPageAuthorSuggestion', () => {
    afterEach(() => {
        document.body.innerHTML = '';
    });

    test('adds an author row above book results when the query names a top-result author', () => {
        const container = renderSearchResults('octavia butler');

        initSearchPageAuthorSuggestion(container);

        const first = container.querySelector('.list-books').firstElementChild;
        expect(first.classList.contains('search-page-author-suggestion')).toBe(true);
        expect(first.querySelector('a').getAttribute('href')).toBe('/authors/OL1A');
        expect(first.textContent).toContain('Octavia E. Butler');
        expect(first.textContent).toContain('Author');
    });

    test('does not add a row for a title query', () => {
        const container = renderSearchResults('parable');

        initSearchPageAuthorSuggestion(container);

        expect(container.querySelector('.search-page-author-suggestion')).toBeNull();
    });
});
