import { debounce } from './nonjquery_utils.js';

export var Browser = {
    getJsonFromUrl: function () {
        var query = location.search.substr(1);
        var result = {};
        query.split('&').forEach(function(part) {
            var item = part.split('=');
            result[item[0]] = decodeURIComponent(item[1]);
        });
        return result;
    },

    change_url: function(query) {
        var getUrl = window.location;
        var baseUrl = `${getUrl.protocol  }//${  getUrl.host
        }/${  getUrl.pathname.split('/')[1]}`;
        window.history.pushState({
            'html': document.html,
            'pageTitle': `${document.title  } ${  query}`,
        }, '', `${baseUrl  }?id=${  query}`);
    },

    removeURLParameter: function(url, parameter) {
        var urlparts = url.split('?');
        var prefix = urlparts[0];
        var query, paramPrefix, params, i;
        if (urlparts.length >= 2) {
            query = urlparts[1];
            paramPrefix = `${encodeURIComponent(parameter)  }=`;
            params = query.split(/[&;]/g);

            //reverse iteration as may be destructive
            for (i = params.length; i-- > 0;) {
                //idiom for string.startsWith
                if (params[i].lastIndexOf(paramPrefix, 0) !== -1) {
                    params.splice(i, 1);
                }
            }

            url = prefix + (params.length > 0 ? `?${  params.join('&')}` : '');
            return url;
        } else {
            return url;
        }
    }
}

export function isScrolledIntoView(elem) {
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

// BOOK COVERS
// used in templates/work_search.html
export function bookCovers(){
    $('img.cover').error(function(){
        $(this).closest('.SRPCover').hide();
        $(this).closest('.coverMagic').find('.SRPCoverBlank').show();
    });
}

// CLOSE POP-UP FROM IFRAME
// used in templates/covers/saved.html
export function closePop(){
    $('#popClose').click(function(){
        parent.$.fn.colorbox.close();
    });
}

export default function init(){
    var $searchResults = $('header#header-bar .search-component ul.search-results');
    var $searchInput = $('header#header-bar .search-component .search-bar-input input[type="text"]');
    var cover_url = function(id) {
        return `//covers.openlibrary.org/b/id/${  id  }-S.jpg`
    };
    // stores the state of the search result for resizing window
    var instantSearchResultState = false;
    var searchModes, searchModeDefault, defaultFacet, searchFacets, composeSearchUrl, marshalBookSearchQuery, renderInstantSearchResults, setFacet, setMode, setSearchMode, options, q, parts, enteredSearchMinimized, searchExpansionActivated, toggleSearchbar, renderInstantSearchResult, val, facet_value;

    // searches should be cancelled if you click anywhere in the page
    $('body').on('click', function () {
        instantSearchResultState = false;
        $searchResults.empty();
    });
    // but clicking search input should not empty search results.
    $searchInput.on('click', false);

    $(window).scroll(function(){
        var scroller = $('#formScroll');
        if(isScrolledIntoView(scroller)){$('#scrollBtm').show();}else{$('#scrollBtm').hide();}
    });

    // Search mode
    searchModes = ['everything', 'ebooks', 'printdisabled'];
    searchModeDefault = 'ebooks';

    // Maps search facet label with value
    defaultFacet = 'all';
    searchFacets = {
        'title': 'books',
        'author': 'authors',
        'lists': 'lists',
        'subject': 'subjects',
        'all': 'all',
        'advanced': 'advancedsearch',
        'text': 'inside'
    };

    composeSearchUrl = function(q, json, limit) {
        var facet_value = searchFacets[localStorage.getItem('facet')];
        var url = ((facet_value === 'books' || facet_value === 'all')? '/search' : `/search/${  facet_value}`);
        if (json) {
            url += '.json';
        }
        url += `?q=${  q}`;
        if (limit) {
            url += `&limit=${  limit}`;
        }
        return `${url  }&mode=${  localStorage.getItem('mode')}`;
    }

    marshalBookSearchQuery = function(q) {
        if (q && q.indexOf(':') == -1 && q.indexOf('"') == -1) {
            q = `title: "${  q  }"`;
        }
        return q;
    }

    renderInstantSearchResults = function(q) {
        var facet_value = searchFacets[localStorage.getItem('facet')];
        var url, facet;
        if (q === '') {
            return;
        }
        if (facet_value === 'books') {
            q = marshalBookSearchQuery(q);
        }

        url = composeSearchUrl(q, true, 10);

        facet = facet_value === 'all'? 'books' : facet_value;
        $searchResults.css('opacity', 0.5);
        $.getJSON(url, function(data) {
            var d;
            $searchResults.css('opacity', 1).empty();
            for (d in data.docs) {
                renderInstantSearchResult[facet](data.docs[d]);
            }
        });
    }

    setFacet = function(facet) {
        var facet_key = facet.toLowerCase();
        var text, url;

        if (facet_key === 'advanced') {
            localStorage.setItem('facet', '');
            window.location.assign('/advancedsearch')
            return;
        }

        localStorage.setItem('facet', facet_key);
        $('header#header-bar .search-facet-selector select').val(facet_key)
        text = $('header#header-bar .search-facet-selector select').find('option:selected').text()
        $('header#header-bar .search-facet-value').html(text);
        $('header#header-bar .search-component ul.search-results').empty()
        q = $searchInput.val();
        url = composeSearchUrl(q)
        $('.search-bar-input').attr('action', url);
        renderInstantSearchResults(q);
    }

    setMode = function(form) {
        var url;
        if (!$(form).length) {
            return;
        }

        $('input[value=\'Protected DAISY\']').remove();
        $('input[name=\'has_fulltext\']').remove();

        url = $(form).attr('action');
        if (url) {
            url = Browser.removeURLParameter(url, 'm');
            url = Browser.removeURLParameter(url, 'has_fulltext');
            url = Browser.removeURLParameter(url, 'subject_facet');
        } else {
            // Don't set mode if no action.. it's too risky!
            // see https://github.com/internetarchive/openlibrary/issues/1569
            return;
        }

        if (localStorage.getItem('mode') !== 'everything') {
            $(form).append('<input type="hidden" name="m" value="edit"/>');
            url = `${url + (url.indexOf('?') > -1 ? '&' : '?')   }m=edit`;
            $(form).append('<input type="hidden" name="has_fulltext" value="true"/>');
            url = `${url + (url.indexOf('?') > -1 ? '&' : '?')   }has_fulltext=true`;
        } if (localStorage.getItem('mode') === 'printdisabled') {
            $(form).append('<input type="hidden" name="subject_facet" value="Protected DAISY"/>');
            url = `${url + (url.indexOf('?') > -1 ? '&' : '?')   }subject_facet=Protected DAISY`;
        }
        $(form).attr('action', url);
    }

    setSearchMode = function(mode) {
        var searchMode = mode || localStorage.getItem('mode');
        var isValidMode = searchModes.indexOf(searchMode) != -1;
        localStorage.setItem('mode', isValidMode?
            searchMode : searchModeDefault);
        $('.instantsearch-mode').val(localStorage.getItem('mode'));
        $(`input[name=mode][value=${  localStorage.getItem('mode')  }]`)
            .attr('checked', 'true');
        setMode('.olform');
        setMode('.search-bar-input');
    }

    options = Browser.getJsonFromUrl();

    if (!searchFacets[localStorage.getItem('facet')]) {
        localStorage.setItem('facet', defaultFacet)
    }
    setFacet(options.facet || localStorage.getItem('facet') || defaultFacet);
    setSearchMode(options.mode);

    if (options.q) {
        q = options.q.replace(/\+/g, ' ')
        if (localStorage.getItem('facet') === 'title' && q.indexOf('title:') != -1) {
            parts = q.split('"');
            if (parts.length === 3) {
                q = parts[1];
            }
        }
        $('.search-bar-input [type=text]').val(q);
    }

    // updateWorkAvailability is defined in openlibrary\openlibrary\plugins\openlibrary\js\availability.js
    // eslint-disable-next-line no-undef
    updateWorkAvailability();

    $(document).on('submit','.trigger', function(e) {
        e.preventDefault(e);
        toggleSearchbar();
        $('.search-bar-input [type=text]').focus();
    });

    enteredSearchMinimized = false;
    searchExpansionActivated = false;
    if ($(window).width() < 568) {
        if (!enteredSearchMinimized) {
            $('.search-bar-input').addClass('trigger')
        }
        enteredSearchMinimized = true;
    }
    $(window).resize(function(){
        var search_query;
        if($(this).width() < 568){
            if (!enteredSearchMinimized) {
                $('.search-bar-input').addClass('trigger')
                $('header#header-bar .search-component ul.search-results').empty()
            }
            enteredSearchMinimized = true;
        } else {
            if (enteredSearchMinimized) {
                $('.search-bar-input').removeClass('trigger');
                search_query = $searchInput.val()
                if (search_query && instantSearchResultState) {
                    renderInstantSearchResults(search_query);
                }
            }
            enteredSearchMinimized = false;
            searchExpansionActivated = false;
            $('header#header-bar .logo-component').removeClass('hidden');
            $('header#header-bar .search-component').removeClass('search-component-expand');
        }
    });

    toggleSearchbar = function() {
        searchExpansionActivated = !searchExpansionActivated;
        if (searchExpansionActivated) {
            $('header#header-bar .logo-component').addClass('hidden');
            $('header#header-bar .search-component').addClass('search-component-expand');
            $('.search-bar-input').removeClass('trigger')
        } else {
            $('header#header-bar .logo-component').removeClass('hidden');
            $('header#header-bar .search-component').removeClass('search-component-expand');
            $('.search-bar-input').addClass('trigger')
        }
    }

    $('header#header-bar .search-facet-selector select').change(function(e) {
        var facet = $('header .search-facet-selector select').val();
        if (facet.toLowerCase() === 'advanced') {
            e.preventDefault(e);
        }
        setFacet(facet);
    })

    renderInstantSearchResult = {
        books: function(work) {
            var author_name = work.author_name ? work.author_name[0] : '';
            $('header#header-bar .search-component ul.search-results').append(
                `<li class="instant-result"><a href="${  work.key  }"><img src="${  cover_url(work.cover_i)
                }"/><span class="book-desc"><div class="book-title">${
                    work.title  }</div>by <span class="book-author">${
                    author_name  }</span></span></a></li>`
            );
        },
        authors: function(author) {
            // Todo: default author img to: https://dev.openlibrary.org/images/icons/avatar_author-lg.png
            $('header#header-bar .search-component ul.search-results').append(
                `<li><a href="/authors/${  author.key  }"><img src="` + `http://covers.openlibrary.org/a/olid/${  author.key  }-S.jpg` + `"/><span class="author-desc"><div class="author-name">${
                    author.name  }</div></span></a></li>`
            );
        }
    }

    // e is a event object
    $('form.search-bar-input').on('submit', function() {
        q = $searchInput.val();
        facet_value = searchFacets[localStorage.getItem('facet')];
        if (facet_value === 'books') {
            $('header#header-bar .search-component .search-bar-input input[type=text]').val(marshalBookSearchQuery(q));
        }
        setMode('.search-bar-input');
    });


    $('.search-mode').change(function() {
        $('html,body').css('cursor', 'wait');
        setSearchMode($(this).val());
        if ($('.olform').length) {
            $('.olform').submit();
        } else {
            location.reload();
        }
    });

    $('.olform').submit(function() {
        if (localStorage.getItem('mode') !== 'everything') {
            $('.olform').append('<input type="hidden" name="has_fulltext" value="true"/>');
        } if (localStorage.getItem('mode') === 'printdisabled') {
            $('.olform').append('<input type="hidden" name="subject_facet" value="Protected DAISY"/>');
        }

    });

    $('li.instant-result a').on('click', function() {
        $('html,body').css('cursor', 'wait');
        $(this).css('cursor', 'wait');
    });

    // e is a event object
    $('header#header-bar .search-component .search-results li a').on('click', debounce(function() {
        $(document.body).css({'cursor' : 'wait'});
    }, 300, false));

    $searchInput.on('keyup', debounce(function(e) {
        instantSearchResultState = true;
        // ignore directional keys and enter for callback
        if (![13,37,38,39,40].includes(e.keyCode)){
            renderInstantSearchResults($(this).val());
        }
    }, 500, false));

    $searchInput.on('focus',debounce(function(e) {
        instantSearchResultState = true;
        e.stopPropagation();
        val = $(this).val();
        renderInstantSearchResults(val);
    }, 300, false));

    $('textarea.markdown').focus(function(){
        $('.wmd-preview').show();
        if ($('#prevHead').length == 0) {
            $('.wmd-preview').before('<h3 id="prevHead" style="margin:15px 0 10px;padding:0;">Preview</h3>');
        }
    });
    initReadingListFeature();
    initBorrowAndReadLinks();
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

    // Close any open dropdown list if the user clicks outside...
    $(document).on('click', function() {
        closeDropdown($('#widget-add'));
    });

    // ... but don't let that happen if user is clicking inside dropdown
    $(document).on('click', '#widget-add', function(e) {
        e.stopPropagation();
    });

    /* eslint-disable no-unused-vars */
    // success function receives data on successful request
    $(document).on('change', '.reading-log-lite select', function(e) {
        var self = this;
        var form = $(self).closest('form');
        var remove = $(self).children('option').filter(':selected').text().toLowerCase() === 'remove';
        var url = $(form).attr('action');
        $.ajax({
            'url': url,
            'type': 'POST',
            'data': {
                bookshelf_id: $(self).val()
            },
            'datatype': 'json',
            success: function(data) {
                if (remove) {
                    $(self).closest('.searchResultItem').remove();
                } else {
                    location.reload();
                }
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
