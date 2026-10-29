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
    const pricedLinks = template.content.querySelectorAll('[data-store] .buy-option__link');
    // Refill the existing links rather than swapping them, so focus and hover survive.
    for (const pricedLink of pricedLinks) {
        if (!pricedLink.querySelector('.buy-option__price, .buy-option__details')) continue;
        const store = pricedLink.closest('[data-store]').dataset.store;
        for (const section of affiliateLinksSections) {
            const link = section.querySelector(`[data-store="${store}"] .buy-option__link`);
            if (link) {
                link.replaceChildren(...[...pricedLink.childNodes].map(node => node.cloneNode(true)));
            }
        }
    }
}
