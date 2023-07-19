/* global render_subjects_carousel */

import { render } from 'less';

export function initRelatedSubjectsCarousel() {
    const subjectCheckboxes = document.querySelectorAll('.subject-filter');
    subjectCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener('change', renderSubjectsCarousel);
    })
}

function generateQuery() {
    const selectedSubjects = [];
    const checkboxes = document.querySelectorAll('.subject-filter:checked');
    checkboxes.forEach((checkbox) => {
        const subject = checkbox.parentNode.textContent.trim();
        selectedSubjects.push(subject);
    });
    const generatedString = 'subject:("' + selectedSubjects.join('" AND "') + '")';
    return generatedString;
}

function renderSubjectsCarousel() {
    const queryString = generateQuery();
    const container = document.getElementById('related-subjects-carousel');
    $(window.render_subjects_carousel(queryString));
    $( "#related-subjects-carousel" ).load(window.location.href + " #related-subjects-carousel" )
    container.classList.remove('hidden');
    // $('#related-subjects-carousel').html(render_subjects_carousel(queryString));
}