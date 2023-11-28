/**
 * Defines functionality related to the ILE's Bulk Tagger tool.
 * @module ile/BulkTagger
 */
import { SelectedTag } from './BulkTagger/SelectedTag';
import { debounce } from '../nonjquery_utils';
import { FadingToast } from '../Toast'

const maxDisplayResults = 25;

const classTypeSuffixes = {
    subject: '--subject',
    person: '--person',
    place: '--place',
    time: '--time'
}

const subjectTypeMapping = {
    subject: 'subjects',
    person: 'subject_people',
    place: 'subject_places',
    time: 'subject_times'
}

/**
 * Represents the Bulk Tagger tool.
 *
 * The Bulk Tagger tool allows librarians to add or remove subjects in batches.
 *
 * @see `/openlibrary/templates/subjects/tagging_menu.html` for component's base template.
 * @class
 */
export class BulkTagger {
    /**
     * Sets references to key Bulk Tagger affordances.
     *
     * @param {HTMLElement} bulkTagger Reference to root element of the Bulk Tagger
     */
    constructor(bulkTagger) {
        /**
         * Reference to root Bulk Tagger element.
         * @member {HTMLFormElement}
         */
        this.bulkTagger = bulkTagger

        /**
         * Reference to the Bulk Tagger's subject search box.
         * @member {HTMLInputElement}
         */
        this.searchInput = bulkTagger.querySelector('.subjects-search-input')

        /**
         * Reference to container that displays search results.
         * @member {HTMLElement}
         */
        this.searchResultsContainer = bulkTagger.querySelector('.subjects-search-results')

        /**
         * Reference to the element which contains the affordance that creates new subjects.
         * @member {HTMLElement}
         */
        this.createSubjectElem = bulkTagger.querySelector('.search-subject-row-name')

        /**
         * Element which displays the subject name within the "create new tag" affordance.
         * @member {HTMLElement}
         */
        this.subjectNameElem = this.createSubjectElem.querySelector('.subject-name')

        /**
         * Reference to container which holds the selected subject tags.
         * @member {HTMLElement}
         */
        this.selectedTagsContainer = bulkTagger.querySelector('.selected-tag-subjects')

        /**
         * Reference to input which holds the subjects to be batch added.
         * @member {HTMLInputElement}
         */
        this.addSubjectsInput = bulkTagger.querySelector('input[name=tags_to_add]')

        /**
         * Input which contains the subjects to be batch removed.
         * @member {HTMLInputElement}
         */
        this.removeSubjectsInput = bulkTagger.querySelector('input[name=tags_to_remove]')

        /**
         * Reference to hidden input which holds a comma-separated list of work OLIDs
         * @member {HTMLInputElement}
         */
        this.selectedWorksInput = bulkTagger.querySelector('input[name=work_ids]')

        /**
         * @typedef {Object} SubjectEntry
         * @property {Array<String>} subjects
         * @property {Array<String>} subject_people
         * @property {Array<String>} subject_places
         * @property {Array<String>} subject_times
         */
        /**
         * Stores works' subjects that have been fetched from the server.
         *
         * Keys to the map are work IDs.
         * @member {Map<String, SubjectEntry>}
         */
        this.fetchedSubjects = new Map()

        /**
         * @typedef {Object} SelectedTagEntry
         * @property {SelectedTag} selectedTag
         * @property {String} tagType
         * @property {String} tagName
         * @property {Number} taggedWorksCount Number of selected works which share this tag.
         */
        /**
         * Stores information about each selected tag.
         *
         * Tag names are used as keys to this map.
         *
         * @member {Map<String, Array<SelectedTagEntry>>}
         */
        this.selectedTags = new Map()

        /**
         * Array containing OLIDs of each selected work.
         *
         * @member {Array<String>}
         */
        this.selectedWorks = []
    }

    /**
     * Adds event listeners to the Bulk Tagger.
     */
    initialize() {
        // Add "hide menu" functionality:
        const closeFormButton = this.bulkTagger.querySelector('.close-bulk-tagging-form')
        closeFormButton.addEventListener('click', () => {
            this.hideTaggingMenu()
        })

        // Add input listener to subject search box:
        this.searchInput.addEventListener('input', () => {
            const searchTerm = this.searchInput.value.trim();
            // XXX : debounce is not working as expected here
            debounce(this.onSearchInputChange(searchTerm), 500)
        });

        // Prevent redirect on batch subject submission:
        const submitButton = this.bulkTagger.querySelector('.bulk-tagging-submit')
        submitButton.addEventListener('click', (event) => {
            event.preventDefault()
            this.submitBatch()
        })

        // Add click listeners to "create subject" options:
        const createSubjectButtons = this.bulkTagger.querySelectorAll('.subject-type-option')
        for (const elem of createSubjectButtons) {
            elem.addEventListener('click', () => this.onSelectTag(this.searchInput.value, elem.dataset.tagType))
        }
    }

    /**
     * Hides the Bulk Tagger.
     */
    hideTaggingMenu() {
        this.bulkTagger.classList.add('hidden')
    }

    /**
     * Displays the Bulk Tagger.
     */
    showTaggingMenu() {
        this.bulkTagger.classList.remove('hidden')
    }

    /**
     * Updates the BulkTagger when works are selected.
     *
     * Add the given work OLIDs to the bulk tagging form, fetches the
     * existing tags for each given work, and updates the view with
     * the existing tags.
     *
     * @param {Array<String>} workIds
     */
    async updateWorks(workIds) {
        this.selectedWorks = workIds
        this.selectedWorksInput.value = workIds.join(',')

        await this.fetchSubjectsForWorks(workIds)
        this.updateSelectedTags()
    }

    processArray(tags, tagType) {
        for (const tagName of tags) {
            if (this.selectedTags.has(tagName)) {
                const existingEntries = this.selectedTags.get(tagName)
                const matchingTag = existingEntries.find((tag) => tag.tagType === tagType)
                if (matchingTag) {
                    matchingTag.taggedWorksCount++
                } else {
                    const newTag = {
                        tagType: tagType,
                        tagName: tagName,
                        taggedWorksCount: 1
                    }
                    existingEntries.push(newTag)
                }
            } else {
                const newTag = {
                    tagType: tagType,
                    tagName: tagName,
                    taggedWorksCount: 1
                }
                this.selectedTags.set(tagName, [newTag])
            }
        }
    }

    updateSelectedTags() {
        this.selectedTags.clear()
        for (const workOlid of this.selectedWorks) {
            const subjectEntry = this.fetchedSubjects.get(workOlid)
            if (subjectEntry) {
                this.processArray(subjectEntry.subjects, 'subjects')
                this.processArray(subjectEntry.subject_people, 'subject_people')
                this.processArray(subjectEntry.subject_places, 'subject_places')
                this.processArray(subjectEntry.subject_times, 'subject_times')
            }
        }

        this.selectedTags.forEach((arr) => {
            for (const tag of arr) {
                const allWorksTagged = tag.taggedWorksCount === this.selectedWorks.length
                const selectedTag = new SelectedTag(tag.tagType, tag.tagName, allWorksTagged)
                tag.selectedTag = selectedTag
                selectedTag.renderAndAttach()
                selectedTag.selectedTag.addEventListener('click', () => this.onSelectedTagClick(tag))
            }
        })
    }

    /**
     * 
     * @param {SelectedTagEntry} selectedTagEntry
     */
    onSelectedTagClick(selectedTagEntry) {
        const selectedTag = selectedTagEntry.selectedTag

        if (selectedTag.allWorksTagged) {  // Remove this tag from all selected works:
            // Add subject to `tags_to_remove`
            this.updateSubjectInput(selectedTagEntry.tagName, selectedTagEntry.tagType, this.addSubjectsInput, false)
            this.updateSubjectInput(selectedTagEntry.tagName, selectedTagEntry.tagType, this.removeSubjectsInput, true)

            // Remove from DOM
            selectedTag.remove()

            // Remove reference
            const selectedEntries = this.selectedTags.get(selectedTagEntry.tagName)
            const matchIndex = selectedEntries.findIndex((t) => t.tagType === selectedTagEntry.tagType)
            if (matchIndex > -1) {
                this.selectedTags.set(selectedTagEntry.tagName, selectedEntries.splice(matchIndex, 1))
            }
        } else {  // Add this tag to all selected works:
            // Add subject to `tags_to_add`
            this.updateSubjectInput(selectedTagEntry.tagName, selectedTagEntry.tagType, this.addSubjectsInput, true)

            // Update view
            selectedTag.updateAllWorksTagged(true)
        }
    }

    /**
     * Updates the value of the given input, either adding or removing the given subject.
     *
     * @param {String} subjectName Name of the subject.
     * @param {String} subjectType The subject type.
     * @param {HTMLInputElement} input Reference to hidden input being modified.
     * @param {boolean} isAdding `true` if this subject is being added to the given input, `false` if it's being removed.
     */
    updateSubjectInput(subjectName, subjectType, input, isAdding) {
        const existingSubjects = JSON.parse(input.value === '' ? '{}' : input.value)

        // Add entry for the subject type if none exists:
        existingSubjects[subjectType] = existingSubjects[subjectType] || []
        if (isAdding) {
            // Only add the subject if it isn't already in the array:
            if (!existingSubjects[subjectType].includes(subjectName)) {
                existingSubjects[subjectType].push(subjectName)
            }
        } else {
            // Remove subject only if subject exists in the array:
            const matchIndex = existingSubjects[subjectType].findIndex((item) => item === subjectName)
            if (matchIndex > -1) {
                existingSubjects[subjectType].splice(matchIndex, 1)
            }
        }

        input.value = JSON.stringify(existingSubjects)
    }

    /**
     * Fetches and stores subject information for the given work OLIDs.
     *
     * If we already have fetched the data for a work ID, we do not fetch it
     * again.
     * @param {Array<String>} workIds
     */
    async fetchSubjectsForWorks(workIds) {
        const worksWithMissingSubjects = workIds.filter(id => !this.fetchedSubjects.has(id))

        await Promise.all(worksWithMissingSubjects.map(async (id) => {
            // XXX : Too many network requests --- use bulk search when/if able
            await this.fetchWork(id)
                .then(response => response.json())
                .then(data => {
                    const entry = {
                        subjects: data.subjects || [],
                        subject_people: data.subject_people || [],
                        subject_places: data.subject_places || [],
                        subject_times: data.subject_times || []
                    }
                    this.fetchedSubjects.set(id, entry)
                })
        }))
    }

    /**
     * Fetches a work from OL.
     *
     * @param {String} workOlid
     */
    async fetchWork(workOlid) {
        return fetch(`/works/${workOlid}.json`)
    }

    /**
     * Performs a subject search for the given search term, and updates
     * the Bulk Tagger with the results.
     *
     * If the given search term, when trimmed, is an empty string, this
     * instead hides the "create subject" affordance.
     *
     * @param {String} searchTerm
     */
    onSearchInputChange(searchTerm) {
        const trimmedSearchTerm = searchTerm.trim()
        this.searchResultsContainer.innerHTML = '';
        if (trimmedSearchTerm !== '') {
            fetch(`/search/subjects.json?q=${searchTerm}&limit=${maxDisplayResults}`)
                .then((response) => response.json())
                .then((data) => {
                    if (data['docs'].length !== 0) {
                        data['docs']
                            .forEach(result => {
                                const isSelected = this.addSubjectsInput.value.includes(result.name);
                                this.createSearchResult(result.name, result['subject_type'], result['work_count'], isSelected);
                            });
                    }

                    // Update and show create subject affordance
                    this.updateAndShowNewSubjectAffordance(trimmedSearchTerm)
                });
        } else {
            // Hide create subject affordance
            this.createSubjectElem.classList.add('hidden')
        }
    }

    /**
     * Updates the "create subject" affordance with the given subject name,
     * and shows the affordance if it is hidden.
     *
     * @param {String} subjectName The name of the subject
     */
    updateAndShowNewSubjectAffordance(subjectName) {
        this.subjectNameElem.innerText = subjectName
        this.createSubjectElem.classList.remove('hidden')
    }

    /**
     * Creates, hydrates, and attaches a new search result affordance.
     *
     * @param {String} subjectName The subject's name.
     * @param {String} subjectType The subject's type. Will be displayed in UI.
     * @param {Number} workCount Number of works that are tagged with this subject.
     */
    createSearchResult(subjectName, subjectType, workCount) {
        const workCountString = workCount > 999 ? 'works: 999+' : `works: ${workCount}`
        const div = document.createElement('div')
        div.classList.add('search-subject-row')

        const markup = `<div class="search-subject-row-name">${subjectName}</div>
        <div class="search-subject-row-subject-info">
            <div class="search-subject-type subject-type-option${classTypeSuffixes[subjectType]}">${subjectType}</div>
            <div class="search-subject-work-count">${workCountString}</div>
        </div>`

        div.innerHTML = markup
        const subjectTypeKey = subjectTypeMapping[subjectType]
        div.addEventListener('click', () => {
            this.onSelectTag(subjectName, subjectTypeKey)
            div.remove()
        })
        this.searchResultsContainer.appendChild(div)
    }

    /**
     *
     * @param {String} tagName
     * @param {String} tagType Expected to be in snake_case form
     */
    onSelectTag(tagName, tagType) {
        // Ensure that this tag is not already selected:
        const entryExists = this.selectedTags.has(tagName) && this.selectedTags.get(tagName).some((entry) => entry.tagType === tagType)

        if (!entryExists) {
            // Create new selected tag:
            const selectedTag = new SelectedTag(tagType, tagName, true)
            const selectedTagEntry = {
                tagType: tagType,
                tagName: tagName,
                taggedWorksCount: this.selectedWorks.length,
                selectedTag: selectedTag
            }
            if (!this.selectedTags.has(tagName)) {
                this.selectedTags.set(tagName, [selectedTagEntry])
            } else {
                this.selectedTags.get(tagName).push(selectedTagEntry)
            }

            // Update the UI:
            selectedTag.renderAndAttach()

            // Update the form inputs:
            this.updateSubjectInput(tagName, tagType, this.addSubjectsInput, true)
            this.updateSubjectInput(tagName, tagType, this.removeSubjectsInput, false)

            // Update the fetched subjects store:
            this.updateFetchedSubjects()
        }
    }

    /**
     * Submits the bulk tagging form and updates the view.
     */
    submitBatch() {
        const url = this.bulkTagger.action

        fetch(url, {
            method: 'post',
            body: new FormData(this.bulkTagger)
        })
            .then(response => {
                if (!response.ok) {
                    new FadingToast('Batch subject update failed. Please try again in a few minutes.').show()
                } else {
                    this.hideTaggingMenu()
                    this.resetTaggingMenu()
                    new FadingToast('Subjects successfully updated.').show()

                    // Update fetched subjects:
                    this.updateFetchedSubjects()
                }
            })
    }

    /**
     * Updates the data structure which contains the fetched works' subjects.
     */
    updateFetchedSubjects() {
        const formData = new FormData(this.bulkTagger)
        const addedTags = JSON.parse(formData.get('tags_to_add') ? formData.get('tags_to_add') : '{}')
        const removedTags = JSON.parse(formData.get('tags_to_remove') ? formData.get('tags_to_remove') : '{}')

        for (const [key, arr] of Object.entries(addedTags)) {
            this.fetchedSubjects.forEach((entry) => {
                if (!entry[key]) {
                    entry[key] = arr
                } else {
                    arr.forEach((tagName) => {
                        if (!entry[key].includes(tagName)) {
                            entry[key].push(tagName)
                        }
                    })
                }
            })
        }

        for (const [key, arr] of Object.entries(removedTags)) {
            this.fetchedSubjects.forEach((entry) => {
                if (!entry[key]) {
                    entry[key] = []
                } else {
                    arr.forEach((tagName) => {
                        const matchIndex = entry[key].indexOf(tagName)
                        if (matchIndex > -1) {
                            entry[key].splice(matchIndex, 1)
                        }
                    })
                }
            })
        }
    }

    /**
     * Clears the bulk tagger form.
     */
    resetTaggingMenu() {
        this.searchInput.value = ''
        this.addSubjectsInput.value = ''
        this.removeSubjectsInput.value = ''
        this.searchResultsContainer.innerHTML = ''
        this.selectedTagsContainer.innerHTML = ''

        this.createSubjectElem.classList.add('hidden')
    }
}
