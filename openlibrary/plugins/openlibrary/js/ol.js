import * as Browser from './Browser';
import { SearchBar } from './SearchBar';
import { SearchPage } from './SearchPage';
import { SearchModeSelector, mode as searchMode } from './SearchUtils';

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

    initBorrowAndReadLinks();
    initPreviewButton();
    initWebsiteTranslationOptions();
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
