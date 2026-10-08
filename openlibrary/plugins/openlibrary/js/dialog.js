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
 * Wires up the book preview dialog and the search-inside form.
 *
 * Listeners are delegated on document so triggers added later (e.g. from
 * lazy-loaded carousels) work without re-initializing.
 *
 * @param {AbortSignal} signal Removes this set's listeners when aborted.
 */
function initPreviewDialogs(signal) {
    // Open the preview dialog for the clicked book.
    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-book-preview]');
        if (!button) return;
        event.preventDefault();
        trackEvent('BookOptions', 'Preview');

        const dialog = document.getElementById('bookPreview');
        if (!dialog) return;
        const iframe = dialog.querySelector('iframe');
        if (iframe) iframe.src = button.dataset.iframeSrc;
        const link = dialog.querySelector('.learn-more a');
        if (link) link.href = button.dataset.iframeLink;
        dialog.open = true;
    }, { signal });

    // Drop the preview embed when the dialog closes, so a stale book's
    // iframe can't keep loading in the background.
    document.getElementById('bookPreview')?.addEventListener('ol-close', function() {
        const iframe = this.querySelector('iframe');
        if (iframe) iframe.src = '';
    }, { signal });

    // Expand the "Search Inside" button into its input form.
    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-search-trigger]');
        if (!trigger) return;
        event.preventDefault();
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
    }, { signal });

    // Escape collapses the form back to the button state.
    document.addEventListener('keydown', (event) => {
        const input = event.target.closest('.search-inside-input');
        if (!input || event.key !== 'Escape') return;
        collapseSearchForm(input.closest('.cta-button-group'));
        event.stopPropagation();
    }, { signal });

    // The cancel (×) button collapses the form back.
    document.addEventListener('click', (event) => {
        const cancel = event.target.closest('.search-cancel-btn');
        if (!cancel) return;
        event.preventDefault();
        collapseSearchForm(cancel.closest('.cta-button-group'));
    }, { signal });

    // Submitting the form runs the query inside the preview dialog.
    document.addEventListener('submit', (event) => {
        const form = event.target.closest('.search-inside-form');
        if (!form) return;
        event.preventDefault();
        const query = form.querySelector('.search-inside-input')?.value ?? '';
        const ocaid = form.dataset.ocaid;

        const dialog = document.getElementById('bookPreview');
        if (dialog) {
            const iframe = dialog.querySelector('iframe');
            if (iframe) {
                iframe.src = `https://archive.org/details/${ocaid}?view=theater&wrapper=false&q=${encodeURIComponent(query)}`;
            }
            const link = dialog.querySelector('.learn-more a');
            if (link) link.href = `https://archive.org/details/${ocaid}`;
            dialog.open = true;
        }
        collapseSearchForm(form.closest('.cta-button-group'));
    }, { signal });
}

let dialogController;

/**
 * Wires up dialog triggers.
 *
 * An element with class `dialog--open` opens the <ol-dialog> named by its
 * `aria-controls` attribute, e.g. the cover preview and add/manage cover
 * dialogs. Closing is the component's job (close button, backdrop, Escape),
 * so no close wiring is needed here.
 */
export function initDialogs() {
    dialogController?.abort();
    dialogController = new AbortController();
    const { signal } = dialogController;

    document.querySelectorAll('.dialog--open').forEach((trigger) => {
        const getTarget = () => document.getElementById(trigger.getAttribute('aria-controls'));
        // Start fetching the dialog's lazy images on hover/focus so they're loaded by the click.
        const warmImages = () => getTarget()?.querySelectorAll('img[loading="lazy"]').forEach((img) => { img.loading = 'eager'; });
        trigger.addEventListener('pointerenter', warmImages, { once: true, signal });
        trigger.addEventListener('focus', warmImages, { once: true, signal });
        trigger.addEventListener('click', (e) => {
            const target = getTarget();
            if (target?.tagName !== 'OL-DIALOG') {
                return;
            }
            e.preventDefault();
            target.open = true;
        }, { signal });
    });

    initPreviewDialogs(signal);
}
