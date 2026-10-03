import $ from 'jquery';
import { alertFromTemplate, confirmFromTemplate } from './confirm-template';
import { declineRequest } from './merge-request-table/MergeRequestService';

/**
 * Every value the confirmation dialog shows is already on the page, including
 * the work count, which the server has translated and pluralised. Read it,
 * don't rebuild it.
 *
 * @returns {Map<String, {key: String, name: String, works: String}>} by author key
 */
function authorRows() {
    const rows = new Map();
    for (const row of document.querySelectorAll('#mergeForm .entry.author')) {
        const key = row.querySelector('input[name=merge_key]')?.value;
        if (!key) continue;
        rows.set(key, {
            key,
            name: row.querySelector('.name')?.textContent.trim() || key,
            works: row.querySelector('.data.count a')?.textContent.trim() || '',
        });
    }
    return rows;
}

/**
 * The dialog body: the record being kept, then the records redirected into it,
 * so the decision can be made without reading the page behind the dialog.
 *
 * @param {Object} primary
 * @param {Array<Object>} duplicates
 * @param {Object} i18n - Parsed from the template's data-i18n.
 * @returns {HTMLElement}
 */
function mergeSummary(primary, duplicates, i18n) {
    const wrap = document.createElement('div');
    wrap.className = 'merge-summary';
    for (const [label, entries] of [[i18n.keep, [primary]], [i18n.redirect, duplicates]]) {
        if (!entries.length) continue;
        const heading = document.createElement('h3');
        heading.className = 'merge-summary__label';
        heading.textContent = label;
        const list = document.createElement('ul');
        list.className = 'merge-summary__list';
        for (const entry of entries) {
            const name = document.createElement('span');
            name.className = 'merge-summary__name';
            name.textContent = entry.name;
            const meta = document.createElement('span');
            meta.className = 'merge-summary__meta';
            meta.textContent = entry.works ? `${entry.key} · ${entry.works}` : entry.key;
            const item = document.createElement('li');
            item.className = 'merge-summary__row';
            item.append(name, meta);
            list.append(item);
        }
        wrap.append(heading, list);
    }
    return wrap;
}

export function initAuthorMergePage() {
    $('#save').on('click', async function(event) {
        event.preventDefault();
        const master = document.querySelector('#mergeForm input[name=master]:checked');
        // Only rendered for librarians who can merge directly; others submit a request.
        const confirmTemplate = document.getElementById('confirmMerge');
        if (!master) {
            await alertFromTemplate(document.getElementById('noMaster'));
            return;
        }
        if (!confirmTemplate) {
            submitMerge();
            return;
        }
        const i18n = JSON.parse(confirmTemplate.dataset.i18n);
        const rows = authorRows();
        const primary = rows.get(master.value);
        // Selecting a primary also ticks its own merge box, so drop it here.
        const duplicates = Array.from(document.querySelectorAll('#mergeForm input[name=merge_key]:checked'))
            .map((box) => box.value)
            .filter((key) => key !== master.value)
            .map((key) => rows.get(key))
            .filter(Boolean);
        // English pluralises on n !== 1, so a zero-duplicate merge reads correctly too.
        if (!duplicates.length) {
            await alertFromTemplate(document.getElementById('noDuplicates'));
            return;
        }
        const plural = duplicates.length !== 1;
        const fill = (text) => text
            .replace('%(count)s', duplicates.length)
            .replace('%(name)s', primary.name);
        const confirmed = await confirmFromTemplate(confirmTemplate, {
            message: mergeSummary(primary, duplicates, i18n),
            title: fill(plural ? i18n.titleMany : i18n.titleOne),
            confirmLabel: fill(plural ? i18n.confirmMany : i18n.confirmOne),
            destructive: false,
        });
        if (confirmed) submitMerge();
    });
    $('div.radio').first().find('input[type=radio]').prop('checked', true);
    $('div.checkbox').first().find('input[type=checkbox]').prop('checked', true);
    $('div.author').first().addClass('master');
    $('#include input[type=radio]').on('mouseover', function() {
        $(this).parent().parent().addClass('mouseoverHighlight', 300);
    });
    $('#include input[type=radio]').on('mouseout', function() {
        $(this).parent().parent().removeClass('mouseoverHighlight', 100);
    });
    $('#include input[type=radio]').on('click', function() {
        const previousMaster = $('.merge').find('div.master');
        previousMaster.removeClass('master mergeSelection');
        previousMaster.find('input[type=checkbox]').prop('checked', false);
        $(this).parent().parent().addClass('master');
        $(this).parent().parent().find('input[type=checkbox]').prop('checked', true);
    });
    $('#include input[type=checkbox]').on('change', function() {
        if (!$(this).parent().parent().hasClass('master')) {
            if ($(this).is(':checked')) {
                $(this).parent().parent().addClass('mergeSelection');
            } else {
                $(this).parent().parent().removeClass('mergeSelection');
            }
        }
    });
    initRejectButton();
}

function submitMerge() {
    const comment = document.querySelector('#author-merge-comment').value;
    if (comment) {
        document.querySelector('#hidden-comment-input').value = comment;
    }
    $('#mergeForm').trigger('submit');
    for (const button of document.querySelectorAll('.merge-feedback__buttons button')) {
        button.disabled = true;
    }
}

function initRejectButton() {
    const rejectButton = document.querySelector('#reject-author-merge-btn');
    if (rejectButton) {
        rejectButton.addEventListener('click', function() {
            rejectMerge();
            rejectButton.disabled = true;
            const approveButton = document.querySelector('#save');
            approveButton.disabled = true;
        });
    }
}

function rejectMerge() {
    const commentInput = document.querySelector('#author-merge-comment');
    const mridInput = document.querySelector('#mrid-input');
    declineRequest(Number(mridInput.value), commentInput.value);
}

/**
 * Initializes preMerge element on author page.
 *
 * Show 'preMerge' element and launch author merge of duplicate keys into master key.
 * Assumes presence of element with '#preMerge' id and 'data-keys' attribute.
 */
export function initAuthorView() {
    const dataKeysJSON = $('#preMerge').data('keys');

    $('#preMerge').show();
    $('#preMerge').parent().show();

    const data = {
        master: dataKeysJSON['master'],
        duplicates: dataKeysJSON['duplicates'],
        olids: dataKeysJSON['olids']
    };

    const mrid = dataKeysJSON['mrid'];
    const comment = dataKeysJSON['comment'];

    if (mrid) {
        data['mrid'] = mrid;
    }
    if (comment) {
        data['comment'] = comment;
    }

    $.ajax({
        url: '/authors/merge.json',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        error: function() {
            $('#preMerge').fadeOut();
            $('#errorMerge').fadeIn();
        },
        success: function() {
            $('#preMerge').fadeOut();
            $('#postMerge').fadeIn();
        }
    });
}
