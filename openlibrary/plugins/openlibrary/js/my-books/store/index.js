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
    this._store = {
      droppers: [],
      showcases: [],
      userkey: '',
      openDropper: null
    }
  }

  /**
     * @returns {Array<MyBooksDropper>}
     */
  getDroppers() {
    return this._store.droppers
  }

  /**
     * @param {Array<MyBooksDropper>} droppers
     */
  setDroppers(droppers) {
    this._store.droppers = droppers
  }

  /**
     * @returns {Array<ShowcaseItem>}
     */
  getShowcases() {
    return this._store.showcases
  }

  /**
     * @param {Array<ShowcaseItem>} showcases
     */
  setShowcases(showcases) {
    this._store.showcases = showcases
  }

  /**
     * @returns {string}
     */
  getUserKey() {
    return this._store.userKey
  }

  /**
     * @param {string} userKey
     */
  setUserKey(userKey) {
    this._store.userKey = userKey
  }

  /**
     * @returns {MyBooksDropper}
     */
  getOpenDropper() {
    return this._store.openDropper
  }

  /**
     * @param {MyBooksDropper} dropper
     */
  setOpenDropper(dropper) {
    this._store.openDropper = dropper
  }
}

const myBooksStore = new MyBooksStore()
Object.freeze(myBooksStore)

export default myBooksStore
