import { buildPartialsUrl } from './utils';

/**
 * Fills live prices into the page-rendered affiliate store rows.
 *
 * Prices are an enhancement: the store links are already on the page, so
 * nothing is shown while prices load, and a failed lookup leaves the rows as-is.
 *
 * @param {NodeList<HTMLElement>} affiliateLinksSections Sections carrying a price lookup (data-title/isbn/asin)
 */
export async function initAffiliateLinks(affiliateLinksSections) {
    const { title, isbn, asin } = affiliateLinksSections[0].dataset;
    let partials;
    try {
        const resp = await fetch(buildPartialsUrl('AffiliateLinks', { title, isbn, asin, prices: true }));
        if (!resp.ok) return;
        partials = (await resp.json()).partials;
    } catch {
        return;
    }

    const template = document.createElement('template');
    template.innerHTML = partials;
    const prices = template.content.querySelectorAll('[data-store] .buy-option__price');
    // Insert into the existing rows rather than swapping them, so focus and hover survive.
    for (const price of prices) {
        const store = price.closest('[data-store]').dataset.store;
        for (const section of affiliateLinksSections) {
            const link = section.querySelector(`[data-store="${store}"] .buy-option__link`);
            if (link && !link.querySelector('.buy-option__price')) {
                link.append(price.cloneNode(true));
            }
        }
    }
}
