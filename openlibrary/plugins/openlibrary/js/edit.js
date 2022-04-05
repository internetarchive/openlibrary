/* global render_language_field, render_work_autocomplete_item, render_language_autocomplete_item, render_work_field */
/* Globals are provided by the edit edition template */

/* global render_author, render_author_autocomplete_item */
/* Globals are provided by the author-autocomplete template */

function error(errordiv, input, message) {
    $(errordiv).show().html(message);
    $(input).trigger('focus');
    return false;
}

function update_len() {
    var len = $('#excerpts-excerpt').val().length;
    var color;
    if (len > 2000) {
        color = '#e44028';
    } else {
        color = 'gray';
    }
    $('#excerpts-excerpt-len').html(2000 - len).css('color', color);
}

/**
 * Gets length of 'textid' section and limit textid value length to input 'limit'
 *
 * @param {String} textid  text section id name
 * @param {Number} limit   character number limit
 * @return {boolean} is character number below or equal to limit
 */
function limitChars(textid, limit) {
    var text = $(`#${textid}`).val();
    var textlength = text.length;
    if (textlength > limit) {
        $(`#${textid}`).val(text.substr(0, limit));
        return false;
    } else {
        return true;
    }
}

/**
 * This is needed because jQuery has no forEach equivalent that works with jQuery elements instead of DOM elements
 * @param selector - css selector used by jQuery
 * @returns {*[]} - array of jQuery elements
 */
function getJqueryElements(selector){
    const queryResult = $(selector);
    const jQueryElementArray = [];
    for (let i = 0; i < queryResult.length; i++){
        jQueryElementArray.push(queryResult.eq(i))
    }
    return jQueryElementArray;
}

export function initRoleValidation() {
    const dataConfig = JSON.parse(document.querySelector('#roles').dataset.config);
    $('#roles').repeat({
        vars: {prefix: 'edition--'},
        validate: function (data) {
            if (data.role === '' || data.role === '---') {
                return error('#role-errors', '#select-role', dataConfig['Please select a role.']);
            }
            if (data.name === '') {
                return error('#role-errors', '#role-name', dataConfig['You need to give this ROLE a name.'].replace(/ROLE/, data.role));
            }
            $('#role-errors').hide();
            return true;
        }
    });
}

export function initIdentifierValidation() {
    const dataConfig = JSON.parse(document.querySelector('#identifiers').dataset.config);
    $('#identifiers').repeat({
        vars: {prefix: 'edition--'},
        validate: function (data) {
            if (data.name === '' || data.name === '---') {
                return error('#id-errors', 'select-id', dataConfig['Please select an identifier.'])
            }
            const label = $('#select-id').find(`option[value='${data.name}']`).html();
            if (data.value === '') {
                return error('#id-errors', 'id-value', dataConfig['You need to give a value to ID.'].replace(/ID/, label));
            }
            if (['ocaid'].includes(data.name) && /\s/g.test(data.value)) {
                return error('#id-errors', 'id-value', dataConfig['ID ids cannot contain whitespace.'].replace(/ID/, label));
            }
            if (data.name === 'isbn_10' && data.value.length !== 10) {
                return error('#id-errors', 'id-value', dataConfig['ID must be exactly 10 characters [0-9] or X.'].replace(/ID/, label));
            }
            if (data.name === 'isbn_13' && data.value.replace(/-/g, '').length !== 13) {
                return error('#id-errors', 'id-value', dataConfig['ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4'].replace(/ID/, label));
            }
            $('id-errors').hide();
            return true;
        }
    });
}

export function initClassificationValidation() {
    const dataConfig = JSON.parse(document.querySelector('#classifications').dataset.config);
    $('#classifications').repeat({
        vars: {prefix: 'edition--'},
        validate: function (data) {
            if (data.name === '' || data.name === '---') {
                return error('#classification-errors', '#select-classification', dataConfig['Please select a classification.']);
            }
            if (data.value === '') {
                const label = $('#select-classification').find(`option[value='${data.name}']`).html();
                return error('#classification-errors', '#classification-value', dataConfig['You need to give a value to CLASS.'].replace(/CLASS/, label));
            }
            $('#classification-errors').hide();
            return true;
        }
    });
}

export function initLanguageMultiInputAutocomplete() {
    $(function() {
        getJqueryElements('.multi-input-autocomplete--language').forEach(jqueryElement => {
            jqueryElement.setup_multi_input_autocomplete(
                'input.language-autocomplete',
                render_language_field,
                {endpoint: '/languages/_autocomplete'},
                {
                    max: 6,
                    formatItem: render_language_autocomplete_item
                }
            );
        })
    });
}

export function initWorksMultiInputAutocomplete() {
    $(function() {
        getJqueryElements('.multi-input-autocomplete--works').forEach(jqueryElement => {
            /* Values in the html passed from Python code */
            const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
            jqueryElement.setup_multi_input_autocomplete(
                'input.work-autocomplete',
                render_work_field,
                {
                    endpoint: '/works/_autocomplete',
                    addnew: dataConfig['isPrivilegedUser'] === 'true',
                    new_name: dataConfig['-- Move to a new work'],
                },
                {
                    minChars: 2,
                    max: 11,
                    matchSubset: false,
                    autoFill: false,
                    formatItem: render_work_autocomplete_item
                });
        });
    });
}

export function initAuthorMultiInputAutocomplete() {
    getJqueryElements('.multi-input-autocomplete--author').forEach(jqueryElement => {
        /* Values in the html passed from Python code */
        const dataConfig = JSON.parse(jqueryElement[0].dataset.config);
        jqueryElement.setup_multi_input_autocomplete(
            'input.author-autocomplete',
            render_author.bind(null, dataConfig.name_path, dataConfig.dict_path, false),
            {
                endpoint: '/authors/_autocomplete',
                // Don't render "Create new author" if searching by key
                addnew: query => !/OL\d+A/i.test(query),
            },
            {
                minChars: 2,
                max: 11,
                matchSubset: false,
                autoFill: false,
                formatItem: render_author_autocomplete_item
            });
    });
}

export function initEditRow(){
    document.querySelector('#add_row_button').addEventListener('click', ()=>add_row('website'));
}

/**
 * Adds another input box below the last when adding multiple websites to user profile.
 * @param string name - when prefixed with clone_ should match an element identifier in the page. e.g. if name would refer to clone_website
**/
function add_row(name) {
    const inputBoxes = document.querySelectorAll(`#clone_${name} input`);
    const inputBox = document.createElement('input');
    inputBox.name = `${name}#${inputBoxes.length}`;
    inputBox.type = 'text';
    inputBoxes[inputBoxes.length-1].after(inputBox);
}

function show_hide_title() {
    if ($('#excerpts-display .repeat-item').length > 1) {
        $('#excerpts-so-far').show();
    } else {
        $('#excerpts-so-far').hide();
    }
}

export function initEditExcerpts() {
    $('#excerpts').repeat({
        vars: {
            prefix: 'work--excerpts',
        },
        validate: function(data) {
            if (!data.excerpt) {
                return error('#excerpts-errors', '#excerpts-excerpt', 'Please provide an excerpt.');
            }
            if (data.excerpt.length > 2000) {
                return error('#excerpts-errors', '#excerpts-excerpt', 'That excerpt is too long.')
            }
            $('#excerpts-errors').hide();
            return true;
        }
    });

    // update length on every keystroke
    $('#excerpts-excerpt').on('keyup', function() {
        limitChars('excerpts-excerpt', 2000);
        update_len();
    });

    // update length on add.
    $('#excerpts')
        .on('repeat-add', update_len)
        .on('repeat-add', show_hide_title)
        .on('repeat-remove', show_hide_title);

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
    $('#links').repeat({
        vars: {
            prefix: $('#links').data('prefix')
        },
        validate: function(data) {
            if (data.url.trim() === '' || data.url.trim() === 'https://') {
                $('#link-errors').html('Please provide a URL.');
                $('#link-errors').removeClass('hidden');
                $('#link-url').trigger('focus');
                return false;
            }
            if (data.title.trim() === '') {
                $('#link-errors').html('Please provide a label.');
                $('#link-errors').removeClass('hidden');
                $('#link-label').trigger('focus');
                return false;
            }
            $('#link-errors').addClass('hidden');
            return true;
        }
    });
}

/**
 * Initializes edit page.
 *
 * Assumes presence of elements with id:
 *    - '#link_edition'
 *    - '#tabsAddbook'
 *    - '#contentHead'
 */
export function initEdit() {
    var hash = document.location.hash || '#edition';
    var tab = hash.split('/')[0];
    var link = `#link_${tab.substring(1)}`;
    var fieldname = `:input${hash.replace('/', '-')}`;

    $(link).trigger('click');

    // input field is enabled only after the tab is selected and that takes some time after clicking the link.
    // wait for 1 sec after clicking the link and focus the input field
    if ($(fieldname).length !== 0) {
        setTimeout(function() {
        // scroll such that top of the content is visible
            $(fieldname).trigger('focus');
            $(window).scrollTop($('#contentHead').offset().top);
        }, 1000);
    }
}
