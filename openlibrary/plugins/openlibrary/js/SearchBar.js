import { debounce } from './nonjquery_utils.js';
import * as SearchUtils from './SearchUtils';
import { PersistentValue } from './SearchUtils';

const FACET_TO_ENDPOINT = {
    title: 'books',
    author: 'authors',
    lists: 'lists',
    subject: 'subjects',
    all: 'all',
    advanced: 'advancedsearch',
    text: 'inside',
};
const DEFAULT_FACET = 'all';
const RENDER_INSTANT_SEARCH_RESULT = {
    books(work) {
        const author_name = work.author_name ? work.author_name[0] : '';
        return `
            <li>
                <a href="${work.key}">
                    <img src="//covers.openlibrary.org/b/id/${work.cover_i}-S.jpg"/>
                    <span class="book-desc">
                        <div class="book-title">${work.title}</div> by <span class="book-author">${author_name}</span>
                    </span>
                </a>
            </li>`;
    },
    authors(author) {
        // Todo: default author img to: https://dev.openlibrary.org/images/icons/avatar_author-lg.png
        return `
            <li>
                <a href="/authors/${author.key}">
                    <img src="http://covers.openlibrary.org/a/olid/${author.key}-S.jpg"/>
                    <span class="author-desc"><div class="author-name">${author.name}</div></span>
                </a>
            </li>`;
    }
}

/**
 * Manages the interactions associated with the search bar in the header
 */
export class SearchBar {
    /**
     * @param {Object} urlParams
     */
    constructor(urlParams) {
        /** UI Elements */
        this.$component = $('header#header-bar .search-component');
        this.$form = this.$component.find('form.search-bar-input');
        this.$input = this.$form.find('input[type="text"]');
        this.$results = this.$component.find('ul.search-results');
        this.$facetSelect = this.$component.find('.search-facet-selector select');

        /** State */
        /** Whether the search bar is currently collapsed */
        this.collapsed = false;
        /** Selected facet (persisted) */
        this.facet = new PersistentValue('facet', {
            default: DEFAULT_FACET,
            initValidation(val) { return val in FACET_TO_ENDPOINT; }
        });

        this.initFromUrlParams(urlParams);
        this.initCollapsibleMode();

        // searches should be cancelled if you click anywhere in the page
        $(document.body).on('click', this.clearResults.bind(this));
        // but clicking search input should not empty search results.
        this.$input.on('click', false);
        // Bind to changes in the search state
        SearchUtils.mode.change(this.handleSearchModeChange.bind(this));
        this.facet.change(this.handleFacetValueChange.bind(this));
        this.$facetSelect.change(() => this.handleFacetSelectChange(this.$facetSelect.val()));

        this.$form.on('submit', () => {
            const q = this.$input.val();
            if (this.facetEndpoint === 'books') {
                this.$input.val(SearchBar.marshalBookSearchQuery(q));
            }
            SearchUtils.addModeInputsToForm(this.$form, SearchUtils.mode.read());
        });

        this.initAutocompletionLogic();
    }

    get facetEndpoint() {
        return FACET_TO_ENDPOINT[this.facet.read()];
    }

    initFromUrlParams(urlParams) {
        if (urlParams.facet in FACET_TO_ENDPOINT) {
            this.facet.write(urlParams.facet);
        }

        if (urlParams.q) {
            let q = urlParams.q.replace(/\+/g, ' ');
            if (this.facet.read() === 'title' && q.indexOf('title:') != -1) {
                const parts = q.split('"');
                if (parts.length === 3) {
                    q = parts[1];
                }
            }
            this.$input.val(q);
        }
    }

    initAutocompletionLogic() {
        this.$input.on('keyup', debounce(event => {
            // ignore directional keys and enter for callback
            if (![13,37,38,39,40].includes(event.keyCode)) {
                this.renderInstantSearchResults($(event.target).val());
            }
        }, 500, false));

        this.$input.on('focus', debounce(event => {
            event.stopPropagation();
            this.renderInstantSearchResults($(event.target).val());
        }, 300, false));
    }

    initCollapsibleMode() {
        this.handleResize();
        $(window).resize(debounce(this.handleResize.bind(this)));
        $(document).on('submit','.in-collapsible-mode', event => {
            if (this.collapsed) {
                event.preventDefault();
                this.toggleCollapse();
                this.$input.focus();
            }
        });
    }

    handleResize() {
        if ($(window).width() < 568){
            this.collapse();
            this.$form.addClass('in-collapsible-mode');
            this.clearResults();
        } else {
            this.expand();
            this.$form.removeClass('in-collapsible-mode');
        }
    }

    clearResults() {
        this.$results.empty();
    }

    /**
     * Expands/hides the searchbar
     */
    toggleCollapse() {
        if (this.collapsed) {
            this.expand();
        } else {
            this.collapse();
        }
    }

    collapse() {
        $('header#header-bar .logo-component').removeClass('hidden');
        this.$component.removeClass('search-component-expand');
        this.collapsed = true;
    }

    expand() {
        $('header#header-bar .logo-component').addClass('hidden');
        this.$component.addClass('search-component-expand');
        this.collapsed = false;
    }

    /**
     * Compose search url for what?!? is the clickable? The autocomplete?!? WHAT?!?
     * @param {String} q query
     * @param {Boolean} [json]
     * @param {Number} [limit]
     */
    composeSearchUrl(q, json=true, limit=10) {
        const facet_value = this.facetEndpoint;
        let url = ((facet_value === 'books' || facet_value === 'all')? '/search' : `/search/${facet_value}`);
        if (json) {
            url += '.json';
        }
        url += `?q=${q}`;
        if (limit) {
            url += `&limit=${limit}`;
        }
        return `${url}&mode=${SearchUtils.mode.read()}`;
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
        const facet_value = this.facetEndpoint;
        // Not implemented; also, this call is _expensive_ and should not be done!
        if (facet_value === 'inside') return;
        if (q === '') {
            return;
        }
        if (facet_value === 'books') {
            q = SearchBar.marshalBookSearchQuery(q);
        }

        this.$results.css('opacity', 0.5);
        $.getJSON(this.composeSearchUrl(q), data => {
            const facet = facet_value === 'all' ? 'books' : facet_value;
            this.$results.css('opacity', 1);
            this.clearResults();
            for (let d in data.docs) {
                const html = RENDER_INSTANT_SEARCH_RESULT[facet](data.docs[d]);
                this.$results.append(html);
            }
        });
    }

    /**
     * Set the selected facet
     * @param {String} newFacet
     */
    handleFacetValueChange(newFacet) {
        // update the UI
        this.$facetSelect.val(newFacet);
        const text = this.$facetSelect.find('option:selected').text();
        $('header#header-bar .search-facet-value').html(text);

        // Get new results
        this.clearResults();
        if (this.$input.is(':focus')) {
            const q = this.$input.val();
            const url = this.composeSearchUrl(q);
            this.$form.attr('action', url);
            this.renderInstantSearchResults(q);
        }
    }

    handleFacetSelectChange(newFacet) {
        // We don't want to persist advanced becaues it behaves like a button
        if (newFacet == 'advanced') {
            event.preventDefault();
            window.location.assign('/advancedsearch');
        } else {
            this.facet.write(newFacet);
        }
    }

    handleSearchModeChange(newMode) {
        $('.instantsearch-mode').val(newMode);
        $(`input[name=mode][value=${newMode}]`).prop('checked', true);
        SearchUtils.addModeInputsToForm(this.$form, SearchUtils.mode.read());
    }
}
