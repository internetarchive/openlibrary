/**
 * The home page's top for a signed-in reader: the book they have in hand, what
 * else is in progress, and their Want to Read books with a copy free now.
 *
 * The home page is cached and the same for everyone, so the reader's own part
 * is fetched here and put in the slot home/index.html leaves for it. Signed
 * out, or with nothing to show, the slot is removed.
 *
 * @module home-member
 */
import { SHELF } from '../../../components/lit/utils/books-api.js';
import { buildPartialsUrl } from './utils';

/**
 * @param {HTMLElement} slot - `.home-member-slot`
 * @returns {Promise<void>}
 */
export async function initHomeMember(slot) {
    if (!document.body.dataset.userKey) {
        slot.remove();
        return;
    }
    try {
        const resp = await fetch(buildPartialsUrl('HomeMember'));
        if (!resp.ok) throw new Error(`HomeMember: ${resp.status}`);
        const html = ((await resp.json()).partials || '').trim();
        if (!html) {
            slot.remove();
            return;
        }
        slot.innerHTML = html;
        watchShelves(slot);
    } catch {
        // The rest of the home page stands without it.
        slot.remove();
    }
}

/**
 * Keeps the books in progress honest after a shelf change made here: a book
 * that has left Currently Reading stays in place, dimmed, and says where it
 * went, so the menu beside it can still bring it back. The next load drops it.
 *
 * @param {HTMLElement} slot
 */
function watchShelves(slot) {
    const section = slot.querySelector('.home-now');
    if (!section) return;
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
