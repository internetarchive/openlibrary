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

async function copyText(trigger, text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        return; // No clipboard permission — silently leave the page as it was.
    }

    trigger.classList.add('is-copied');
    setTimeout(() => trigger.classList.remove('is-copied'), 1200);
}

/** Click-to-copy. `data-ds-copy-text`, else the nearest code block. */
function initCopy(root) {
    root.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-ds-copy]');
        if (!trigger) return;

        const block = trigger.closest('[data-ds-code]');
        const text = trigger.dataset.dsCopyText || (block && block.querySelector('code').textContent);
        if (text) copyText(trigger, text);
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

function iconSnippets(name) {
    return {
        templetor: `$:macros.icon("${name}")`,
        jinja: `{{ icon("${name}") }}`,
        html: `<ol-icon name="${name}"></ol-icon>`,
    };
}

/**
 * Icon gallery popover: clicking a glyph opens one shared panel with the four
 * usage forms, each row copyable. Browsers without the Popover API keep the
 * old behaviour — the click copies the Templetor macro call.
 */
function initIconPopover(root) {
    const popover = root.querySelector('[data-ds-icon-popover]');
    const grid = root.querySelector('#ds-icon-grid');
    if (!popover || !grid) return;

    const supported = typeof popover.showPopover === 'function';
    if (supported) popover.hidden = false;

    const nameEl = popover.querySelector('[data-ds-icon-popover-name]');
    const previewEl = popover.querySelector('[data-ds-icon-popover-preview]');
    const codeEls = [...popover.querySelectorAll('[data-ds-snippet]')];

    function position(cell) {
        const rect = cell.getBoundingClientRect();
        const panel = popover.getBoundingClientRect();
        const margin = 8;
        let left = rect.left + rect.width / 2 - panel.width / 2;
        left = Math.min(Math.max(margin, left), window.innerWidth - panel.width - margin);
        let top = rect.bottom + margin;
        if (top + panel.height > window.innerHeight - margin) top = rect.top - panel.height - margin;
        popover.style.left = `${Math.round(left)}px`;
        popover.style.top = `${Math.round(Math.max(margin, top))}px`;
    }

    // Clicking the anchor cell while its panel is open should just close it.
    // Light dismiss runs on pointerdown, before the click, so note the anchor
    // here and swallow the click that follows.
    let anchor = null;
    let suppressed = null;
    grid.addEventListener('pointerdown', (event) => {
        const cell = event.target.closest('.ds-icon-gallery__cell');
        suppressed = popover.matches(':popover-open') && cell === anchor ? cell : null;
    });

    grid.addEventListener('click', (event) => {
        const item = event.target.closest('[data-ds-icon-name]');
        if (!item) return;
        const cell = item.querySelector('.ds-icon-gallery__cell');
        const name = item.dataset.dsIconName;

        if (!supported) {
            copyText(cell, `$:macros.icon("${name}")`);
            return;
        }
        if (cell === suppressed) {
            suppressed = null;
            return;
        }

        const snippets = iconSnippets(name);
        codeEls.forEach((code) => {
            code.textContent = snippets[code.dataset.dsSnippet];
        });
        nameEl.textContent = name;
        previewEl.innerHTML = '';
        const glyph = item.querySelector('svg');
        if (glyph) previewEl.appendChild(glyph.cloneNode(true));

        anchor = cell;
        popover.showPopover();
        position(cell); // Measurable only once shown.
        if (event.detail === 0) popover.focus(); // Keyboard open: put Tab inside.
    });

    const reposition = () => {
        if (anchor && popover.matches(':popover-open')) position(anchor);
    };
    window.addEventListener('scroll', reposition, { passive: true });
    window.addEventListener('resize', reposition);
}

/** Substring filter over the icon gallery. Hides cells rather than rebuilding
 *  the grid, so the copy handler keeps working on whatever stays visible. */
function initIconFilter(root) {
    const filter = root.querySelector('[data-ds-icon-filter]');
    if (!filter) return;

    const items = [...root.querySelectorAll('[data-ds-icon-name]')];
    filter.addEventListener('input', () => {
        const query = filter.value.trim().toLowerCase();
        items.forEach((item) => {
            item.hidden = Boolean(query) && !item.dataset.dsIconName.includes(query);
        });
    });
}

export function initDesignSystem(root) {
    initCodeToggle(root);
    initCopy(root);
    initScrollSpy(root);
    initRampLabels(root);
    renderContrastBadges(root);
    initIconFilter(root);
    initIconPopover(root);
}
