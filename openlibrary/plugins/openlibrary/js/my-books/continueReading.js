import { getHistory } from './store/readingHistory';

/**
 * Initializes the "Continue Reading" client-side carousel on the My Books page
 * using reading history stored in localStorage (ol_read_history).
 */
export function initContinueReading() {
    const container = document.querySelector('#continue-reading-container');
    if (!container) return;

    const history = getHistory();
    if (!history || !history.length) return;

    const carouselTrack = container.querySelector('.continue-reading-carousel');
    if (!carouselTrack) return;

    // Clear existing content
    carouselTrack.innerHTML = '';

    const fallbackCover = 'https://openlibrary.org/static/images/icons/avatar_book.png';

    history.forEach(item => {
        const card = document.createElement('div');
        card.className = 'book carousel__item';
        card.style.textAlign = 'center';

        const workUrl = item.workKey || (item.olid ? `/works/${item.olid}` : '#');
        let coverUrl = fallbackCover;
        if (item.coverId && item.coverId !== -1) {
            coverUrl = `https://covers.openlibrary.org/b/id/${item.coverId}-M.jpg`;
        } else if (item.coverEditionKey) {
            coverUrl = `https://covers.openlibrary.org/b/olid/${item.coverEditionKey}-M.jpg`;
        }

        const readUrl = item.ocaid ? `/borrow/ia/${item.ocaid}?ref=ol` : workUrl;
        const authorLine = Array.isArray(item.authorNames) && item.authorNames.length > 0
            ? `by ${item.authorNames.join(', ')}`
            : '';

        card.innerHTML = `
            <div class="book-cover" style="position: relative; display: inline-block; margin: 0 auto; border-radius: 4px; max-width: 100%;">
                <a href="${escapeHtml(workUrl)}">
                    <img class="bookcover" loading="lazy" title="${escapeHtml(item.title)} ${escapeHtml(authorLine)}" alt="${escapeHtml(item.title)}" src="${escapeHtml(coverUrl)}" />
                </a>
            </div>
            <div class="ol-action-row">
                <div class="ol-macro-wrapper">
                    <div class="cta-button-group">
                        <a href="${escapeHtml(readUrl)}" class="cta-btn cta-btn--available" data-ol-action="read">
                            Read
                        </a>
                    </div>
                </div>
            </div>
        `;

        carouselTrack.appendChild(card);
    });

    // Make section visible
    container.style.display = 'block';
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
