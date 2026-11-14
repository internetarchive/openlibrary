import $ from 'jquery';

/**
 * Quotes one CSV field when it needs it (RFC 4180): a field holding a comma, a double quote or a
 * line break is wrapped in double quotes, with every double quote inside it doubled.
 * @param {string} value
 * @returns {string}
 */
export function toCsvField(value) {
    return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/**
 * The rows of the import table that could not be imported: the ones the import marked as failed,
 * and the ones without an ISBN, which are never sent.
 * @param {HTMLTableElement} table
 * @returns {HTMLTableRowElement[]}
 */
export function getFailedRows(table) {
    return [...table.tBodies[0].rows].filter(row => row.classList.contains('import-failure') || row.querySelector('td.books-wo-isbn') !== null);
}

/**
 * Builds a CSV of the books that could not be imported, with the table's own columns (ISBN,
 * Title, My Rating, Exclusive Shelf, Date Read) followed by the reason, so the patron can add
 * those books by hand.
 * @param {HTMLTableElement} table
 * @returns {string}
 */
export function buildFailuresCsv(table) {
    const headers = [...table.tHead.rows[0].cells].map(th => th.textContent.trim());
    // The first column is the checkbox, the last two are the import status and its reason
    const columns = headers.slice(1, -2);
    const lines = [[...columns, headers[headers.length - 1]]];
    for (const row of getFailedRows(table)) {
        const cells = [...row.cells].map(td => td.textContent.trim());
        lines.push([...cells.slice(1, 1 + columns.length), cells[cells.length - 1]]);
    }
    return lines.map(fields => fields.map(toCsvField).join(',')).join('\r\n');
}

/**
 * Shows how many books were imported and how many were not, and offers the ones that were not as
 * a CSV. Called once every row has its outcome.
 * @param {HTMLTableElement} table
 */
function showImportSummary(table) {
    const summary = document.querySelector('.import-summary');
    if (!summary) {
        return;
    }
    const i18n = JSON.parse(summary.dataset.i18n);
    const imported = table.querySelectorAll('td.success-imported').length;
    const failed = getFailedRows(table).length;
    summary.querySelector('.import-summary-text').textContent = i18n.summary.replace('%(imported)s', imported).replace('%(failed)s', failed);
    summary.querySelector('.download-failures').classList.toggle('hidden', failed === 0);
    summary.classList.remove('hidden');
}

export function initGoodreadsImport() {
    var count, prevPromise;

    $(document).on('click', 'th.toggle-all input', function () {
        var checked = $(this).prop('checked');
        $('input.add-book').each(function () {
            $(this).prop('checked', checked);
            if (checked) {
                $(this).attr('checked', 'checked');
            } else {
                $(this).removeAttr('checked');
            }
        });
        const l = $('.add-book[checked*="checked"]').length;
        $('.import-submit').attr('value', `Import ${l} Books`);
    });

    $(document).on('click', 'input.add-book', function () {
        if ($(this).prop('checked')) {
            $(this).attr('checked', 'checked');
        } else {
            $(this).removeAttr('checked');
        }
        const l = $('.add-book[checked*="checked"]').length;
        $('.import-submit').attr('value', `Import ${l} Books`);
    });

    $(document).on('click', '.download-failures', function () {
        const csv = buildFailuresCsv(document.querySelector('.import-table'));
        // The byte order mark lets spreadsheet apps read non-ASCII titles as UTF-8
        const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = 'goodreads-import-failures.csv';
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 0);
    });

    //updates the progress bar based on the book count
    function func1(value) {
        const l = $('.add-book[checked*="checked"]').length;
        const elem = document.getElementById('myBar');
        elem.style.width = `${value * (100 / l)}%`;
        elem.innerHTML = `${value} Books`;
        if (value * (100 / l) >= 100) {
            elem.innerHTML = '';
            $('#myBar').append('<a href="/account/books" style="color:white"> Go to your Reading Log </a>');
            $('.cancel-button').addClass('hidden');
        }
    }

    $('.import-submit').on('click', function () {
        $('#myProgress').removeClass('hidden');
        $('.cancel-button').removeClass('hidden');
        $('input.import-submit').addClass('hidden');
        $('th.import-status').removeClass('hidden');
        $('th.status-reason').removeClass('hidden');
        const shelves = { read: 3, 'currently-reading': 2, 'to-read': 1 };
        count = 0;
        prevPromise = Promise.resolve();
        $('input.add-book').each(function () {
            var input = $(this),
                checked = input.prop('checked');
            var value = JSON.parse(input.val().replace(/'/g, '"'));
            var shelf = value['Exclusive Shelf'];
            var shelf_id = 0;
            const row = $(`[isbn="${value['ISBN']}"]`);
            const hasFailure = function () {
                return row.hasClass('import-failure');
            };
            const fail = function (reason) {
                if (!hasFailure()) {
                    row.append(`<td class="error-imported">Error</td><td class="error-imported">${reason}</td>`);
                    row.removeClass('selected');
                    row.addClass('import-failure');
                }
            };

            // An unchecked book is not imported, so it does not count towards the progress bar,
            // whose total is the number of checked books
            if (!checked) {
                return;
            }

            if (shelves[shelf]) {
                shelf_id = shelves[shelf];
            }

            //used 'return' instead of 'return false' because the loop was being exited entirely
            if (shelf_id === 0) {
                fail('Custom shelves are not supported');
                func1(++count);
                return;
            }

            // Each book waits for every request of the one before it, and is only counted once
            // its own requests have finished, so the bar reaches 100% when the import is done
            prevPromise = prevPromise
                .then(async function () {
                    row.addClass('selected');
                    let editionKey, workKey;
                    try {
                        const obj = JSON.parse(await getWork(value['ISBN']));
                        editionKey = obj['key'];
                        workKey = obj['works'][0].key;
                    } catch {
                        fail('Book not in collection');
                        return;
                    }

                    try {
                        await $.ajax({
                            url: `${workKey}/bookshelves.json`,
                            type: 'POST',
                            data: {
                                dont_remove: true,
                                edition_id: editionKey,
                                bookshelf_id: shelf_id
                            },
                            dataType: 'json'
                        });
                    } catch {
                        fail('Failed to add book to reading log');
                        return;
                    }

                    if (value['My Rating'] !== '0') {
                        try {
                            await $.ajax({
                                url: `${workKey}/ratings.json`,
                                type: 'POST',
                                data: {
                                    rating: parseInt(value['My Rating']),
                                    edition_id: editionKey,
                                    bookshelf_id: shelf_id
                                },
                                dataType: 'json'
                            });
                        } catch {
                            fail('Failed to add rating');
                        }
                    }

                    if (value['Date Read'] !== '') {
                        const date_read = value['Date Read'].split('/'); // Format: "YYYY/MM/DD"
                        try {
                            await $.ajax({
                                url: `${workKey}/check-ins`,
                                type: 'POST',
                                data: JSON.stringify({
                                    edition_key: editionKey,
                                    event_type: 3, // BookshelfEvent.FINISH
                                    year: parseInt(date_read[0]),
                                    month: parseInt(date_read[1]),
                                    day: parseInt(date_read[2])
                                }),
                                dataType: 'json',
                                contentType: 'application/json',
                                beforeSend: function (xhr) {
                                    xhr.setRequestHeader('Content-Type', 'application/json');
                                    xhr.setRequestHeader('Accept', 'application/json');
                                }
                            });
                        } catch {
                            fail('Failed to set the read date');
                        }
                    }

                    if (!hasFailure()) {
                        row.append('<td class="success-imported">Imported</td>');
                        row.removeClass('selected');
                    }
                })
                .then(function () {
                    func1(++count);
                });
        });

        $('td.books-wo-isbn').each(function () {
            $(this).removeClass('hidden');
        });

        const table = document.querySelector('.import-table');
        prevPromise.then(() => showImportSummary(table));
    });

    function getWork(isbn) {
        return new Promise(function (resolve, reject) {
            var request = new XMLHttpRequest();

            request.open('GET', `/isbn/${isbn}.json`);
            request.onload = function () {
                if (request.status === 200) {
                    resolve(request.response); // we get the data here, so resolve the Promise
                } else {
                    reject(Error(request.statusText)); // if status is not 200 OK, reject.
                }
            };

            request.onerror = function () {
                reject(Error('Error fetching data.')); // error occurred, so reject the Promise
            };

            request.send(); // send the request
        });
    }
}
