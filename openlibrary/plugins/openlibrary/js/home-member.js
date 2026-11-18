/**
 * The home page's top for a signed-in reader: the book they have in hand, their
 * loans and holds, and their Want to Read books with a copy free now.
 *
 * The home page is cached and the same for everyone, so the reader's own part
 * is fetched here and put in the slot home/index.html leaves for it. Signed
 * out, or with nothing to show, the slot is removed.
 *
 * @module home-member
 */
import { initNativeCarousels } from './carousel/native.js';
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
        initNativeCarousels(slot.querySelectorAll('ol-carousel'));
    } catch {
        // The rest of the home page stands without it.
        slot.remove();
    }
}
