/**
 * Open Library Tasks (/tasks) page behavior.
 *
 * Saved tasks leave the list on the server. Skipped ones are remembered for
 * the browser session so they drop out of the list too.
 */

import { initFeed } from './contribute-feed';
import { parseLccn, isValidLccn, parseOclc, isValidOclc } from './idValidation';

const SKIPPED_KEY = 'ol-contribute-skipped';

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
function initTaskList(root) {
    hideSkippedTasks(root, '[data-book-row]');
    const empty = root.querySelector('[data-list-empty]');
    if (empty) empty.hidden = !!root.querySelector('[data-book-row]:not([hidden])');
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
    const currentAnswer = () => (isPicker ? control.selected : control.value.trim());
    const chips = [...group.querySelectorAll('ol-chip')];
    const syncChipSelection = () =>
        chips.forEach(chip => {
            chip.selected = chip.dataset.value === currentAnswer();
        });

    group.addEventListener('ol-chip-select', event => {
        const chip = event.target.closest('ol-chip');
        const value = event.detail.selected ? chip.dataset.value : '';
        if (isPicker) control.selected = value;
        else control.value = value;
        syncChipSelection();
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
        }
    });
}

/**
 * The inline task page (``/tasks/<field>``): a list of records, each fixed in place. Picking an answer and
 * saving posts it and moves the card to the Done tab, with no page navigation.
 * @param {HTMLElement} root - the ``[data-inline-tasks]`` container
 * @returns {void}
 */
function initInlineTasks(root) {
    const field = root.dataset.field;
    const items = readInlineItems(root);
    initTabs(root);
    root.querySelectorAll('[data-card]').forEach(card => initInlineCard(card, field, items));
}

/**
 * The page-level language list, shared by every picker so the long list isn't repeated per card.
 * @param {HTMLElement} root - the ``[data-inline-tasks]`` container
 * @returns {{value: string, label: string}[]} the picker items, or an empty list
 */
function readInlineItems(root) {
    try {
        return JSON.parse(root.querySelector('[data-inline-items]')?.textContent || '[]');
    } catch (e) {
        return [];
    }
}

/**
 * Wire the Needs review / Done tabs: show one panel at a time and track selection for screen readers.
 * @param {HTMLElement} root - the ``[data-inline-tasks]`` container
 * @returns {void}
 */
function initTabs(root) {
    const tabs = [...root.querySelectorAll('[data-tab]')];
    const select = name => {
        tabs.forEach(tab => {
            const on = tab.dataset.tab === name;
            tab.classList.toggle('is-on', on);
            tab.setAttribute('aria-selected', String(on));
            tab.tabIndex = on ? 0 : -1;
        });
        root.querySelectorAll('[data-panel]').forEach(panel => {
            panel.hidden = panel.dataset.panel !== name;
        });
    };
    tabs.forEach(tab => tab.addEventListener('click', () => select(tab.dataset.tab)));
}

/**
 * Wire one record card: the language picker adds a chip per choice, and Save posts the chosen codes.
 * @param {HTMLElement} card - a ``[data-card]`` element carrying ``data-olid``
 * @param {string} field - the task field (``languages``)
 * @param {{value: string, label: string}[]} items - the picker items
 * @returns {void}
 */
function initInlineCard(card, field, items) {
    const picker = card.querySelector('[data-lang-picker]');
    const chipList = card.querySelector('[data-chips]');
    const error = card.querySelector('[data-error]');
    const labelFor = code => items.find(it => it.value === code)?.label || code;

    if (picker) {
        customElements.whenDefined('ol-options-popover').then(() => {
            picker.items = items;
        });
        picker.addEventListener('ol-options-popover-change', event => {
            const code = event.detail.selected;
            if (code) addChip(chipList, code, labelFor(code));
            // Reset so the same picker can add the next language.
            picker.selected = '';
        });
    }

    card.querySelector('[data-save]')?.addEventListener('click', () => {
        const codes = [...chipList.querySelectorAll('[data-code]')].map(c => c.dataset.code);
        saveInlineCard(card, field, codes, error);
    });
}

/**
 * Add a language chip, unless its code is already chosen.
 * @param {HTMLElement} chipList - the ``[data-chips]`` list
 * @param {string} code - the language code
 * @param {string} label - the language name to show
 * @returns {void}
 */
function addChip(chipList, code, label) {
    if (chipList.querySelector(`[data-code="${code}"]`)) return;
    const chip = document.createElement('li');
    chip.className = 'contrib-chip';
    chip.dataset.code = code;
    const name = document.createElement('span');
    name.textContent = label;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'contrib-chip__remove';
    remove.setAttribute('aria-label', `${label}`);
    remove.textContent = '×';
    remove.addEventListener('click', () => chip.remove());
    chip.append(name, remove);
    chipList.append(chip);
}

/**
 * Post one card's answer. On success the card leaves Needs review and a receipt is added to Done.
 * @param {HTMLElement} card - the record card
 * @param {string} field - the task field
 * @param {string[]} codes - the chosen value codes
 * @param {HTMLElement} error - the card's error element
 * @returns {void}
 */
async function saveInlineCard(card, field, codes, error) {
    error.hidden = true;
    if (!codes.length) {
        showCardError(error, error.dataset.msgEmpty || 'Choose at least one.');
        return;
    }
    const save = card.querySelector('[data-save]');
    if (save) save.loading = true;
    try {
        const response = await fetch(`/tasks/${field}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ olid: card.dataset.olid, value: codes.join(',') })
        });
        const result = await response.json();
        if (!result.ok) {
            showCardError(error, result.error);
            return;
        }
        moveCardToDone(card, result);
    } catch (e) {
        showCardError(error, error.dataset.msgFailed || 'Could not save. Try again.');
    } finally {
        if (save) save.loading = false;
    }
}

/**
 * Show an error on a card and keep it in Needs review.
 * @param {HTMLElement} error - the card's error element
 * @param {string} message - the message to show
 * @returns {void}
 */
function showCardError(error, message) {
    error.textContent = message;
    error.hidden = false;
}

/**
 * Remove a saved card from Needs review and add its receipt to Done, updating both tab counts.
 * @param {HTMLElement} card - the saved card
 * @param {{olid: string, title: string, value: string, history_url: string}} result - the save receipt
 * @returns {void}
 */
function moveCardToDone(card, result) {
    const root = card.closest('[data-inline-tasks]');
    card.remove();
    const doneList = root.querySelector('[data-done-list]');
    doneList.prepend(buildDoneCard(result, root.dataset.msgHistory || 'History'));
    bumpCount(root.querySelector('[data-count-todo]'), -1);
    bumpCount(root.querySelector('[data-count-done]'), 1);
    toggleEmpty(root.querySelector('[data-todo-list]'), root.querySelector('[data-todo-empty]'));
    toggleEmpty(doneList, root.querySelector('[data-done-empty]'));
}

/**
 * Build a Done-tab receipt card for a just-saved record.
 * @param {{olid: string, title: string, value: string, history_url: string}} result - the save receipt
 * @param {string} historyLabel - the translated label for the history link
 * @returns {HTMLLIElement} the done card
 */
function buildDoneCard(result, historyLabel) {
    const li = document.createElement('li');
    li.className = 'contrib-card contrib-card--done';
    li.dataset.doneOlid = result.olid;
    const check = document.createElement('span');
    check.className = 'contrib-card__check';
    check.setAttribute('aria-hidden', 'true');
    check.textContent = '✓';
    const meta = document.createElement('div');
    meta.className = 'contrib-card__meta';
    const title = document.createElement('a');
    title.className = 'contrib-card__title';
    title.href = `/books/${result.olid}`;
    title.textContent = result.title;
    const value = document.createElement('div');
    value.className = 'contrib-done__value';
    value.textContent = result.value;
    meta.append(title, value);
    const history = document.createElement('a');
    history.className = 'contrib-done__history';
    history.href = result.history_url;
    history.textContent = historyLabel;
    li.append(check, meta, history);
    return li;
}

/**
 * Add ``delta`` to a count element's integer text.
 * @param {HTMLElement|null} el - the count element
 * @param {number} delta - the change
 * @returns {void}
 */
function bumpCount(el, delta) {
    if (el) el.textContent = String(Math.max(0, (parseInt(el.textContent, 10) || 0) + delta));
}

/**
 * Show an empty-state message when its list has no cards left.
 * @param {HTMLElement} list - the card list
 * @param {HTMLElement|null} empty - the empty-state element
 * @returns {void}
 */
function toggleEmpty(list, empty) {
    if (empty) empty.hidden = !!list.querySelector('li');
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
export function init() {
    document.querySelectorAll('[data-contribute-list]').forEach(root => {
        initTaskList(root);
    });
    document.querySelectorAll('[data-feed]').forEach(initFeed);
    document.querySelectorAll('[data-inline-tasks]').forEach(initInlineTasks);
    document.querySelectorAll('form[data-task-form]').forEach(form => {
        initSkipButton(form);
        initSiblingSuggestions(form);
    });
    if (document.querySelector('[data-receipt]')) clearSavedReceipt();
    document.querySelectorAll('form[data-id-form]').forEach(initIdentifierForm);
    document.querySelectorAll('[data-contribute-done]').forEach(root => hideSkippedTasks(root, '[data-same-book]'));
}
