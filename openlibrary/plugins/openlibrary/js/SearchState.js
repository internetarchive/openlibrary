/** Manages search state variables */

const MODES = ['everything', 'ebooks', 'printdisabled'];
const DEFAULT_MODE = 'ebooks';
const FACET_TO_ENDPOINT = {
    title: 'books',
    author: 'authors',
    lists: 'lists',
    subject: 'subjects',
    all: 'all',
    advanced: 'advancedsearch',
    text: 'inside',
};
const DEFAULT_FACET = 'all';

export class SearchState {
    constructor(urlParams) {
        this._listeners = {};

        if (!(this.facet in FACET_TO_ENDPOINT)) {
            this.facet = DEFAULT_FACET;
        }
        this.facet = urlParams.facet || this.facet || DEFAULT_FACET;
        this.searchMode = urlParams.mode;
    }

    get facet() {
        return localStorage.getItem('facet');
    }
    set facet(newFacet) {
        const oldValue = this.facet;
        localStorage.setItem('facet', newFacet);
        this._trigger('facet', newFacet, oldValue);
    }
    get facetValue() {
        return FACET_TO_ENDPOINT[this.facet];
    }

    get searchMode() {
        return localStorage.getItem('mode');
    }
    set searchMode(mode) {
        const oldValue = this.searchMode;
        const searchMode = (mode && mode.toLowerCase()) || oldValue;
        const isValidMode = MODES.indexOf(searchMode) != -1;
        const newMode = isValidMode ? searchMode : DEFAULT_MODE;
        localStorage.setItem('mode', newMode);
        this._trigger('searchMode', newMode, oldValue);
    }

    sync(key, handler, user_opts={}) {
        const DEFAULT_OPTS = {
            fireAtStart: true,
            onlyFireOnChange: true
        };

        if (!(key in this))
            throw Error('Invalid key', key);

        const opts = Object.assign({}, DEFAULT_OPTS, user_opts);
        this._listeners[key] = this._listeners[key] || [];
        this._listeners[key].push({ handle: handler, opts });
        if (opts.fireAtStart) handler(this[key]);
    }

    /**
     * @param {String} key
     * @param {any} newValue
     * @param {any} oldValue
     */
    _trigger(key, newValue, oldValue) {
        if (!(key in this._listeners)) {
            return;
        }

        for (let listener of this._listeners[key]) {
            if (listener.opts.onlyFireOnChange) {
                if (newValue != oldValue) {
                    listener.handle(newValue)
                }
            } else {
                listener.handle(newValue);
            }
        }
    }
}