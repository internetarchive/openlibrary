/**
 * Author merge page (js/merge.js). Librarians who can merge directly do it with
 * a POST from this page, so Back or refresh can't repeat a merge (#7506).
 */
import { initAuthorMergePage } from '../../../openlibrary/plugins/openlibrary/js/merge';
import { confirmFromTemplate } from '../../../openlibrary/plugins/openlibrary/js/confirm-template';

vi.mock('../../../openlibrary/plugins/openlibrary/js/confirm-template', () => ({
    alertFromTemplate: vi.fn(() => Promise.resolve()),
    confirmFromTemplate: vi.fn(() => Promise.resolve(true))
}));

const plurals = { one: 'x', two: 'x', few: 'x', many: 'x', other: 'x' };

function row(key, name) {
    return `
        <div class="entry author">
            <input type="radio" name="master" value="${key}">
            <input type="checkbox" name="merge_key" value="${key}">
            <span class="name">${name}</span>
        </div>`;
}

function mount({ canMerge = true, mrid = '' } = {}) {
    const i18n = JSON.stringify({ titleForCount: plurals, confirmForCount: plurals, keep: 'Keep', redirect: 'Redirect' });
    document.body.innerHTML = `
        <template id="noMaster" data-i18n="{}"></template>
        ${canMerge ? `<template id="noDuplicates" data-i18n="{}"></template><template id="confirmMerge" data-i18n='${i18n}'></template>` : ''}
        <form id="mergeForm" method="POST" action="/authors/merge">
            ${mrid ? `<input type="hidden" id="mrid-input" name="mrid" value="${mrid}">` : ''}
            <input type="hidden" id="hidden-comment-input" name="comment" value="">
            <div class="merge" id="include">
                ${row('OL1A', 'Primary Author')}
                ${row('OL2A', 'Duplicate One')}
                ${row('OL3A', 'Duplicate Two')}
            </div>
            <div class="merge-feedback">
                <input type="text" id="author-merge-comment">
                <div class="merge-feedback__buttons"><button id="save" type="submit">Merge</button></div>
            </div>
        </form>
        <div id="merge-status">
            <p data-state="pending" hidden></p>
            <div data-state="done" hidden><a data-primary-link></a></div>
            <p data-state="error" hidden></p>
        </div>`;
    initAuthorMergePage();
    document.querySelector('input[name=master][value=OL1A]').checked = true;
    for (const box of document.querySelectorAll('input[name=merge_key]')) {
        box.checked = true;
    }
}

const visibleStatus = () => document.querySelector('#merge-status [data-state]:not([hidden])')?.dataset.state;
const saveButton = () => document.querySelector('#save');

describe('author merge page', () => {
    let submitForm;

    beforeEach(() => {
        global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
        confirmFromTemplate.mockClear();
        // jQuery's trigger('submit') ends in the native form.submit().
        submitForm = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {});
    });

    afterEach(() => submitForm.mockRestore());

    test('confirming POSTs the merge from this page instead of submitting the form', async () => {
        mount({ mrid: '42' });
        document.querySelector('#author-merge-comment').value = 'same person';
        saveButton().click();

        await vi.waitFor(() => expect(visibleStatus()).toBe('done'));
        expect(global.fetch).toHaveBeenCalledTimes(1);
        const [url, options] = global.fetch.mock.calls[0];
        expect(url).toBe('/authors/merge.json');
        expect(options.method).toBe('POST');
        expect(JSON.parse(options.body)).toEqual({
            master: '/authors/OL1A',
            duplicates: ['/authors/OL2A', '/authors/OL3A'],
            olids: 'OL1A,OL2A,OL3A',
            mrid: '42',
            comment: 'same person'
        });
        expect(submitForm).not.toHaveBeenCalled();
        expect(saveButton().disabled).toBe(true);
        const link = document.querySelector('[data-primary-link]');
        expect(link.getAttribute('href')).toBe('/authors/OL1A');
        expect(link.textContent).toBe('Primary Author');
    });

    test('cancelling the confirmation sends nothing', async () => {
        confirmFromTemplate.mockResolvedValueOnce(false);
        mount();
        saveButton().click();

        await vi.waitFor(() => expect(confirmFromTemplate).toHaveBeenCalled());
        await Promise.resolve();
        expect(global.fetch).not.toHaveBeenCalled();
        expect(visibleStatus()).toBeUndefined();
    });

    test('a failed merge reports the error and lets the librarian try again', async () => {
        global.fetch = vi.fn(() => Promise.resolve({ ok: false }));
        mount();
        saveButton().click();

        await vi.waitFor(() => expect(visibleStatus()).toBe('error'));
        expect(saveButton().disabled).toBe(false);
    });

    test('librarians without merge rights still submit the form as a merge request', async () => {
        mount({ canMerge: false });
        saveButton().click();

        await vi.waitFor(() => expect(submitForm).toHaveBeenCalledTimes(1));
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
