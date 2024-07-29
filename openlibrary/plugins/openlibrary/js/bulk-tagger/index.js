/**
 * Returns the HMTL for the Bulk Tagger component.
 *
 * @returns HTML for the bulk tagging form
 */
export function renderBulkTagger() {
  return `<form action="/tags/bulk_tag_works" method="post" class="bulk-tagging-form hidden">
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
        <div class="loading-indicator"></div>
        <div class="selection-container hidden">
            <div class="selected-tag-subjects"></div>
            <div class="subjects-search-results"></div>
            <div class="create-new-subject-tag">
            <div class="search-subject-row-name search-subject-row-name-create hidden">
                <div class="search-subject-row-name-create-p">Create new subject <strong class="subject-name"></strong> with type:</div>
                <div class="search-subject-row-name-create-select">
                    <div class="subject-type-option subject-type-option--subject" data-tag-type="subjects">subject</div>
                    <div class="subject-type-option subject-type-option--person" data-tag-type="subject_people">person</div>
                    <div class="subject-type-option subject-type-option--place" data-tag-type="subject_places">place</div>
                    <div class="subject-type-option subject-type-option--time" data-tag-type="subject_times">time</div>
                </div>
            </div>
        </div>
        </div>
        <div class="submit-tags-section">
            <button type="submit" class="bulk-tagging-submit cta-btn cta-btn--primary" disabled>Submit</button>
        </div>
    </form>`
}
