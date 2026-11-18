/**
 * The home page's top for a signed-in reader: the book they have in hand, what
 * else is in progress, and their Want to Read books with a copy free now.
 *
 * The home page is cached and the same for everyone, so the reader's own part
 * is fetched here, in two halves, and put in the skeleton home/index.html
 * leaves for it. Signed out, or with nothing to show, the slot is removed.
 *
 * @module home-member
 */
import { SHELF } from '../../../components/lit/utils/books-api.js';
import { buildPartialsUrl } from './utils';

/** The section's halves, each fetched on its own so the quicker one doesn't wait for the other. */
const PARTS = ['reading', 'want'];

/**
 * @param {HTMLElement} slot - `.home-member-slot`, holding the section's skeleton
 * @returns {Promise<void>}
 */
export async function initHomeMember(slot) {
    const section = slot.querySelector('.home-now');
    if (!document.body.dataset.userKey || !section) {
        slot.remove();
        return;
    }
    const shown = await Promise.all(PARTS.map(part => loadPart(section, part)));
    if (!shown.some(Boolean)) {
        slot.remove();
        return;
    }
    section.classList.remove('home-now--skeleton');
    section.querySelector('.home-now__loading')?.remove();
}

/**
 * Fetches one half and puts it in place of its skeleton. A half that is empty,
 * or fails, gives up its place: the rest of the home page stands without it.
 *
 * @param {HTMLElement} section - `.home-now`
 * @param {string} part - one of PARTS
 * @returns {Promise<boolean>} whether the half has anything to show
 */
async function loadPart(section, part) {
    const fetched = document.createElement('template');
    try {
        const resp = await fetch(buildPartialsUrl('HomeMember', { part }));
        if (resp.ok) fetched.innerHTML = (await resp.json()).partials || '';
    } catch {
        // Left empty.
    }
    const placeholder = section.querySelector(`.home-now__${part}`);
    const content = fetched.content.querySelector(`.home-now__${part}`);
    if (!content) {
        placeholder.remove();
        section.classList.add(`home-now--no-${part}`);
        return false;
    }
    placeholder.replaceWith(content);
    // The heading comes with each half; the first to arrive supplies it.
    const head = section.querySelector('.home-now__head');
    const fetchedHead = fetched.content.querySelector('.home-now__head');
    if (fetchedHead && head.hasAttribute('aria-hidden')) {
        head.replaceWith(fetchedHead);
        section.setAttribute('aria-labelledby', 'home-now-title');
    }
    if (part === 'reading') watchShelves(content);
    return true;
}

/**
 * Keeps the books in progress honest after a shelf change made here: a book
 * that has left Currently Reading stays in place, dimmed, and says where it
 * went, so the menu beside it can still bring it back. The next load drops it.
 *
 * @param {HTMLElement} section - `.home-now__reading`
 */
function watchShelves(section) {
    const labels = JSON.parse(section.dataset.movedLabels || '{}');

    document.addEventListener('ol-book-state-change', e => {
        const { key, shelf } = e.detail;
        for (const row of section.querySelectorAll(`[data-work-key="${key}"]`)) {
            const moved = shelf !== SHELF.CURRENTLY_READING;
            row.classList.toggle('is-moved', moved);
            const note = row.querySelector('.home-now__moved');
            if (note) note.textContent = moved ? labels[shelf ?? 'none'] || '' : '';
        }
    });
}
