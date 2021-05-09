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

/**
 * Returns the HTML string for one item of the language input field dropdown.
 * @param object item - has one property "name" which is shown to the user
 * @param string title - the text to show when hovering over a dropdown item
 * title is a parameter for i18n purposes
**/
function render_language_autocomplete_item(item, title){
    return `<div class="ac_language" title="${title}">
        <span class="name">${item.name}</span>
    </div>`
}

/**
 * Returns the HTML string for one language input field. Editions can have multiple languages and as such multiple of these fields.
 * @param integer i - 0 is the first language, 1 is the second language, etc
 * @param object language - has two properties, "name" which is shown to user and "key" which is sent to server
 * @param string removeWorkTitle - the text to show when hovering over the remove button
 * @param string addAnotherLanguageText - the text to show for adding another language
 * removeButtonTitle and addAnotherLanguageText are parameters for i18n purposes
**/
function render_language_field(i, language, removeWorkTitle, addAnotherLanguageText){
    return `<div class="input">
        <input name="languages--${i}" class="language language-autocomplete" type="text" id="language-${i}"
               value="${language.name}"/>
        <input name="edition--languages--${i}--key" type="hidden" id="language-${i}-key" value="${language.key}"/>
        <a href="javascript:;" class="remove red plain hidden" title="${removeWorkTitle}">[x]</a>
        <br/><a href="javascript:;" class="add small">${addAnotherLanguageText}</a>
    </div>`
}

/**
 * Returns the HTML string for one work input field.
 * @param integer i - 0 is the first work, 1 is the second work, etc
 * @param object work - has one property, "key" which is sent to server and not shown to user
 * @param string removeWorkTitle - the text to show when hovering over the remove button
 * removeWorkText is a parameter for i18n purposes
**/
function render_work_field(i, work, removeWorkTitle){
    return `<div class="input">
        <input name="works--${i}" class="work work-autocomplete" type="text" id="work-${i}"
               value="${work.key.split('/')[-1]}"/>
        <input name="edition--works--${i}--key" type="hidden" id="work-${i}-key" value="${work.key}"/>
        <a href="javascript:;" class="remove red plain hidden" title="${removeWorkTitle}">[x]</a>
    </div>`
}

/**
 * Returns the HTML string for one item of the work input field dropdown.
 * @param object work - has many properties used to show the user key details of the work
 * @param string newWorkText - the text to show when hovering over a dropdown item
 * @param string by - the text to show when hovering over a dropdown item
 * newWorkText and by are parameterized for i18n purposes
**/
function render_work_autocomplete_item(work, newWorkText, by){
    if (work.key === '__new__') {
        return `<div class="ac_work ac_addnew">
            <span class="action">${newWorkText}</span>
        </div>`
    }

    const coverImg = `<img src="https://covers.openlibrary.org/b/id/${work.cover_i}-M.jpg" alt="Cover of ${work.title}">`
    const firstYearSpan = `<span class="first_publish_year">(${work.first_publish_year})</span>`
    const byLine = `<span class="byline">${by} <span class="authors">${work.author_name.join(', ')}</span></span>`
    return `
        <div class="ac_work" title="Select this work">
            <div class="cover">
                ${work.cover_i ? coverImg : ''}
            </div>
            <span class="olid">${work.key.split('/').pop()}</span>
            <span class="name">
                <span class="title">${work.full_title}</span>
                ${work.first_publish_year ? firstYearSpan : ''}
            </span>
            ${work.author_name ? byLine : ''}
            &bull;
            <span class="edition_count">${work.edition_count} edition${work.edition_count === 1 ? '' : 's'}</span>
        </div>
        `
}

export function initEditionEditPage(){
    const editionPageData = document.querySelector('[value="edition-edit-page"]');
    const isPrivilegedUser = editionPageData.dataset.isprivilegeduser === 'true';
    const newWorkText = editionPageData.dataset.newwork;
    const removeWorkText = editionPageData.dataset.removework;
    const selectLanguage = editionPageData.dataset.selectlanguage;
    const removeLanguage = editionPageData.dataset.removelanguage;
    const anotherLanguage = editionPageData.dataset.removelanguage;
    const by = editionPageData.dataset.by;
    $(function() {
        ['#languages','#translated_from_languages'].forEach((selector)=>{
            $(selector).setup_multi_input_autocomplete(
                'input.language-autocomplete',
                (i, language) => render_language_field(i, language, removeLanguage, anotherLanguage),
                { endpoint: '/languages/_autocomplete' },
                {
                    max: 6,
                    formatItem: item => render_language_autocomplete_item(item, selectLanguage)
                });
        })

        $('#works').setup_multi_input_autocomplete(
            'input.work-autocomplete',
            (i, work) => render_work_field(i, work, removeWorkText),
            {
                endpoint: '/works/_autocomplete',
                addnew: isPrivilegedUser,
                new_name: newWorkText,
            },
            {
                minChars: 2,
                max: 11,
                matchSubset: false,
                autoFill: false,
                formatItem: item => render_work_autocomplete_item(item, newWorkText, by)
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
