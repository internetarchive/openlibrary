/**
 * Removes spaces and hyphens from an ISBN string and returns it.
 * @param {String} isbn  ISBN string for parsing
 * @returns {String}  parsed isbn string
 */
export function parseIsbn(isbn) {
  return isbn.replace(/[ -]/g, '');
}

/**
 * Takes an ISBN 10 string and verifies that is the correct length and has the
 * correct characters for an ISBN. It does not verify the checksum.
 * @param {String} isbn  ISBN string to check
 * @returns {boolean}  true if the isbn has a valid format
 */
export function isFormatValidIsbn10(isbn) {
  const regex = /^[0-9]{9}[0-9X]$/;
  return regex.test(isbn);
}

/**
 * Verify the checksum for ISBN 10.
 * Adapted from https://www.oreilly.com/library/view/regular-expressions-cookbook/9781449327453/ch04s13.html
 * @param {String} isbn  ISBN string for validating
 * @returns {boolean}  true if ISBN string is a valid ISBN 10
 */
export function isChecksumValidIsbn10(isbn) {
  const chars = isbn.replace('X', 'A').split('');

  chars.reverse();
  const sum = chars
    .map((char, idx) => ((idx + 1) * parseInt(char, 16)))
    .reduce((acc, sum) => acc + sum, 0);

  // The ISBN 10 is valid if the checksum mod 11 is 0.
  return sum % 11 === 0;
}

/**
 * Takes an isbn string and verifies that is the correct length and has the
 * correct characters for an ISBN. It does not verify the checksum.
 * @param {String} isbn  ISBN string to check
 * @returns {boolean}  true if the isbn has a valid format
 */
export function isFormatValidIsbn13(isbn) {
  const regex = /^[0-9]{13}$/;
  return regex.test(isbn);
}

/**
* Verify the checksum for ISBN 13.
* Adapted from https://www.oreilly.com/library/view/regular-expressions-cookbook/9781449327453/ch04s13.html
* @param {String} isbn  ISBN string for validating
* @returns {Boolean}  true if ISBN string is a valid ISBN 13
*/
export function isChecksumValidIsbn13(isbn) {
  const chars = isbn.split('');
  const sum = chars
    .map((char, idx) => ((idx % 2 * 2 + 1) * parseInt(char, 10)))
    .reduce((sum, num) => sum + num, 0);

  // The ISBN 13 is valid if the checksum mod 10 is 0.
  return sum % 10 === 0;
}

/**
 * JS re-write of the existing python LCCN parsing found in /openlibrary/utils/lccn.py.
 * Validates the syntax described at https://www.loc.gov/marc/lccn-namespace.html
 * @param {String} lccn  LCCN string for parsing
 * @returns {String}  parsed LCCN string
 */
export function parseLccn(lccn) {
  // cleaning initial lccn entry
  const parsed = lccn
  // any alpha characters need to be lowercase
    .toLowerCase()
  // remove any whitespace
    .replace(/\s/g, '')
  // remove leading and trailing dashes
    .replace(/^[-]+/, '').replace(/[-]+$/, '')
  // remove any revised text
    .replace(/rev.*/g, '')
  // remove first forward slash and everything to its right
    .replace(/[/]+.*$/, '');

  // splitting at hyphen and padding the right hand value with zeros up to 6 characters
  const groups = parsed.match(/(.+)-+([0-9]+)/)
  if (groups && groups.length === 3) {
    return groups[1] + groups[2].padStart(6, '0');
  }
  return parsed;
}

/**
 * Verify LCCN syntax. Regex taken from /openlibrary/utils/lccn.py.
 * Based on instructions from https://www.loc.gov/marc/lccn-namespace.html.
 * @param {String} lccn  LCCN string to test for valid syntax
 * @returns {boolean}  true if given LCCN is valid syntax, false otherwise
 */
export function isValidLccn(lccn) {
  // matching parsed entry to regex representing valid lccn
  // regex taken from /openlibrary/utils/lccn.py
  const regex = /^([a-z]|[a-z]?([a-z]{2}|[0-9]{2})|[a-z]{2}[0-9]{2})?[0-9]{8}$/;
  return regex.test(lccn);
}

/**
 * Given a list of identifier entries from edition page form and a new
 * identifier, determines if the new identifier has already been entered
 * under the same type as an existing identifier entry.
 * Expects identifiers that have already been parsed/normalized.
 * @param {Array} idEntries  Array of identifier entries
 * @param {String} newId  New identifier entry to be checked
 * @returns {boolean}  true if the new identifier has already been entered
 */
export function isIdDupe(idEntries, newId) {
  // check each current entry value against new identifier
  return Array.from(idEntries).some(
    entry => entry['value'] === newId
  );
}
