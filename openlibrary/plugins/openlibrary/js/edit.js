function error(errordiv, input, message) {
    $(errordiv).show().html(message);
    $(input).focus();
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


export function initEdit() {

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
    $('#excerpts-excerpt').keyup(update_len);

    // update length on add.
    $('#excerpts')
        .bind('repeat-add', update_len)
        .bind('repeat-add', show_hide_title)
        .bind('repeat-remove', show_hide_title);

    // update length on load
    update_len();
    show_hide_title();
}

/**
 * Initializes select-role-popup element on edit page.
 *
 * Assumes presence of elements with id:
 *    - '#select-role'
 *    - '#select-role-popup'
 *    - '#select-role-popup-errors'
 *    - '#select-role-popup-value'
 */
export function initEditRoleSelectPopup() {
    $('#select-role').add_new_field({
        href: '#select-role-popup',
        validate: function(data) {
            if (data.value === '') {
                return error('#select-role-popup-errors', '#select-role-popup-value', 'Please enter a new role.');
            }
            $('#select-role-popup-errors').hide();
            return true;
        },
        onshow: function() {
            $('#select-role-popup-errors').hide();
            $('#select-role-popup input[type=text]').val('');
        }
    });
}

/**
 * Initializes select-id-popup element on edit page.
 *
 * Assumes presence of elements with id:
 *    - '#select-id'
 *    - '#select-id-popup'
 *    - '#select-id-popup-errors'
 *    - '#select-id-popup-label'
 */
export function initEditIdSelectPopup() {
    $('#select-id').add_new_field({
        href: '#select-id-popup',
        validate: function(data) {
            if (data.label === '') {
                return error('#select-id-popup-errors', '#select-id-popup-label', 'Please enter name of the new identifier type.');
            }
            data.value = data.label.toLowerCase().replace(/ /g, '_');
            return true;
        },
        onshow: function() {
            $('#select-id-popup-errors').hide();
            $('#select-id-popup input[type=text]').val('');
        }
    });
}

/**
 * Initializes select-classification-popup element on edit page.
 *
 * Assumes presence of elements with id:
 *    - '#select-classification'
 *    - '#select-classification-popup'
 *    - '#select-classification-popup-errors'
 *    - '#select-classification-popup-label'
 */
export function initEditClassificationSelectPopup() {
    $('#select-classification').add_new_field({
        href: '#select-classification-popup',
        validate: function(data) {
            if (data.label === '') {
                return error('#select-classification-popup-errors', '#select-classification-popup-label', 'Please enter name of the new classification type.');
            }
            data.value = data.label.toLowerCase().replace(/ /g, '_');
            return true;
        },
        onshow: function() {
            $('#select-classification-popup-errors').hide();
            $('#select-classification-popup input[type=text]').val('');
        }
    });
}
