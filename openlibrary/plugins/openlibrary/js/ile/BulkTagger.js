/**
 * Defines functionality related to the ILE's Bulk Tagger tool.
 * @module ile/BulkTagger
 */
import { debounce } from '../nonjquery_utils';
import { FadingToast } from '../Toast'

const maxDisplayResults = 25;

const subjectTypeClasses = {
    subject: 'subject-type-option--subject',
    person: 'subject-type-option--person',
    place: 'subject-type-option--place',
    time: 'subject-type-option--time'
};

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
        this.hiddenSubjectInput = bulkTagger.querySelector('.tag-subjects')
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
                                const isSelected = this.hiddenSubjectInput.value.includes(result.name);
                                this.createSearchResult(result.name, result['subject_type'], result['work_count'], isSelected);
                            });
                    }
                    this.createSubjectContainer.innerHTML = '';
                    // create new subject option
                    this.createNewSubjectOption(trimmedSearchTerm);
                });
        }
    }

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
            optionElement.classList.add(subjectTypeClasses[option])
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
        tag.classList.add(subjectTypeClasses[subjectType]);
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

        const existingSubjects = JSON.parse(this.hiddenSubjectInput.value === '' ? '{}' : this.hiddenSubjectInput.value);
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
            newTag.classList.add(subjectTypeClasses[rawSubjectType]);
            const removeButton = document.createElement('span');
            removeButton.innerText = 'X';
            removeButton.className = 'remove-selected-subject';
            removeButton.addEventListener('click', () => this.handleRemoveSubject(name, subjectType, newTag));
            newTag.appendChild(removeButton);

            this.selectedTagsContainer.appendChild(newTag);

            this.hiddenSubjectInput.setAttribute('value', JSON.stringify(existingSubjects));
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
        const existingSubjects = JSON.parse(this.hiddenSubjectInput.value === '' ? '{}' : this.hiddenSubjectInput.value);
        existingSubjects[subjectType] = existingSubjects[subjectType] || [];

        existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

        tagElement.remove();

        this.hiddenSubjectInput.setAttribute('value', JSON.stringify(existingSubjects));
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
                    // Deselect search items:
                    window.ILE.reset()
                }
            })
    }

    /**
     * Clears the bulk tagger form.
     */
    resetTaggingMenu() {
        this.searchInput.value = ''
        this.hiddenSubjectInput.value = ''
        this.resultsContainer.innerHTML = ''
        this.createSubjectContainer.innerHTML = ''
        this.selectedTagsContainer.innerHTML = ''
    }
}
