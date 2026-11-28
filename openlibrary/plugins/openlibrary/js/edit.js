import $ from 'jquery';
import { _, fmt } from './i18n.js';
import { init as initAutocomplete } from './autocomplete';
import { init as initJqueryRepeat } from './jquery.repeat';
import { trimInputValues } from './utils.js';

// render_* globals are provided by the edit edition, author-autocomplete and
// edit about templates; they are declared for oxlint in .oxlintrc.json.

function error(errordiv, input, message) {
    $(errordiv).show().html(message);
    $(input).trigger('focus');
    return false;
}

function update_len() {
    const len = $('#excerpts-excerpt').val().length;
    let color;
    if (len > 2000) {
        color = '#e44028';
    } else {
        color = 'gray';
    }
    $('#excerpts-excerpt-len')
        .html(2000 - len)
        .css('color', color);
}

/**
 * Gets length of 'textid' section and limit textid value length to input 'limit'
 *
 * @param {String} textid  text section id name
 * @param {Number} limit   character number limit
 * @return {boolean} is character number below or equal to limit
 */
function limitChars(textid, limit) {
    const text = $(`#${textid}`).val();
    const textlength = text.length;
    if (textlength > limit) {
        $(`#${textid}`).val(text.slice(0, limit));
        return false;
    }
    return true;
}

/**
 * This is needed because jQuery has no forEach equivalent that works with jQuery elements instead of DOM elements
 * @param selector - css selector used by jQuery
 * @returns {*[]} - array of jQuery elements
 */
function getJqueryElements(selector) {
    const queryResult = $(selector);
    const jQueryElementArray = [];
    for (let i = 0; i < queryResult.length; i++) {
        jQueryElementArray.push(queryResult.eq(i));
    }
    return jQueryElementArray;
}

export function initRoleValidation() {
    initJqueryRepeat();
    $('#roles').repeat({
        vars: { prefix: 'edition--' },
        validate: function (data) {
            if (data.role === '' || data.role === '---') {
                return error('#role-errors', '#select-role', _('Please select a role.'));
            }
            if (data.name === '') {
                return error('#role-errors', '#role-name', fmt(_('You need to give this %(role)s a name.'), { role: data.role }));
            }
            $('#role-errors').hide();
            $('#select-role, #role-name').val('');
            return true;
        }
    });
}

export function initClassificationValidation() {
    initJqueryRepeat();
    // Prevent form submission on Enter for classification fields
    $('#classification-value').on('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            $('#classifications .repeat-add').trigger('click');
            return false;
        }
    });

    $('#classifications').repeat({
        vars: { prefix: 'edition--' },
        validate: function (data) {
            if (data.name === '' || data.name === '---') {
                return error('#classification-errors', '#select-classification', _('Please select a classification.'));
            }
            if (data.value === '') {
                const label = $('#select-classification').find(`option[value='${data.name}']`).html();
                return error('#classification-errors', '#classification-value', fmt(_('You need to give a value to %(name)s.'), { name: label }));
            }
            $('#classification-errors').hide();
            $('#select-classification, #classification-value').val('');
            return true;
        }
    });
}

export function initLanguageMultiInputAutocomplete() {
    initAutocomplete();
    $(function () {
        getJqueryElements('.multi-input-autocomplete--language').forEach(jqueryElement => {
            jqueryElement.setup_multi_input_autocomplete(
                render_language_field,
                {
                    endpoint: '/languages/_autocomplete',
                    sortable: true
                },
                {
                    max: 6,
                    formatItem: render_language_autocomplete_item
                }
            );
        });
    });
}

export function initWorksMultiInputAutocomplete() {
    initAutocomplete();
    $(function () {
        getJqueryElements('.multi-input-autocomplete--works').forEach(jqueryElement => {
            /* Values in the html passed from Python code */
            const dataConfig = JSON.parse(jqueryElement[0].dataset.config || '{}');
            jqueryElement.setup_multi_input_autocomplete(
                render_work_field,
                {
                    endpoint: '/works/_autocomplete',
                    addnew: dataConfig['addnew'] || false,
                    new_name: dataConfig['new_name'] || '',
                    allow_empty: dataConfig['allow_empty'] || false
                },
                {
                    minChars: 2,
                    max: 11,
                    matchSubset: false,
                    autoFill: true,
                    formatItem: render_work_autocomplete_item
                }
            );
        });
    });

    // Show the new work options checkboxes only if "New work" selected
    $('input[name="works--0"]').on('autocompleteselect', function (_event, ui) {
        $('.new-work-options').toggle(ui.item.key === '__new__');
    });
}

export function initSeedsMultiInputAutocomplete() {
    initAutocomplete();
    $(function () {
        getJqueryElements('.multi-input-autocomplete--seeds').forEach(jqueryElement => {
            /* Values in the html passed from Python code */
            jqueryElement.setup_multi_input_autocomplete(
                render_seed_field,
                {
                    endpoint: '/works/_autocomplete',
                    addnew: false,
                    allow_empty: true,
                    sortable: true
                },
                {
                    minChars: 2,
                    max: 11,
                    matchSubset: false,
                    autoFill: true,
                    formatItem: render_lazy_work_preview
                }
            );
        });
    });
}

export function initAuthorMultiInputAutocomplete() {
    initAutocomplete();
    getJqueryElements('.multi-input-autocomplete--author').forEach(jqueryElement => {
        /* Values in the html passed from Python code */
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_multi_input_autocomplete(
            render_author.bind(null, dataConfig.name_path, dataConfig.dict_path, false),
            {
                endpoint: '/authors/_autocomplete',
                // Don't render "Create new author" if searching by key
                addnew: query => !/OL\d+A/i.test(query),
                sortable: true
            },
            {
                minChars: 2,
                max: 11,
                matchSubset: false,
                autoFill: true,
                formatItem: render_author_autocomplete_item
            }
        );
    });
}

export function initSeriesMultiInputAutocomplete() {
    initAutocomplete();
    getJqueryElements('.multi-input-autocomplete--series').forEach(jqueryElement => {
        /* Values in the html passed from Python code */
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_multi_input_autocomplete(
            render_series.bind(null, dataConfig.name_path, dataConfig.dict_path, false),
            {
                endpoint: '/series/_autocomplete',
                // Don't render "Create new series" if searching by key
                addnew: query => !/OL\d+L/i.test(query),
                sortable: true
            },
            {
                minChars: 2,
                max: 11,
                matchSubset: false,
                autoFill: true,
                formatItem: render_series_autocomplete_item
            }
        );
    });
}

export function initSubjectsAutocomplete() {
    initAutocomplete();
    getJqueryElements('.csv-autocomplete--subjects').forEach(jqueryElement => {
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_csv_autocomplete(
            'textarea',
            {
                endpoint: `/subjects_autocomplete?type=${dataConfig.facet}`,
                addnew: false
            },
            {
                formatItem: render_subject_autocomplete_item
            }
        );
    });

    /* Resize textarea to fit on input */
    $('.csv-autocomplete--subjects textarea').on('input', function () {
        this.style.height = 'auto';
        this.style.height = `${this.scrollHeight + 5}px`;
    });
}

export function initEditRow() {
    document.querySelector('#add_row_button').addEventListener('click', () => add_row('website'));
}

/**
 * Adds another input box below the last when adding multiple websites to user profile.
 * @param string name - when prefixed with clone_ should match an element identifier in the page. e.g. if name would refer to clone_website
 */
function add_row(name) {
    const inputBoxes = document.querySelectorAll(`#clone_${name} input`);
    const inputBox = document.createElement('input');
    inputBox.name = `${name}#${inputBoxes.length}`;
    inputBox.type = 'url';
    inputBox.placeholder = 'https://...';
    inputBoxes[inputBoxes.length - 1].after(inputBox);
}

function show_hide_title() {
    if ($('#excerpts-display .repeat-item').length > 1) {
        $('#excerpts-so-far').show();
    } else {
        $('#excerpts-so-far').hide();
    }
}

export function initEditExcerpts() {
    initJqueryRepeat();
    $('#excerpts').repeat({
        vars: {
            prefix: 'work--excerpts'
        },
        validate: function (data) {
            if (!data.excerpt) {
                return error('#excerpts-errors', '#excerpts-excerpt', _('Please provide an excerpt.'));
            }
            if (data.excerpt.length > 2000) {
                return error('#excerpts-errors', '#excerpts-excerpt', _('That excerpt is too long.'));
            }
            $('#excerpts-errors').hide();
            $('#excerpts-excerpt').val('');
            return true;
        }
    });

    // update length on every keystroke
    $('#excerpts-excerpt').on('keyup', function () {
        limitChars('excerpts-excerpt', 2000);
        update_len();
    });

    // update length on add.
    $('#excerpts').on('repeat-add', update_len).on('repeat-add', show_hide_title).on('repeat-remove', show_hide_title);

    // update length on load
    update_len();
    show_hide_title();
}

/**
 * Initializes links element on edit page.
 *
 * Assumes presence of elements with id:
 *    - '#links' and 'data-prefix' attribute
 *    - '#link-label'
 *    - '#link-url'
 *    - '#link-errors'
 */
export function initEditLinks() {
    initJqueryRepeat();
    $('#links').repeat({
        vars: {
            prefix: $('#links').data('prefix')
        },
        validate: function (data) {
            const url = data.url.trim();

            if (data.title.trim() === '') {
                $('#link-errors').html(_('Please provide a label.'));
                $('#link-errors').removeClass('hidden');
                $('#link-label').trigger('focus');
                return false;
            }
            if (url === '') {
                $('#link-errors').html(_('Please provide a URL.'));
                $('#link-errors').removeClass('hidden');
                $('#link-url').trigger('focus');
                return false;
            }
            if (!isValidURL(url)) {
                $('#link-errors').html(_('Please enter a valid URL.'));
                $('#link-errors').removeClass('hidden');
                $('#link-url').trigger('focus');
                return false;
            }
            $('#link-errors').addClass('hidden');
            $('#link-label, #link-url').val('');
            return true;
        }
    });
}

/**
 * Initializes edit page.
 *
 * Assumes presence of elements with id:
 *    - '#contentHead'
 *
 * A `#tab/field` hash deep-links into the form: <ol-tabs> selects the tab
 * itself, and this focuses the field with id `tab-field`.
 */
export async function initEdit() {
    trimInputValues('.olform input');

    const [tab, field] = document.location.hash.slice(1).split('/');
    const input = field && document.getElementById(`${tab}-${field}`);
    if (!input) return;
    // The field can only take focus once <ol-tabs> has shown its panel.
    await customElements.whenDefined('ol-tabs');
    input.focus();
    // scroll such that top of the content is visible
    document.getElementById('contentHead')?.scrollIntoView();
}

/**
 * Assesses URL validity using built-in URL object.
 * @param string url
 */
export function isValidURL(url) {
    try {
        new URL(url);
        return true;
    } catch (e) {
        return false;
    }
}

/**
 * @param {NodeList<HTMLElement>} elems
 */
export function initRecordDeletion(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', event => {
            event.preventDefault();
            const form = elem.form;
            const commentInput = document.querySelector('input[name=_comment]');
            form.appendChild(commentInput);
            // pass elem as submitter so its name/value pair is included in the submission
            form.requestSubmit(elem);
        });
    }
}
