import { initDialogTriggers, initDialogs } from '../../../openlibrary/plugins/openlibrary/js/native-dialog/index.js';

/** jsdom implements neither <dialog>'s modal methods nor showModal. */
function installDialogStubs() {
    const dialogProto = window.HTMLDialogElement.prototype;
    dialogProto.showModal = function() { this.open = true; };
    dialogProto.close = function() { this.open = false; };
    return () => {
        delete dialogProto.showModal;
        delete dialogProto.close;
    };
}

describe('initDialogTriggers', () => {
    let restoreDom;

    beforeEach(() => {
        restoreDom = installDialogStubs();
        document.body.innerHTML = `
            <dialog id="yearly-goal-modal" class="native-dialog"></dialog>
            <div id="goal-ol-dialog"></div>
            <a id="edit-trigger" href="javascript:;" data-dialog-trigger="#yearly-goal-modal">Edit</a>
            <a id="ol-trigger" href="javascript:;" data-dialog-trigger="#goal-ol-dialog">Edit</a>
            <a id="missing-trigger" href="javascript:;" data-dialog-trigger="#no-such-dialog">Missing</a>
        `;
    });

    afterEach(() => {
        document.body.innerHTML = '';
        restoreDom();
    });

    test('clicking a trigger opens the referenced dialog', () => {
        initDialogTriggers(document.querySelectorAll('[data-dialog-trigger]'));
        const dialog = document.querySelector('#yearly-goal-modal');
        expect(dialog.open).toBe(false);

        document.querySelector('#edit-trigger').click();
        expect(dialog.open).toBe(true);
    });

    test('a trigger pointing at an ol-dialog sets its open property', () => {
        initDialogTriggers(document.querySelectorAll('[data-dialog-trigger]'));
        const dialog = document.querySelector('#goal-ol-dialog');
        expect(dialog.open).toBeUndefined();

        document.querySelector('#ol-trigger').click();
        expect(dialog.open).toBe(true);
    });

    test('a trigger pointing at a missing dialog does not throw', () => {
        initDialogTriggers(document.querySelectorAll('[data-dialog-trigger]'));
        expect(() => document.querySelector('#missing-trigger').click()).not.toThrow();
    });

    test('trigger click does not navigate', () => {
        initDialogTriggers(document.querySelectorAll('[data-dialog-trigger]'));
        const event = new MouseEvent('click', { bubbles: true, cancelable: true });
        const prevented = !document.querySelector('#edit-trigger').dispatchEvent(event);
        expect(prevented).toBe(true);
    });
});

describe('initDialogs', () => {
    let restoreDom;

    beforeEach(() => {
        restoreDom = installDialogStubs();
        document.body.innerHTML = `
            <dialog id="yearly-goal-modal" class="native-dialog">
                <a class="native-dialog--close" href="javascript:;">x</a>
            </dialog>
        `;
    });

    afterEach(() => {
        document.body.innerHTML = '';
        restoreDom();
    });

    test('close icon closes an open dialog', () => {
        const dialog = document.querySelector('#yearly-goal-modal');
        initDialogs([dialog]);
        dialog.open = true;

        dialog.querySelector('.native-dialog--close').click();
        expect(dialog.open).toBe(false);
    });
});
