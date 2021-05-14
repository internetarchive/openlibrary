import Promise from 'promise-polyfill';

export function initGoodreadsImport() {

    var l, elem, count, prevPromise;

    $(document).on('click', 'th.toggle-all input', function () {
        var checked = $(this).prop('checked');
        if (!checked) {
            $(this).prop('checked', false);
            $('input.add-book').each(function () {
                $(this).prop('checked', false);
            });
        }
        else {
            $(this).prop('checked', true)
            $('input.add-book').each(function () {
                $(this).prop('checked', true);
            });
        }
        l = $('.add-book[checked*="checked"]').length;
        $('.import-submit').attr('value', `Import ${l} Books`);
    });

    $(document).on('click', 'input.add-book', function () {
        var checked = $(this).prop('checked');
        if (!checked) {
            $(this).prop('checked', false);
        }
        else {
            $(this).prop('checked', true);
        }
        l = $('.add-book[checked*="checked"]').length;
        $('.import-submit').attr('value', `Import ${l} Books`);
    });

    function func1(value) {
        l = $('.add-book[checked*="checked"]').length;
        elem = document.getElementById('myBar');
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
        count = 0;
        prevPromise = Promise.resolve();
        $('input.add-book').each(function () {
            var input = $(this),
                checked = input.prop('checked');
            var value = JSON.parse(input.val().replace(/'/g, '"'));
            var shelf = value['Exclusive Shelf'];
            const shelves = {read: 3, 'currently-reading': 2,  'to-read': 1};
            var shelf_id = 0;
            if (shelves[shelf]){
                shelf_id = shelves[shelf];
            }
            if (checked && shelf_id != 0) {
                prevPromise = prevPromise.then(function () { // prevPromise changes in each iteration
                    $(`[isbn=${value['ISBN']}]`).addClass('selected');
                    return getWork(value['ISBN']); // return a new Promise
                }).then(function (data) {
                    var obj = JSON.parse(data);
                    $.ajax({
                        url: `${obj['works'][0].key}/bookshelves.json`,
                        type: 'POST',
                        data: {
                            dont_remove: true,
                            edition_id: obj['key'],
                            bookshelf_id: shelf_id
                        },
                        datatype: 'json',
                        success: function () {
                            if (value['My Rating'] != '0') {
                                $.ajax({
                                    url: `${obj['works'][0].key}/ratings.json`,
                                    type: 'POST',
                                    data: {
                                        rating: parseInt(value['My Rating']),
                                        edition_id: obj['key'],
                                        bookshelf_id: shelf_id
                                    },
                                    datatype: 'json',
                                    success: function () {
                                        $(`[isbn=${value['ISBN']}]`).append('<td class="success-imported">Imported</td>')
                                        $(`[isbn=${value['ISBN']}]`).removeClass('selected');
                                    },
                                    fail: function () {
                                        $(`[isbn=${value['ISBN']}]`).append('<td class="error-imported">Error</td><td class="error-imported">Failed to add Rating</td>')
                                        $(`[isbn=${value['ISBN']}]`).removeClass('selected');
                                    }
                                });
                            }
                            else {
                                $(`[isbn=${value['ISBN']}]`).append('<td class="success-imported">Imported</td>')
                                $(`[isbn=${value['ISBN']}]`).removeClass('selected');
                            }
                        },
                        fail: function () {
                            $(`[isbn=${value['ISBN']}]`).append('<td class="error-imported">Error</td><td class="error-imported">Failed to add book to reading log</td>')
                            $(`[isbn=${value['ISBN']}]`).removeClass('selected');
                        }
                    });
                    func1(++count);
                }).catch(function () {
                    $(`[isbn=${value['ISBN']}]`).append('<td class="error-imported">Error</td><td class="error-imported">Book not in collection</td>')
                    $(`[isbn=${value['ISBN']}]`).removeClass('selected');
                    func1(++count);
                });
            }
            else if (checked && shelf_id == 0) {
                $(`[isbn=${value['ISBN']}]`).append('<td class="error-imported">Error</td><td class="error-imported">Book in different Shelf</td>');
                func1(++count);
            }
        });
        $('td.books-wo-isbn').each(function () {
            $(this).removeClass('hidden');
        });
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
