/**
 * Converts URI encoded JSON strings to JavaScript objects
 *
 * @param {String} str A URI encoded JSON string
 * @returns A JavaScript object
 */
export function decodeAndParseJSON(str) {
    return JSON.parse(decodeURIComponent(str));
}

/**
 * Returns new array of observation schema objects, with observation types
 * and values capitalized.
 *
 * @param {Object[]} observationsArray An array of observation objects
 * @returns An array of observation objects, but with capitalized types and values
 */
export function capitalizeTypesAndValues(observationsArray) {
    const results = observationsArray;

    for (const item of results) {
        item.label = capitalize(item.label);

        for (const index in item.values) {
            item.values[index] = capitalize(item.values[index])
        }
    }

    return results;
}

/**
 * Creates and returns a copy of the given object, with observation types
 * and values capitalized.
 *
 * Example `observationObject`:
 * {
 *   "mood": ["joyful", "humorous"],
 *   "genres": ["memoir"]
 * }
 *
 * @param {Object} observationObject Object containing a patron's book tags.
 * @returns Copy of `observationObject` with types and values capitalized.
 */
export function capitalizePatronObservations(observationObject) {
    const results = {};

    for (const item in observationObject) {
        const values = []
        for (const value of observationObject[item]) {
            values.push(capitalize(value))
        }

        results[capitalize(item)] = values
    }

    return results;
}

/**
 * Returns a capitalized copy of the given string.
 *
 * @param {String} str A string that should be capitalized
 * @returns A copy of str with an uppercase first character
 */
function capitalize(str) {
    return str[0].toUpperCase() + str.substring(1)
}

export function resizeColorbox() {
    window.$.colorbox.resize();
}
