export function decodeAndParseJSON(str) {
    return JSON.parse(decodeURIComponent(str));
}

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

function capitalize(str) {
  return str[0].toUpperCase() + str.substring(1)
}
