import { debounce } from './nonjquery_utils.js';
import * as Browser from './Browser';
import { SearchBar } from './SearchBar';
import { SearchPage } from './SearchPage';
import { SearchModeSelector, mode as searchMode } from './SearchUtils';

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

/*
Sets the key in the website cookie to the specified value
*/
function setValueInCookie(key, value) {
    document.cookie = `${key}=${value};path=/`;
}

export default function init() {
    const urlParams = Browser.getJsonFromUrl(location.search);
    if (urlParams.mode) {
        searchMode.write(urlParams.mode);
    }
    new SearchBar($('header#header-bar .search-component'), urlParams);

    if ($('.siteSearch.olform').length) {
        // Only applies to search results page (as of writing)
        new SearchPage($('.siteSearch.olform'), new SearchModeSelector($('.search-mode')));
    }

    $(window).on('scroll', function(){
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
    initWebsiteTranslationOptions();
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
    $(function(){
        $('.cta-btn--ia.cta-btn--borrow,.cta-btn--ia.cta-btn--read').on('click', function(){
            $(this).removeClass('cta-btn cta-btn--available').addClass('cta-btn cta-btn--available--load');
        });
    });
    $(function(){
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

export function initWebsiteTranslationOptions() {
    $('.locale-options li a').on('click', function (event) {
        event.preventDefault();
        const locale = $(this).data('lang-id');
        setValueInCookie('HTTP_LANG', locale);
        location.reload();
    });

}
