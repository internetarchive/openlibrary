/**
 * js/history.js is the revision-comparison glue for a page's edit history.
 * Two elements on the site share the #pageHistory id: the real revision table
 * on ?m=history, which carries the compare strings in data-i18n, and the
 * History box in a page footer (templates/lib/history.html), which has neither
 * the attribute nor the comparison bar.
 */
import { initHistory } from '../../../openlibrary/plugins/openlibrary/js/history';

const I18N = JSON.stringify({ compare_label: 'Compare revisions %(a)s and %(b)s' });

/**
 * Render the parts of the history page the script touches.
 * @param {{tableAttributes?: string, withBar?: boolean}} options
 */
function mount({ tableAttributes = `data-i18n='${I18N}'`, withBar = true } = {}) {
    document.body.innerHTML = `
        ${withBar ? '<div id="pageHistoryCompare" hidden><a data-compare-link></a><button data-compare-clear></button></div>' : ''}
        <table id="pageHistory" ${tableAttributes}><tbody></tbody></table>`;
    return document.querySelector('#pageHistory');
}

afterEach(() => {
    document.body.innerHTML = '';
    window.history.replaceState(null, '', '/');
});

describe('initHistory', () => {
    test('does not throw for a #pageHistory element without data-i18n', () => {
        const footerHistory = mount({ tableAttributes: '', withBar: false });
        expect(() => initHistory(footerHistory)).not.toThrow();
    });

    test('does not throw when the comparison bar is absent', () => {
        const table = mount({ withBar: false });
        expect(() => initHistory(table)).not.toThrow();
    });

    test('restores a selection from the URL and links it to the diff', () => {
        window.history.replaceState(null, '', '/works/OL45804W?m=history&a=2&b=5');
        const table = mount();
        const row = document.createElement('tr');
        row.innerHTML = '<input type="radio" name="a" value="2"><input type="radio" name="b" value="5">';
        table.querySelector('tbody').append(row);

        initHistory(table);

        const bar = document.getElementById('pageHistoryCompare');
        const link = bar.querySelector('[data-compare-link]');
        expect(bar.hidden).toBe(false);
        expect(link.textContent).toBe('Compare revisions 2 and 5');
        expect(link.getAttribute('href')).toBe('?m=diff&a=2&b=5');
        expect(table.querySelector('input[name="a"]').checked).toBe(true);
        expect(row.classList.contains('pick-ab-selected')).toBe(true);
    });

    test('picking a revision writes it to the URL and waits for a second one', () => {
        window.history.replaceState(null, '', '/works/OL45804W?m=history');
        const table = mount();
        const row = document.createElement('tr');
        row.innerHTML = '<input type="radio" name="a" value="7">';
        table.querySelector('tbody').append(row);
        initHistory(table);

        const radio = table.querySelector('input[name="a"]');
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));

        expect(new URLSearchParams(window.location.search).get('a')).toBe('7');
        expect(document.querySelector('[data-compare-link]').getAttribute('aria-disabled')).toBe('true');
    });
});
