/** Manages search state variables */

const MODES = ['everything', 'ebooks', 'printdisabled'];
const DEFAULT_MODE = 'ebooks';

export class SearchState {
    constructor(urlParams) {
        this._listeners = {};
        this.searchMode = urlParams.mode;
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

/**
 * @typedef {Object} PersistentValue.Options
 * @property {any?} [default]
 * @property {Function?} [initValidation] validation to perform on intialization
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
        localStorage.setItem(this.key, newValue);
        if (oldValue != newValue) {
            this._trigger(newValue);
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
};
