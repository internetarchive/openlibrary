/**
 * Browser-mode tests for smooth-scroll-links.js. Needs real layout: the
 * behaviour under test is whether a native fragment jump animates.
 */
import { afterEach, expect, test } from 'vitest';
import { initSmoothScrollLinks } from '../../openlibrary/plugins/openlibrary/js/smooth-scroll-links.js';

const frame = () => new Promise(requestAnimationFrame);
let fixture;

/** Mount a tall page with a link to a far-down target; return the link. */
function mountPage({ optIn }) {
    fixture = document.createElement('div');
    fixture.innerHTML = `
        <a href="#far-target" ${optIn ? 'data-ol-smooth-scroll' : ''} style="position: fixed; top: 0">Jump</a>
        <div style="height: 6000px"></div>
        <div id="far-target" style="height: 10px"></div>
        <div style="height: 2000px"></div>
    `;
    document.body.append(fixture);
    return fixture.querySelector('a');
}

afterEach(() => {
    fixture?.remove();
    history.replaceState(null, '', location.pathname + location.search);
    window.scrollTo({ top: 0, behavior: 'instant' });
});

test('an opted-in link animates its fragment jump', async() => {
    const link = mountPage({ optIn: true });
    initSmoothScrollLinks([link]);

    link.click();
    await frame();
    await frame();

    // Mid-animation: nowhere near the ~6000px target yet.
    expect(window.scrollY).toBeLessThan(1000);
    expect(location.hash).toBe('#far-target');

    // Cleared once the scroll settles, so unrelated scrolls stay instant.
    await new Promise((resolve) => document.addEventListener('scrollend', resolve, { once: true }));
    await new Promise((resolve) => setTimeout(resolve));
    expect(window.scrollY).toBe(6000);
    expect(document.documentElement.style.scrollBehavior).toBe('');
});

test('a link without the attribute jumps instantly', async() => {
    const link = mountPage({ optIn: false });

    link.click();
    await frame();

    expect(window.scrollY).toBeGreaterThan(5000);
});
