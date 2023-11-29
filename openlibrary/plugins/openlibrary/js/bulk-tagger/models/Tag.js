const displayTypeMapping = {
    subjects: 'subject',
    subject_people: 'person',
    subject_places: 'place',
    subject_times: 'time'
}

export const subjectTypeMapping = {
    subject: 'subjects',
    person: 'subject_people',
    place: 'subject_places',
    time: 'subject_times'
}

export class Tag {
    constructor(tagName, tagType = null, displayType = null) {
        if (!(tagType || displayType)) {
            throw new Error('Tag must have at least one type')
        }
        this.tagName = tagName
        this.tagType = tagType || this.convertToType(displayType)
        this.displayType = displayType || this.convertToDisplayType(tagType)
    }

    convertToType(displayType) {
        const result = subjectTypeMapping[displayType]
        if (!result) {
            throw new Error('Unrecognized `displayType` value')
        }
        return result
    }

    convertToDisplayType(tagType) {
        const result = displayTypeMapping[tagType]
        if (!result) {
            throw new Error('Unrecognized `tagType` value')
        }
        return result
    }
}