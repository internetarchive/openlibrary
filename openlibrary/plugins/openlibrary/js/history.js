/**
 * History page revision comparison.
 *
 * The A/B selection lives in the URL query string (?a=&b=), not the DOM, so it
 * survives pagination: <ol-pagination> rebuilds its links from the current URL,
 * carrying a/b across pages. A sticky bar reflects the selection even when the
 * picked revision sits on another page, and provides the Compare action.
 *
 * @param {HTMLElement} pageHistoryElement - the #pageHistory table
 */
export function initHistory(pageHistoryElement) {
    const i18n = JSON.parse(pageHistoryElement.dataset.i18n);
    const bar = document.getElementById('pageHistoryCompare');
    if (!bar) return;

    const compareLink = bar.querySelector('[data-compare-link]');
    const clearButton = bar.querySelector('[data-compare-clear]');

    // Slots ('a'/'b') in the order the user picked them, so the button reads
    // "Compare revisions <first> and <second>" matching selection order.
    let pickOrder = [];

    /**
     * Read the current selection from the URL.
     * @returns {{a: ?number, b: ?number}}
     */
    function readSelection() {
        const params = new URLSearchParams(window.location.search);
        const parse = (key) => {
            const value = parseInt(params.get(key), 10);
            return Number.isInteger(value) && value > 0 ? value : null;
        };
        return { a: parse('a'), b: parse('b') };
    }

    /**
     * Persist the selection to the URL without navigating, then nudge the
     * pagination controls to rebuild their links so a page click carries a/b.
     * @param {{a: ?number, b: ?number}} selection
     */
    function writeSelection({ a, b }) {
        const url = new URL(window.location.href);
        const setOrDelete = (key, value) => {
            if (value) {
                url.searchParams.set(key, value);
            } else {
                url.searchParams.delete(key);
            }
        };
        setOrDelete('a', a);
        setOrDelete('b', b);
        window.history.replaceState(null, '', url);
        // <ol-pagination> derives its hrefs from window.location.href at render
        // time, so force a re-render now that the URL has changed.
        document.querySelectorAll('ol-pagination')
            .forEach((el) => el.requestUpdate && el.requestUpdate());
    }

    /**
     * Reflect the selection in this page's radios and row highlights. Revisions
     * that live on another page simply have no radio here and are skipped.
     * @param {{a: ?number, b: ?number}} selection
     */
    function syncRows({ a, b }) {
        pageHistoryElement.querySelectorAll('input[name="a"], input[name="b"]')
            .forEach((radio) => {
                const value = parseInt(radio.value, 10);
                radio.checked = (radio.name === 'a' && value === a) ||
                    (radio.name === 'b' && value === b);
            });
        pageHistoryElement.querySelectorAll('tr.pick-ab-selected')
            .forEach((row) => row.classList.remove('pick-ab-selected'));
        [a, b].forEach((value) => {
            if (!value) return;
            const radio = pageHistoryElement.querySelector(`input[value="${value}"]`);
            if (radio) radio.closest('tr').classList.add('pick-ab-selected');
        });
    }

    /**
     * Render the sticky comparison bar from the selection. The bar is hidden
     * until at least one revision is picked. Its single button reads
     * "Compare revisions <first> and ?" while one revision is chosen and is
     * disabled; once a second, distinct revision is picked it fills in the "?"
     * and links to the diff.
     * @param {{a: ?number, b: ?number}} selection
     */
    function renderBar(selection) {
        const [first, second] = pickOrder.map((slot) => selection[slot]).filter(Boolean);
        if (!first) {
            bar.hidden = true;
            return;
        }
        bar.hidden = false;
        compareLink.textContent = i18n.compare_label
            .replace('%(a)s', first)
            .replace('%(b)s', second || '?');

        if (second && first !== second) {
            const [lower, higher] = first < second ? [first, second] : [second, first];
            compareLink.href = `?m=diff&a=${lower}&b=${higher}`;
            compareLink.removeAttribute('aria-disabled');
            compareLink.removeAttribute('tabindex');
            compareLink.classList.remove('is-disabled');
        } else {
            compareLink.removeAttribute('href');
            compareLink.setAttribute('aria-disabled', 'true');
            compareLink.setAttribute('tabindex', '-1');
            compareLink.classList.add('is-disabled');
        }
    }

    /**
     * @param {{a: ?number, b: ?number}} selection
     */
    function update(selection) {
        syncRows(selection);
        renderBar(selection);
    }

    // A radio change updates only its own side, merging with the opposite side
    // already stored in the URL (which may point to an off-page revision).
    pageHistoryElement.addEventListener('change', (event) => {
        const { name, value } = event.target;
        if (name !== 'a' && name !== 'b') return;
        const selection = readSelection();
        selection[name] = parseInt(value, 10);
        if (!pickOrder.includes(name)) pickOrder.push(name);
        writeSelection(selection);
        update(selection);
    });

    clearButton.addEventListener('click', () => {
        pickOrder = [];
        const cleared = { a: null, b: null };
        writeSelection(cleared);
        update(cleared);
    });

    // Restore from the URL on load.
    const initial = readSelection();
    pickOrder = ['a', 'b'].filter((slot) => initial[slot]);
    update(initial);
}
