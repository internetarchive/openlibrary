const urlParams = new URLSearchParams(location.search);

const IS_VUE_APP =  document.title == 'Vue App';
const OL_BASE_DEFAULT = IS_VUE_APP ? 'openlibrary.org' : urlParams.get('ol_base');

const CONFIGS = {
    OL_BASE_COVERS: urlParams.get('ol_base_covers') || 'covers.openlibrary.org',
    OL_BASE_SEARCH: urlParams.get('ol_base_search') || OL_BASE_DEFAULT || '',
    OL_BASE_BOOKS: urlParams.get('ol_base_books') || OL_BASE_DEFAULT || '',
    OL_BASE_PUBLIC: urlParams.get('ol_base') || 'openlibrary.org',
    DEBUG_MODE: urlParams.get('debug') == 'true',
};

for (const key of ['OL_BASE_COVERS', 'OL_BASE_SEARCH', 'OL_BASE_BOOKS']) {
    if (CONFIGS[key] && !CONFIGS[key].startsWith('http')) {
        CONFIGS[key] = `https://${CONFIGS[key]}`;
    }
}

export default CONFIGS;
