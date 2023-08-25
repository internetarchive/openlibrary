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
  const regex = /^[0-9]{13}$/
  return regex.test(isbn)
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
