import { debounce } from './nonjquery_utils';
import { FadingToast } from './Toast'

const subjectTypeColors = {
    subject: 'subject-blue',
    person: 'subject-purple',
    place: 'subject-red',
    time: 'subject-yellow'
};

function addSubjectTypeBackgroundColor(element, subjectType) {
    element.classList.add(subjectTypeColors[subjectType]);
}

function parseSubjectType(subjectType) {
    switch (subjectType) {
    case 'subject':
        return 'subjects';
    case 'person':
        return 'subject_people';
    case 'place':
        return 'subject_places';
    case 'time':
        return 'subject_times';
    }
}

function newSubjectRowHtml(subjectName, subjectType, workCount) {
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
    addSubjectTypeBackgroundColor(tag, subjectType)
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
    div.addEventListener('click', () => handleSelectSubject(subjectName, subjectType));

    return div;
}

function newCreateSubjectOption(subjectName) {
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
        addSubjectTypeBackgroundColor(optionElement, option)

        optionElement.addEventListener('click', () => handleSelectSubject(subjectName, option, null));

        select.appendChild(optionElement);
    });
    div.appendChild(select);

    return div
}

const maxDisplayResults = 25;

function fetchSubjects(searchTerm) {
    const resultsContainer = document.querySelector('.subjects-search-results');
    const hiddenInput = document.querySelector('.tag-subjects');
    resultsContainer.innerHTML = '';
    fetch(`/search/subjects.json?q=${searchTerm}&limit=${maxDisplayResults}`)
        .then((response) => response.json())
        .then((data) => {
            if (data['docs'].length !== 0) {
                data['docs']
                    .forEach(result => {
                        const isSelected = hiddenInput.value.includes(result.name);

                        const div = newSubjectRowHtml(result.name, result['subject_type'], result['work_count'], isSelected);
                        resultsContainer.appendChild(div);
                    });
            }
            const createSubjectContainer = document.querySelector('.create-new-subject-tag');
            createSubjectContainer.innerHTML = '';
            if (searchTerm !== '') { // create new subject option
                const div = newCreateSubjectOption(searchTerm);
                createSubjectContainer.appendChild(div);
            }
        });
}

const debouncedFetchSubjects = debounce(fetchSubjects, 500);

export function initSubjectTagsSearchBox() {
    const searchInput = document.querySelector('.subjects-search-input');
    document.querySelector('.close-bulk-tagging-form').addEventListener('click', hideTaggingMenu)
    searchInput.addEventListener('input', function () {
        const searchTerm = this.value.trim();
        debouncedFetchSubjects(searchTerm);
    });

    const submitButton = document.querySelector('.bulk-tagging-submit')
    submitButton.addEventListener('click', (event) => {
        event.preventDefault()
        submitBatch()
    })
}

function submitBatch() {
    const bulkTaggingForm = document.querySelector('.bulk-tagging-form')
    const url = bulkTaggingForm.action
    const formData = new FormData(bulkTaggingForm)

    fetch(url, {
        method: 'post',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                new FadingToast('Batch subject update failed. Please try again in a few minutes.').show()
            } else {
                hideTaggingMenu()
                resetTaggingMenu()
                new FadingToast('Subjects successfully updated.').show()
                // Deselect search items:
                window.ILE.reset()
            }
        })
}

function handleSelectSubject(name, rawSubjectType) {
    const hiddenInput = document.querySelector('.tag-subjects');
    const selectedTagsContainer = document.querySelector('.selected-tag-subjects');
    const subjectType = parseSubjectType(rawSubjectType);

    const existingSubjects = JSON.parse(hiddenInput.value === '' ? '{}' : hiddenInput.value);
    existingSubjects[subjectType] = existingSubjects[subjectType] || [];

    const isTagged = existingSubjects[subjectType].includes(name);

    if (!isTagged) {
        existingSubjects[subjectType].push(name);

        const newTag = document.createElement('div');
        newTag.innerText = name;
        newTag.dataset.name = `${rawSubjectType}-${name}`;
        newTag.className = 'new-selected-subject-tag';
        addSubjectTypeBackgroundColor(newTag, rawSubjectType)

        const removeButton = document.createElement('span');
        removeButton.innerText = 'X';
        removeButton.className = 'remove-selected-subject';
        removeButton.addEventListener('click', () => handleRemoveSubject(name, subjectType, newTag));
        newTag.appendChild(removeButton);

        selectedTagsContainer.appendChild(newTag);

        hiddenInput.setAttribute('value', JSON.stringify(existingSubjects));
    }
}

function handleRemoveSubject(name, subjectType, tagElement) {
    const hiddenInput = document.querySelector('.tag-subjects');

    const existingSubjects = JSON.parse(hiddenInput.value === '' ? '{}' : hiddenInput.value);
    existingSubjects[subjectType] = existingSubjects[subjectType] || [];

    existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

    tagElement.remove();

    hiddenInput.setAttribute('value', JSON.stringify(existingSubjects));
}

function hideTaggingMenu() {
    const form = document.querySelector('.bulk-tagging-form');
    if (form) {
        form.style.display = 'none';
    }
}

/**
 * Clears the bulk tagger form.
 */
function resetTaggingMenu() {
    const searchInput = document.querySelector('.subjects-search-input')
    searchInput.value = ''

    const resultsContainer = document.querySelector('.subjects-search-results')
    resultsContainer.innerHTML = ''

    const createSubjectContainer = document.querySelector('.create-new-subject-tag')
    createSubjectContainer.innerHTML = ''

    const selectedTagsContainer = document.querySelector('.selected-tag-subjects')
    selectedTagsContainer.innerHTML = ''

    const hiddenSubjectInput = document.querySelector('.tag-subjects')
    hiddenSubjectInput.value = ''
}
