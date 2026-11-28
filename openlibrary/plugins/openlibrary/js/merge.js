import $ from 'jquery';
import { _, fmt, ngettext } from './i18n.js';
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
            works: row.querySelector('.data.count a')?.textContent.trim() || ''
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
 * @returns {HTMLElement}
 */
function mergeSummary(primary, duplicates) {
    const wrap = document.createElement('div');
    wrap.className = 'merge-summary';
    for (const [label, entries] of [
        [_('Keep'), [primary]],
        [_('Merge in and redirect'), duplicates]
    ]) {
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
    $('#save').on('click', async function (event) {
        event.preventDefault();
        const master = document.querySelector('#mergeForm input[name=master]:checked');
        // Only rendered for librarians who can merge directly; others submit a request.
        const confirmTemplate = document.getElementById('confirmMerge');
        if (!master) {
            await alertFromTemplate(document.getElementById('noMaster'), _('No primary record'));
            return;
        }
        if (!confirmTemplate) {
            submitMergeRequest();
            return;
        }
        // Selecting a primary also ticks its own merge box, so drop it here.
        const duplicateKeys = Array.from(document.querySelectorAll('#mergeForm input[name=merge_key]:checked'))
            .map(box => box.value)
            .filter(key => key !== master.value);
        if (!duplicateKeys.length) {
            await alertFromTemplate(document.getElementById('noDuplicates'), _('No authors selected.'));
            return;
        }
        const rows = authorRows();
        const primary = rows.get(master.value);
        // Without a matching row there is nothing to summarize; merge without the dialog.
        if (primary) {
            const duplicates = duplicateKeys.map(key => rows.get(key)).filter(Boolean);
            const vars = { count: duplicates.length, name: primary.name };
            const confirmed = await confirmFromTemplate(confirmTemplate, {
                message: mergeSummary(primary, duplicates),
                title: fmt(ngettext('Merge %(count)s author into %(name)s?', 'Merge %(count)s authors into %(name)s?', vars.count), vars),
                confirmLabel: fmt(ngettext('Merge %(count)s author', 'Merge %(count)s authors', vars.count), vars),
                destructive: false
            });
            if (!confirmed) return;
        }
        await mergeAuthors(master.value, duplicateKeys, primary?.name);
    });
    $('div.radio').first().find('input[type=radio]').prop('checked', true);
    $('div.author').first().addClass('master');
    $('#include input[type=radio]').on('mouseover', function () {
        $(this).closest('.entry').addClass('mouseoverHighlight', 300);
    });
    $('#include input[type=radio]').on('mouseout', function () {
        $(this).closest('.entry').removeClass('mouseoverHighlight', 100);
    });
    $('#include input[type=radio]').on('click', function () {
        const previousMaster = $('.merge').find('div.master');
        previousMaster.removeClass('master mergeSelection');
        previousMaster.find('input[type=checkbox]').prop('checked', false);
        $(this).closest('.entry').addClass('master');
        $(this).closest('.entry').find('input[type=checkbox]').prop('checked', true);
    });
    $('#include input[type=checkbox]').on('change', function () {
        if (!$(this).closest('.entry').hasClass('master')) {
            if ($(this).is(':checked')) {
                $(this).closest('.entry').addClass('mergeSelection');
            } else {
                $(this).closest('.entry').removeClass('mergeSelection');
            }
        }
    });
    initRejectButton();
}

function setButtonsDisabled(disabled) {
    for (const button of document.querySelectorAll('.merge-feedback__buttons button')) {
        button.disabled = disabled;
    }
}

function submitMergeRequest() {
    const comment = document.querySelector('#author-merge-comment').value;
    if (comment) {
        document.querySelector('#hidden-comment-input').value = comment;
    }
    $('#mergeForm').trigger('submit');
    setButtonsDisabled(true);
}

/**
 * POST the merge from this page and show the result here. Don't move this back
 * onto a page load: Back and refresh would run the merge again (#7506).
 *
 * @param {String} master - OLID of the primary author
 * @param {Array<String>} duplicates - OLIDs to merge into it
 * @param {String} [masterName]
 */
async function mergeAuthors(master, duplicates, masterName) {
    const showStatus = state => {
        for (const message of document.querySelectorAll('#merge-status [data-state]')) {
            message.hidden = message.dataset.state !== state;
        }
    };
    const data = {
        master: `/authors/${master}`,
        duplicates: duplicates.map(key => `/authors/${key}`),
        olids: [master, ...duplicates].join(',')
    };
    const mrid = document.querySelector('#mrid-input')?.value;
    if (mrid) {
        data.mrid = mrid;
    }
    const comment = document.querySelector('#author-merge-comment').value;
    if (comment) {
        data.comment = comment;
    }

    setButtonsDisabled(true);
    showStatus('pending');
    let ok = false;
    try {
        const response = await fetch('/authors/merge.json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        ok = response.ok;
    } catch {
        // Network error; handled below the same as a failed response.
    }
    if (!ok) {
        showStatus('error');
        setButtonsDisabled(false);
        return;
    }
    const link = document.querySelector('#merge-status a[data-primary-link]');
    link.href = `/authors/${master}`;
    link.textContent = masterName || master;
    showStatus('done');
}

function initRejectButton() {
    const rejectButton = document.querySelector('#reject-author-merge-btn');
    if (rejectButton) {
        rejectButton.addEventListener('click', function () {
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
