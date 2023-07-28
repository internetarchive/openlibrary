import { debounce } from './nonjquery_utils';

const subjectTypeColors = {
    'subject': '#0067D5',
    'person': '#D100D5',
    'place': '#D50033',
    'time': '#D5A600'
}

function newSubjectRowHtml(subjectName, subjectType = null, isSelected = false) {
    const exists = subjectType != null;
    const buttonStyle = 'font-size: 13px; color: black; font-weight: 700; cursor: pointer; width: 40px;';
    const nameStyle = 'font-size: 13px; color: black; font-weight: 400';
    const tagStyle = 'font-size: 11px; font-weight: 400; border-radius: 8px; border-top: 1px solid #CCC; border-bottom: 1px solid #CCC; padding: 2px 6px; color: #FFF; margin-left: auto';
    const divStyle = 'display: flex; align-items: center; font-size: 16px; border-bottom: 1px solid lightgray; padding: 9px 10px; width: 100%;';

    const div = document.createElement('div');
    div.style = divStyle;
    if (exists) {
        div.style.height = '33px';
    }

    if (exists) {
        const buttonIcon = isSelected ? '-' : '+';
        const button = document.createElement('div');
        button.innerText = buttonIcon;
        button.style = buttonStyle;
        button.addEventListener('click', () => handleSelectSubject(subjectName, subjectType, button));

        div.appendChild(button);
    }

    const name = document.createElement('div');
    name.style = nameStyle;
    if (exists) {
        name.innerText = subjectName;
    } else {
        name.style.display = 'flex';
        name.style.flexDirection = 'column';
        name.style.justifyContent = 'center';
        let p = document.createElement('div');
        p.innerHTML = `Create new subject <strong>'${subjectName}'</strong> with type:`;
        p.style = 'font-size: 13px; color: black; font-weight: 400; margin-bottom: 5px;'
        name.appendChild(p);

        let subjectTypeOptions = ['subject', 'person', 'place', 'time'];
        let select = document.createElement('div');
        select.style = 'width: 100%; display: flex; flex-direction: row; gap: 5px;';
        subjectTypeOptions.forEach((option) => {
            let optionElement = document.createElement('div');
            optionElement.style = 'font-size: 11px; color: white; font-weight: 400; width: fit-content; padding: 3px 6px; border-radius: 8px; cursor: pointer;';
            optionElement.style.backgroundColor = subjectTypeColors[option];
            optionElement.textContent = option;

            optionElement.addEventListener('click', () => handleSelectSubject(subjectName, option, null));

            select.appendChild(optionElement);
        })
        name.appendChild(select);
    }

    div.appendChild(name);

    const tag = document.createElement('div');
    if (exists) {
        tag.innerText = subjectType;
        tag.style = tagStyle;
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
                        console.log(div);
                        resultsContainer.appendChild(div);
                    });
            }
            if (searchTerm != '' && (data['docs'].length == 0 || !data['docs'].slice(0, maxDisplayResults).includes(searchTerm))) {
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

    const existingSubjects = JSON.parse(hiddenInput.value == "" ? "{}" : hiddenInput.value);
    existingSubjects[subjectType] = existingSubjects[subjectType] || [];

    // Check if the name is already in the hidden input value
    const isTagged = existingSubjects[subjectType].includes(name);

    if (isTagged) {
        // Remove the name from the hidden input value
        existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

        // Remove the corresponding tag element
        const tagToRemove = selectedTagsContainer.querySelector(`[data-name="${rawSubjectType + '-' + name}"]`);
        if (tagToRemove) {
            tagToRemove.remove();
        }
        if (button) {
            button.innerText = '+';
        }
    } else {
        // Append the name to the hidden input value
        existingSubjects[subjectType].push(name);

        // Create a new tag element
        const newTag = document.createElement('div');
        newTag.innerText = name;
        newTag.dataset.name = rawSubjectType + '-' + name;
        newTag.style = 'border: 1px solid #CCC; padding: 2px 6px; font-size: 13px; width: fit-content;';
        newTag.style.backgroundColor = subjectTypeColors[rawSubjectType];

        const removeButton = document.createElement('span');
        removeButton.innerText = 'X';
        removeButton.style = 'font-size: 11px; color: black; font-weight: bold; cursor: pointer; margin-left: 7px;';
        removeButton.addEventListener('click', () => handleRemoveSubject(name, subjectType, newTag));
        newTag.appendChild(removeButton);

        if (button) {
            button.innerText = '-';
        }
        // Add the new tag element to the "selected-tag-subjects" div
        selectedTagsContainer.appendChild(newTag);
    }

    hiddenInput.value = JSON.stringify(existingSubjects);
}

function handleRemoveSubject(name, subjectType, tagElement) {
    const hiddenInput = document.getElementById('tag-subjects');
    const selectedTagsContainer = document.getElementById('selected-tag-subjects');
    subjectType = parseSubjectType(subjectType);

    const existingSubjects = JSON.parse(hiddenInput.value == "" ? "{}" : hiddenInput.value);
    existingSubjects[subjectType] = existingSubjects[subjectType] || [];

    // Remove the name from the hidden input value
    existingSubjects[subjectType] = existingSubjects[subjectType].filter((subject) => subject !== name);

    // Remove the corresponding tag element
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



