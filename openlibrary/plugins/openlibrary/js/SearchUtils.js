import { removeURLParameter } from './Browser';
import { PersistentValue } from './SearchState';

/**
 * Oh, between SEARCH_MODES
 * @param {HTMLFormElement|String|JQuery} form
 * @param {String} searchMode
 */
export function updateSearchMode(form, searchMode) {
    if (!$(form).length) {
        return;
    }

    $('input[value=\'Protected DAISY\']').remove();
    $('input[name=\'has_fulltext\']').remove();

    let url = $(form).attr('action');
    if (url) {
        url = removeURLParameter(url, 'm');
        url = removeURLParameter(url, 'has_fulltext');
        url = removeURLParameter(url, 'subject_facet');
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
        url = `${url + (url.indexOf('?') > -1 ? '&' : '?')}subject_facet=Protected DAISY`;
    }

    $(form).attr('action', url);
}

const MODES = ['everything', 'ebooks', 'printdisabled'];
const DEFAULT_MODE = 'ebooks';
/** The type of thing the user is searching for. {@see MODES} */
export const mode = new PersistentValue('mode', {
    default: DEFAULT_MODE,
    initValidation: mode => MODES.indexOf(mode) != -1,
    writeTransformation(newValue, oldValue) {
        const mode = (newValue && newValue.toLowerCase()) || oldValue;
        const isValidMode = MODES.indexOf(mode) != -1;
        return isValidMode ? mode : DEFAULT_MODE;
    }
});
