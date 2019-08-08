/** Manages search state variables */

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
