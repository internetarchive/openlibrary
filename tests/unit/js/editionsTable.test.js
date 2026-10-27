import $ from 'jquery';
import { foldDiacritics, initEditionsTable } from '../../../openlibrary/plugins/openlibrary/js/editions-table/index.js';

// Titles from the report on #10927 (OL276558W), spelled with and without accents.
const TITLES = ['Armas, gérmenes y acero', 'Armas, germenes y acero', 'Armi, acciaio e malattie', 'Guns, Germs, and Steel'];

function renderEditionsTable(titles) {
    const rows = titles.map((title, i) => `<tr><td class="book"><a href="/books/OL${i + 1}M">${title}</a></td><td>${i}</td></tr>`).join('');
    document.body.innerHTML = `
        <table id="editions">
            <thead><tr><th class="title">Edition</th><th class="read">Availability</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

function search(term) {
    const input = document.querySelector('#editions_wrapper .dataTables_filter input');
    input.value = term;
    input.dispatchEvent(new Event('input', { bubbles: true }));
}

function visibleTitles() {
    return [...document.querySelectorAll('#editions tbody td.book')].map(td => td.textContent).sort();
}

describe('foldDiacritics', () => {
    test.each([
        ['gérmenes', 'germenes'],
        ['Bjørk Ångström', 'Bjørk Angstrom'],
        ['café', 'cafe'],
        ['GERMENES', 'GERMENES'],
        ['9780393317558', '9780393317558']
    ])('%s -> %s', (input, expected) => {
        expect(foldDiacritics(input)).toBe(expected);
    });

    test('decomposed and precomposed accents fold the same way', () => {
        expect(foldDiacritics('gérmenes')).toBe(foldDiacritics('gérmenes'));
    });
});

describe('editions table filter', () => {
    beforeEach(() => {
        localStorage.clear();
        if ($.fn.DataTable.isDataTable('#editions')) {
            $('#editions').DataTable().destroy();
        }
        renderEditionsTable(TITLES);
        initEditionsTable();
        $('#editions').DataTable().page.len(-1).draw();
    });

    test.each(['germenes', 'gérmenes', 'GÉRMENES'])('"%s" matches the title with and without accents', term => {
        search(term);
        expect(visibleTitles()).toEqual(['Armas, germenes y acero', 'Armas, gérmenes y acero']);
    });

    test('a term without diacritics still matches as before', () => {
        search('steel');
        expect(visibleTitles()).toEqual(['Guns, Germs, and Steel']);
    });

    test('cells are displayed with their accents intact', () => {
        expect(visibleTitles()).toContain('Armas, gérmenes y acero');
    });
});
