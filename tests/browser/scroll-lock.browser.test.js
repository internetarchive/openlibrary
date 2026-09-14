/**
 * Browser-mode tests for the body scroll-lock used by ol-popover (mobile tray),
 * ol-dialog and ol-drawer. Needs real layout: the bug is a visible scroll
 * animation, which jsdom cannot produce.
 */
import { afterEach, expect, test } from 'vitest';
import { lockBodyScroll, unlockBodyScroll } from '../../openlibrary/components/lit/utils/scroll-lock.js';

let spacer;

afterEach(() => {
    spacer?.remove();
    document.documentElement.style.scrollBehavior = '';
    window.scrollTo({ top: 0, behavior: 'instant' });
});

test('restores the scroll offset instantly despite html { scroll-behavior: smooth }', async() => {
    // Smooth scrolling on <html>, as smooth-scroll-links.js sets during a jump.
    document.documentElement.style.scrollBehavior = 'smooth';
    spacer = document.createElement('div');
    spacer.style.height = '5000px';
    document.body.append(spacer);

    window.scrollTo({ top: 1200, behavior: 'instant' });
    expect(window.scrollY).toBe(1200);

    lockBodyScroll();
    // Let layout run while locked, as when a tray stays open: the pinned body
    // collapses the document, clamping the scroll offset to 0.
    await new Promise(requestAnimationFrame);
    expect(window.scrollY).toBe(0);
    unlockBodyScroll();

    // A smooth restore would start from 0 and animate back over later frames.
    await new Promise(requestAnimationFrame);
    expect(window.scrollY).toBe(1200);
});
