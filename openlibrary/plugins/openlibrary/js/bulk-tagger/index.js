import { _ } from '../i18n.js';

/** Escape a translated string for the markup below. */
const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function esc(text) {
    return text.replace(/[&<>\u0022\u0027]/g, ch => ENTITIES[ch]);
}

/**
 * Returns the HMTL for the Bulk Tagger component.
 *
 * @returns HTML for the bulk tagging form
 */
export function renderBulkTagger() {
    const heading = esc(_('Manage Subjects'));
    const filterPlaceholder = esc(_('Filter subjects e.g. Epic'));
    const [createBefore, createAfter] = esc(_('Create new subject %(name)s with type:')).split('%(name)s');
    const typeSubject = esc(_('subject'));
    const typePerson = esc(_('person'));
    const typePlace = esc(_('place'));
    const typeTime = esc(_('time'));
    const typeCollection = esc(_('collection'));
    const submit = esc(_('Submit'));
    return `<form action="/tags/bulk_tag_works" method="post" class="bulk-tagging-form hidden">
        <div class="form-header">
            <p>${heading}</p>
            <div class="close-bulk-tagging-form">x</div>
        </div>
        <div class="search-subject-container">
            <input type="text" class="subjects-search-input" placeholder="${filterPlaceholder}">
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
                <div class="search-subject-row-name-create-p">${createBefore}<strong class="subject-name"></strong>${createAfter ?? ''}</div>
                <div class="search-subject-row-name-create-select">
                    <div class="subject-type-option subject-type-option--subject" data-tag-type="subjects">${typeSubject}</div>
                    <div class="subject-type-option subject-type-option--person" data-tag-type="subject_people">${typePerson}</div>
                    <div class="subject-type-option subject-type-option--place" data-tag-type="subject_places">${typePlace}</div>
                    <div class="subject-type-option subject-type-option--time" data-tag-type="subject_times">${typeTime}</div>
                    <div class="subject-type-option subject-type-option--collection" data-tag-type="collections">${typeCollection}</div>
                </div>
            </div>
        </div>
        </div>
        <div class="submit-tags-section">
            <button type="submit" class="bulk-tagging-submit cta-btn cta-btn--primary" disabled>${submit}</button>
        </div>
    </form>`;
}
