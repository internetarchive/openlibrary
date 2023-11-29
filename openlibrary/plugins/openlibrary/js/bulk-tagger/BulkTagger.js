/**
 * Defines functionality related to the ILE's Bulk Tagger tool.
 * @module ile/BulkTagger
 */
import { SelectedTag } from './BulkTagger/SelectedTag';
import { Tag, subjectTypeMapping } from './models/Tag'
import { debounce } from '../nonjquery_utils';
import { FadingToast } from '../Toast'

const maxDisplayResults = 25;

const classTypeSuffixes = {
    subject: '--subject',
    person: '--person',
    place: '--place',
    time: '--time'
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
         * Stores works' subjects that have been fetched from the server.
         *
         * Keys to the map are work IDs.
         * @member {Map<String, Array<Tag>>}
         */
        this.existingSubjects = new Map()

        /**
         * @typedef {Object} SelectedTagEntry
         * @property {SelectedTag} selectedTag
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

        /**
         * Tags queued for adding to all selected works.
         *
         * @member {Array<Tag>}
         */
        this.tagsToAdd = []

        /**
         * Tags queued for removal from all selected works.
         *
         * @member {Array<Tag>}
         */
        this.tagsToRemove = []
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
     * Stores given array in `selectedWorks`, fetches the
     * existing tags for each given work, and updates the view with
     * the existing tags.
     *
     * @param {Array<String>} workIds
     */
    async updateWorks(workIds) {
        this.selectedWorks = workIds

        await this.fetchSubjectsForWorks(workIds)
        this.updateSelectedTags()
    }

    /**
     * Fetches and stores subject information for the given work OLIDs.
     *
     * If we already have fetched the data for a work ID, we do not fetch it
     * again.
     * @param {Array<String>} workIds
     */
    async fetchSubjectsForWorks(workIds) {
        const worksWithMissingSubjects = workIds.filter(id => !this.existingSubjects.has(id))

        await Promise.all(worksWithMissingSubjects.map(async (id) => {
            // XXX : Too many network requests --- use bulk search if/when it is available
            await this.fetchWork(id)
                .then(response => response.json())
                .then(data => {
                    const entry = {
                        subjects: data.subjects || [],
                        subject_people: data.subject_people || [],
                        subject_places: data.subject_places || [],
                        subject_times: data.subject_times || []
                    }
                    if (!this.existingSubjects.has(id)) {
                        this.existingSubjects.set(id, [])
                    }
                    // `key` is the type, `value` is the array of tag names
                    for (const [key, value] of Object.entries(entry)) {
                        for (const tagName of value) {
                            this.existingSubjects.get(id).push(new Tag(tagName, key))
                        }
                    }
                })
        }))
    }

    updateSelectedTags() {
        // Create SelectedTags for each existing tag:
        this.selectedTags.clear()
        for (const workOlid of this.selectedWorks) {
            const existingTagsForWork = this.existingSubjects.get(workOlid)
            for (const tag of existingTagsForWork) {
                if (!this.selectedTags.has(tag.tagName)) {
                    const entry = {
                        selectedTag: new SelectedTag(tag, false),
                        taggedWorksCount: 1
                    }
                    this.selectedTags.set(tag.tagName, [entry])
                } else {
                    const existingEntries = this.selectedTags.get(tag.tagName)
                    const matchingEntry = existingEntries.find((entry) => entry.selectedTag.tagType === tag.tagType)
                    if (matchingEntry) {
                        matchingEntry.taggedWorksCount++
                    } else {
                        const newEntry = {
                            selectedTag: new SelectedTag(tag, false),
                            taggedWorksCount: 1
                        }
                        existingEntries.push(newEntry)
                    }
                }
            }
        }

        // Update SelectedTags if all works have the same tag, then show affordance:
        this.selectedTags.forEach((arr) => {
            for (const entry of arr) {
                const allWorksTagged = entry.taggedWorksCount === this.selectedWorks.length
                entry.selectedTag.allWorksTagged = allWorksTagged
                if (allWorksTagged) {
                    this.tagsToAdd.push(entry.selectedTag.tag)
                }
                entry.selectedTag.renderAndAttach()
                entry.selectedTag.selectedTag.addEventListener('click', () => this.onSelectedTagClick(entry))
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
            const tagIndex = this.tagsToAdd.findIndex((tag) => (tag.tagName === selectedTag.tagName && tag.tagType === selectedTag.tagType))
            this.tagsToRemove.push(this.tagsToAdd[tagIndex])
            this.tagsToAdd.splice(tagIndex, 1)

            // Remove from DOM
            selectedTag.remove()

            // Remove reference
            const selectedEntries = this.selectedTags.get(selectedTag.tagName)
            const matchIndex = selectedEntries.findIndex((t) => t.tagType === selectedTag.tagType)
            if (matchIndex > -1) {
                this.selectedTags.set(selectedTag.tagName, selectedEntries.splice(matchIndex, 1))
            }
        } else {  // Add this tag to all selected works:
            // Queue tag for adding to all selected works
            const tag = selectedTag.tag
            this.tagsToAdd.push(tag)

            // Update view
            selectedTag.updateAllWorksTagged(true)
        }
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
                                this.createSearchResult(result.name, result['subject_type'], result['work_count']);
                            });
                    }

                    // Update and show create subject affordance
                    this.updateAndShowNewSubjectAffordance(trimmedSearchTerm)
                });
        } else {
            // Hide create subject affordance
            this.createSubjectElem.classList.add('hidden')
        }

        // Hide selected tags that do not begin with the search term (case-insensitive)
        this.selectedTags.forEach((tagEntries, tagName) => {
            if (tagName.toLowerCase().startsWith(trimmedSearchTerm.toLowerCase())) {
                tagEntries.forEach((entry) => {
                    entry.selectedTag.show()
                })
            } else {
                tagEntries.forEach((entry) => {
                    entry.selectedTag.hide()
                })
            }
        })
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
        const entryExists = this.selectedTags.has(tagName) && this.selectedTags.get(tagName).some((entry) => entry.selectedTag.tagType === tagType)

        if (!entryExists) {
            // Create new selected tag:
            const newTag = new Tag(tagName, tagType)
            this.tagsToAdd.push(newTag)

            const selectedTag = new SelectedTag(newTag, true)
            const selectedTagEntry = {
                selectedTag: selectedTag,
                taggedWorksCount: this.selectedWorks.length
            }

            if (this.selectedTags.has(tagName)) {
                this.selectedTags.get(tagName).push(selectedTagEntry)
            } else {
                this.selectedTags.set(tagName, [selectedTagEntry])
            }

            // Update the UI:
            selectedTag.renderAndAttach()

            // Update the fetched subjects store:
            this.updateFetchedSubjects()
        }
    }

    /**
     * Submits the bulk tagging form and updates the view.
     */
    submitBatch() {
        const url = this.bulkTagger.action
        this.prepareFormForSubmission()

        fetch(url, {
            method: 'post',
            body: new FormData(this.bulkTagger)
        })
            .then(response => {
                if (!response.ok) {
                    new FadingToast('Batch subject update failed. Please try again in a few minutes.').show()
                } else {
                    this.hideTaggingMenu()
                    new FadingToast('Subjects successfully updated.').show()

                    // Update fetched subjects:
                    this.updateFetchedSubjects()
                    this.resetTaggingMenu()
                }
            })
    }

    /**
     * Populates the form's hidden inputs.
     *
     * Expected to be called just before the form is submitted.
     */
    prepareFormForSubmission() {
        this.selectedWorksInput.value = this.selectedWorks.join(',')

        const addSubjectsValue = {
            subjects: this.findMatches(this.tagsToAdd, 'subjects'),
            subject_people: this.findMatches(this.tagsToAdd, 'subject_people'),
            subject_places: this.findMatches(this.tagsToAdd, 'subject_places'),
            subject_times: this.findMatches(this.tagsToAdd, 'subject_times')
        }
        this.addSubjectsInput.value = JSON.stringify(addSubjectsValue)

        const removeSubjectsValue = {
            subjects: this.findMatches(this.tagsToRemove, 'subjects'),
            subject_people: this.findMatches(this.tagsToRemove, 'subject_people'),
            subject_places: this.findMatches(this.tagsToRemove, 'subject_places'),
            subject_times: this.findMatches(this.tagsToRemove, 'subject_times')
        }
        this.removeSubjectsInput.value = JSON.stringify(removeSubjectsValue)
    }

    /**
     * Filters tags that match the given type, and returns the names of
     * each filtered tag.
     *
     * @param {Array<Tag>} tags Tags to be filtered
     * @param {String} type Snake-cased tag type
     * @returns {Array<String>} The names of the filtered tags
     */
    findMatches(tags, type) {
        const results = []
        tags.reduce((_acc, tag) => {
            if (tag.tagType === type) {
                results.push(tag.tagName)
            }
        }, [])
        return results
    }

    /**
     * Updates the data structure which contains the fetched works' subjects.
     *
     * Meant to be called after the form has been submitted, but before the
     * `resetTaggingMenu` call is made.
     */
    updateFetchedSubjects() {
        for (const tag of this.tagsToAdd) {
            this.existingSubjects.forEach((tags) => {
                const tagExists = tags.findIndex((t) => t.tagName === tag.tagName && t.tagType === tag.tagType) > -1
                if (!tagExists) {
                    tags.push(tag)
                }
            })
        }

        for (const tag of this.tagsToRemove) {
            this.existingSubjects.forEach((tags) => {
                const tagIndex = tags.findIndex((t) => t.tagName === tag.tagName && t.tagType === tag.tagType)
                const tagExists = tagIndex > -1
                if (tagExists) {
                    tags.splice(tagIndex, 1)
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

        this.tagsToAdd = []
        this.tagsToRemove = []
    }
}
