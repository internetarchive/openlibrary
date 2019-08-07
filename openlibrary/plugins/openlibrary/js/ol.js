import { debounce } from './nonjquery_utils.js';
import * as Browser from './Browser';
import { updateWorkAvailability } from './availability';

function isScrolledIntoView(elem) {
    var docViewTop = $(window).scrollTop();
    var docViewBottom = docViewTop + $(window).height();
    var elemTop, elemBottom;
    if ($(elem).offset()) {
        elemTop = $(elem).offset().top;
        elemBottom = elemTop + $(elem).height();
        return ((docViewTop < elemTop) && (docViewBottom > elemBottom));
    }
    return false;
}

const SEARCH_MODES = ['everything', 'ebooks', 'printdisabled'];
const SEARCH_MODE_DEFAULT = 'ebooks';
const SEARCH_FACETS = {
    title: 'books',
    author: 'authors',
    lists: 'lists',
    subject: 'subjects',
    all: 'all',
    advanced: 'advancedsearch',
    text: 'inside',
};
const DEFAULT_SEARCH_FACET = 'all';
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
}

/** Manages search state variables */
class SearchState {
    constructor(urlParams) {
        this._listeners = {};

        if (!(this.facet in SEARCH_FACETS)) {
            this.facet = DEFAULT_SEARCH_FACET;
        }
        this.facet = urlParams.facet || this.facet || DEFAULT_SEARCH_FACET;
        this.searchMode = urlParams.mode;
    }

    get facet() {
        return localStorage.getItem('facet');
    }
    set facet(newFacet) {
        const oldValue = this.facet;
        localStorage.setItem('facet', newFacet);
        this._trigger('facet', newFacet, oldValue);
    }

    get searchMode() {
        return localStorage.getItem('mode');
    }
    set searchMode(mode) {
        const oldValue = this.searchMode;
        const searchMode = (mode && mode.toLowerCase()) || oldValue;
        const isValidMode = SEARCH_MODES.indexOf(searchMode) != -1;
        const newMode = isValidMode ? searchMode : SEARCH_MODE_DEFAULT;
        localStorage.setItem('mode', newMode);
        this._trigger('searchMode', newMode, oldValue);
    }

    sync(key, handler, user_opts={}) {
        const DEFAULT_OPTS = {
            fireAtStart: true,
            onlyFireOnChange: true
        };

        if (!(key in this))
            throw Error('Invalid key', key);

        const opts = Object.assign({}, DEFAULT_OPTS, user_opts);
        this._listeners[key] = this._listeners[key] || [];
        this._listeners[key].push({ handle: handler, opts });
        if (opts.fireAtStart) handler(this[key]);
    }

    /**
     * @param {String} key
     * @param {any} newValue
     * @param {any} oldValue
     */
    _trigger(key, newValue, oldValue) {
        if (!(key in this._listeners)) {
            return;
        }

        for (let listener of this._listeners[key]) {
            if (listener.opts.onlyFireOnChange) {
                if (newValue != oldValue) {
                    listener.handle(newValue)
                }
            } else {
                listener.handle(newValue);
            }
        }
    }
}

class SearchBar {
    /**
     *
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
            const facet_value = SEARCH_FACETS[this.searchState.facet];
            if (facet_value === 'books') {
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
    static composeSearchUrl(q, json, limit) {
        const facet_value = SEARCH_FACETS[localStorage.getItem('facet')];
        let url = ((facet_value === 'books' || facet_value === 'all')? '/search' : `/search/${facet_value}`);
        if (json) {
            url += '.json';
        }
        url += `?q=${q}`;
        if (limit) {
            url += `&limit=${limit}`;
        }
        return `${url}&mode=${localStorage.getItem('mode')}`;
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
        const facet_value = SEARCH_FACETS[localStorage.getItem('facet')];
        // Not implemented; also, this call is _expensive_ and should not be done!
        if (facet_value === 'inside') return;
        if (q === '') {
            return;
        }
        if (facet_value === 'books') {
            q = SearchBar.marshalBookSearchQuery(q);
        }

        this.$searchResults.css('opacity', 0.5);
        $.getJSON(SearchBar.composeSearchUrl(q, true, 10), data => {
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
        const url = SearchBar.composeSearchUrl(q);
        $('.search-bar-input').attr('action', url);
        this.renderInstantSearchResults(q);
    }

    handleSearchModeChange(newMode) {
        $('.instantsearch-mode').val(newMode);
        $(`input[name=mode][value=${newMode}]`).prop('checked', true);
        SearchUtils.updateSearchMode('.search-bar-input', this.searchState.searchMode);
    }
}

class SearchPage {
    /**
     * @param {SearchState} searchState
     */
    constructor(searchState) {
        this.searchState = searchState;
        this.searchState.sync('searchMode', () => SearchUtils.updateSearchMode('.olform', this.searchState.searchMode));

        updateWorkAvailability();

        $('.search-mode').change(event => {
            $('html,body').css('cursor', 'wait');
            this.searchState.searchMode = $(event.target).val();
            if ($('.olform').length) {
                $('.olform').submit();
            } else {
                location.reload();
            }
        });

        $('.olform').submit(() => {
            if (this.searchState.searchMode !== 'everything') {
                $('.olform').append('<input type="hidden" name="has_fulltext" value="true"/>');
            }
            if (this.searchState.searchMode === 'printdisabled') {
                $('.olform').append('<input type="hidden" name="subject_facet" value="Protected DAISY"/>');
            }
        });
    }
}

class SearchUtils {
    /**
     * Oh, between SEARCH_MODES
     * @param {HTMLFormElement|String|JQuery} form
     * @param {String} searchState
     */
    static updateSearchMode(form, searchMode) {
        if (!$(form).length) {
            return;
        }

        $('input[value=\'Protected DAISY\']').remove();
        $('input[name=\'has_fulltext\']').remove();

        let url = $(form).attr('action');
        if (url) {
            url = Browser.removeURLParameter(url, 'm');
            url = Browser.removeURLParameter(url, 'has_fulltext');
            url = Browser.removeURLParameter(url, 'subject_facet');
        } else {
            // Don't set mode if no action.. it's too risky!
            // see https://github.com/internetarchive/openlibrary/issues/1569
            return;
        }

        if (searchMode !== 'everything') {
            $(form).append('<input type="hidden" name="has_fulltext" value="true"/>');
            url = `${url + (url.indexOf('?') > -1 ? '&' : '?')}has_fulltext=true`;
        }
        if (searchMode === 'printdisabled') {
            $(form).append('<input type="hidden" name="subject_facet" value="Protected DAISY"/>');
        }

        $(form).attr('action', url);
    }
}

export default function init() {
    const urlParams = Browser.getJsonFromUrl(location.search);
    const searchState = new SearchState(urlParams);
    new SearchBar(searchState, urlParams);
    new SearchPage(searchState);

    $(window).scroll(function(){
        var scroller = $('#formScroll');
        if (isScrolledIntoView(scroller)) {
            $('#scrollBtm').show();
        } else {
            $('#scrollBtm').hide();
        }
    });

    initReadingListFeature();
    initBorrowAndReadLinks();
    initPreviewButton();
}

export function initReadingListFeature() {
    /**
     * close an open dropdown in a given container
     * @param {jQuery.Object} $container
     */
    function closeDropdown($container) {
        $container.find('.dropdown').slideUp(25);
        $container.find('.arrow').removeClass('up');
    }
    // Events are registered on document as HTML is subject to change due to JS inside
    // openlibrary/templates/lists/widget.html
    $(document).on('click', '.dropclick', debounce(function(){
        $(this).next('.dropdown').slideToggle(25);
        $(this).parent().next('.dropdown').slideToggle(25);
        $(this).parent().find('.arrow').toggleClass('up');
    }, 300, false));

    $(document).on('click', 'a.add-to-list', debounce(function(){
        $(this).closest('.dropdown').slideToggle(25);
        $(this).closest('.arrow').toggleClass('up');
    }, 300, false));

    $(document).on('click', '.work-menu li', debounce(function() {
        $('.work-menu li').removeClass('selected');
        $(this).addClass('selected');
    }, 300, false));

    // Close any open dropdown list if the user clicks outside...
    $(document).on('click', function() {
        closeDropdown($('.widget-add'));
    });

    // ... but don't let that happen if user is clicking inside dropdown
    $(document).on('click', '.widget-add', function(e) {
        e.stopPropagation();
    });

    /* eslint-disable no-unused-vars */
    // success function receives data on successful request
    $(document).on('change', '.reading-log-lite select', function(e) {
        const $self = $(this);

        // On /account/books/want-to-read avoid a page reload by sending the
        // new shelf to the server and removing the associated item.
        // Note that any change to this select will result in the book changing
        // shelf.
        $.ajax({
            url: $self.closest('form').attr('action'),
            type: 'POST',
            data: {
                bookshelf_id: $self.val()
            },
            datatype: 'json',
            success: function() {
                $self.closest('.searchResultItem').remove();
            }
        });
        e.preventDefault();
    });
}

export function initBorrowAndReadLinks() {
    // LOADING ONCLICK FUNCTIONS FOR BORROW AND READ LINKS
    /* eslint-disable no-unused-vars */
    // used in openlibrary/macros/AvailabilityButton.html and openlibrary/macros/LoanStatus.html
    $(document).ready(function(){
        $('#borrow_ebook,#read_ebook').on('click', function(){
            $(this).removeClass('cta-btn cta-btn--available').addClass('cta-btn cta-btn--available--load');
        });
    });
    $(document).ready(function(){
        $('#waitlist_ebook').on('click', function(){
            $(this).removeClass('cta-btn cta-btn--unavailable').addClass('cta-btn cta-btn--unavailable--load');
        });
    });

    /* eslint-enable no-unused-vars */
}

export function initPreviewButton() {
    // Colorbox modal + iframe for Book Preview Button
    const $buttons = $('.cta-btn--preview');
    $buttons.each((i, button) => {
        const $button = $(button);
        $button.colorbox({
            width: '100%',
            maxWidth: '640px',
            inline: true,
            opacity: '0.5',
            href: '#bookPreview',
            onOpen() {
                const $iframe = $('#bookPreview iframe');
                $iframe.prop('src', $button.data('iframe-src'));

                const $link = $('#bookPreview .learn-more a');
                $link[0].href = $button.data('iframe-link');
            },
            onCleanup() {
                $('#bookPreview iframe').prop('src', '');
            },
        });
    });
}
