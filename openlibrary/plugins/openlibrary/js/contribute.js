/**
 * Open Library Tasks (/tasks) page behavior.
 *
 * Saved tasks leave the list on the server. Skipped ones are remembered for
 * the browser session so they drop out of the list too.
 */

import { setBannerCookie } from './banner';
import { initFeed } from './contribute-feed';
import { parseLccn, isValidLccn, parseOclc, isValidOclc } from './idValidation';
import { trackEvent } from './ol.analytics.js';

const SKIPPED_KEY = 'ol-contribute-skipped';
// While placeholder cards are up, the server is building the list in the background: ask again soon, then
// every few seconds, for as long as its Solr query may take, then give up and say the list couldn't load.
const ROWS_RETRY_MS = [1000, 1000, 2000, 3000, 5000];
const ROWS_MAX_TRIES = 36;

// Same normalization the server applies, so the verdict on screen matches what is stored.
const ID_RULES = {
    lccn: { parse: parseLccn, isValid: isValidLccn },
    oclc_numbers: { parse: parseOclc, isValid: isValidOclc }
};

/**
 * The task keys skipped this browser session.
 * @returns {Set<string>} the stored skipped-task keys (empty if none/unavailable)
 */
function readSkippedTaskKeys() {
    try {
        return new Set(JSON.parse(sessionStorage.getItem(SKIPPED_KEY) || '[]'));
    } catch (e) {
        return new Set();
    }
}

/**
 * Remember a task as skipped for this browser session.
 * @param {string} key - the task key (``OL…M/<field>``) to mark skipped
 * @returns {void}
 */
function markTaskSkipped(key) {
    const skipped = readSkippedTaskKeys();
    skipped.add(key);
    try {
        sessionStorage.setItem(SKIPPED_KEY, JSON.stringify([...skipped]));
    } catch (e) {
        // Blocked storage: the skipped task just stays listed.
    }
}

/**
 * Hide skipped tasks, then any group (book row, same-book section) left with none.
 * @param {ParentNode} root - the subtree to hide within
 * @param {string} groupSelector - selector for the grouping element to collapse when empty
 * @returns {void}
 */
function hideSkippedTasks(root, groupSelector) {
    const skipped = readSkippedTaskKeys();
    root.querySelectorAll('[data-task-key]').forEach(el => {
        if (skipped.has(el.dataset.taskKey)) el.hidden = true;
    });
    root.querySelectorAll(groupSelector).forEach(group => {
        if (!group.querySelector('[data-task-key]:not([hidden])')) group.hidden = true;
    });
}

/**
 * Hide skipped rows in the dashboard list and toggle its empty state.
 * @param {ParentNode} root - the ``[data-contribute-list]`` container
 * @returns {void}
 */
function settleTaskList(root) {
    hideSkippedTasks(root, '[data-book-row]');
    const empty = root.querySelector('[data-list-empty]');
    if (empty) empty.hidden = !!root.querySelector('[data-book-row]:not([hidden])');
}

/**
 * Fetch the rows a page rendered placeholders for. The server answers 202 until the pool is built.
 * An error status, or running out of tries, shows the "couldn't load" message rather than the empty state.
 * @param {ParentNode} root - the ``[data-contribute-list]`` container
 * @param {HTMLOListElement} list - the ``[data-rows-url]`` list of placeholders
 * @returns {Promise<void>}
 */
async function loadTaskRows(root, list) {
    let loaded = false;
    for (let attempt = 0; attempt < ROWS_MAX_TRIES; attempt++) {
        try {
            const res = await fetch(list.dataset.rowsUrl, { headers: { Accept: 'text/html' } });
            if (res.ok && res.status !== 202) {
                list.innerHTML = await res.text();
                loaded = true;
                break;
            }
            if (!res.ok) break;
        } catch (e) {
            // Offline or a dropped request: try again.
        }
        const delay = ROWS_RETRY_MS[Math.min(attempt, ROWS_RETRY_MS.length - 1)];
        await new Promise(resolve => setTimeout(resolve, delay));
    }
    list.querySelectorAll('[data-row-skeleton]').forEach(li => li.remove());
    delete list.dataset.rowsUrl;
    if (loaded) {
        settleTaskList(root);
        return;
    }
    const error = root.querySelector('[data-list-error]');
    if (error) error.hidden = false;
}

/**
 * Wire the dashboard list: load it when the page rendered placeholders, else settle what's there.
 * @param {ParentNode} root - the ``[data-contribute-list]`` container
 * @returns {void}
 */
function initTaskList(root) {
    const pending = root.querySelector('[data-rows-url]');
    if (pending) {
        loadTaskRows(root, pending);
    } else {
        settleTaskList(root);
    }
}

/**
 * Remember this task as skipped when its "I couldn't find it" control is clicked.
 * @param {HTMLFormElement} form - a ``[data-task-form]`` whose ``data-task-key`` identifies the task
 * @returns {void}
 */
function initSkipButton(form) {
    form.querySelector('[data-skip]')?.addEventListener('click', () => markTaskSkipped(form.dataset.taskKey));
}

/**
 * The answer control's current value, whichever control the field uses.
 * @param {HTMLFormElement} form - the task form
 * @returns {string} the trimmed answer, or '' with no control
 */
function currentAnswer(form) {
    const control = form.querySelector('#contrib-other-value');
    if (!control) return '';
    return control.tagName === 'OL-OPTIONS-POPOVER' ? control.selected : control.value.trim();
}

/**
 * Where the answer came from, for the Save event's label: a sibling chip or
 * the keyboard. Fields without suggestions report neither.
 * @param {HTMLFormElement} form - the task form
 * @returns {'chip'|'typed'|''} the source, or '' when the form has no chips
 */
function answerSource(form) {
    const chips = [...form.querySelectorAll('[data-suggest] ol-chip')];
    if (!chips.length) return '';
    const answer = currentAnswer(form);
    return chips.some(chip => chip.dataset.value === answer) ? 'chip' : 'typed';
}

/**
 * Report a save as ``TaskForm|Save`` or ``TaskForm|SaveNext`` with the field as
 * label, plus ``:chip``/``:typed`` when the field offered suggestions. On the
 * ``submit`` event rather than the buttons' clicks so Enter in the answer field
 * counts too; the submitter is the button's in-form proxy.
 * @param {HTMLFormElement} form - a ``[data-task-form]`` with ``data-task-field``
 * @returns {void}
 */
function initSaveTracking(form) {
    form.addEventListener('submit', event => {
        const then = event.submitter?.closest('ol-button')?.value || event.submitter?.value;
        const source = answerSource(form);
        trackEvent('TaskForm', then === 'next' ? 'SaveNext' : 'Save', source ? `${form.dataset.taskField}:${source}` : form.dataset.taskField);
    });
}

/**
 * Wire the "Other editions say" chips to the answer control. The chip matching
 * the current answer shows selected; clicking it again clears it.
 * @param {HTMLFormElement} form - the task form holding the chips and answer control
 * @returns {void}
 */
function initSiblingSuggestions(form) {
    const group = form.querySelector('[data-suggest]');
    const control = form.querySelector('#contrib-other-value');
    if (!group || !control) return;
    const isPicker = control.tagName === 'OL-OPTIONS-POPOVER';
    const chips = [...group.querySelectorAll('ol-chip')];
    const syncChipSelection = () =>
        chips.forEach(chip => {
            chip.selected = chip.dataset.value === currentAnswer(form);
        });

    group.addEventListener('ol-chip-select', event => {
        const chip = event.target.closest('ol-chip');
        const value = event.detail.selected ? chip.dataset.value : '';
        if (isPicker) control.selected = value;
        else control.value = value;
        syncChipSelection();
        if (event.detail.selected) trackEvent('TaskForm', 'PickSuggestion', form.dataset.taskField);
    });
    control.addEventListener(isPicker ? 'ol-options-popover-change' : 'input', syncChipSelection);
    syncChipSelection();
}

/**
 * Check an identifier answer as it's typed: a wrong identifier corrupts record
 * matching silently, so the verdict mirrors the server's normalization.
 * @param {HTMLFormElement} form - a ``[data-id-form]`` whose input carries ``data-id-field``
 * @returns {void}
 */
function initIdentifierForm(form) {
    const input = form.querySelector('[data-id-input]');
    const verdict = form.querySelector('[data-id-verdict]');
    if (!input || !verdict) return;
    const rule = ID_RULES[input.dataset.idField];
    if (!rule) return;
    // One rejection event per form, not one per keystroke.
    let rejected = false;

    input.addEventListener('input', () => {
        const raw = input.value.trim();
        if (!raw) {
            verdict.textContent = '';
            verdict.dataset.state = '';
            return;
        }
        const parsed = rule.parse(raw);
        const msg = input.dataset;
        if (rule.isValid(parsed)) {
            verdict.dataset.state = 'ok';
            verdict.textContent = parsed === raw ? msg.msgOk : msg.msgTidied.replace('__VALUE__', parsed);
        } else {
            verdict.dataset.state = 'bad';
            verdict.textContent = /https?:|\//.test(raw) ? msg.msgUrl : msg.msgBad;
            if (!rejected) trackEvent('TaskForm', 'IdentifierRejected', input.dataset.idField);
            rejected = true;
        }
    });
}

/**
 * Cover task: show the chosen image in the record's cover slot, and take an
 * image dropped onto the slot or pasted anywhere on the page into the file input.
 * @param {HTMLFormElement} form - a ``[data-cover-form]`` holding ``[data-cover-input]`` and ``[data-cover-drop]``
 * @returns {void}
 */
function initCoverForm(form) {
    const input = form.querySelector('[data-cover-input]');
    const drop = form.querySelector('[data-cover-drop]');
    const preview = drop?.querySelector('[data-cover-preview]');
    if (!input || !preview) return;
    let previewUrl = '';

    const showChosen = () => {
        const file = input.files[0];
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = file ? URL.createObjectURL(file) : '';
        preview.src = previewUrl;
        preview.hidden = !file;
        drop.classList.toggle('has-image', !!file);
    };
    // The server checks the extension, and a pasted image may arrive without one.
    const take = files => {
        const image = [...files].find(file => file.type.startsWith('image/'));
        if (!image) return false;
        const name = /\.\w+$/.test(image.name) ? image.name : `cover.${image.type.split('/')[1]}`;
        const transfer = new DataTransfer();
        transfer.items.add(new File([image], name, { type: image.type }));
        input.files = transfer.files;
        showChosen();
        return true;
    };

    input.addEventListener('change', showChosen);
    drop.addEventListener('dragover', event => {
        event.preventDefault();
        drop.classList.add('is-over');
    });
    drop.addEventListener('dragleave', () => drop.classList.remove('is-over'));
    drop.addEventListener('drop', event => {
        event.preventDefault();
        drop.classList.remove('is-over');
        take(event.dataTransfer.files);
    });
    document.addEventListener('paste', event => {
        if (event.clipboardData && take(event.clipboardData.files)) event.preventDefault();
    });
}

/**
 * A member sees the Tasks intro once: clicking through sets a cookie the way
 * banner dismissals do, and /tasks skips to the dashboard from then on. The
 * cookie has to land before the next page is requested, so a plain click waits
 * on the POST; a modified click (new tab) is left to the browser.
 * @param {HTMLElement} link - an ``[data-intro-cookie]`` link, with ``data-intro-days`` for the cookie's life
 * @returns {void}
 */
function initIntroDismiss(link) {
    link.addEventListener('click', event => {
        if (event.defaultPrevented) return;
        const dismiss = setBannerCookie(link.dataset.introCookie, Number(link.dataset.introDays) || 365);
        const modified = event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
        if (modified) {
            dismiss.catch(() => {});
            return;
        }
        event.preventDefault();
        const go = () => window.location.assign(link.href);
        dismiss.then(go, go);
    });
}

/**
 * Drop the "Save and next" receipt from the URL, so a reload doesn't show its toast again.
 * @returns {void}
 */
function clearSavedReceipt() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('saved')) return;
    url.searchParams.delete('saved');
    history.replaceState(history.state, '', url);
}

/**
 * Entry point for the Tasks pages; wires the list, task forms, and done page.
 * @returns {void}
 */
/**
 * Show a spinner on the pressed rail filter while the next page loads.
 * @param {HTMLElement} rail - the ``[data-rail]`` nav
 * @returns {void}
 */
function initRailLoading(rail) {
    rail.addEventListener('click', e => {
        const link = e.target.closest('a[href]');
        if (!link || link.classList.contains('is-on')) return;
        // New-tab / modified / non-left clicks don't navigate this window.
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        link.classList.add('is-target');
    });
    // Back/forward restores this DOM from bfcache with the spinner still showing.
    window.addEventListener('pageshow', e => {
        if (!e.persisted) return;
        rail.querySelectorAll('.is-target').forEach(link => link.classList.remove('is-target'));
    });
}

export function init() {
    document.querySelectorAll('[data-contribute-list]').forEach(root => {
        initTaskList(root);
    });
    document.querySelectorAll('[data-rail]').forEach(initRailLoading);
    document.querySelectorAll('[data-feed]').forEach(initFeed);
    document.querySelectorAll('[data-intro-cookie]').forEach(initIntroDismiss);
    document.querySelectorAll('form[data-task-form]').forEach(form => {
        initSkipButton(form);
        initSiblingSuggestions(form);
        initSaveTracking(form);
    });
    if (document.querySelector('[data-receipt]')) clearSavedReceipt();
    document.querySelectorAll('form[data-id-form]').forEach(initIdentifierForm);
    document.querySelectorAll('form[data-cover-form]').forEach(initCoverForm);
    document.querySelectorAll('[data-contribute-done]').forEach(root => hideSkippedTasks(root, '[data-same-book]'));
}
