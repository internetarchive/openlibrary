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

function render_language_autocomplete_item(item, title){
    return `<div class="ac_language" title="${title}">
        <span class="name">${item.name}</span>
    </div>`
}


function render_language_field(i, language, title, isPriviligedUser){
    const removeButton = isPriviligedUser ? `<a href="javascript:;" class="remove red plain" title="${title}">[x]</a>` : '';
    return `<div class="input">
        <input name="languages--${i}" class="language language-autocomplete" type="text" id="language-${i}"
               value="${language.name}"/>
        <input name="edition--languages--${i}--key" type="hidden" id="language-${i}-key" value="${language.key}"/>
        ${removeButton}
        <br/><a href="javascript:;" class="add small">Add another language?</a>
    </div>`
}

function render_work_field(i, work, removeWorkText){
    return `<div class="input">
        <input name="works--${i}" class="work work-autocomplete" type="text" id="work-${i}"
               value="${work.key.split('/')[-1]}"/>
        <input name="edition--works--${i}--key" type="hidden" id="work-${i}-key" value="${work.key}"/>
        <a href="javascript:;" class="remove red plain hidden" title="${removeWorkText}">[x]</a>
    </div>`
}

function render_work_autocomplete_item(item, newWorkText){
    if (item.key === '__new__') {
        return `<div class="ac_work ac_addnew">
            <span class="action">${newWorkText}</span>
        </div>`
    }

    const coverImg = `<img src="https://covers.openlibrary.org/b/id/${item.cover_i}-M.jpg" alt="Cover of ${item.title}">`
    const firstYearSpan = `<span class="first_publish_year">(${item.first_publish_year})</span>`
    const byLine = `<span class="byline">by <span class="authors">${item.author_name.join(', ')}</span></span>`
    return `
        <div class="ac_work" title="Select this work">
            <div class="cover">
                ${item.cover_i ? coverImg : ''}
            </div>
            <span class="olid">${item.key.split('/').pop()}</span>
            <span class="name">
                <span class="title">${item.full_title}</span>
                ${item.first_publish_year ? firstYearSpan : ''}
            </span>
            ${item.author_name ? byLine : ''}
            &bull;
            <span class="edition_count">${item.edition_count} edition${item.edition_count === 1 ? '' : 's'}</span>
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
    $(function() {
        ['#languages','#translated_from_languages'].forEach((selector)=>{
            $(selector).setup_multi_input_autocomplete(
                'input.language-autocomplete',
                (i, language) => render_language_field(i, language, removeLanguage, isPrivilegedUser),
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
                formatItem: item => render_work_autocomplete_item(item, newWorkText)
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
