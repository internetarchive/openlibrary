/**
 * Defines functionality related to the ILE's Bulk Tagger tool.
 * @module ile/BulkTagger
 */
import debounce from 'lodash/debounce'

import { MenuOption, MenuOptionState } from './BulkTagger/MenuOption';
import { SortedMenuOptionContainer } from './BulkTagger/SortedMenuOptionContainer';
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
         * Menu option container that holds options for staged tags and tags
         * that already exist on one or more selected works.
         *
         * @member {SortedMenuOptionContainer}
         */
        this.selectedOptionsContainer

        /**
         * Menu option container that holds options representing search results.
         *
         * @member {SortedMenuOptionContainer}
         */
        this.searchResultsOptionsContainer

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
         * Reference to the bulk tagger form's submit button.
         *
         * @member {HTMLButtonElement}
         */
        this.submitButton = this.rootElement.querySelector('.bulk-tagging-submit')

        /**
         * Stores works' subjects that have been fetched from the server.
         *
         * Keys to the map are work IDs.
         * @member {Map<String, Array<Tag>>}
         */
        this.existingSubjects = new Map()

        /**
         * Stores arrays of selected menu options.
         *
         * Tag names are the keys to this map.  Corresponding arrays
         * will contain menu options having the same name, but different
         * types.
         *
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
     * Initialized the menu option containers, and adds event listeners to the Bulk Tagger.
     */
    initialize() {
        // Create sorted menu option containers:
        this.selectedOptionsContainer = new SortedMenuOptionContainer(this.rootElement.querySelector('.selected-tag-subjects'))
        this.searchResultsOptionsContainer = new SortedMenuOptionContainer(this.rootElement.querySelector('.subjects-search-results'))

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
        this.submitButton.addEventListener('click', (event) => {
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
        this.rootElement.dispatchEvent(new CustomEvent('option-hidden'))
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
        this.showLoadingIndicator()

        this.selectedWorks = workIds

        await this.fetchSubjectsForWorks(workIds)
        this.updateMenuOptions()

        this.hideLoadingIndicator()
    }

    /**
     * Hides all menu options and shows a loading indicator.
     */
    showLoadingIndicator() {
        const menuOptionContainer = this.rootElement.querySelector('.selection-container')
        menuOptionContainer.classList.add('hidden')
        const loadingIndicator = this.rootElement.querySelector('.loading-indicator')
        loadingIndicator.classList.remove('hidden')
    }

    /**
     * Hides the loading indicator and shows all menu options.
     */
    hideLoadingIndicator() {
        const loadingIndicator = this.rootElement.querySelector('.loading-indicator')
        loadingIndicator.classList.add('hidden')
        const menuOptionContainer = this.rootElement.querySelector('.selection-container')
        menuOptionContainer.classList.remove('hidden')
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
                // XXX : Handle failures
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
     * Creates `MenuOption` affordances for all staged tags, and each existing tag that
     * was fetched from the server.
     */
    updateMenuOptions() {
        this.selectedOptionsContainer.clear()

        // Add staged tags first, then add all other missing subjects.
        // This order prevents unnecessary state mangement steps.

        // Create menu options for each staged tag:
        this.tagsToAdd.forEach((tag) => {
            const menuOption = new MenuOption(tag, MenuOptionState.ALL_TAGGED, this.selectedWorks.length)
            menuOption.initialize()
            this.selectedOptionsContainer.add(menuOption)
        })

        this.tagsToRemove.forEach((tag) => {
            const menuOption = new MenuOption(tag, MenuOptionState.NONE_TAGGED, 0)
            menuOption.initialize()
            this.selectedOptionsContainer.add(menuOption)
        })

        // Create menu options for each existing tag:
        const stagedMenuOptions = []
        for (const workOlid of this.selectedWorks) {
            const existingTagsForWork = this.existingSubjects.get(workOlid)
            for (const tag of existingTagsForWork) {

                // Does an option for this tag already exist in the container?
                if (!this.selectedOptionsContainer.containsOptionWithTag(tag)) {

                    // Have we already created and staged a menu option for this tag?
                    const stagedOption = stagedMenuOptions.find((option) => option.tag.equals(tag))
                    if (stagedOption) {
                        stagedOption.taggedWorksCount++
                        if (stagedOption.taggedWorksCount === this.selectedWorks.length) {
                            stagedOption.updateMenuOptionState(MenuOptionState.ALL_TAGGED)
                        }
                    } else {
                        const state = this.selectedWorks.length === 1 ? MenuOptionState.ALL_TAGGED : MenuOptionState.SOME_TAGGED
                        const newOption = new MenuOption(tag, state, 1)
                        newOption.initialize()
                        stagedMenuOptions.push(newOption)
                    }
                }
            }
        }

        stagedMenuOptions.forEach((option) => option.rootElement.addEventListener('click', () => this.onMenuOptionClick(option)))
        this.selectedOptionsContainer.add(...stagedMenuOptions)
    }

    /**
     * Click handler for menu options.
     *
     * Changes the menu option's state, and stages the option's tag
     * for addition or removal.
     *
     * @param {MenuOption} menuOption The clicked menu option
     */
    onMenuOptionClick(menuOption) {
        let stagedTagIndex
        switch (menuOption.optionState) {
        case MenuOptionState.NONE_TAGGED:
            stagedTagIndex = this.tagsToRemove.findIndex((tag) => (tag.tagName === menuOption.tag.tagName && tag.tagType === menuOption.tag.tagType))
            if (stagedTagIndex > -1) {
                this.tagsToRemove.splice(stagedTagIndex, 1)
            }
            this.tagsToAdd.push(menuOption.tag)
            menuOption.updateMenuOptionState(MenuOptionState.ALL_TAGGED)
            break
        case MenuOptionState.SOME_TAGGED:
            this.tagsToAdd.push(menuOption.tag)
            menuOption.updateMenuOptionState(MenuOptionState.ALL_TAGGED)
            break
        case MenuOptionState.ALL_TAGGED:
            stagedTagIndex = this.tagsToAdd.findIndex((tag) => (tag.tagName === menuOption.tag.tagName && tag.tagType === menuOption.tag.tagType))
            if (stagedTagIndex > -1) {
                this.tagsToAdd.splice(stagedTagIndex, 1)
            }
            this.tagsToRemove.push(menuOption.tag)
            menuOption.updateMenuOptionState(MenuOptionState.NONE_TAGGED)
            break
        }

        menuOption.stage()
        this.updateSubmitButtonState()
    }

    /**
     * Disables or enables form submission button.
     *
     * Button is enabled if there are any tags staged for submission.
     * Otherwise, the button will be disabled.
     */
    updateSubmitButtonState() {
        const stagedTagCount = this.tagsToAdd.length + this.tagsToRemove.length

        if (stagedTagCount > 0) {
            this.submitButton.removeAttribute('disabled')
        } else {
            this.submitButton.setAttribute('disabled', 'true')
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
        // Remove search results that are not selected:
        const resultsToRemove = this.searchResultsOptionsContainer.sortedMenuOptions.filter((option) => option.optionState !== MenuOptionState.ALL_TAGGED)
        this.searchResultsOptionsContainer.remove(...resultsToRemove)

        // Hide menu options that do not begin with the search term (case-insensitive)
        const trimmedSearchTerm = searchTerm.trim()

        const allOptions = this.selectedOptionsContainer.sortedMenuOptions.concat(this.searchResultsOptionsContainer.sortedMenuOptions)
        allOptions.forEach((option) => {
            if (option.tag.tagName.toLowerCase().startsWith(trimmedSearchTerm.toLowerCase())) {
                option.show()
            } else {
                option.hide()
            }
        })

        if (trimmedSearchTerm !== '') {  // Perform search:
            fetch(`/search/subjects.json?q=${searchTerm}&limit=${maxDisplayResults}`)
                .then((response) => response.json())
                .then((data) => {
                    if (data['docs'].length !== 0) {
                        for (const obj of data['docs']) {
                            const tag = new Tag(obj.name, null, obj['subject_type'])

                            if (!this.selectedOptionsContainer.containsOptionWithTag(tag) && !this.searchResultsOptionsContainer.containsOptionWithTag(tag)) {
                                const menuOption = this.createSearchMenuOption(tag)
                                this.searchResultsOptionsContainer.add(menuOption)
                            }
                        }
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
     * Creates, hydrates, and returns a new menu option based on a search result.
     *
     * In addition to the usual click listener, the newly created element will have an
     * `option-hidden` event handler, which will move any selected menu option to the
     * selected options container whenever the menu option is hidden.  This is done to
     * maintain the correct menu option ordering when search results are updated.
     *
     * Precondition: Menu option representing the given tag is not attached to the DOM.
     *
     * @param {Tag} tag
     * @returns {MenuOption} A menu option representing the given tag
     */
    createSearchMenuOption(tag) {
        const menuOption = new MenuOption(tag, MenuOptionState.NONE_TAGGED, 0)
        menuOption.initialize()
        menuOption.rootElement.addEventListener('click', () => this.onMenuOptionClick(menuOption))
        menuOption.rootElement.addEventListener('option-hidden', () => {
            // Move to selected menu options container if selected and hidden
            if (menuOption.optionState === MenuOptionState.ALL_TAGGED) {
                if (menuOption.rootElement.parentElement === this.searchResultsOptionsContainer.rootElement) {
                    this.searchResultsOptionsContainer.remove(menuOption)
                    this.selectedOptionsContainer.add(menuOption)
                }
            }
        })

        return menuOption
    }

    /**
     * Adds a menu option representing the given tag to the selected options container.
     *
     * If the container already has a menu option for the given tag, this method returns
     * without making any changes.
     *
     * If a corresponding menu option is found in the search results container, that menu
     * option is added to the selected options container.  Otherwise, a new menu option is
     * created, hydrated, and added to the container.
     *
     * @param {Tag} tag
     */
    onCreateTag(tag) {
        // Return if menu option already exists in selected options:
        if (this.selectedOptionsContainer.containsOptionWithTag(tag)) {
            return
        }

        // Stage tag for addition:
        this.tagsToAdd.push(tag)

        // If tag is represented by a search result object, update existing object
        // instead of creating a new one:
        const existingOption = this.searchResultsOptionsContainer.findByTag(tag)
        if (existingOption) {
            this.searchResultsOptionsContainer.remove(existingOption)
            this.selectedOptionsContainer.add(existingOption)
            existingOption.taggedWorksCount = this.selectedWorks.length
            existingOption.updateMenuOptionState(MenuOptionState.ALL_TAGGED)
        } else {
            const menuOption = new MenuOption(tag, MenuOptionState.ALL_TAGGED, this.selectedWorks.length)
            menuOption.initialize()
            menuOption.rootElement.addEventListener('click', () => this.onMenuOptionClick(menuOption))
            this.selectedOptionsContainer.add(menuOption)
        }

        this.updateSubmitButtonState()
    }

    /**
     * Submits the bulk tagging form and updates the view.
     */
    submitBatch() {


        // Disable button
        this.submitButton.disabled = true;

        this.submitButton.textContent = 'Submitting...';

        const url = this.rootElement.action
        this.prepareFormForSubmission()

        fetch(url, {
            method: 'post',
            body: new FormData(this.rootElement)
        })
            .then(response => {
                if (!response.ok) {
                    this.submitButton.disabled = false;
                    this.submitButton.textContent = 'Submit';
                    new FadingToast('Batch subject update failed. Please try again in a few minutes.').show();
                } else {
                    this.hideTaggingMenu();
                    new FadingToast('Subjects successfully updated.').show()
                    this.submitButton.textContent = 'Submit';
                    this.updateFetchedSubjects();
                    this.resetTaggingMenu();
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
        this.selectedOptionsContainer.clear()
        this.searchResultsOptionsContainer.clear()

        this.createSubjectElem.classList.add('hidden')

        this.tagsToAdd = []
        this.tagsToRemove = []
    }
}
