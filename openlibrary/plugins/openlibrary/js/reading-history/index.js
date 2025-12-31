// Tracks when users click "Borrow" or "Read" buttons
// Stores edition IDs in localStorage for the reading history carousel

import { ReadingHistory } from './ReadingHistory';
import { ReadingHistoryCarousel } from './ReadingHistoryCarousel';

// Try to extract edition ID from a URL or DOM element
function extractEditionId(source) {
    if (source instanceof HTMLElement) {
        // Check data attributes first (most reliable)
        const editionId = source.getAttribute('data-edition-id') ||
                          source.getAttribute('data-edition-key');
        if (editionId) {
            // If it's already an OLID like "OL123M", return it
            if (editionId.match(/^OL[A-Z0-9]+[MWE]?$/)) {
                return editionId;
            }
            // If it's a full key like "/books/OL123M", extract the ID
            const keyMatch = editionId.match(/\/books\/(OL[A-Z0-9]+[MWE]?)/);
            if (keyMatch) {
                return keyMatch[1];
            }
        }
        // Fall back to href attribute
        const href = source.getAttribute('href');
        if (href) {
            return extractEditionId(href);
        }
    } else if (typeof source === 'string') {
        // Try to match OLID in URL like /books/OL123456M/...
        const match = source.match(/\/books\/(OL[A-Z0-9]+[MWE]?)/);
        if (match) {
            return match[1];
        }
        // Try /books/{key}/-/borrow format
        const altMatch = source.match(/\/books\/([^\/]+)\/-\/borrow/);
        if (altMatch) {
            const key = altMatch[1];
            // If the key is already an OLID, use it
            if (key.match(/^OL[A-Z0-9]+[MWE]?$/)) {
                return key;
            }
        }
        // Note: /borrow/ia/{ocaid} URLs don't have edition IDs, would need to resolve separately
    }
    return null;
}

// Set up click tracking for borrow/read buttons
export function initReadingHistoryTracking() {
    if (!ReadingHistory.isAvailable()) {
        console.warn('localStorage not available, reading history tracking disabled');
        return;
    }

    // Track clicks on borrow/read buttons
    $(document).on('click', '.cta-btn--borrow, .cta-btn--read, a[href*="/borrow"]', function(e) {
        const $link = $(this);
        const href = $link.attr('href') || '';

        // Make sure it's actually a borrow/read action
        if (href.includes('/borrow') || href.includes('action=read') || href.includes('action=borrow')) {
            const editionId = extractEditionId(href) || extractEditionId(this);

            if (editionId) {
                ReadingHistory.add(editionId);
            }
        }
    });

    // Also handle external read buttons (for open access books)
    $(document).on('click', '.cta-btn--external.cta-btn--read, a[href*="action=read"]', function(e) {
        const $link = $(this);
        const href = $link.attr('href') || '';

        if (href.includes('action=read')) {
            const editionId = extractEditionId(href) || extractEditionId(this);

            if (editionId) {
                ReadingHistory.add(editionId);
            }
        }
    });
}

// Initialize the carousel on My Books page
export function initReadingHistoryCarousel() {
    const container = document.getElementById('reading-history-carousel-container');
    if (container) {
        const carousel = new ReadingHistoryCarousel(container);
        carousel.init();
    }
}

export { ReadingHistory, ReadingHistoryCarousel };

