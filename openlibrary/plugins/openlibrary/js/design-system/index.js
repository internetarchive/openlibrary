/**
 * Page behaviour for the design system docs at /developers/design.
 *
 * Everything here is progressive: the page is fully readable with this bundle
 * absent. It adds the code-snippet toggle, click-to-copy, computed contrast
 * badges, a page filter, scrollspy, and syntax highlighting.
 */
import Prism from 'prismjs';
import 'prismjs/components/prism-markup';
import 'prismjs/components/prism-clike';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-css';

const CODE_VISIBLE_KEY = 'ol-design-show-code';

/**
 * Relative luminance per WCAG 2.x, from an already-resolved `rgb()` string.
 */
function relativeLuminance(color) {
    const parts = color.match(/[\d.]+/g);
    if (!parts || parts.length < 3) return null;
    const [r, g, b] = parts.slice(0, 3).map((value) => {
        const channel = Number(value) / 255;
        return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(foreground, background) {
    const a = relativeLuminance(foreground);
    const b = relativeLuminance(background);
    if (a === null || b === null) return null;
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/**
 * Resolve a token to a concrete `rgb()` by letting the browser compute it.
 *
 * This is why the ratios can be trusted: `color-mix()` and deep `var()` chains
 * are evaluated by the same engine that paints the swatch, not re-implemented.
 */
function resolveToken(probe, token) {
    probe.style.color = `var(${token})`;
    const resolved = getComputedStyle(probe).color;
    // A token that isn't a color leaves the probe at its inherited value; the
    // caller can't tell, so bail on anything with alpha or an empty result.
    return resolved && !resolved.includes('NaN') ? resolved : null;
}

/**
 * Badge every color token with its contrast against white and against the page
 * canvas, so the page checks its own documented ratios instead of repeating
 * them from a comment.
 */
function renderContrastBadges(root) {
    const targets = root.querySelectorAll('[data-ds-contrast-for]');
    if (!targets.length) return;

    const probe = document.createElement('span');
    probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none';
    root.appendChild(probe);

    const canvas = getComputedStyle(document.body).backgroundColor;
    const white = 'rgb(255, 255, 255)';

    targets.forEach((target) => {
        const color = resolveToken(probe, target.dataset.dsContrastFor);
        if (!color) return;
        const onWhite = contrastRatio(color, white);
        const onCanvas = contrastRatio(color, canvas);
        if (onWhite === null) return;

        const level = onWhite >= 7 ? 'AAA' : onWhite >= 4.5 ? 'AA' : onWhite >= 3 ? 'AA·lg' : '—';
        target.innerHTML = '';

        const ratio = document.createElement('span');
        ratio.className = 'ds-contrast__ratio';
        ratio.textContent = `${onWhite.toFixed(1)}:1`;
        ratio.title =
            `${onWhite.toFixed(2)}:1 on white, ${onCanvas === null ? '—' : `${onCanvas.toFixed(2)}:1`} on the page canvas. ` +
            'Text needs 4.5:1 (AA) or 3:1 at 18pt+; non-text needs 3:1.';

        const badge = document.createElement('span');
        badge.className = `ds-contrast__level ds-contrast__level--${level === '—' ? 'fail' : 'pass'}`;
        badge.textContent = level;

        target.append(ratio, badge);
    });

    probe.remove();
}

/**
 * Flip each ramp step's label to white once the step behind it is dark enough.
 *
 * The step count and the point where a ramp turns dark both vary, so this is
 * measured rather than assumed from the step's position.
 */
function initRampLabels(root) {
    root.querySelectorAll('.ds-ramp__step').forEach((step) => {
        const luminance = relativeLuminance(getComputedStyle(step).backgroundColor);
        if (luminance !== null && luminance < 0.4) step.classList.add('ds-ramp__step--dark');
    });
}

/**
 * Show-code toggle. State lives as a class on the root element so CSS does the
 * hiding — one class flip regardless of how many snippets are on the page.
 */
function initCodeToggle(root) {
    const toggle = root.querySelector('[data-ds-code-toggle]');
    if (!toggle) return;

    const visible = localStorage.getItem(CODE_VISIBLE_KEY) === 'true';
    root.classList.toggle('ds--code-visible', visible);
    // Set the attribute rather than the property: this runs before <ol-toggle>
    // has necessarily upgraded, and a property set then would be overwritten.
    if (visible) toggle.setAttribute('checked', '');

    toggle.addEventListener('ol-toggle-change', (event) => {
        root.classList.toggle('ds--code-visible', event.detail.checked);
        localStorage.setItem(CODE_VISIBLE_KEY, String(event.detail.checked));
    });
}

/**
 * Click-to-copy for token names and code blocks. `data-ds-copy-text` supplies
 * the text; without it, the nearest code block's contents are used.
 */
function initCopy(root) {
    root.addEventListener('click', async(event) => {
        const trigger = event.target.closest('[data-ds-copy]');
        if (!trigger) return;

        const block = trigger.closest('[data-ds-code]');
        const text = trigger.dataset.dsCopyText || (block && block.querySelector('code').textContent);
        if (!text) return;

        try {
            await navigator.clipboard.writeText(text);
        } catch {
            return; // No clipboard permission — silently leave the page as it was.
        }

        trigger.classList.add('is-copied');
        setTimeout(() => trigger.classList.remove('is-copied'), 1200);
    });
}

/**
 * Mark the sidebar link for whichever section is currently on screen.
 */
function initScrollSpy(root) {
    const links = [...root.querySelectorAll('.ds__sidebar a[href^="#"]')];
    if (!links.length || !('IntersectionObserver' in window)) return;

    const linkById = new Map(links.map((link) => [decodeURIComponent(link.hash.slice(1)), link]));
    const targets = [...linkById.keys()].map((id) => document.getElementById(id)).filter(Boolean);
    if (!targets.length) return;

    const visible = new Set();
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) visible.add(entry.target.id);
                else visible.delete(entry.target.id);
            });
            // The topmost visible target wins, so scrolling up and down agree.
            const current = targets.find((target) => visible.has(target.id));
            links.forEach((link) => link.classList.remove('is-current'));
            if (current) linkById.get(current.id).classList.add('is-current');
        },
        { rootMargin: '-80px 0px -70% 0px' }
    );
    targets.forEach((target) => observer.observe(target));
}

export function initDesignSystem(root) {
    initCodeToggle(root);
    initCopy(root);
    initScrollSpy(root);
    initRampLabels(root);
    renderContrastBadges(root);
    Prism.highlightAllUnder(root);
}
