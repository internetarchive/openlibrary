/**
 * Floating debug panel for "Browse the stacks" (dev only, not translated). Opened by ?debug=stacks;
 * its state lives in localStorage until the panel is closed.
 */

const STORAGE_KEY = 'ol-stacks-debug';

function loadState() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

function saveState(state) {
    try {
        if (state) localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        else localStorage.removeItem(STORAGE_KEY);
    } catch { /* storage blocked */ }
}

/** @param {HTMLElement} tile */
function subgenresOf(tile) {
    return JSON.parse(tile.dataset.shelf || '{}').subgenres || [];
}

/**
 * @param {object} stacks - from initBrowseStacks
 * @param {HTMLElement[]} stacks.tiles - every tile, in rail order
 * @param {(keep: (tile: HTMLElement) => boolean) => void} stacks.filterTiles
 */
export function initStacksDebug({ tiles, filterTiles }) {
    const state = { hideEmpty: false, ...loadState() };
    saveState(state);

    const panel = document.createElement('aside');
    panel.className = 'stacks-debug';
    panel.setAttribute('aria-label', 'Stacks debug');
    panel.innerHTML = `
        <div class="stacks-debug__header">
            <strong>Stacks debug</strong>
            <button type="button" class="stacks-debug__close" aria-label="Close debug panel">×</button>
        </div>
        <ol-toggle class="stacks-debug__toggle" label="Hide genres without subgenres"></ol-toggle>
        <p class="stacks-debug__stats"></p>
        <details class="stacks-debug__details">
            <summary>Genres</summary>
            <ul class="stacks-debug__list"></ul>
        </details>
    `;
    const toggle = panel.querySelector('ol-toggle');
    const stats = panel.querySelector('.stacks-debug__stats');
    const list = panel.querySelector('.stacks-debug__list');

    // Trending isn't a genre, so it always stays.
    const empty = tiles.filter(tile => !tile.hasAttribute('data-pinned') && !subgenresOf(tile).length);

    list.append(...tiles.map(tile => {
        const item = document.createElement('li');
        const count = subgenresOf(tile).length;
        item.textContent = `${JSON.parse(tile.dataset.shelf).name} — ${count}`;
        item.classList.toggle('stacks-debug__empty', empty.includes(tile));
        return item;
    }));

    function apply() {
        toggle.checked = state.hideEmpty;
        panel.classList.toggle('stacks-debug--hiding', state.hideEmpty);
        filterTiles(tile => !(state.hideEmpty && empty.includes(tile)));
        const shown = tiles.filter(tile => tile.isConnected).length;
        stats.textContent = `Showing ${shown} of ${tiles.length} tiles · ${empty.length} without subgenres`;
    }

    toggle.addEventListener('ol-toggle-change', (e) => {
        state.hideEmpty = e.detail.checked;
        saveState(state);
        apply();
    });
    panel.querySelector('.stacks-debug__close').addEventListener('click', () => {
        saveState(null);
        state.hideEmpty = false;
        apply();
        panel.remove();
    });

    document.body.append(panel);
    apply();
}
