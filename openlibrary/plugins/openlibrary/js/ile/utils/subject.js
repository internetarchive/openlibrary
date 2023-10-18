import { initSubjectTagsSearchBox } from '../initTaggingSearchBar';

export function renderBulkTaggingMenu(workIds) {
    const existingForm = document.querySelector('.bulk-tagging-form');
    if (existingForm) {
        existingForm.style.display = 'block';
        const target = document.getElementById('ile-hidden-forms')
        target.style.display = 'block';
        // If the form already exists, change the value of the hidden input to include the new work ids
        const hiddenInput = document.querySelector('.tag-work-ids');
        hiddenInput.defaultValue = workIds.join(',');
    } else {
        fetchTaggingMenu(workIds);
    }
}

const fetchTaggingMenu = function(workIds) {
    $.ajax({
        url: '/tags/partials.json',
        type: 'GET',
        data: {
            work_ids: workIds.join(','),
        },
        datatype: 'json',
        success: function (response) {
            if (response){
                response = JSON.parse(response)
                const target = document.getElementById('ile-hidden-forms')
                target.style.display = 'block';
                target.innerHTML += response['tagging_menu']
                initSubjectTagsSearchBox();
            }
        }
    });
};
