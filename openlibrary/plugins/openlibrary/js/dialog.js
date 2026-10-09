// For dialog boxes (e.g. add to list, book preview)
import { trackEvent } from './ol.analytics.js';

/**
 * Collapses the search-inside form back to the button state.
 * @param {HTMLElement} btnGroup - The .cta-button-group container.
 */
function collapseSearchForm(btnGroup) {
    if (!btnGroup) return;
    const form = btnGroup.querySelector('.search-inside-form');
    const input = btnGroup.querySelector('.search-inside-input');
    if (form) form.style.display = 'none';
    if (input) input.value = '';
    btnGroup.querySelectorAll('.preview-btn, .search-inside-trigger-btn')
        .forEach(el => { el.style.display = ''; });
    btnGroup.querySelectorAll('[data-search-trigger]')
        .forEach(el => el.setAttribute('aria-expanded', 'false'));
}

/**
 * Opens the preview dialog on the given embed.
 * @param {string} src - URL for the preview iframe.
 * @param {string} href - URL for the dialog's "learn more" link.
 */
function showPreview(src, href) {
    const dialog = document.getElementById('bookPreview');
    if (!dialog) return;
    const iframe = dialog.querySelector('iframe');
    if (iframe) iframe.src = src;
    const link = dialog.querySelector('.learn-more a');
    if (link) link.href = href;
    dialog.open = true;
}

/**
 * Expands the "Search Inside" button into its input form.
 * @param {HTMLElement} trigger - The [data-search-trigger] button.
 */
function expandSearchForm(trigger) {
    trackEvent('BookOptions', 'SearchInside');
    trigger.setAttribute('aria-expanded', 'true');

    const btnGroup = trigger.closest('.cta-button-group');
    if (!btnGroup) return;
    btnGroup.querySelectorAll('.preview-btn, .search-inside-trigger-btn')
        .forEach(el => { el.style.display = 'none'; });
    const form = btnGroup.querySelector('.search-inside-form');
    if (form) {
        form.style.display = '';
        form.querySelector('.search-inside-input')?.focus();
    }
}

/**
 * Wires up the book preview dialog and the search-inside form.
 *
 * Listeners are delegated on document so triggers added later (e.g. from
 * lazy-loaded carousels) work without re-initializing.
 */
function initPreviewDialogs() {
    document.addEventListener('click', (event) => {
        const target = event.target.closest('[data-book-preview], [data-search-trigger], .search-cancel-btn');
        if (!target) return;
        event.preventDefault();
        if (target.matches('[data-book-preview]')) {
            trackEvent('BookOptions', 'Preview');
            showPreview(target.dataset.iframeSrc, target.dataset.iframeLink);
        } else if (target.matches('[data-search-trigger]')) {
            expandSearchForm(target);
        } else {
            collapseSearchForm(target.closest('.cta-button-group'));
        }
    });

    // Drop the preview embed when the dialog closes, so a stale book's
    // iframe can't keep loading in the background. Delegated so it doesn't
    // depend on which #bookPreview existed at init (partials can add copies).
    document.addEventListener('ol-close', (event) => {
        if (event.target.id !== 'bookPreview') return;
        const iframe = event.target.querySelector('iframe');
        if (iframe) iframe.src = '';
    });

    // Escape collapses the form back to the button state.
    document.addEventListener('keydown', (event) => {
        const input = event.target.closest('.search-inside-input');
        if (!input || event.key !== 'Escape') return;
        collapseSearchForm(input.closest('.cta-button-group'));
        event.stopPropagation();
    });

    // Submitting the form runs the query inside the preview dialog.
    document.addEventListener('submit', (event) => {
        const form = event.target.closest('.search-inside-form');
        if (!form) return;
        event.preventDefault();
        const query = form.querySelector('.search-inside-input')?.value ?? '';
        const ocaid = form.dataset.ocaid;

        showPreview(
            `https://archive.org/details/${ocaid}?view=theater&wrapper=false&q=${encodeURIComponent(query)}`,
            `https://archive.org/details/${ocaid}`,
        );
        collapseSearchForm(form.closest('.cta-button-group'));
    });
}

/**
 * Wires up dialog triggers.
 *
 * An element with class `dialog--open` opens the <ol-dialog> named by its
 * `aria-controls` attribute, e.g. the cover preview and add/manage cover
 * dialogs. Closing is the component's job (close button, backdrop, Escape),
 * so no close wiring is needed here.
 */
export function initDialogs() {
    document.querySelectorAll('.dialog--open').forEach((trigger) => {
        const getTarget = () => document.getElementById(trigger.getAttribute('aria-controls'));
        // Start fetching the dialog's lazy images on hover/focus so they're loaded by the click.
        const warmImages = () => getTarget()?.querySelectorAll('img[loading="lazy"]').forEach((img) => { img.loading = 'eager'; });
        trigger.addEventListener('pointerenter', warmImages, { once: true });
        trigger.addEventListener('focus', warmImages, { once: true });
        trigger.addEventListener('click', (e) => {
            const target = getTarget();
            if (target?.tagName !== 'OL-DIALOG') {
                return;
            }
            e.preventDefault();
            target.open = true;
        });
    });

    initPreviewDialogs();
}
