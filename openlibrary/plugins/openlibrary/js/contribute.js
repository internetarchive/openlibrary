/**
 * Open Library Tasks (/tasks) page behavior.
 *
 * Saved tasks leave the list on the server. Skipped ones are remembered for
 * the browser session so they drop out of the list too.
 */

import { setBannerCookie } from './banner';
import { confirmFromTemplate } from './confirm-template';
import { initFeed } from './contribute-feed';
import { parseLccn, isValidLccn, parseOclc, isValidOclc } from './idValidation';
import { trackEvent } from './ol.analytics.js';

const SKIPPED_KEY = 'ol-contribute-skipped';
// The "Not sure" row's value on a choice list; mirrors ``UNSURE`` in contribute.py.
const UNSURE = 'unsure';
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
 * Remember this task as skipped when "Skip" or "I couldn't find it" is clicked.
 * @param {HTMLFormElement} form - a ``[data-task-form]`` whose ``data-task-key`` identifies the task
 * @returns {void}
 */
function initSkipButton(form) {
    for (const control of form.querySelectorAll('[data-skip]')) {
        control.addEventListener('click', () => markTaskSkipped(form.dataset.taskKey));
    }
}

/**
 * The answer control's current value, whichever control the field uses.
 * @param {HTMLFormElement} form - the task form
 * @returns {string} the trimmed answer, or '' with no control
 */
function currentAnswer(form) {
    // A choice list is a set of radios rather than one control.
    const checked = form.querySelector('input[name="value"]:checked');
    if (checked) return checked.value;
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
 * label, plus ``:chip``/``:typed`` when the field offered suggestions. A "Not sure"
 * answer reports as ``NotFound`` and is remembered as skipped, like the button. On the
 * ``submit`` event rather than the buttons' clicks so Enter in the answer field
 * counts too; the submitter is the button's in-form proxy.
 * @param {HTMLFormElement} form - a ``[data-task-form]`` with ``data-task-field``
 * @returns {void}
 */
function initSaveTracking(form) {
    form.addEventListener('submit', event => {
        const then = event.submitter?.closest('ol-button')?.value || event.submitter?.value;
        // "I couldn't find it" also submits; its click is already tracked as NotFound.
        if (then === 'notfound') return;
        // "Not sure" on a choice list is the same honest exit: the server counts it as "couldn't find it".
        if (currentAnswer(form) === UNSURE) {
            markTaskSkipped(form.dataset.taskKey);
            trackEvent('TaskForm', 'NotFound', form.dataset.taskField);
            return;
        }
        const source = answerSource(form);
        trackEvent('TaskForm', then === 'next' ? 'SaveNext' : 'Save', source ? `${form.dataset.taskField}:${source}` : form.dataset.taskField);
    });
}

/**
 * Show a spinner on the pressed submit button while the next page loads, and disable the others so a second
 * press can't save twice. Deferred because a loading ol-button disables its proxy: on Enter, that could land
 * before the browser reads the form and drop ``then=next`` from the submission.
 * @param {HTMLFormElement} form - a ``[data-task-form]``
 * @returns {void}
 */
function initSubmitLoading(form) {
    const buttons = form.querySelectorAll('ol-button[type="submit"]');
    form.addEventListener('submit', event => {
        const pressed = event.submitter?.closest('ol-button');
        setTimeout(() => {
            if (event.defaultPrevented) return;
            buttons.forEach(button => {
                button.loading = button === pressed;
                button.disabled = button !== pressed;
            });
        }, 0);
    });
    // Back/forward restores this DOM from bfcache with the spinner still showing.
    window.addEventListener('pageshow', event => {
        if (!event.persisted) return;
        buttons.forEach(button => {
            button.loading = false;
            button.disabled = false;
        });
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
 * Quick next: on a form that opts in, clicking the already-picked choice row saves and moves on, so an easy
 * call (fiction or nonfiction) takes two clicks on the answer and none on the buttons. The first click on a
 * row only selects it; a double-click is just the two clicks in a row. Keyboard activation (Space on a
 * checked radio also fires ``click``) is left alone: Enter already submits with "Save and next".
 * @param {HTMLFormElement} form - a ``[data-task-form][data-quick-next]``
 * @returns {void}
 */
function initQuickNext(form) {
    if (!('quickNext' in form.dataset)) return;
    let picked = form.querySelector('input[name="value"]:checked');
    // A click with no pointerdown before it came from the keyboard or a script.
    let pointer = false;
    form.addEventListener('pointerdown', () => {
        pointer = true;
    });
    form.addEventListener('keydown', () => {
        pointer = false;
    });
    form.addEventListener('change', event => {
        if (event.target.name === 'value') picked = event.target;
    });
    form.addEventListener('click', event => {
        const input = event.target;
        if (!(input instanceof HTMLInputElement) || input.name !== 'value' || input.type !== 'radio') return;
        // The row that opens the companion field asks for a second look at the page, not a second click.
        if (input.dataset.reveals) return;
        const viaPointer = pointer;
        pointer = false;
        // ``change`` for a fresh pick fires after this click, so ``picked`` still names the previous row here.
        if (!viaPointer || input !== picked) return;
        // ol-button keeps a native submit proxy in the form; submitting through it keeps ``then=next`` and the Save tracking.
        const next = form.querySelector('button[name="then"][value="next"]');
        if (!next) return;
        trackEvent('TaskForm', 'QuickNext', form.dataset.taskField);
        form.requestSubmit(next);
    });
}

/**
 * A many-tags answer: chips that toggle, with a hidden input per picked key so
 * the form posts the picks under the group's name. A chip the subjects suggested
 * carries them in ``data-subjects``: hovering or focusing it lights those subjects
 * in the record, and picking it reports as ``PickSuggestion``, like a sibling chip
 * on a text field.
 * @param {HTMLElement} group - a ``[data-many-choice]`` holding ``ol-chip[data-value]`` elements
 * @returns {void}
 */
function initManyChoice(group) {
    const name = group.dataset.manyChoice;
    const form = group.closest('form');
    const field = form?.dataset.taskField;
    const light = (chip, on) => {
        const subjects = JSON.parse(chip.dataset.subjects);
        form?.querySelectorAll('[data-subject]').forEach(el => el.toggleAttribute('data-lit', on && subjects.includes(el.dataset.subject)));
    };
    for (const chip of group.querySelectorAll('ol-chip[data-subjects]')) {
        chip.addEventListener('mouseenter', () => light(chip, true));
        chip.addEventListener('mouseleave', () => light(chip, false));
        chip.addEventListener('focusin', () => light(chip, true));
        chip.addEventListener('focusout', () => light(chip, false));
    }
    const sync = () => {
        group.querySelectorAll('input[type="hidden"]').forEach(input => input.remove());
        // By property: the chip reflects ``selected`` to its attribute only on its next render.
        for (const chip of [...group.querySelectorAll('ol-chip')].filter(chip => chip.selected)) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = chip.dataset.value;
            group.append(input);
        }
    };
    group.addEventListener('ol-chip-select', event => {
        const chip = event.target.closest('ol-chip');
        chip.selected = event.detail.selected;
        sync();
        if (event.detail.selected && chip.dataset.subjects && field) trackEvent('TaskForm', 'PickSuggestion', `${field}:${name}`);
    });
    sync();
}

/**
 * The companion field (the genres under "fiction"): shown while the choice row
 * that opens it, marked ``data-reveals`` with the field's name, is the one picked.
 * @param {HTMLFormElement} form - a task form that may hold a ``[data-companion]`` row
 * @returns {void}
 */
function initCompanion(form) {
    const panel = form.querySelector('[data-companion]');
    if (!panel) return;
    const sync = () => {
        const checked = form.querySelector('input[name="value"]:checked');
        panel.hidden = checked?.dataset.reveals !== panel.dataset.companion;
    };
    form.addEventListener('change', event => {
        if (event.target.name === 'value') sync();
    });
    sync();
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
 * Cover task: the new cover is one of a few rows, Amazon's image for the ISBN once it loads or an
 * upload (picked, dropped, or pasted anywhere on the page). The chosen row's image goes into the
 * one file input the form submits, and shows in the record's cover slot.
 * @param {HTMLFormElement} form - a ``[data-cover-form]`` holding ``[data-cover-input]`` and the ``[data-cover-option]`` rows
 * @returns {void}
 */
function initCoverForm(form) {
    const input = form.querySelector('[data-cover-input]');
    const preview = form.querySelector('[data-cover-preview]');
    const slot = preview?.closest('[data-cover-drop]');
    const suggestedRow = form.querySelector('[data-cover-option="suggested"]');
    const uploadRow = form.querySelector('[data-cover-option="upload"]');
    if (!input || !slot || !uploadRow) return;
    const uploadThumb = uploadRow.querySelector('[data-cover-upload-thumb]');
    const uploadName = uploadRow.querySelector('[data-cover-upload-name]');
    const files = {};
    const urls = {};

    const setFile = (choice, file) => {
        if (urls[choice]) URL.revokeObjectURL(urls[choice]);
        files[choice] = file;
        urls[choice] = file ? URL.createObjectURL(file) : '';
    };
    const select = choice => {
        const transfer = new DataTransfer();
        if (files[choice]) transfer.items.add(files[choice]);
        input.files = transfer.files;
        form.querySelector(`input[name="cover_choice"][value="${choice}"]`).checked = true;
        preview.src = urls[choice] || '';
        preview.hidden = !files[choice];
        slot.classList.toggle('has-image', !!files[choice]);
    };
    const checkedChoice = () => form.querySelector('input[name="cover_choice"]:checked')?.value;
    // The server checks the extension, and a pasted image may arrive without one.
    const upload = file => {
        const name = /\.\w+$/.test(file.name) ? file.name : `cover.${file.type.split('/')[1]}`;
        setFile('upload', new File([file], name, { type: file.type }));
        uploadThumb.src = urls.upload;
        uploadThumb.hidden = false;
        uploadRow.classList.add('has-image');
        uploadName.textContent = name;
        select('upload');
    };
    const take = fileList => {
        const image = [...fileList].find(file => file.type.startsWith('image/'));
        if (image) upload(image);
        return !!image;
    };

    form.addEventListener('change', event => {
        if (event.target.name !== 'cover_choice') return;
        // Picking the upload row with nothing uploaded yet opens the file picker.
        if (event.target.value === 'upload' && !files.upload) input.click();
        select(event.target.value);
    });
    uploadRow.querySelector('[data-cover-browse]')?.addEventListener('click', () => input.click());
    // A cancelled picker empties the input, so put back whichever row is chosen.
    input.addEventListener('change', () => {
        if (input.files[0]) upload(input.files[0]);
        else if (checkedChoice()) select(checkedChoice());
    });
    form.querySelectorAll('[data-cover-drop]').forEach(target => {
        target.addEventListener('dragover', event => {
            event.preventDefault();
            target.classList.add('is-over');
        });
        target.addEventListener('dragleave', () => target.classList.remove('is-over'));
        target.addEventListener('drop', event => {
            event.preventDefault();
            target.classList.remove('is-over');
            take(event.dataTransfer.files);
        });
    });
    document.addEventListener('paste', event => {
        if (event.clipboardData && take(event.clipboardData.files)) event.preventDefault();
    });

    // Amazon sends a tiny GIF when it has no cover for the ISBN; the row stays hidden then.
    const suggestion = suggestedRow?.dataset.coverSuggestion;
    if (suggestion) {
        fetch(suggestion)
            .then(response => (response.ok ? response.blob() : null))
            .then(blob => {
                if (!blob || blob.type !== 'image/jpeg' || blob.size < 1000) return;
                setFile('suggested', new File([blob], 'amazon-cover.jpg', { type: blob.type }));
                suggestedRow.querySelector('[data-cover-suggested-thumb]').src = urls.suggested;
                suggestedRow.hidden = false;
            })
            .catch(() => {});
    }
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
 * Drop the "Save and next" receipt from the URL, so a reload doesn't show its callout again.
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
 * Show a spinner on the pressed project link while the next page loads.
 * @param {HTMLElement} rail - a ``[data-nav-loading]`` nav
 * @returns {void}
 */
function initNavLoading(rail) {
    rail.addEventListener('click', e => {
        const link = e.target.closest('a[href]');
        if (!link || link.hasAttribute('aria-current')) return;
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

/**
 * Ask before a form on the project admin page posts, with the dialog text from the ``<template>`` it names.
 * Without the script the form posts straight away, which the server allows.
 * @param {HTMLFormElement} form - a ``form[data-confirm]``
 * @returns {void}
 */
function initConfirmForm(form) {
    const template = document.getElementById(form.dataset.confirm);
    if (!template) return;
    let confirmed = false;
    form.addEventListener('submit', async e => {
        if (confirmed) return;
        e.preventDefault();
        if (await confirmFromTemplate(template, { destructive: template.dataset.destructive !== 'false' })) {
            confirmed = true;
            form.submit();
        }
    });
}

/**
 * A date input's Clear button: empties the date, and shows only while there is one to clear.
 * @param {HTMLElement} button - an element marked ``data-clear-date`` with the input's id
 * @returns {void}
 */
function initDateClear(button) {
    const input = document.getElementById(button.dataset.clearDate);
    if (!input) return;
    const sync = () => {
        button.hidden = !input.value;
    };
    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
    button.addEventListener('click', () => {
        input.value = '';
        sync();
        input.focus();
    });
    sync();
}

/**
 * The create form's goal: follows the details ticked (lower for ones many books lack) until the
 * person types their own, then offers the suggestion as a one-click button.
 * @param {HTMLInputElement} input - the goal input, carrying ``data-goal-rule``
 * @returns {void}
 */
function initGoalSuggestion(input) {
    const form = input.form;
    const line = form.querySelector('[data-goal-suggestion]');
    const use = form.querySelector('[data-goal-use]');
    const rule = JSON.parse(input.dataset.goalRule);
    const suggest = () => {
        const chosen = [...form.querySelectorAll('input[name="fields"]:checked')].map(box => box.value);
        const hard = chosen.filter(field => rule.hard.includes(field));
        if (!hard.length) return rule.default;
        return hard.length === chosen.length ? rule.all : rule.some;
    };
    // A value that isn't the suggestion was typed, here or before an error sent the form back.
    let typed = input.value !== String(suggest());
    const sync = () => {
        const goal = String(suggest());
        if (!typed) input.value = goal;
        use.textContent = `${goal}%`;
        line.hidden = !typed || input.value === goal;
    };
    input.addEventListener('input', () => {
        typed = true;
        sync();
    });
    form.addEventListener('change', event => {
        if (event.target.name === 'fields') sync();
    });
    use.addEventListener('click', () => {
        typed = false;
        sync();
    });
    sync();
}

/**
 * The create form's summary: restates the books and details as they're chosen, and keeps Create
 * off until there is at least one of each. The server checks the form again either way.
 * @param {HTMLElement} root - the ``[data-create-summary]`` block at the foot of the form
 * @returns {void}
 */
function initCreateSummary(root) {
    const form = root.closest('form');
    const i18n = JSON.parse(root.dataset.i18n);
    const books = root.querySelector('[data-summary-books]');
    const fields = root.querySelector('[data-summary-fields]');
    const submit = root.querySelector('[data-create-submit]');
    // The server sends a string per plural category of the page's language.
    const rules = new Intl.PluralRules(document.documentElement.lang || undefined);
    const plural = (key, count) => (i18n[key][rules.select(count)] ?? i18n[key].other).replace('{count}', count.toLocaleString());
    const describeBooks = () => {
        const source = form.querySelector('input[name="source"]:checked')?.value;
        if (source === 'pasted') {
            // Split as the server splits it (booklist.split_entries).
            const count = form.elements.books.value.split(/[\s,;]+/).filter(Boolean).length;
            return count ? plural('books', count) : '';
        }
        if (source === 'list') return form.elements.list_url.value.trim() ? i18n.list : '';
        const size = Number(form.elements.size.value.trim());
        return Number.isInteger(size) && size > 0 ? plural('shelved', size) : '';
    };
    const sync = () => {
        const bookText = describeBooks();
        const chosen = [...form.querySelectorAll('input[name="fields"]:checked')].map(box => box.closest('label').textContent.trim());
        books.textContent = bookText || i18n.none;
        books.classList.toggle('is-missing', !bookText);
        fields.textContent = chosen.join(', ') || i18n.none;
        fields.classList.toggle('is-missing', !chosen.length);
        submit.disabled = !bookText || !chosen.length;
    };
    form.addEventListener('input', sync);
    form.addEventListener('change', sync);
    root.querySelector('.contrib-admin__summary').hidden = false;
    sync();
}

export function init() {
    document.querySelectorAll('[data-contribute-admin] form[data-confirm]').forEach(initConfirmForm);
    document.querySelectorAll('[data-contribute-admin] [data-clear-date]').forEach(initDateClear);
    document.querySelectorAll('[data-contribute-admin] input[data-goal-rule]').forEach(initGoalSuggestion);
    document.querySelectorAll('[data-contribute-admin] [data-create-summary]').forEach(initCreateSummary);
    document.querySelectorAll('[data-contribute-list]').forEach(root => {
        initTaskList(root);
    });
    document.querySelectorAll('[data-nav-loading]').forEach(initNavLoading);
    document.querySelectorAll('[data-feed]').forEach(initFeed);
    document.querySelectorAll('[data-intro-cookie]').forEach(initIntroDismiss);
    document.querySelectorAll('form[data-task-form]').forEach(form => {
        initSkipButton(form);
        initSiblingSuggestions(form);
        initSaveTracking(form);
        initSubmitLoading(form);
        initQuickNext(form);
        initCompanion(form);
    });
    document.querySelectorAll('[data-many-choice]').forEach(initManyChoice);
    if (document.querySelector('[data-receipt]')) clearSavedReceipt();
    document.querySelectorAll('form[data-id-form]').forEach(initIdentifierForm);
    document.querySelectorAll('form[data-cover-form]').forEach(initCoverForm);
    document.querySelectorAll('[data-contribute-done]').forEach(root => hideSkippedTasks(root, '[data-same-book]'));
}
