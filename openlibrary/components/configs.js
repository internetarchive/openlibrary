// Useful configs that make testing the app easier. Exposes url parameters
// to the app that you can use to override eg where to fetch data from.

const urlParams = new URLSearchParams(location.search);

const IS_VUE_APP =  document.title === 'Vue App';
const OL_BASE_DEFAULT = urlParams.get('ol_base') || (IS_VUE_APP ? 'openlibrary.org' : '');

const CONFIGS = {
    OL_BASE_COVERS: urlParams.get('ol_base_covers') || 'covers.openlibrary.org',
    OL_BASE_SEARCH: urlParams.get('ol_base_search') || OL_BASE_DEFAULT || '',
    OL_BASE_BOOKS: urlParams.get('ol_base_books') || OL_BASE_DEFAULT || '',
    OL_BASE_LANGS: urlParams.get('ol_base_langs') || OL_BASE_DEFAULT || '',
    // Make the save location explicitly different from ol_base to avoid
    // accidentally triggering saves to prod (which shouldn't work anyways
    // due to cookies, but just in case!)
    OL_BASE_SAVES: urlParams.get('ol_base_saves') || '',
    OL_BASE_PUBLIC: urlParams.get('ol_base') || 'openlibrary.org',
    DEBUG_MODE: urlParams.get('debug') === 'true',
    LANG: urlParams.get('lang'),
};

for (const key of ['OL_BASE_COVERS', 'OL_BASE_SEARCH', 'OL_BASE_BOOKS', 'OL_BASE_LANGS', 'OL_BASE_SAVES']) {
    if (CONFIGS[key] && !CONFIGS[key].startsWith('http')) {
        CONFIGS[key] = `https://${CONFIGS[key]}`;
    }
}

export default CONFIGS;
