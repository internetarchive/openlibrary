import { debounce } from './nonjquery_utils';

const subjectTypeColors = {
    subject: '#0067D5',
    person: '#D100D5',
    place: '#D50033',
    time: '#D5A600'
};

function newSubjectRowHtml(subjectName, subjectType = null, isSelected = false) {
    const exists = subjectType != null;

    const div = document.createElement('div');
    div.className = 'subject-row';
    if (exists) {
        div.classList.add('subject-row-exists');
    }

    if (exists) {
        const buttonIcon = isSelected ? '-' : '+';
        const button = document.createElement('div');
        button.innerText = buttonIcon;
        button.className = 'row-button';
        button.addEventListener('click', () => handleSelectSubject(subjectName, subjectType, button));

        div.appendChild(button);
    }

    const name = document.createElement('div');
    name.className = 'row-name';
    if (exists) {
        name.innerText = subjectName;
    } else {
        name.className += ' row-name-create';
        const p = document.createElement('div');
        p.innerHTML = `Create new subject <strong>'${subjectName}'</strong> with type:`;
        p.className = 'row-name-create-p';
        name.appendChild(p);

        const subjectTypeOptions = ['subject', 'person', 'place', 'time'];
        const select = document.createElement('div');
        select.className = 'row-name-create-select';
        subjectTypeOptions.forEach((option) => {
            const optionElement = document.createElement('div');
            optionElement.className = 'subject-type-option';
            optionElement.textContent = option;
            optionElement.style.backgroundColor = subjectTypeColors[option];

            optionElement.addEventListener('click', () => handleSelectSubject(subjectName, option, null));

            select.appendChild(optionElement);
        });
        name.appendChild(select);
    }

    div.appendChild(name);

    const tag = document.createElement('div');
    if (exists) {
        tag.innerText = subjectType;
        tag.className = 'row-tag';
        tag.style.backgroundColor = subjectTypeColors[subjectType];

        div.appendChild(tag);
    }

    return div;
}

const maxDisplayResults = 10;

function fetchSubjects(searchTerm) {
    const resultsContainer = document.getElementById('subjects-search-results');
    const hiddenInput = document.getElementById('tag-subjects');
    resultsContainer.innerHTML = '';
    fetch(`/search/subjects.json?q=${searchTerm}`)
        .then((response) => response.json())
        .then((data) => {
            if (data['docs'].length !== 0) {
                data['docs'].slice(0, maxDisplayResults)
                    .forEach(result => {
                        const isSelected = hiddenInput.value.includes(result.name);

                        const div = newSubjectRowHtml(result.name, result['subject_type'], isSelected);
                        resultsContainer.appendChild(div);
                    });
            }
            if (searchTerm != '') { // create new subject option
                const div = newSubjectRowHtml(searchTerm);
                resultsContainer.appendChild(div);
            }
        });
}

const debouncedFetchSubjects = debounce(fetchSubjects, 500);

export function initSubjectTagsSearchBox() {
    const searchInput = document.getElementById('subjects-search-input');
    document.getElementById('close-bulk-tagging-form').addEventListener('click', hideTaggingMenu)
    searchInput.addEventListener('input', function () {
        const searchTerm = this.value.trim();
        debouncedFetchSubjects(searchTerm);
    });
}

function handleSelectSubject(name, rawSubjectType, button=null) {
    const hiddenInput = document.getElementById('tag-subjects');
    const selectedTagsContainer = document.getElementById('selected-tag-subjects');
    const subjectType = parseSubjectType(rawSubjectType);

    const existingSubjects = JSON.parse(hiddenInput.value == '' ? '{}' : hiddenInput.value);
    existingSubjects[subjectType] = existingSubjects[subjectType] || [];

    const isTagged = existingSubjects[subjectType].includes(name);

    if (isTagged) {
        existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

        const tagToRemove = selectedTagsContainer.querySelector(`[data-name="${`${rawSubjectType}-${name}`}"]`);
        if (tagToRemove) {
            tagToRemove.remove();
        }
        if (button) {
            button.innerText = '+';
        }
    } else {
        existingSubjects[subjectType].push(name);

        const newTag = document.createElement('div');
        newTag.innerText = name;
        newTag.dataset.name = `${rawSubjectType}-${name}`;
        newTag.className = 'new-tag';
        newTag.style.backgroundColor = subjectTypeColors[rawSubjectType];

        const removeButton = document.createElement('span');
        removeButton.innerText = 'X';
        removeButton.className = 'remove-button';
        removeButton.addEventListener('click', () => handleRemoveSubject(name, subjectType, newTag));
        newTag.appendChild(removeButton);

        if (button) {
            button.innerText = '-';
        }
        selectedTagsContainer.appendChild(newTag);
    }

    hiddenInput.value = JSON.stringify(existingSubjects);
}

function handleRemoveSubject(name, subjectType, tagElement) {
    const hiddenInput = document.getElementById('tag-subjects');
    const selectedTagsContainer = document.getElementById('selected-tag-subjects');
    subjectType = parseSubjectType(subjectType);

    const existingSubjects = JSON.parse(hiddenInput.value == '' ? '{}' : hiddenInput.value);
    existingSubjects[subjectType] = existingSubjects[subjectType] || [];

    existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

    tagElement.remove();

    hiddenInput.value = JSON.stringify(existingSubjects);
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

function hideTaggingMenu() {
    const form = document.getElementById('bulk-tagging-form');
    if (form) {
        form.style.display = 'none';
    }
}
