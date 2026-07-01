/**
 * Subject-page browse toolbar.
 *
 * Wires the availability ("Readable now"), language, and era controls rendered
 * by subjects.html to the rails below them. Each control re-filters *every* rail
 * client-side by rewriting the rail's lazy-carousel config and re-fetching.
 *
 * Availability and language are persisted to localStorage so they stick across
 * sessions (the "global, sticky filter" model); era is intentionally not
 * persisted — it's a per-visit browsing choice.
 *
 * The module captures each rail's original ("base") config once, then derives an
 * effective config from base + current filter state. This lets us toggle filters
 * on and off repeatedly without losing the original queries.
 */

const STORAGE_KEY = 'ol.subjectFilters';

let loadCarousel;
let readableEl;
let langEl;
let eraBtns = [];
let emptyMsg = '';
let retryMsg = '';

// [{ rail: HTMLElement, base: object }] captured at init, in DOM order.
const rails = [];

function loadPersisted() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

function savePersisted(state) {
    try {
        localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({ readableNow: state.readableNow, language: state.language })
        );
    } catch {
        // localStorage may be unavailable (private mode); filters still work for
        // the current page, they just won't persist.
    }
}

function readState() {
    const activeEra = eraBtns.find((b) => b.classList.contains('is-active'));
    return {
        readableNow: Boolean(readableEl && readableEl.checked),
        language: langEl ? langEl.value : '',
        era: activeEra ? activeEra.dataset.era : '',
    };
}

/**
 * Derive a rail's effective lazy-carousel config from its base config and the
 * current filter state.
 *
 * @param {object} base
 * @param {object} state
 * @returns {object}
 */
function computeConfig(base, state) {
    const cfg = { ...base };
    let query = base.query;
    if (state.language) {
        query += ` language:${state.language}`;
    }
    if (state.era) {
        query += ` first_publish_year:${state.era}`;
    }
    cfg.query = query;
    cfg.has_fulltext_only = Boolean(base.has_fulltext_only) || state.readableNow;

    const filtered = Boolean(state.readableNow || state.language || state.era);
    if (filtered) {
        // With user filters active, don't silently fall back to the unfiltered
        // query, and keep an empty rail in place (with a message) so toggling the
        // filter back off can restore it.
        cfg.fallback = false;
        cfg.keepOnEmpty = true;
        cfg.emptyMsg = emptyMsg;
    }
    return cfg;
}

/** Build a fresh lazy-carousel placeholder element for a given config. */
function buildPlaceholder(config) {
    const el = document.createElement('div');
    el.className = 'lazy-carousel';
    el.dataset.config = JSON.stringify(config);
    el.innerHTML =
        '<div class="loadingIndicator">' +
        '<figure><img src="/static/images/ajax-loader-bar.gif" alt="" loading="lazy"></figure>' +
        '</div>' +
        '<div class="lazy-carousel-retry hidden">' +
        `<a href="#" class="retry-btn">${retryMsg}</a>` +
        '</div>';
    return el;
}

/** Capture each rail's original config exactly once, in DOM order. */
function captureBase() {
    document.querySelectorAll('.subject-rails .subject-rail').forEach((rail) => {
        const placeholder = rail.querySelector('.lazy-carousel');
        if (!placeholder) {
            return;
        }
        rails.push({ rail, base: JSON.parse(placeholder.dataset.config) });
    });
}

/**
 * Replace every rail's carousel with a fresh, re-filtered one. A filter change
 * is an explicit user action, so we (re)load each rail imperatively rather than
 * waiting for it to scroll into view.
 */
async function rebuildAll(state) {
    if (!loadCarousel) {
        ({ loadCarousel } = await import(/* webpackChunkName: "lazy-carousels" */ './lazy-carousel'));
    }
    rails.forEach(({ rail, base }) => {
        // Drop whatever is currently under the heading (placeholder or a
        // previously-loaded carousel) and start fresh.
        Array.from(rail.children).forEach((child) => {
            if (!child.classList.contains('subject-rail__head')) {
                child.remove();
            }
        });
        const placeholder = buildPlaceholder(computeConfig(base, state));
        rail.appendChild(placeholder);
        wireRetry(placeholder);
        loadCarousel(placeholder);
    });
}

/** Let a rebuilt rail be retried if its fetch fails (loadCarousel shows retry). */
function wireRetry(placeholder) {
    const retryBtn = placeholder.querySelector('.retry-btn');
    if (!retryBtn) {
        return;
    }
    retryBtn.addEventListener('click', (e) => {
        e.preventDefault();
        placeholder.querySelector('.loadingIndicator').classList.remove('hidden');
        placeholder.querySelector('.lazy-carousel-retry').classList.add('hidden');
        loadCarousel(placeholder);
    });
}

function onChange() {
    const state = readState();
    savePersisted(state);
    rebuildAll(state);
}

// ── Cross-shelf de-duplication ──────────────────────────────────────────────
// The rails overlap heavily (a blockbuster shows up under "Reader favorites",
// "Most loved", "Begin a series"…). We keep the first appearance in DOM order
// and drop repeats from later rails so each shelf earns its space.

const railContainer = () => document.querySelector('.subject-rails');

function cardKey(card) {
    const save = card.querySelector('.cover-save');
    return save ? save.dataset.workKey : null;
}

/**
 * Walk every rail in DOM order; the first rail to show a given work keeps it,
 * later rails drop it. Cleared and re-walked from scratch on each pass so it's
 * idempotent and order-independent: already-removed repeats stay gone, and the
 * earliest-in-DOM occurrence always wins regardless of which rail loaded first.
 */
function dedupeRails() {
    const seen = new Set();
    rails.forEach(({ rail }) => {
        rail.querySelectorAll('.book.carousel__item').forEach((card) => {
            const key = cardKey(card);
            if (!key) {
                return;
            }
            if (seen.has(key)) {
                card.remove();
            } else {
                seen.add(key);
            }
        });
    });
}

let dedupeTimer;
function setupDedup() {
    const container = railContainer();
    if (!container || !rails.length) {
        return;
    }
    const observer = new MutationObserver(() => {
        clearTimeout(dedupeTimer);
        dedupeTimer = setTimeout(() => {
            // Detach while we mutate so our own card removals don't re-trigger us.
            observer.disconnect();
            dedupeRails();
            observer.observe(container, { childList: true, subtree: true });
        }, 80);
    });
    observer.observe(container, { childList: true, subtree: true });
}

/**
 * Initialize the subject browse toolbar.
 *
 * Runs synchronously (no awaits) so it can apply any persisted filters to the
 * placeholders *before* the caller kicks off the lazy-carousel load — and so it
 * can never block that load. The lazy-carousel module is imported lazily, only
 * when a filter change actually requires a rebuild.
 */
export function initSubjectBrowse() {
    const toolbar = document.querySelector('.subject-browse');
    if (!toolbar) {
        return;
    }

    captureBase();
    if (!rails.length) {
        return;
    }

    // Drop repeat works across rails as they load (and after any rebuild).
    setupDedup();

    readableEl = toolbar.querySelector('.subject-browse__readable');
    langEl = toolbar.querySelector('.subject-browse__lang-select');
    eraBtns = Array.from(toolbar.querySelectorAll('.subject-browse__era'));
    emptyMsg = toolbar.dataset.emptyMsg || '';
    retryMsg = toolbar.dataset.retryMsg || '';

    // Restore sticky filters (availability + language only; era is per-visit).
    const persisted = loadPersisted();
    if (readableEl && persisted.readableNow) {
        readableEl.checked = true;
    }
    if (langEl && persisted.language) {
        langEl.value = persisted.language;
        // If the saved language isn't offered on this subject, the select falls
        // back to "All languages" — read it back so state stays consistent.
    }

    // If sticky filters are active, re-fetch every rail with them applied. The
    // page's own lazy-load (kicked off separately) handles the unfiltered case.
    const state = readState();
    if (state.readableNow || state.language) {
        rebuildAll(state);
    }

    if (readableEl) {
        // <ol-toggle> owns its checked state and fires ol-toggle-change.
        readableEl.addEventListener('ol-toggle-change', onChange);
    }
    if (langEl) {
        langEl.addEventListener('change', onChange);
    }
    eraBtns.forEach((btn) => {
        btn.addEventListener('click', () => {
            eraBtns.forEach((b) => {
                const active = b === btn;
                b.classList.toggle('is-active', active);
                b.setAttribute('aria-pressed', String(active));
            });
            onChange();
        });
    });
}
