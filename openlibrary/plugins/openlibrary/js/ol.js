import $ from 'jquery';
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

    initWebsiteTranslationOptions();
}

export function initWebsiteTranslationOptions() {
    $('.locale-options li a').on('click', function(event) {
        event.preventDefault();
        const locale = $(this).data('lang-id');
        setValueInCookie('HTTP_LANG', locale);
        location.reload();
    });

}
