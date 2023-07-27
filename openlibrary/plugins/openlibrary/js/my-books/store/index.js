/**
 * Represents a store of data related to the currently
 * open My Books dropper.
 *
 * Used to pass data between individual My Books droppers on
 * a page, and the list creation form.
 *
 * @class
 */
class MyBooksStore {
    /**
     * Initializes the store.
     */
    constructor() {
        this._store = {}
    }

    /**
     * Adds data to the store, using the given key.
     *
     * @param {string} key
     * @param {*} data
     */
    set(key, data) {
        this._store[key] = data
    }

    /**
     * Gets the store data referenced by the given key.
     *
     * @param {string} key
     * @returns {*} Stored data, or `undefined` if no entry exists.
     */
    get(key) {
        return this._store[key]
    }
}

const myBooksStore = new MyBooksStore()
Object.freeze(myBooksStore)

export default myBooksStore
