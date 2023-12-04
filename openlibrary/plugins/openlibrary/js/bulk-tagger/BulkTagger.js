/**
 * Defines functionality related to the ILE's Bulk Tagger tool.
 * @module ile/BulkTagger
 */
import debounce from 'lodash/debounce'

import { MenuOption, MenuOptionState } from './BulkTagger/MenuOption';
import { Tag } from './models/Tag'
import { FadingToast } from '../Toast'

/**
 * Maximum amount of search result to be returned by subject
 * search calls.
 */
const maxDisplayResults = 25;

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
        this.rootElement = bulkTagger

        /**
         * Reference to the Bulk Tagger's subject search box.
         * @member {HTMLInputElement}
         */
        this.searchInput = bulkTagger.querySelector('.subjects-search-input')

        /**
         * Reference to container which holds the selected subject tags.
         * @member {HTMLElement}
         */
        this.selectedTagsContainer = bulkTagger.querySelector('.selected-tag-subjects')

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
         * @member {Map<String, Array<MenuOption>}
         */
        this.menuOptions = new Map()

        /**
         * Array containing OLIDs of each selected work.
         *
         * @member {Array<String>}
         */
        this.selectedWorks = []

        /**
         * Tags staged for adding to all selected works.
         *
         * @member {Array<Tag>}
         */
        this.tagsToAdd = []

        /**
         * Tags staged for removal from all selected works.
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
        const closeFormButton = this.rootElement.querySelector('.close-bulk-tagging-form')
        closeFormButton.addEventListener('click', () => {
            this.hideTaggingMenu()
        })

        // Add input listener to subject search box:
        const debouncedInputChangeHandler = debounce(this.onSearchInputChange.bind(this), 500)
        this.searchInput.addEventListener('input', () => {
            const searchTerm = this.searchInput.value.trim();
            debouncedInputChangeHandler(searchTerm)
        });

        // Prevent redirect on batch subject submission:
        const submitButton = this.rootElement.querySelector('.bulk-tagging-submit')
        submitButton.addEventListener('click', (event) => {
            event.preventDefault()
            this.submitBatch()
        })

        // Add click listeners to "create subject" options:
        const createSubjectButtons = this.rootElement.querySelectorAll('.subject-type-option')
        for (const elem of createSubjectButtons) {
            elem.addEventListener('click', () => this.onCreateTag(new Tag(this.searchInput.value, elem.dataset.tagType)))
        }
    }

    /**
     * Hides the Bulk Tagger.
     */
    hideTaggingMenu() {
        this.rootElement.classList.add('hidden')
    }

    /**
     * Displays the Bulk Tagger.
     */
    showTaggingMenu() {
        this.rootElement.classList.remove('hidden')
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
        this.updateMenuOptions()
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

    /**
     * Creates `MenuOption` affordances for each existing tag that was
     * fetched from the server.
     */
    updateMenuOptions() {
        this.clearMenuOptions()
        // Create SelectedTags for each existing tag:
        for (const workOlid of this.selectedWorks) {
            const existingTagsForWork = this.existingSubjects.get(workOlid)
            for (const tag of existingTagsForWork) {
                if (!this.menuOptions.has(tag.tagName)) {
                    const entry = new MenuOption(tag, MenuOptionState.SOME_TAGGED, 1)
                    this.menuOptions.set(tag.tagName, [entry])
                } else {
                    const existingOptions = this.menuOptions.get(tag.tagName)
                    const matchingEntry = existingOptions.find((option) => option.tag.tagType === tag.tagType)
                    if (matchingEntry) {
                        matchingEntry.worksTagged++
                        if (matchingEntry.worksTagged === this.selectedWorks.length) {
                            matchingEntry.updateWorksTagged(MenuOptionState.ALL_TAGGED)
                        }
                    } else {
                        const newEntry = new MenuOption(tag, MenuOptionState.SOME_TAGGED, 1)
                        existingOptions.push(newEntry)
                    }
                }
            }
        }

        const orderedKeys = [...this.menuOptions.keys()].sort((a, b) => {
            const lowerA = a.toLowerCase()
            const lowerB = b.toLowerCase()
            if (lowerA > lowerB) {
                return -1
            }
            else if (lowerA === lowerB) {
                return 0
            } else {
                return 1
            }
        })

        orderedKeys.forEach((key) => {
            const arr = this.menuOptions.get(key)
            for (const menuOption of arr) {
                menuOption.renderAndAttach(this.selectedTagsContainer)
                menuOption.rootElement.addEventListener('click', () => this.onMenuOptionClick(menuOption))
            }
        })

        // XXX : Update menu options' states based on staged tags
    }

    /**
     * Removes all previously selected tags from the DOM, and empties
     * the `menuOptions` Map.
     */
    clearMenuOptions() {
        this.menuOptions.forEach((arr) => {
            for (const menuOption of arr) {
                menuOption.remove()
            }
        })
        this.menuOptions.clear()
    }

    // XXX : What do I do?
    /**
     * @param {MenuOption} menuOption
     */
    onMenuOptionClick(menuOption) {
        switch (menuOption.optionState) {
        // XXX : Is something else needed here?
        case MenuOptionState.NONE_TAGGED:
        case MenuOptionState.SOME_TAGGED:
            this.tagsToAdd.push(menuOption.tag)
            menuOption.updateWorksTagged(MenuOptionState.ALL_TAGGED)
            break;
        case MenuOptionState.ALL_TAGGED:
            const tagIndex = this.tagsToAdd.findIndex((tag) => (tag.tagName === menuOption.tag.tagName && tag.tagType === menuOption.tag.tagType))
            if (tagIndex > -1) {
                this.tagsToRemove.push(this.tagsToAdd[tagIndex])
                this.tagsToAdd.splice(tagIndex, 1)
            } else {
                this.tagsToRemove.push(menuOption.tag)
            }
            menuOption.updateWorksTagged(MenuOptionState.NONE_TAGGED)
            break;
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
                        const sortedDocs = [...data['docs']].sort((a, b) => {
                            const aNameLower = a.name.toLowerCase()
                            const bNameLower = b.name.toLowerCase()

                            if (aNameLower > bNameLower) {
                                return -1
                            }
                            else if (aNameLower === bNameLower) {
                                return 0
                            } else {
                                return 1
                            }
                        })
                        sortedDocs.forEach(result => {
                            this.createMenuOption(new Tag(result.name, null, result['subject_type']))
                        });
                    }

                    // Update and show create subject affordance
                    this.updateAndShowNewSubjectAffordance(trimmedSearchTerm)
                });
        } else {
            // Hide create subject affordance
            this.createSubjectElem.classList.add('hidden')
        }

        // Hide menu options that do not begin with the search term (case-insensitive)
        this.menuOptions.forEach((options, tagName) => {
            if (tagName.toLowerCase().startsWith(trimmedSearchTerm.toLowerCase())) {
                options.forEach((option) => {
                    option.show()
                })
            } else {
                options.forEach((option) => {
                    option.hide()
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
     * @param {Tag} tag
     */
    createMenuOption(tag) {
        // XXX : Check if menu option exists before creating a new one

        // XXX : Find correct state and works tagged values
        const menuOption = new MenuOption(tag, MenuOptionState.NONE_TAGGED, 0)
        menuOption.renderAndAttach(this.searchResultsContainer)
        // XXX : Use new handler
        menuOption.rootElement.addEventListener('click', () => this.onMenuOptionClick(menuOption))
    }

    // XXX : What do I do?
    /**
     * @param {Tag} tag
     */
    onCreateTag(tag) {
        // XXX : Check if menu option already exists

        this.tagsToAdd.push(tag)
        const menuOption = new MenuOption(tag, MenuOptionState.ALL_TAGGED, this.selectedWorks.length)

        if (this.menuOptions.has(tag.tagName)) {
            this.menuOptions.get(tag.tagName).push(menuOption)
        } else {
            this.menuOptions.set(tag.tagName, [menuOption])
        }

        // Update the UI:
        // XXX : Render, then attach in the correct position
        menuOption.renderAndAttach(this.selectedTagsContainer)
        menuOption.rootElement.addEventListener('click', () => this.onMenuOptionClick(menuOption))

        // Update the fetched subjects store:
        // XXX : Should this be updated now?  I don't think so...
        // this.updateFetchedSubjects()
    }

    /**
     * Submits the bulk tagging form and updates the view.
     */
    submitBatch() {
        const url = this.rootElement.action
        this.prepareFormForSubmission()

        fetch(url, {
            method: 'post',
            body: new FormData(this.rootElement)
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
