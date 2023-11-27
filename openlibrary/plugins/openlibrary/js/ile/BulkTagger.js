/**
 * Defines functionality related to the ILE's Bulk Tagger tool.
 * @module ile/BulkTagger
 */
import { debounce } from '../nonjquery_utils';
import { FadingToast } from '../Toast'

const maxDisplayResults = 25;

const classTypeSuffixes = {
    subject: '--subject',
    person: '--person',
    place: '--place',
    time: '--time'
}

const classTypeSuffixes2 = {
    subjects: '--subject',
    subject_people: '--person',
    subject_places: '--place',
    subject_times: '--time'
}

const subjectTypeMapping = {
    subject: 'subjects',
    person: 'subject_people',
    place: 'subject_places',
    time: 'subject_times'
}

/**
 * Returns the HMTL for the Bulk Tagger component.
 *
 * @returns HTML for the bulk tagging form
 */
export function renderBulkTagger() {
    return `<form action="/tags/bulk_tag_works" method="post" class="bulk-tagging-form">
        <div class="form-header">
            <p>Manage Subjects</p>
            <div class="close-bulk-tagging-form">x</div>
        </div>
        <div class="search-subject-container">
            <input type="text" class="subjects-search-input" placeholder='Filter subjects e.g. Epic'>
        </div>

        <input name="work_ids" value="" type="hidden">
        <input name="tags_to_add" value="" type="hidden">
        <input name="tags_to_remove" value="" type="hidden">
        <div class="selection-container">
            <div class="selected-tag-subjects"></div>
            <div class="subjects-search-results"></div>
        </div>
        <div class="create-new-subject-tag"></div>
        <div class="submit-tags-section">
            <button type="submit" class="bulk-tagging-submit">Submit</button>
        </div>
    </form>`
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
        this.resultsContainer = bulkTagger.querySelector('.subjects-search-results')

        /**
         * Reference to the container which contains the affordance that creates new subjects.
         * @member {HTMLElement}
         */
        this.createSubjectContainer = bulkTagger.querySelector('.create-new-subject-tag')

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
         * @typedef {Object} Tag
         * @property {SelectedTag} selectedTag
         * @property {String} tagType
         * @property {String} tagName
         * @property {Number} taggedWorksCount Number of selected works which share this tag.
         */
        /**
         * @member {Map<String, Array<Tag>>}
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
            debounce(this.fetchSubjects(searchTerm), 500)
        });

        // Prevent redirect on batch subject submission:
        const submitButton = this.bulkTagger.querySelector('.bulk-tagging-submit')
        submitButton.addEventListener('click', (event) => {
            event.preventDefault()
            this.submitBatch()
        })
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

        await this.fetchMissingSubjects(workIds)
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
                selectedTag.renderAndAttach()
                selectedTag.selectedTag.addEventListener('click', () => {
                    if (selectedTag.allWorksTagged) {  // Remove this tag from all selected works:
                        // Add subject to `tags_to_remove`
                        this.updateSubjectInput(tag.tagName, tag.tagType, this.addSubjectsInput, false)
                        this.updateSubjectInput(tag.tagName, tag.tagType, this.removeSubjectsInput, true)

                        // Remove from DOM
                        selectedTag.remove()

                        // Remove reference
                        const selectedEntries = this.selectedTags.get(tag.tagName)
                        const matchIndex = selectedEntries.findIndex((t) => t.tagType === tag.tagType)
                        if (matchIndex > -1) {
                            this.selectedTags.set(tag.tagName, selectedEntries.splice(matchIndex, 1))
                        }
                    } else {  // Add this tag to all selected works:
                        // Add subject to `tags_to_add`
                        this.updateSubjectInput(tag.tagName, tag.tagType, this.addSubjectsInput, true)

                        // Update view
                        selectedTag.updateAllWorksTagged(true)
                    }
                })

                tag.selectedTag = selectedTag
            }
        })
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
    async fetchMissingSubjects(workIds) {
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
     * @param {String} searchTerm
     */
    fetchSubjects(searchTerm) {
        const trimmedSearchTerm = searchTerm.trim()
        this.resultsContainer.innerHTML = '';
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
                    this.createSubjectContainer.innerHTML = '';
                    // create new subject option
                    this.createNewSubjectOption(trimmedSearchTerm);
                });
        }
    }

    // XXX : Add HTML to renderBulkTagger() and remove this function
    /**
     * Creates, hydrates, and attaches a new "create subject" affordance.
     *
     * @param {String} subjectName
     */
    createNewSubjectOption(subjectName) {
        const div = document.createElement('div');
        div.className = 'search-subject-row-name';

        div.className += ' search-subject-row-name-create';
        const p = document.createElement('div');
        p.innerHTML = `Create new subject <strong>'${subjectName}'</strong> with type:`;
        p.className = 'search-subject-row-name-create-p';
        div.appendChild(p);

        const subjectTypeOptions = ['subject', 'person', 'place', 'time'];
        const select = document.createElement('div');
        select.className = 'search-subject-row-name-create-select';
        subjectTypeOptions.forEach((option) => {
            const optionElement = document.createElement('div');
            optionElement.className = 'subject-type-option';
            optionElement.textContent = option;
            optionElement.classList.add(`subject-type-option${classTypeSuffixes[option]}`)
            optionElement.addEventListener('click', () => this.handleSelectSubject(subjectName, option));

            select.appendChild(optionElement);
        });
        div.appendChild(select);

        this.createSubjectContainer.appendChild(div)
    }

    /**
     * Creates, hydrates, and attaches a new search result affordance.
     *
     * @param {String} subjectName The subject's name.
     * @param {String} subjectType The subject's type.
     * @param {Number} workCount Number of works that are tagged with this subject.
     */
    createSearchResult(subjectName, subjectType, workCount) {
        const div = document.createElement('div');
        div.className = 'search-subject-row';

        const name = document.createElement('div');
        name.className = 'search-subject-row-name';
        name.innerText = subjectName;
        div.appendChild(name);

        const subjectInfoDiv = document.createElement('div');
        subjectInfoDiv.className = 'search-subject-row-subject-info';
        const tag = document.createElement('div');
        tag.innerText = subjectType;
        tag.className = 'search-subject-type';
        tag.classList.add(`subject-type-option${classTypeSuffixes[subjectType]}`);
        subjectInfoDiv.appendChild(tag);

        const workCountDiv = document.createElement('div');
        if (workCount > 1000) {
            workCountDiv.innerText = 'works: 1000+';
        } else {
            workCountDiv.innerText = `works: ${workCount}`;
        }
        workCountDiv.className = 'search-subject-work-count';
        subjectInfoDiv.appendChild(workCountDiv);

        div.appendChild(subjectInfoDiv);
        div.addEventListener('click', () => this.handleSelectSubject(subjectName, subjectType));

        this.resultsContainer.appendChild(div);
    }

    /**
     * Adds subject to selected subject container and updates the batch update form.
     *
     * @param {String} name
     * @param {String} rawSubjectType
     */
    handleSelectSubject(name, rawSubjectType) {
        const subjectType = subjectTypeMapping[rawSubjectType]

        const existingSubjects = JSON.parse(this.addSubjectsInput.value === '' ? '{}' : this.addSubjectsInput.value);
        existingSubjects[subjectType] = existingSubjects[subjectType] || [];

        // The same subject can be added twice by:
        // 1. Adding an existing subject
        // 2. Creating a new subject using an existing subject's name
        const isTagged = existingSubjects[subjectType].includes(name);
        if (!isTagged) {  // Check for duplicate subjects
            existingSubjects[subjectType].push(name);

            const newTag = document.createElement('div');
            newTag.innerText = name;
            newTag.className = 'new-selected-subject-tag';
            newTag.classList.add(`subject-type-option${classTypeSuffixes[rawSubjectType]}`);
            const removeButton = document.createElement('span');
            removeButton.innerText = 'X';
            removeButton.className = 'remove-selected-subject';
            removeButton.addEventListener('click', () => this.handleRemoveSubject(name, subjectType, newTag));
            newTag.appendChild(removeButton);

            this.selectedTagsContainer.appendChild(newTag);

            this.addSubjectsInput.setAttribute('value', JSON.stringify(existingSubjects));
        }
    }

    /**
     * Updates batch update form and removes given tag element from the selected tags container.
     *
     * @param {String} name
     * @param {String} subjectType
     * @param {HTMLElement} tagElement
     */
    handleRemoveSubject(name, subjectType, tagElement) {
        const existingSubjects = JSON.parse(this.addSubjectsInput.value === '' ? '{}' : this.addSubjectsInput.value);
        existingSubjects[subjectType] = existingSubjects[subjectType] || [];

        existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

        tagElement.remove();

        this.addSubjectsInput.setAttribute('value', JSON.stringify(existingSubjects));
    }

    /**
     * Submits the bulk tagging form and updates the view.
     */
    submitBatch() {
        const url = this.bulkTagger.action
        const formData = new FormData(this.bulkTagger)

        fetch(url, {
            method: 'post',
            body: formData
        })
            .then(response => {
                if (!response.ok) {
                    new FadingToast('Batch subject update failed. Please try again in a few minutes.').show()
                } else {
                    this.hideTaggingMenu()
                    this.resetTaggingMenu()
                    new FadingToast('Subjects successfully updated.').show()

                    // Update fetched subjects:
                    const additions = JSON.parse(formData.get('tags_to_add') ? formData.get('tags_to_add') : '{}')
                    const subtractions = JSON.parse(formData.get('tags_to_remove') ? formData.get('tags_to_remove') : '{}')
                    this.updateFetchedSubjects(additions, subtractions)
                }
            })
    }

    updateFetchedSubjects(addedTags, removedTags) {
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
        this.resultsContainer.innerHTML = ''
        this.createSubjectContainer.innerHTML = ''
        this.selectedTagsContainer.innerHTML = ''
    }
}

/**
 * Affordance that displays a tag, and whether all selected works share the tag.
 *
 * Affordance has two states:
 *   1. Indeterminate : at least one, but not all, selected works share the given tag.
 *   2. All works tagged : All works have the given tag.
 *
 * Behavior on click:
 *   1. When the inital state is "Indeterminate", the subject is added to the `tags_to_add` form input. State changes to "All works tagged"
 *   2. When initial state is "All works tagged", the subject is added to the `tags_to_remove` form input. This row is removed from the DOM.
 *
 * To support bloom filtering, the visiblity of this affordance can be toggled.
 */
class SelectedTag {

    /**
     * @param {String} tagType
     * @param {String} tagName
     * @param {boolean} allWorksTagged
     */
    constructor(tagType, tagName, allWorksTagged) {
        /**
         * Reference to the root element of this SelectedTag.
         *
         * @member {HTMLElement}
         */
        this.selectedTag

        /**
         * Type of the tag represented by this affordance.
         *
         * @member {String}
         */
        this.tagType = tagType

        /**
         * Name of the tag represented by this affordance.
         *
         * @member {String}
         */
        this.tagName = tagName

        /**
         * `true` if all selected works share the same tag.
         *
         * @member {boolean}
         */
        this.allWorksTagged = allWorksTagged

        /**
         * `true` if this component is visible on the page.
         *
         * @member {boolean}
         */
        this.isVisible = true

        /**
         * Reference to the root element of this SelectedTag.
         *
         * @member {HTMLElement}
         */
        this.selectedTag

        /**
         * Lowercase representation of the `tagName`.
         *
         * @readonly
         * @member {String}
         */
        this.LOWERCASE_TAG_NAME = tagName.toLowerCase()
    }

    /**
     * Renders a new SelectedTag, and attaches it to the DOM.
     */
    renderAndAttach() {
        const parentElem = document.createElement('div')
        parentElem.classList.add('selected-tag')
        const markup = `<span class="selected-tag__status selected-tag__status--${this.allWorksTagged ? 'all-tagged' : 'some-tagged'}"></span>
            <span class="selected-tag__type selected-tag__type${classTypeSuffixes2[this.tagType]}"></span>
            <span class="selected-tag__name">${this.tagName}</span>`
        parentElem.innerHTML = markup

        const selectedTagsElem = document.querySelector('.selected-tag-subjects')
        selectedTagsElem.prepend(parentElem)
        this.selectedTag = parentElem
    }

    /**
     * Removes this SelectedTag from the DOM.
     */
    remove() {
        this.selectedTag.remove()
    }

    /**
     * Updates value of `this.allWorksTagged` and updates the view.
     *
     * @param {boolean} allWorksTagged `true` if all selected works share this tag.
     */
    updateAllWorksTagged(allWorksTagged) {
        this.allWorksTagged = allWorksTagged
        const statusIndicator = this.selectedTag.querySelector('.selected-tag__status')
        if (allWorksTagged) {
            statusIndicator.classList.remove('selected-tag__status--some-tagged')
            statusIndicator.classList.add('selected-tag__status--all-tagged')
        } else {
            statusIndicator.classList.remove('selected-tag__status--all-tagged')
            statusIndicator.classList.add('selected-tag__status--some-tagged')
        }
    }

    /**
     * Hides this SelectedTag.
     */
    hide() {
        this.selectedTag.classList.add('hidden')
        this.isVisible = false
    }

    /**
     * Shows this SelectedTag.
     */
    show() {
        this.selectedTag.classList.remove('hidden')
        this.isVisible = true
    }

    // XXX : Useful and needed?
    /**
     * Toggles visibility of this SelectedTag.
     */
    toggleVisibility() {
        this.selectedTag.classList.toggle('hidden')
        this.isVisible = !this.isVisible
    }

    /**
     * Checks if the tag name begins with the given string when doing a case insensitive
     * comparison.
     *
     * @param {String} searchString
     * @returns {boolean} `true` if the tag name starts with the given string (case insensitive)
     */
    tagNameStartsWith(searchString) {
        return this.LOWERCASE_TAG_NAME.startsWith(searchString.toLowerCase())
    }
}
