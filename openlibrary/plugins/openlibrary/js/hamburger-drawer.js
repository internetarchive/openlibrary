/**
 * Wires the header's hamburger button to the <ol-drawer> menu it opens, and
 * gives pressed menu rows a loading treatment while the next page loads.
 *
 * @param {HTMLElement} trigger The `.hamburger-trigger` button.
 * @param {HTMLElement} drawer The `<ol-drawer>` holding the menu.
 */
export function initHamburgerDrawer(trigger, drawer) {
    trigger.addEventListener('click', function() {
        drawer.open = !drawer.open;
    });
    drawer.addEventListener('ol-drawer-show', function() {
        trigger.setAttribute('aria-expanded', 'true');
    });
    drawer.addEventListener('ol-drawer-after-hide', function() {
        trigger.setAttribute('aria-expanded', 'false');
    });

    // Pressing a menu link navigates the whole window; the next page can take
    // a beat to start painting. Flag the pressed row so it shows a spinner
    // and the rest dim back (mirrors the search modal's result loading
    // treatment) — the drawer stays open until the new page takes over.
    drawer.addEventListener('click', function(e) {
        const el = e.target.closest('a[href], button[type="submit"], button:not([type])');
        if (!el) return;
        // New-tab / modified / non-left clicks don't navigate this window.
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        if (el.tagName === 'A' && el.target === '_blank') return;
        const menu = drawer.querySelector('.drawer-menu');
        if (menu) menu.classList.add('is-navigating');
        el.classList.add('is-target');
        // Mark the row too, so it stays lit while its siblings dim.
        const row = el.closest('li');
        if (row) row.classList.add('is-target-row');
    });

    // Restoring from bfcache (back/forward) reuses this DOM with the spinner
    // still on the pressed row — clear it so the menu looks idle again.
    window.addEventListener('pageshow', function(e) {
        if (!e.persisted) return;
        const menu = drawer.querySelector('.drawer-menu');
        if (!menu) return;
        menu.classList.remove('is-navigating');
        menu.querySelectorAll('.is-target, .is-target-row').forEach(function(t) {
            t.classList.remove('is-target');
            t.classList.remove('is-target-row');
        });
    });
}
