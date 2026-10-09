/**
 * First Edits (/contribute) page behavior.
 *
 * Phase 1 saves nothing server-side. Progress within a browser session is a
 * list of task keys in sessionStorage so answered and skipped tasks drop out
 * of the list and the receipt can offer the next open one.
 */

import { parseLccn, isValidLccn, parseOclc, isValidOclc } from './idValidation';

const STORAGE_KEY = 'ol-first-edits-done';

// Same normalization the server applies, so the verdict on screen matches what is stored.
const ID_RULES = {
    lccn: { parse: parseLccn, isValid: isValidLccn },
    oclc_numbers: { parse: parseOclc, isValid: isValidOclc },
};

function readDone() {
    try {
        return new Set(JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]'));
    } catch (e) {
        return new Set();
    }
}

function markDone(key) {
    if (!key) return;
    const done = readDone();
    done.add(key);
    try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...done]));
    } catch (e) {
        // Private mode or blocked storage: the walkthrough still works, just without memory.
    }
}

function initList(root) {
    const done = readDone();
    root.querySelectorAll('[data-task-key]').forEach((el) => {
        if (done.has(el.dataset.taskKey)) el.hidden = true;
    });
    root.querySelectorAll('[data-book-row]').forEach((row) => {
        const open = row.querySelectorAll('[data-task-key]:not([hidden])');
        if (!open.length) row.hidden = true;
    });
    const rows = root.querySelectorAll('[data-book-row]:not([hidden])');
    const empty = root.querySelector('[data-list-empty]');
    if (empty) empty.hidden = rows.length > 0;
}

const INTRO_KEY = 'ol-contribute-intro-hidden';

function initIntro(root) {
    const intro = root.querySelector('[data-intro]');
    if (!intro) return;
    try {
        if (localStorage.getItem(INTRO_KEY)) intro.hidden = true;
    } catch (e) {
        // Blocked storage: the introduction just stays.
    }
    intro.querySelector('[data-intro-close]')?.addEventListener('click', () => {
        intro.hidden = true;
        try {
            localStorage.setItem(INTRO_KEY, '1');
        } catch (e) {
            // Hidden for this visit only.
        }
    });
}

function openTasks(root) {
    return [...root.querySelectorAll('[data-book-row]:not([hidden]) [data-task-key]:not([hidden])')];
}

// Weighted like the server's pick, so busier books with more valuable gaps come up more often.
function weightedPick(tasks, avoidKey) {
    const pool = tasks.length > 1 ? tasks.filter((el) => el.dataset.taskKey !== avoidKey) : tasks;
    const weights = pool.map((el) => Math.max(Number(el.dataset.weight) || 1, 1));
    let r = Math.random() * weights.reduce((a, b) => a + b, 0);
    return pool.find((_el, i) => (r -= weights[i]) <= 0) || pool[pool.length - 1];
}

/**
 * "Surprise me" previews a pick from the tasks still on screen, so one
 * already answered this session is never offered again. With nothing on
 * screen (or no JS) the link falls through to /contribute/one.
 */
function initOneTask(root) {
    const button = root.querySelector('[data-one-task]');
    const card = root.querySelector('[data-pick]');
    if (!button || !card) return;
    let current = '';

    const show = (task) => {
        const row = task.closest('[data-book-row]');
        const cover = row.querySelector('.fe-book__cover');
        card.querySelector('[data-pick-cover]').replaceChildren(cover ? cover.cloneNode(true) : '');
        card.querySelector('[data-pick-question]').textContent = task.dataset.question || task.textContent.trim();
        const title = row.querySelector('.fe-book__title')?.textContent.trim() || '';
        const authors = row.querySelector('.fe-book__authors')?.textContent.trim() || '';
        card.querySelector('[data-pick-book]').textContent = authors ? `${title} · ${authors}` : title;
        card.querySelector('[data-pick-why]').textContent = row.dataset.why || '';
        card.querySelector('[data-pick-start]').setAttribute('href', task.querySelector('a').href);
        current = task.dataset.taskKey;
        card.hidden = false;
        card.querySelector('[data-pick-question]').focus({ preventScroll: true });
        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    };

    button.addEventListener('click', (event) => {
        const tasks = openTasks(root);
        if (!tasks.length) return;
        event.preventDefault();
        show(weightedPick(tasks, current));
    });
    card.querySelector('[data-pick-again]')?.addEventListener('click', () => {
        const tasks = openTasks(root);
        if (tasks.length) show(weightedPick(tasks, current));
    });
}

function initTaskForm(root) {
    const form = root.querySelector('form[data-task-form]');
    if (form) {
        form.addEventListener('submit', () => markDone(form.dataset.taskKey));
        const skip = form.querySelector('[data-skip]');
        if (skip) {
            skip.addEventListener('click', () => markDone(form.dataset.taskKey));
        }
    }
}

/**
 * "Other editions say" chips fill the answer with a sibling's value. The chip
 * matching the current answer shows selected; clicking it again clears it.
 */
function initSuggestions(form) {
    const group = form.querySelector('[data-suggest]');
    const control = form.querySelector('#fe-other-value');
    if (!group || !control) return;
    const isPicker = control.tagName === 'OL-OPTIONS-POPOVER';
    const current = () => (isPicker ? control.selected : control.value.trim());
    const chips = [...group.querySelectorAll('ol-chip')];
    const sync = () => chips.forEach((chip) => { chip.selected = chip.dataset.value === current(); });

    group.addEventListener('ol-chip-select', (event) => {
        const chip = event.target.closest('ol-chip');
        const value = event.detail.selected ? chip.dataset.value : '';
        if (isPicker) control.selected = value;
        else control.value = value;
        sync();
    });
    control.addEventListener(isPicker ? 'ol-options-popover-change' : 'input', sync);
    sync();
}

/**
 * Identifier tasks check the number as it's typed: a wrong identifier
 * corrupts record matching silently.
 */
function initIdForm(form) {
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
            verdict.textContent = parsed === raw
                ? msg.msgOk
                : msg.msgTidied.replace('__VALUE__', parsed);
        } else {
            verdict.dataset.state = 'bad';
            verdict.textContent = /https?:|\//.test(raw) ? msg.msgUrl : msg.msgBad;
        }
    });
}

function initDone(root) {
    markDone(root.dataset.taskKey);
    const done = readDone();
    root.querySelectorAll('[data-task-key]').forEach((el) => {
        if (done.has(el.dataset.taskKey)) el.hidden = true;
    });
    const sameBook = root.querySelector('[data-same-book]');
    if (sameBook && !sameBook.querySelector('[data-task-key]:not([hidden])')) sameBook.hidden = true;
}

export function init() {
    document.querySelectorAll('[data-contribute-list]').forEach((root) => {
        initList(root);
        initIntro(root);
        initOneTask(root);
    });
    document.querySelectorAll('[data-contribute-task]').forEach(initTaskForm);
    document.querySelectorAll('form[data-task-form]').forEach(initSuggestions);
    document.querySelectorAll('form[data-id-form]').forEach(initIdForm);
    document.querySelectorAll('[data-contribute-done]').forEach(initDone);
}
