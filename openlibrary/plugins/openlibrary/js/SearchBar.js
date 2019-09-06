import { debounce } from './nonjquery_utils.js';
import * as SearchUtils from './SearchUtils';
import { PersistentValue } from './SearchUtils';
import $ from 'jquery';

/** Mapping of search bar facets to search endpoints */
const FACET_TO_ENDPOINT = {
    title: '/search',
    author: '/search/authors',
    lists: '/search/lists',
    subject: '/search/subjects',
    all: '/search',
    text: '/search/inside',
};
const DEFAULT_FACET = 'all';
/** Functions that render autocomplete results */
const RENDER_AUTOCOMPLETE_RESULT = {
    ['/search'](work) {
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
    ['/search/authors'](author) {
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
     * @param {HTMLElement|JQuery}
     * @param {Object?} urlParams
     */
    constructor(component, urlParams={}) {
        /** UI Elements */
        this.$component = $(component);
        this.$form = this.$component.find('form.search-bar-input');
        this.$input = this.$form.find('input[type="text"]');
        this.$results = this.$component.find('ul.search-results');
        this.$facetSelect = this.$component.find('.search-facet-selector select');

        /** State */
        /** Whether the bar is in collapsible mode */
        this.inCollapsibleMode = false;
        /** Whether the search bar is currently collapsed */
        this.collapsed = false;
        /** Selected facet (persisted) */
        this.facet = new PersistentValue('facet', {
            default: DEFAULT_FACET,
            initValidation(val) { return val in FACET_TO_ENDPOINT; }
        });

        this.initFromUrlParams(urlParams);
        this.initCollapsibleMode();

        // Bind to changes in the search state
        SearchUtils.mode.sync(this.handleSearchModeChange.bind(this));
        this.facet.sync(this.handleFacetValueChange.bind(this));
        this.$facetSelect.change(this.handleFacetSelectChange.bind(this));
        this.$form.on('submit', this.submitForm.bind(this));

        this.initAutocompletionLogic();
    }

    /** @type {String} The endpoint of the active facet */
    get facetEndpoint() {
        return FACET_TO_ENDPOINT[this.facet.read()];
    }

    /**
     * Update internal state from url parameters
     * @param {Object} urlParams
     */
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

    submitForm() {
        if (this.facet.read() === 'title') {
            const q = this.$input.val();
            this.$input.val(SearchBar.marshalBookSearchQuery(q));
        }
        this.$form.attr('action', this.composeSearchUrl(this.$input.val()));
        SearchUtils.addModeInputsToForm(this.$form, SearchUtils.mode.read());
    }

    /** Initialize event handlers that allow the form to collapse for small screens */
    initCollapsibleMode() {
        this.toggleCollapsibleModeForSmallScreens($(window).width());
        $(window).resize(debounce(() => {
            this.toggleCollapsibleModeForSmallScreens($(window).width());
        }, 50));
        $(document).on('submit','.in-collapsible-mode', event => {
            if (this.collapsed) {
                event.preventDefault();
                this.toggleCollapse();
                this.$input.focus();
            }
        });
    }

    /**
     * Enables/disables CollapsibleMode depending on screen size
     * @param {Number} windowWidth
     */
    toggleCollapsibleModeForSmallScreens(windowWidth) {
        if (windowWidth < 568) {
            if (!this.inCollapsibleMode) {
                this.enableCollapisbleMode();
                this.collapse();
            }
            this.clearAutocompletionResults();
        } else {
            if (this.inCollapsibleMode) {
                this.disableCollapsibleMode();
            }
        }
    }

    /** Collapses or expands the searchbar */
    toggleCollapse() {
        if (this.collapsed) {
            this.expand();
        } else {
            this.collapse();
        }
    }

    collapse() {
        $('header#header-bar .logo-component').removeClass('hidden');
        this.$component.removeClass('expanded');
        this.collapsed = true;
    }

    expand() {
        $('header#header-bar .logo-component').addClass('hidden');
        this.$component.addClass('expanded');
        this.collapsed = false;
    }

    enableCollapisbleMode() {
        this.$form.addClass('in-collapsible-mode');
        this.inCollapsibleMode = true;
    }

    disableCollapsibleMode() {
        this.collapse();
        this.$form.removeClass('in-collapsible-mode');
        this.inCollapsibleMode = false;
    }

    /**
     * Converts an already processed query into a search url
     * @param {String} q query that's ready to get passed to the search endpoint
     * @param {Boolean} [json] whether to hit the JSON endpoint
     * @param {Number} [limit] how many items to get
     */
    composeSearchUrl(q, json, limit) {
        let url = this.facetEndpoint;
        if (json) {
            url += '.json';
        }
        url += `?q=${q}`;
        if (limit) {
            url += `&limit=${limit}`;
        }
        url += `&mode=${SearchUtils.mode.read()}`;
        return url;
    }

    /**
     * Prepare an unprocessed query for book searching
     * @param {String} q
     * @return {String}
     */
    static marshalBookSearchQuery(q) {
        if (q && q.indexOf(':') == -1 && q.indexOf('"') == -1) {
            q = `title: "${q}"`;
        }
        return q;
    }

    /** Setup event listeners for autocompletion */
    initAutocompletionLogic() {
        // searches should be cancelled if you click anywhere in the page
        $(document.body).on('click', this.clearAutocompletionResults.bind(this));
        // but clicking search input should not empty search results.
        this.$input.on('click', false);

        this.$input.on('keyup', debounce(event => {
            // ignore directional keys and enter for callback
            if (![13,37,38,39,40].includes(event.keyCode)) {
                this.renderAutocompletionResults();
            }
        }, 500, false));

        this.$input.on('focus', debounce(event => {
            event.stopPropagation();
            this.renderAutocompletionResults();
        }, 300, false));
    }

    /** Cleans up and performs the query, then update the autocomplete results */
    renderAutocompletionResults() {
        let q = this.$input.val();
        if (q === '' || !(this.facetEndpoint in RENDER_AUTOCOMPLETE_RESULT)) {
            return;
        }
        if (this.facet.read() === 'title') {
            q = SearchBar.marshalBookSearchQuery(q);
        }

        this.$results.css('opacity', 0.5);
        $.getJSON(this.composeSearchUrl(q, true, 10), data => {
            const renderer = RENDER_AUTOCOMPLETE_RESULT[this.facetEndpoint];
            this.$results.css('opacity', 1);
            this.clearAutocompletionResults();
            for (let d in data.docs) {
                this.$results.append(renderer(data.docs[d]));
            }
        });
    }

    clearAutocompletionResults() {
        this.$results.empty();
    }

    /**
     * Updates the UI to match after the facet is changed
     * @param {String} newFacet
     */
    handleFacetValueChange(newFacet) {
        // update the UI
        this.$facetSelect.val(newFacet);
        const text = this.$facetSelect.find('option:selected').text();
        $('header#header-bar .search-facet-value').html(text);

        // Get new results
        if (this.$input.is(':focus')) {
            this.renderAutocompletionResults();
        }
    }

    /**
     * Handles changes to the facet from the UI
     * @param {JQuery.Event} event
     */
    handleFacetSelectChange(event) {
        const newFacet = this.$facetSelect.val();
        // We don't want to persist advanced becaues it behaves like a button
        if (newFacet == 'advanced') {
            event.preventDefault();
            window.location.assign('/advancedsearch');
        } else {
            this.facet.write(newFacet);
        }
    }

    /**
     * Makes changes to the UI after a change occurs to the mode
     * (Parts of this might be dead code)
     * @param {String} newMode
     */
    handleSearchModeChange(newMode) {
        $('.instantsearch-mode').val(newMode);
        $(`input[name=mode][value=${newMode}]`).prop('checked', true);
        SearchUtils.addModeInputsToForm(this.$form, newMode);
    }
}
