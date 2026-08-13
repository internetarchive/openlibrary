/**
 * Page behaviour for the design system docs at /developers/design.
 * All progressive: the page is fully readable with this bundle absent.
 */
import { WHITE, compositeOver, contrastOn, luminanceFromCssColor, parseCssColor } from './contrast.js';

const CODE_VISIBLE_KEY = 'ol-design-show-code';

// localStorage throws when storage is blocked (Safari private mode, some
// enterprise policies). Remembering the toggle isn't worth taking the page down.
function readStored(key) {
    try {
        return localStorage.getItem(key);
    } catch {
        return null;
    }
}

function writeStored(key, value) {
    try {
        localStorage.setItem(key, value);
    } catch {
        // Preference just doesn't persist.
    }
}

/**
 * Highlight the snippets, at most once, and only once they're revealed —
 * snippets are `display: none` by default, so doing it on load meant parsing a
 * couple of hundred hidden blocks, and shipping Prism, for nothing.
 */
let highlighted = false;
async function highlightCode(root) {
    if (highlighted) return;
    highlighted = true;
    // The default build already carries markup, css, clike and javascript —
    // the only languages the snippets use — so no component imports are needed.
    const { default: Prism } = await import(/* webpackChunkName: "prism" */ 'prismjs');
    Prism.highlightAllUnder(root);
}

/**
 * Badge every color token with its contrast, measured off what the browser
 * paints so `color-mix()` and deep `var()` chains stay honest. Reads and writes
 * stay in separate passes: interleaved, each token forces a style recalc.
 */
function renderContrastBadges(root) {
    const targets = [...root.querySelectorAll('[data-ds-contrast-for]')];
    if (!targets.length) return;

    // Write: one probe per token, appended in a single insertion.
    const fragment = document.createDocumentFragment();
    const probes = targets.map((target) => {
        const probe = document.createElement('span');
        probe.style.cssText = `position:absolute;visibility:hidden;pointer-events:none;color:var(${target.dataset.dsContrastFor})`;
        fragment.appendChild(probe);
        return probe;
    });
    root.appendChild(fragment);

    // Read: only the first getComputedStyle costs a recalc, since nothing
    // dirties the tree in between.
    const canvas = parseCssColor(getComputedStyle(document.body).backgroundColor);
    const measured = probes.map((probe) => parseCssColor(getComputedStyle(probe).color));
    probes.forEach((probe) => probe.remove());

    // Write: build every badge, touching no computed style. Each ratio is
    // measured against its own backdrop, so a translucent token (the
    // color-mix() control tints) is composited rather than scored as if the
    // color it was mixed from were painted solid.
    const canvasRgb = canvas && compositeOver(canvas);
    targets.forEach((target, index) => {
        const color = measured[index];
        if (color === null) return;
        const onWhite = contrastOn(color, WHITE);
        const onCanvas = canvasRgb === null ? null : contrastOn(color, canvasRgb);

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
}

/**
 * Flip each ramp step's label to white once the step behind it is dark enough.
 * Measured, not assumed from position — read pass then write pass, as above.
 */
function initRampLabels(root) {
    const steps = [...root.querySelectorAll('.ds-ramp__step')];
    const luminances = steps.map((step) => luminanceFromCssColor(getComputedStyle(step).backgroundColor));
    steps.forEach((step, index) => {
        if (luminances[index] !== null && luminances[index] < 0.4) step.classList.add('ds-ramp__step--dark');
    });
}

/** Show-code toggle. One class on the root, so CSS does the hiding. */
function initCodeToggle(root) {
    const toggle = root.querySelector('[data-ds-code-toggle]');
    if (!toggle) return;

    const visible = readStored(CODE_VISIBLE_KEY) === 'true';
    root.classList.toggle('ds--code-visible', visible);
    // Set the attribute rather than the property: this runs before <ol-toggle>
    // has necessarily upgraded, and a property set then would be overwritten.
    if (visible) {
        toggle.setAttribute('checked', '');
        highlightCode(root);
    }

    toggle.addEventListener('ol-toggle-change', (event) => {
        root.classList.toggle('ds--code-visible', event.detail.checked);
        writeStored(CODE_VISIBLE_KEY, String(event.detail.checked));
        if (event.detail.checked) highlightCode(root);
    });
}

/** Click-to-copy. `data-ds-copy-text`, else the nearest code block. */
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
}
