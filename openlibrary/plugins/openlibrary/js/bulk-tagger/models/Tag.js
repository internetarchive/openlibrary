/**
 * Maps technical subject types to subject types which
 * can be displayed in the UI.
 */
const displayTypeMapping = {
    subjects: 'subject',
    subject_people: 'person',
    subject_places: 'place',
    subject_times: 'time'
}

/**
 * Maps UI-ready subject types to their corresponding
 * technical types.
 */
export const subjectTypeMapping = {
    subject: 'subjects',
    person: 'subject_people',
    place: 'subject_places',
    time: 'subject_times'
}

/**
 * Represents a subject that can be added to a work.
 *
 * Each `Tag` will have a tag name, a technical type, and a
 * type string that is suitable for displaying in the UI.
 */
export class Tag {
    /**
     * Creates a new Tag object.
     *
     * If only one tag type is passed to the constructor, the missing
     * tag type will be inferred and set.
     *
     * @param {String} tagName The name of the Tag
     * @param {String} tagType This tag's technical type
     * @param {String} displayType This tag's type, in UI-ready form.
     *
     * @throws Will throw an error if at least one type is passed to the constructor
     */
    constructor(tagName, tagType = null, displayType = null) {
        if (!(tagType || displayType)) {
            throw new Error('Tag must have at least one type')
        }
        this.tagName = tagName
        this.tagType = tagType || this.convertToType(displayType)
        this.displayType = displayType || this.convertToDisplayType(tagType)
    }

    /**
     * Returns the technical tag type corresponding to the given
     * UI-ready type string.
     *
     * @param {String} displayType A UI-ready type string
     * @returns {String} The corresponding technical tag type
     * @throws Will throw an error if the given type is unrecognized.
     */
    convertToType(displayType) {
        const result = subjectTypeMapping[displayType]
        if (!result) {
            throw new Error('Unrecognized `displayType` value')
        }
        return result
    }

    /**
     * Given a technical tag type, returns a type string that can be
     * displayed in the UI.
     *
     * @param {String} tagType The technical tag type
     * @returns {String} A type string that can be displayed in the UI
     * @throws Will throw an error if the given type is unrecognized
     */
    convertToDisplayType(tagType) {
        const result = displayTypeMapping[tagType]
        if (!result) {
            throw new Error('Unrecognized `tagType` value')
        }
        return result
    }
}
