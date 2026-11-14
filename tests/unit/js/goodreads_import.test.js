import $ from 'jquery';
import { buildFailuresCsv, getFailedRows, initGoodreadsImport, toCsvField } from '../../../openlibrary/plugins/openlibrary/js/goodreads_import.js';

const KEYS = ['ISBN', 'Title', 'My Rating', 'Exclusive Shelf', 'Date Read'];

/** A row of the import table the way `account/import.html` renders a book with an ISBN. */
function bookRow({ isbn, title, rating = '0', shelf = 'to-read', dateRead = '' }) {
    const value = `{'ISBN': '${isbn}', 'My Rating': '${rating}', 'Exclusive Shelf': '${shelf}', 'Date Read': '${dateRead}'}`;
    const cells = [isbn, title, rating, shelf, dateRead].map(text => `<td>${text}</td>`).join('');
    return `<tr class="table-row" isbn="${isbn}"><td><input class="add-book" value="${value}" type="checkbox" checked="checked"></td>${cells}</tr>`;
}

/** A row the way the template renders a book without an ISBN. */
function bookRowWithoutIsbn(title) {
    const cells = ['', title, '0', 'to-read', ''].map(text => `<td>${text}</td>`).join('');
    return `<tr><td></td>${cells}<td class="books-wo-isbn hidden error-imported">Error</td><td class="books-wo-isbn hidden error-imported">No ISBN</td></tr>`;
}

function renderPage(rows) {
    const i18n = JSON.stringify({ summary: '%(imported)s imported, %(failed)s could not be imported' });
    document.body.innerHTML = `
        <div class="import-buttons">
            <div id="myProgress" class="hidden"><div id="myBar">Importing...</div></div>
            <div><button class="hidden cancel-button">Cancel</button></div>
        </div>
        <input type="submit" class="import-submit" value="Import ${rows.length} Books">
        <div class="import-summary hidden" role="status" data-i18n='${i18n}'>
            <p class="import-summary-text"></p>
            <button type="button" class="download-failures hidden">Download</button>
        </div>
        <table class="import-table">
            <thead><tr>
                <th class="toggle-all"><input type="checkbox" checked="checked"></th>
                ${KEYS.map(key => `<th>${key}</th>`).join('')}
                <th class="import-status hidden">Status</th>
                <th class="status-reason hidden">Reason</th>
            </tr></thead>
            <tbody>${rows.join('')}</tbody>
        </table>`;
    initGoodreadsImport();
}

/** Serves `/isbn/<isbn>.json` from `editions`; any other ISBN is a 404, like a book not in the collection. */
function stubEditionLookup(editions) {
    vi.stubGlobal(
        'XMLHttpRequest',
        class {
            open(method, url) {
                this.isbn = url.match(/\/isbn\/(.+)\.json/)[1];
            }
            send() {
                setTimeout(() => {
                    const edition = editions[this.isbn];
                    this.status = edition ? 200 : 404;
                    this.statusText = edition ? 'OK' : 'Not Found';
                    this.response = edition ? JSON.stringify(edition) : '';
                    this.onload();
                });
            }
        }
    );
}

/** Answers every reading log, rating and check-in request; `failing` lists the URL suffixes that fail. */
function stubPosts(failing = []) {
    return vi.spyOn($, 'ajax').mockImplementation(
        ({ url }) =>
            new Promise((resolve, reject) => {
                setTimeout(() => (failing.some(suffix => url.endsWith(suffix)) ? reject(new Error(url)) : resolve({})));
            })
    );
}

const edition = n => ({ key: `/books/OL${n}M`, works: [{ key: `/works/OL${n}W` }] });
const row = isbn => document.querySelector(`[isbn="${isbn}"]`);
const summary = () => document.querySelector('.import-summary');

async function runImport() {
    $('.import-submit').trigger('click');
    await vi.waitFor(() => expect(summary().classList.contains('hidden')).toBe(false));
}

afterEach(() => {
    $(document).off();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
});

describe('toCsvField', () => {
    test('leaves a plain field alone', () => {
        expect(toCsvField('Dune')).toBe('Dune');
    });

    test('quotes a field holding a comma, a quote or a line break, doubling the quotes', () => {
        expect(toCsvField('Love, Again')).toBe('"Love, Again"');
        expect(toCsvField('The "Best" Book')).toBe('"The ""Best"" Book"');
        expect(toCsvField('Line\nBreak')).toBe('"Line\nBreak"');
    });
});

describe('Goodreads import', () => {
    test('summarises the outcome once every book has been processed', async () => {
        stubEditionLookup({ 111: edition(1) });
        stubPosts();
        renderPage([
            bookRow({ isbn: '111', title: 'Found' }),
            bookRow({ isbn: '222', title: 'Missing' }),
            bookRow({ isbn: '333', title: 'Odd Shelf', shelf: 'favourites' }),
            bookRowWithoutIsbn('No ISBN, Here')
        ]);

        await runImport();

        expect(document.querySelector('.import-summary-text').textContent).toBe('1 imported, 3 could not be imported');
        expect(document.querySelector('.download-failures').classList.contains('hidden')).toBe(false);
        expect(row('111').lastElementChild.textContent).toBe('Imported');
        expect(row('222').lastElementChild.textContent).toBe('Book not in collection');
        expect(row('333').lastElementChild.textContent).toBe('Custom shelves are not supported');
    });

    test('hides the download button when every book was imported', async () => {
        stubEditionLookup({ 111: edition(1) });
        stubPosts();
        renderPage([bookRow({ isbn: '111', title: 'Found' })]);

        await runImport();

        expect(document.querySelector('.import-summary-text').textContent).toBe('1 imported, 0 could not be imported');
        expect(document.querySelector('.download-failures').classList.contains('hidden')).toBe(true);
    });

    test('marks a book as failed, not imported, when the reading log request fails', async () => {
        stubEditionLookup({ 111: edition(1) });
        stubPosts(['/bookshelves.json']);
        renderPage([bookRow({ isbn: '111', title: 'Found' })]);

        await runImport();

        expect(row('111').textContent).not.toContain('Imported');
        expect(row('111').lastElementChild.textContent).toBe('Failed to add book to reading log');
    });

    test('reports a rating that could not be saved', async () => {
        stubEditionLookup({ 111: edition(1) });
        stubPosts(['/ratings.json']);
        renderPage([bookRow({ isbn: '111', title: 'Rated', rating: '4' })]);

        await runImport();

        expect(row('111').lastElementChild.textContent).toBe('Failed to add rating');
    });

    test('counts a book only once its reading log request has finished', async () => {
        stubEditionLookup({ 111: edition(1) });
        let answer;
        const ajax = vi.spyOn($, 'ajax').mockImplementation(
            () =>
                new Promise(resolve => {
                    answer = resolve;
                })
        );
        renderPage([bookRow({ isbn: '111', title: 'One' })]);

        $('.import-submit').trigger('click');
        await vi.waitFor(() => expect(ajax).toHaveBeenCalled());

        // The request is still out: the book is neither imported nor counted yet
        expect(row('111').textContent).not.toContain('Imported');
        expect(document.querySelector('#myBar a')).toBeNull();

        answer({});
        await vi.waitFor(() => expect(document.querySelector('#myBar a')).not.toBeNull());
        expect(row('111').lastElementChild.textContent).toBe('Imported');
    });

    test('does not count unchecked books towards the progress bar', async () => {
        stubEditionLookup({ 111: edition(1) });
        stubPosts();
        renderPage([bookRow({ isbn: '000', title: 'Skipped' }), bookRow({ isbn: '111', title: 'One' })]);
        $(row('000')).find('input.add-book').prop('checked', false).removeAttr('checked');

        $('.import-submit').trigger('click');

        // The skipped book alone must not fill the bar while the checked one is still importing
        expect(document.querySelector('#myBar a')).toBeNull();
        await vi.waitFor(() => expect(summary().classList.contains('hidden')).toBe(false));
        expect(document.querySelector('#myBar a')).not.toBeNull();
    });

    test('leaves no stray text after a failed row', async () => {
        stubEditionLookup({});
        stubPosts();
        renderPage([bookRow({ isbn: '222', title: 'Missing' })]);

        await runImport();

        const strayText = [...row('222').childNodes].filter(node => node.nodeType === Node.TEXT_NODE);
        expect(strayText.map(node => node.textContent.trim()).join('')).toBe('');
    });
});

describe('buildFailuresCsv', () => {
    test('lists every book that could not be imported, with its reason', async () => {
        stubEditionLookup({ 111: edition(1) });
        stubPosts();
        renderPage([
            bookRow({ isbn: '111', title: 'Found' }),
            bookRow({ isbn: '222', title: 'Missing "One"', rating: '3', shelf: 'read', dateRead: '2024/05/01' }),
            bookRowWithoutIsbn('No ISBN, Here')
        ]);

        await runImport();
        const table = document.querySelector('.import-table');

        expect(getFailedRows(table)).toHaveLength(2);
        expect(buildFailuresCsv(table).split('\r\n')).toEqual([
            'ISBN,Title,My Rating,Exclusive Shelf,Date Read,Reason',
            '222,"Missing ""One""",3,read,2024/05/01,Book not in collection',
            ',"No ISBN, Here",0,to-read,,No ISBN'
        ]);
    });
});

describe('Downloading the failures', () => {
    test('saves them as a CSV file', async () => {
        stubEditionLookup({});
        stubPosts();
        renderPage([bookRow({ isbn: '222', title: 'Missing' })]);
        await runImport();
        URL.createObjectURL = vi.fn(() => 'blob:failures');
        URL.revokeObjectURL = vi.fn();
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
            expect(this.download).toBe('goodreads-import-failures.csv');
            expect(this.href).toBe('blob:failures');
        });

        $('.download-failures').trigger('click');

        expect(click).toHaveBeenCalledTimes(1);
        const file = URL.createObjectURL.mock.calls[0][0];
        expect(file.type).toBe('text/csv;charset=utf-8');
        // A byte order mark, then the header row, so spreadsheet apps read it as UTF-8
        const bytes = new Uint8Array(await file.arrayBuffer());
        expect(Array.from(bytes.subarray(0, 3))).toEqual([0xef, 0xbb, 0xbf]);
        expect(new TextDecoder().decode(bytes.slice(3))).toBe(
            'ISBN,Title,My Rating,Exclusive Shelf,Date Read,Reason\r\n222,Missing,0,to-read,,Book not in collection'
        );
    });
});
