import { initSearchModal } from './search-modal/SearchModal';

/*
Sets the key in the website cookie to the specified value
*/
function setValueInCookie(key, value) {
    document.cookie = `${key}=${value};path=/`;
}

export default function init() {
    const $searchComponent = $('header#header-bar .search-component');
    initSearchModal($searchComponent.find('.search-bar-trigger')[0]);

    initBorrowAndReadLinks();
    initWebsiteTranslationOptions();
}

export function initBorrowAndReadLinks() {
    // LOADING ONCLICK FUNCTIONS FOR BORROW AND READ LINKS

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


}

export function initWebsiteTranslationOptions() {
    $('.locale-options li a').on('click', function(event) {
        event.preventDefault();
        const locale = $(this).data('lang-id');
        setValueInCookie('HTTP_LANG', locale);
        location.reload();
    });

}
