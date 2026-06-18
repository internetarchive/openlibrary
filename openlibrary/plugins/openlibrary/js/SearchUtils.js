/**
 * @typedef {Object} PersistentValue.Options
 * @property {String?} [default]
 * @property {Function?} [initValidation] (str -> bool) validation to perform on intialization.
 * @property {Function?} [writeTransformation] ((newVal, oldVal) -> val) function to call that
 * transforms a value before save.
 */

/** String value that's persisted to localstorage */
export class PersistentValue {
    /**
     * @param {String} key
     * @param {PersistentValue.Options} options
     */
    constructor(key, options={}) {
        this.key = key;
        this.options = Object.assign({}, PersistentValue.DEFAULT_OPTIONS, options);
        this._listeners = [];

        const noValue = this.read() === null;
        const isValid = () => !this.options.initValidation || this.options.initValidation(this.read());
        if (noValue || !isValid()) {
            this.write(this.options.default);
        }
    }

    /**
     * Read the stored value
     * @return {String}
     */
    read() {
        return localStorage.getItem(this.key);
    }

    /**
     * Update the stored value
     * @param {String} newValue
     */
    write(newValue) {
        const oldValue = this.read();
        let toWrite = newValue;
        if (this.options.writeTransformation) {
            toWrite = this.options.writeTransformation(newValue, oldValue);
        }

        if (toWrite === null) {
            localStorage.removeItem(this.key);
        } else {
            localStorage.setItem(this.key, toWrite);
        }

        if (oldValue !== toWrite) {
            this._emit(toWrite);
        }
    }

    /**
     * Listen to updates to this value
     * @param {Function} listener
     * @param {Boolean} callAtStart whether to call the listener right now with the current value
     */
    sync(listener, callAtStart=true) {
        this._listeners.push(listener);
        if (callAtStart) listener(this.read());
    }

    /**
     * @private
     * Notify listeners of an update
     * @param {String} newValue
     */
    _emit(newValue) {
        this._listeners.forEach(listener => listener(newValue));
    }
}

/** @type {PersistentValue.Options} */
PersistentValue.DEFAULT_OPTIONS = {
    default: null,
    initValidation: null,
    writeTransformation: null,
};


const MODES = ['everything', 'ebooks'];
const DEFAULT_MODE = 'everything';
/** Search mode; {@see MODES} */
export const mode = new PersistentValue('mode', {
    default: DEFAULT_MODE,
    initValidation: mode => MODES.indexOf(mode) !== -1,
    writeTransformation(newValue, oldValue) {
        const mode = (newValue && newValue.toLowerCase()) || oldValue;
        const isValidMode = MODES.indexOf(mode) !== -1;
        return isValidMode ? mode : DEFAULT_MODE;
    }
});
