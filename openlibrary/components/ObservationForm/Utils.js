/**
 * Converts URI encoded JSON strings to JavaScript objects
 *
 * @param {String} str A URI encoded JSON string
 * @returns A JavaScript object
 */
export function decodeAndParseJSON(str) {
    return JSON.parse(decodeURIComponent(str));
}

/*
    window.$ is a jQuery object
    window.$.colorbox is a jQuery plugin
*/
export function resizeColorbox() {
    if (window.$ && window.$.colorbox && typeof window.$.colorbox.resize === 'function') {
        window.$.colorbox.resize();
    }
}
