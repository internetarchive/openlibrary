import { debounce } from './nonjquery_utils.js';
import * as SearchUtils from './SearchUtils';

const RENDER_INSTANT_SEARCH_RESULT = {
    books(work) {
        const author_name = work.author_name ? work.author_name[0] : '';
        $('header#header-bar .search-component ul.search-results').append(
            `<li class="instant-result">
                <a href="${work.key}">
                    <img src="//covers.openlibrary.org/b/id/${work.cover_i}-S.jpg"/>
                    <span class="book-desc">
                        <div class="book-title">${work.title}</div> by <span class="book-author">${author_name}</span>
                    </span>
                </a>
            </li>`
        );
    },
    authors(author) {
        // Todo: default author img to: https://dev.openlibrary.org/images/icons/avatar_author-lg.png
        $('header#header-bar .search-component ul.search-results').append(
            `<li>
                <a href="/authors/${author.key}">
                    <img src="http://covers.openlibrary.org/a/olid/${author.key}-S.jpg"/>
                    <span class="author-desc"><div class="author-name">${author.name}</div></span>
                </a>
            </li>`
        );
    }
};

/**
 * Manages the interactions associated with the search bar in the header
 */
export class SearchBar {
    /**
     * @param {SearchState} searchState
     * @param {Object} urlParams
     */
    constructor(searchState, urlParams) {
        this.searchState = searchState;
        /** The search input element */
        this.$searchInput = $('header#header-bar .search-component .search-bar-input input[type="text"]');
        /** Autocomplete search results */
        this.$searchResults = $('header#header-bar .search-component ul.search-results');
        /** stores the state of the search result for resizing window */
        this.instantSearchResultState = false;
        /** Whether the search bar is expanded */
        this.searchExpansionActivated = false;
        /** ?? Not sure */
        this.enteredSearchMinimized = false;

        if (urlParams.q) {
            let q = urlParams.q.replace(/\+/g, ' ');
            if (searchState.facet === 'title' && q.indexOf('title:') != -1) {
                const parts = q.split('"');
                if (parts.length === 3) {
                    q = parts[1];
                }
            }
            $('.search-bar-input [type=text]').val(q);
        }

        if ($(window).width() < 568) {
            if (!this.enteredSearchMinimized) {
                $('.search-bar-input').addClass('trigger')
            }
            this.enteredSearchMinimized = true;
        }

        // searches should be cancelled if you click anywhere in the page
        $(document.body).on('click', this.cancelSearch.bind(this));
        // but clicking search input should not empty search results.
        $(window).resize(this.handleResize.bind(this));
        this.$searchInput.on('click', false);
        // Bind to changes in the search state
        this.searchState.sync('facet', this.handleFacetChange.bind(this));
        this.searchState.sync('searchMode', this.handleSearchModeChange.bind(this));
        $('header#header-bar .search-facet-selector select').change(event => {
            const facet = $('header .search-facet-selector select').val();
            // Ignore advanced, because we don't want it to stick (since it acts like a button)
            if (facet == 'advanced') {
                event.preventDefault();
                window.location.assign('/advancedsearch');
            } else {
                this.searchState.facet = facet;
            }
        });

        $('form.search-bar-input').on('submit', () => {
            const q = this.$searchInput.val();
            if (this.searchState.facetValue === 'books') {
                $('header#header-bar .search-component .search-bar-input input[type=text]').val(SearchBar.marshalBookSearchQuery(q));
            }
            // TODO can we remove this?
            SearchUtils.updateSearchMode('.search-bar-input', this.searchState.searchMode);
        });

        $('li.instant-result a').on('click', event => {
            $('html, body').css('cursor', 'wait');
            $(event.target).css('cursor', 'wait');
        });

        $('header#header-bar .search-component .search-results li a').on('click', debounce(function() {
            $(document.body).css({cursor: 'wait'});
        }, 300, false));

        this.$searchInput.on('keyup', debounce(event => {
            this.instantSearchResultState = true;
            // ignore directional keys and enter for callback
            if (![13,37,38,39,40].includes(event.keyCode)) {
                this.renderInstantSearchResults($(event.target).val());
            }
        }, 500, false));

        this.$searchInput.on('focus', debounce(event => {
            this.instantSearchResultState = true;
            event.stopPropagation();
            this.renderInstantSearchResults($(event.target).val());
        }, 300, false));

        $(document).on('submit','.trigger', event => {
            event.preventDefault();
            this.toggle();
            $('.search-bar-input [type=text]').focus();
        });
    }

    handleResize() {
        if ($(window).width() < 568){
            if (!this.enteredSearchMinimized) {
                $('.search-bar-input').addClass('trigger')
                $('header#header-bar .search-component ul.search-results').empty()
            }
            this.enteredSearchMinimized = true;
        } else {
            if (this.enteredSearchMinimized) {
                $('.search-bar-input').removeClass('trigger');
                const search_query = this.$searchInput.val()
                if (search_query && this.instantSearchResultState) {
                    this.renderInstantSearchResults(search_query);
                }
            }
            this.enteredSearchMinimized = false;
            this.searchExpansionActivated = false;
            $('header#header-bar .logo-component').removeClass('hidden');
            $('header#header-bar .search-component').removeClass('search-component-expand');
        }
    }

    cancelSearch() {
        this.instantSearchResultState = false;
        this.$searchResults.empty();
    }

    /**
     * Expands/hides the searchbar
     */
    toggle() {
        this.searchExpansionActivated = !this.searchExpansionActivated;
        if (this.searchExpansionActivated) {
            $('header#header-bar .logo-component').addClass('hidden');
            $('header#header-bar .search-component').addClass('search-component-expand');
            $('.search-bar-input').removeClass('trigger');
        } else {
            $('header#header-bar .logo-component').removeClass('hidden');
            $('header#header-bar .search-component').removeClass('search-component-expand');
            $('.search-bar-input').addClass('trigger');
        }
    }

    /**
     * Compose search url for what?!? is the clickable? The autocomplete?!? WHAT?!?
     * @param {String} q query
     * @param {Boolean} [json]
     * @param {Number} [limit]
     */
    composeSearchUrl(q, json, limit) {
        const facet_value = this.searchState.facetValue;
        let url = ((facet_value === 'books' || facet_value === 'all')? '/search' : `/search/${facet_value}`);
        if (json) {
            url += '.json';
        }
        url += `?q=${q}`;
        if (limit) {
            url += `&limit=${limit}`;
        }
        return `${url}&mode=${this.searchState.searchMode}`;
    }

    /**
     * Marshal into what? From what?
     * @param {String} q
     */
    static marshalBookSearchQuery(q) {
        if (q && q.indexOf(':') == -1 && q.indexOf('"') == -1) {
            q = `title: "${q}"`;
        }
        return q;
    }

    /**
     * Perform the query and update autocomplete results
     * @param {String} q
     */
    renderInstantSearchResults(q) {
        const facet_value = this.searchState.facetValue;
        // Not implemented; also, this call is _expensive_ and should not be done!
        if (facet_value === 'inside') return;
        if (q === '') {
            return;
        }
        if (facet_value === 'books') {
            q = SearchBar.marshalBookSearchQuery(q);
        }

        this.$searchResults.css('opacity', 0.5);
        $.getJSON(this.composeSearchUrl(q, true, 10), data => {
            const facet = facet_value === 'all' ? 'books' : facet_value;
            this.$searchResults.css('opacity', 1).empty();
            for (let d in data.docs) {
                RENDER_INSTANT_SEARCH_RESULT[facet](data.docs[d]);
            }
        });
    }

    /**
     * Set the selected facet
     * @param {String} facet
     */
    handleFacetChange(newFacet) {
        $('header#header-bar .search-facet-selector select').val(newFacet)
        const text = $('header#header-bar .search-facet-selector select').find('option:selected').text()
        $('header#header-bar .search-facet-value').html(text);
        $('header#header-bar .search-component ul.search-results').empty()
        const q = this.$searchInput.val();
        const url = this.composeSearchUrl(q);
        $('.search-bar-input').attr('action', url);
        this.renderInstantSearchResults(q);
    }

    handleSearchModeChange(newMode) {
        $('.instantsearch-mode').val(newMode);
        $(`input[name=mode][value=${newMode}]`).prop('checked', true);
        SearchUtils.updateSearchMode('.search-bar-input', this.searchState.searchMode);
    }
}
