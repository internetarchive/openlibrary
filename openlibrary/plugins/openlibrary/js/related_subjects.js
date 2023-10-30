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
    const generatedString = selectedSubjects.join('&');
    return generatedString;
}

function renderSubjectsCarousel() {
    const queryString = generateQuery();
    const url = new URL(window.location.href);
    url.searchParams.set('subjects', queryString);
    window.history.replaceState(null, null, url);
    $('#related-subjects-carousel').load(`${window.location.href} #related-subjects-carousel`)
}
