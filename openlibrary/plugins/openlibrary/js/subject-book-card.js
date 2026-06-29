/**
 * "More info" book-card popover for subject-page carousels.
 *
 * Clicking a cover's "More info" action opens a small card (Wikipedia-style
 * preview) with the cover, title, byline, year, a clipped description, and
 * actions (Add to list, Read/Preview) plus a link to the work page.
 *
 * Title/byline/year/cover and the read action all come from data-* attributes on
 * the trigger (already in the carousel payload — no query). Only the description
 * is fetched lazily, from the work's `.json`, and cached per work.
 *
 * The card is rendered into a single shared element promoted to the browser's
 * top layer via the Popover API. That's deliberate: the carousel's `.track` is
 * `transform`ed, which traps `position: fixed`; the top layer escapes it (the
 * same reason ol-tooltip uses the Popover API here).
 */

const POPOVER_WIDTH = 360;
const MOBILE_MAX = 600;
const GAP = 8;

let popoverEl = null;
let currentTrigger = null;
const descCache = new Map();

function templateNode() {
    const tpl = document.getElementById('subject-book-card');
    return tpl ? tpl.content.firstElementChild.cloneNode(true) : null;
}

function ensurePopover() {
    if (popoverEl) {
        return popoverEl;
    }
    popoverEl = document.createElement('div');
    popoverEl.className = 'book-card-popover';
    // "manual" = top layer without auto light-dismiss; we manage dismissal so a
    // click that opens the popover can't immediately close it.
    popoverEl.setAttribute('popover', 'manual');
    document.body.appendChild(popoverEl);
    return popoverEl;
}

function hide() {
    if (popoverEl && popoverEl.matches(':popover-open')) {
        popoverEl.hidePopover();
    }
    teardownDismiss();
    const trigger = currentTrigger;
    currentTrigger = null;
    if (trigger && typeof trigger.focus === 'function') {
        trigger.focus();
    }
}

function onKeydown(e) {
    if (e.key === 'Escape') {
        e.stopPropagation();
        hide();
    }
}

function onPointerDown(e) {
    if (!popoverEl) {
        return;
    }
    if (popoverEl.contains(e.target) || (currentTrigger && currentTrigger.contains(e.target))) {
        return;
    }
    hide();
}

function onReflow() {
    // Keep it simple: any scroll/resize dismisses rather than chasing the anchor.
    hide();
}

function setupDismiss() {
    document.addEventListener('keydown', onKeydown, true);
    document.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('scroll', onReflow, true);
    window.addEventListener('resize', onReflow);
}

function teardownDismiss() {
    document.removeEventListener('keydown', onKeydown, true);
    document.removeEventListener('pointerdown', onPointerDown, true);
    window.removeEventListener('scroll', onReflow, true);
    window.removeEventListener('resize', onReflow);
}

/** Position the (already-shown) popover next to its trigger, or as a sheet. */
function position(trigger) {
    const mobile = window.innerWidth <= MOBILE_MAX;
    popoverEl.classList.toggle('book-card-popover--sheet', mobile);
    if (mobile) {
        popoverEl.style.left = '';
        popoverEl.style.top = '';
        return;
    }
    const rect = trigger.getBoundingClientRect();
    const width = popoverEl.offsetWidth || POPOVER_WIDTH;
    const left = Math.min(Math.max(12, rect.left), window.innerWidth - width - 12);
    popoverEl.style.left = `${left}px`;
    popoverEl.style.top = `${rect.bottom + GAP}px`;
    // Flip above the trigger if it would overflow the bottom of the viewport.
    const height = popoverEl.offsetHeight;
    if (rect.bottom + GAP + height > window.innerHeight - 12) {
        popoverEl.style.top = `${Math.max(12, rect.top - GAP - height)}px`;
    }
}

async function loadDescription(card, workKey) {
    const descEl = card.querySelector('.book-card__desc');
    if (!descEl || !workKey) {
        descEl && descEl.remove();
        return;
    }
    let text = descCache.get(workKey);
    if (text === undefined) {
        descEl.dataset.state = 'loading';
        try {
            const resp = await fetch(`${workKey}.json`);
            const work = await resp.json();
            const desc = work && work.description;
            text = typeof desc === 'string' ? desc : (desc && desc.value) || '';
        } catch {
            text = '';
        }
        descCache.set(workKey, text);
    }
    // Bail if the user already moved on to a different book.
    if (!descEl.isConnected) {
        return;
    }
    if (text) {
        // textContent (not innerHTML): descriptions are user content / markdown.
        descEl.textContent = text;
        descEl.dataset.state = 'loaded';
        if (currentTrigger) {
            position(currentTrigger);
        }
    } else {
        descEl.remove();
    }
}

function fill(card, data) {
    card.querySelector('.book-card__title').textContent = data.title || '';

    const authorsEl = card.querySelector('.book-card__authors');
    const byEl = card.querySelector('.book-card__by');
    if (data.authors) {
        authorsEl.textContent = data.authors;
    } else {
        byEl && byEl.remove();
        authorsEl && authorsEl.remove();
    }

    const yearEl = card.querySelector('.book-card__year');
    if (data.year) {
        yearEl.textContent = `(${data.year})`;
    } else {
        yearEl && yearEl.remove();
    }

    const cover = card.querySelector('.book-card__cover');
    if (data.cover) {
        cover.src = data.cover;
    } else {
        cover && cover.remove();
    }

    const save = card.querySelector('.js-cover-save');
    if (save) {
        save.dataset.workKey = data.workKey || data.url || '';
    }

    const read = card.querySelector('.book-card__read');
    if (read) {
        if (data.readLabel && data.readHref) {
            read.textContent = data.readLabel;
            read.href = data.readHref;
            read.hidden = false;
        } else {
            read.remove();
        }
    }

    const page = card.querySelector('.book-card__page');
    if (page) {
        page.href = data.url || data.workKey || '#';
    }

    const close = card.querySelector('.book-card__close');
    if (close) {
        close.addEventListener('click', hide);
    }
}

function open(trigger) {
    const card = templateNode();
    if (!card) {
        return; // not a subject page (no template) — let the cover link work
    }
    const pop = ensurePopover();
    pop.innerHTML = '';
    fill(card, trigger.dataset);
    pop.appendChild(card);
    currentTrigger = trigger;

    position(trigger);
    if (pop.showPopover && !pop.matches(':popover-open')) {
        pop.showPopover();
    }
    position(trigger); // re-run now that it's laid out (for flip/measure)
    setupDismiss();

    const close = card.querySelector('.book-card__close');
    if (close) {
        close.focus();
    }

    loadDescription(card, trigger.dataset.workKey || trigger.dataset.url);
}

export function initBookCardPopover() {
    if (!document.getElementById('subject-book-card')) {
        return;
    }
    document.addEventListener('click', (e) => {
        const trigger = e.target.closest('.js-cover-moreinfo');
        if (!trigger) {
            return;
        }
        e.preventDefault();
        if (currentTrigger === trigger && popoverEl && popoverEl.matches(':popover-open')) {
            hide();
        } else {
            open(trigger);
        }
    });
}
