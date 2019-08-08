import { removeURLParameter } from './Browser';

/**
 * No clue what this is doing
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


/**
 * @typedef {Object} PersistentValue.Options
 * @property {any?} [default]
 * @property {Function?} [initValidation] (str -> bool) validation to perform on intialization.
 * @property {Function?} [writeTransformation] ((newVal, oldVal) -> val) function to call that
 * transforms a value before save.
 */

/**
 * String value that's persisted to localstorage.
 */
export class PersistentValue {
    /**
     * @param {String} key
     * @param {PersistentValue.Options} options
     */
    constructor(key, options={}) {
        this.key = key;
        this.options = Object.assign({}, PersistentValue.DEFAULT_OPTIONS, options);
        this._listeners = [];

        const noValue = this.read() == null;
        const isValid = () => !this.initValidation || this.initValidation(this.read());
        if (noValue || !isValid()) {
            this.write(this.options.default);
        }
    }

    read() {
        return localStorage.getItem(this.key);
    }

    write(newValue) {
        const oldValue = this.read();
        let toWrite = newValue;
        if (this.options.writeTransformation) {
            toWrite = this.options.writeTransformation(newValue, oldValue);
        }
        localStorage.setItem(this.key, toWrite);
        if (oldValue != toWrite) {
            this._trigger(toWrite);
        }
    }

    change(handler, fireAtStart=true) {
        this._listeners.push(handler);
        if (fireAtStart) handler(this.read());
    }

    _trigger(newValue) {
        this._listeners.forEach(listener => listener(newValue));
    }
}

/** @type {PersistentValue.Options} */
PersistentValue.DEFAULT_OPTIONS = {
    default: null,
    initValidation: null,
    writeTransformation: null,
};


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
