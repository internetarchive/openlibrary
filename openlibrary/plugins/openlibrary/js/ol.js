import { initSearchModal } from './search-modal/SearchModal';

/*
Sets the key in the website cookie to the specified value
*/
function setValueInCookie(key, value) {
    document.cookie = `${key}=${value};path=/`;
}

export default function init() {
    const searchComponent = document.querySelector('header#header-bar .search-component');
    initSearchModal(searchComponent?.querySelector('.search-bar-trigger'));

    initWebsiteTranslationOptions();
}

export function initWebsiteTranslationOptions() {
    document.querySelectorAll('.locale-options li a').forEach(link => {
        link.addEventListener('click', event => {
            event.preventDefault();
            const locale = link.dataset.langId;
            setValueInCookie('HTTP_LANG', locale);
            location.reload();
        });
    });
}
