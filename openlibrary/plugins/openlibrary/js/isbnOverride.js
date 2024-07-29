/**
 * Exports an object to track the state of an ISBN that is formally valid, but
 * has an invalid checksum and can only be added by a user specifically
 * clicking "yes" to add the invalid ISBN.
 * @property {Object} data - The default data
 * @property {Function(object)} set - Sets the ISBN object
 * @property {Function} get - returns the ISBN object
 * @property {Function} clear - clears the ISBN object
 */
export const isbnOverride = {
  data: null,
  set(isbnData) { this.data = isbnData },
  get() { return this.data },
  clear() { this.data = null },
}
