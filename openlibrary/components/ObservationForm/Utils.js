/**
 * Converts URI encoded JSON strings to JavaScript objects
 *
 * @param {String} str A URI encoded JSON string
 * @returns A JavaScript object
 */
export function decodeAndParseJSON(str) {
  return JSON.parse(decodeURIComponent(str));
}

export function resizeColorbox() {
  window.$.colorbox.resize();
}
