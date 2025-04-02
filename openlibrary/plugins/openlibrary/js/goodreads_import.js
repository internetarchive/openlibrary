// import Promise from 'promise-polyfill';

import { slice } from "lodash";

// export function initGoodreadsImport() {

//     var count, prevPromise;

//     $(document).on('click', 'th.toggle-all input', function () {
//         var checked = $(this).prop('checked');
//         $('input.add-book').each(function () {
//             $(this).prop('checked', checked);
//             if (checked) {
//                 $(this).attr('checked', 'checked');
//             }
//             else {
//                 $(this).removeAttr('checked');
//             }
//         });
//         const l = $('.add-book[checked*="checked"]').length;
//         $('.import-submit').attr('value', `Import ${l} Books`);
//     });

//     $(document).on('click', 'input.add-book', function () {
//         if ($(this).prop('checked')) {
//             $(this).attr('checked', 'checked');
//         }
//         else {
//             $(this).removeAttr('checked');
//         }
//         const l = $('.add-book[checked*="checked"]').length;
//         $('.import-submit').attr('value', `Import ${l} Books`);
//     });

//     //updates the progress bar based on the book count
//     function func1(value) {
//         const l = $('.add-book[checked*="checked"]').length;
//         const elem = document.getElementById('myBar');
//         elem.style.width = `${value * (100 / l)}%`;
//         elem.innerHTML = `${value} Books`;
//         if (value * (100 / l) >= 100) {
//             elem.innerHTML = '';
//             $('#myBar').append('<a href="/account/books" style="color:white"> Go to your Reading Log </a>');
//             $('.cancel-button').addClass('hidden');
//         }
//     }

//     $('.import-submit').on('click', function () {
//         $('#myProgress').removeClass('hidden');
//         $('.cancel-button').removeClass('hidden');
//         $('input.import-submit').addClass('hidden');
//         $('th.import-status').removeClass('hidden');
//         $('th.status-reason').removeClass('hidden');
//         const shelves = { 'read': 3, 'currently-reading': 2, 'to-read': 1 };
//         count = 0;
//         // prevPromise = Promise.resolve();
//         $('input.add-book').each(function () {
//             var input = $(this),
//                 checked = input.prop('checked');
//             var value = JSON.parse(input.val().replace(/'/g, '"'));
//             var shelf = value['Exclusive Shelf'];
//             var shelf_id = 0;
//             const hasFailure = function () {
//                 return $(`[isbn=${value['ISBN']}]`).hasClass('import-failure');
//             };
//             const fail = function (reason) {
//                 if (!hasFailure()) {
//                     const element = $(`[isbn=${value['ISBN']}]`);
//                     element.append(`<td class="error-imported">Error</td><td class="error-imported">${reason}</td>'`)
//                     element.removeClass('selected');
//                     element.addClass('import-failure');
//                 }
//             };

//             if (!checked) {
//                 func1(++count);
//                 return;
//             }

//             if (shelves[shelf]) {
//                 shelf_id = shelves[shelf];
//             }

//             //used 'return' instead of 'return false' because the loop was being exited entirely
//             if (shelf_id === 0) {
//                 fail('Custom shelves are not supported');
//                 func1(++count);
//                 return;
//             }

//             const readingList = {
//                 '1': [],
//                 '2': [],
//                 '3': []
//             }

//             document.querySelectorAll('.table-row').forEach(async function (row) {
//                 if (!row.hasAttribute('isbn')) {
//                     console.log('No ISBN');
//                     return;
//                 }

//                 const shelf = row.querySelector('[key="Exclusive Shelf"]').innerText;

//                 const promise = await getWork(row.getAttribute('isbn'))['works'][0].key;
//                 console.log('Reading List', readingList);
//                 console.log("Stringify Reading List", JSON.stringify(readingList));

//                 fetch("/works/batch/bookshelves.json", {
//                     method: 'POST',
//                     body: JSON.stringify({
//                         "reading_list": readingList,
//                     }),
//                     headers: {
//                         'Content-Type': 'application/json',
//                         'Accept': 'application/json'
//                     }}
//                 ).then(response => {
//                     console.log('Response:', response);
//                 });
//             });
//         });



//         //     prevPromise = prevPromise.then(function () { // prevPromise changes in each iteration
//         //         $(`[isbn=${value['ISBN']}]`).addClass('selected');
//         //         return getWork(value['ISBN']); // return a new Promise
//         //     }).then(function (data) {
//         //         var obj = JSON.parse(data);
//         //         $.ajax({
//         //             url: `${obj['works'][0].key}/bookshelves.json`,
//         //             type: 'POST',
//         //             data: {
//         //                 dont_remove: true,
//         //                 edition_id: obj['key'],
//         //                 bookshelf_id: shelf_id
//         //             },
//         //             dataType: 'json'
//         //         }).fail(function () {
//         //             fail('Failed to add book to reading log');
//         //         }).done(function () {
//         //             if (value['My Rating'] !== '0') {
//         //                 return $.ajax({
//         //                     url: `${obj['works'][0].key}/ratings.json`,
//         //                     type: 'POST',
//         //                     data: {
//         //                         rating: parseInt(value['My Rating']),
//         //                         edition_id: obj['key'],
//         //                         bookshelf_id: shelf_id
//         //                     },
//         //                     dataType: 'json',
//         //                     fail: function () {
//         //                         fail('Failed to add rating');
//         //                     }
//         //                 });
//         //             }
//         //         }).then(function () {
//         //             if (value['Date Read'] !== '') {
//         //                 const date_read = value['Date Read'].split('/'); // Format: "YYYY/MM/DD"
//         //                 return $.ajax({
//         //                     url: `${obj['works'][0].key}/check-ins`,
//         //                     type: 'POST',
//         //                     data: JSON.stringify({
//         //                         edition_key: obj['key'],
//         //                         event_type: 3,  // BookshelfEvent.FINISH
//         //                         year: parseInt(date_read[0]),
//         //                         month: parseInt(date_read[1]),
//         //                         day: parseInt(date_read[2])
//         //                     }),
//         //                     dataType: 'json',
//         //                     contentType: 'application/json',
//         //                     beforeSend: function (xhr) {
//         //                         xhr.setRequestHeader('Content-Type', 'application/json');
//         //                         xhr.setRequestHeader('Accept', 'application/json');
//         //                     },
//         //                     fail: function () {
//         //                         fail('Failed to set the read date');
//         //                     }
//         //                 });
//         //             }
//         //         });
//         //         if (!hasFailure()) {
//         //             $(`[isbn=${value['ISBN']}]`).append('<td class="success-imported">Imported</td>')
//         //             $(`[isbn=${value['ISBN']}]`).removeClass('selected');
//         //         }
//         //         func1(++count);
//         //     }).catch(function () {
//         //         fail('Book not in collection');
//         //         func1(++count);
//         //     });
//         // });

//         // $('td.books-wo-isbn').each(function () {
//         //     $(this).removeClass('hidden');
//         // });
//     });

//     async function getWork(isbn) {
//         return new Promise(function (resolve, reject) {
//             var request = new XMLHttpRequest();

//             request.open('GET', `/isbn/${isbn}.json`);
//             request.onload = function () {
//                 if (request.status === 200) {
//                     resolve(request.response); // we get the data here, so resolve the Promise
//                 } else {
//                     reject(Error(request.statusText)); // if status is not 200 OK, reject.
//                 }
//             };

//             request.onerror = function () {
//                 reject(Error('Error fetching data.')); // error occurred, so reject the Promise
//             };

//             request.send(); // send the request
//         });
//     }
// }

export async function initGoodreadsImport() {

    async function awaitSubmit() {
        document.querySelector('.import-submit').addEventListener('click', async function (event) {
            event.preventDefault();
            const readingList = await parseReadingList();
            success = await batchAddToBookshelves(readingList);
            console.log('Success:', success.status);
        });
    }

    async function batchAddToBookshelves(readingList) {
        console.log('Batch Adding to Bookshelves:', readingList);

        fetch("/works/batch/bookshelves.json", {
            method: 'POST',
            body: JSON.stringify({
                "reading_list": readingList,
            }),
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }}
        ).then(response => {
            // console.log('Response:', response);
            return response.json();
        }).catch(error => {
            console.error('Error:', error);
        });
    }

    async function parseReadingList() {
        const shelves = { 'read': 3, 'currently-reading': 2, 'to-read': 1 };
        const readingList = {
            '1': [],
            '2': [],
            '3': []
        };
    
        const rows = document.querySelectorAll('.table-row');
        for (const row of rows) {
            if (!row.hasAttribute('isbn')) {
                console.log('No ISBN');
                continue;
            }
    
            const shelf = row.querySelector('[key="Exclusive Shelf"]').innerText;
            const shelf_id = shelves[shelf];
            if (shelf_id === undefined) {
                console.log('Custom shelves are not supported');
                continue;
            }
    
            const workId = await getWorkId(row.getAttribute('isbn'));
            console.log('Work ID:', workId);
            if (workId) {
                readingList[shelf_id].push(+workId);
            }
        }
    
        return readingList;
    }

    async function getWorkId(isbn) {
        try {
            const response = await fetch(`/isbn/${isbn}.json`);
            const data = await response.json();
            // console.log('Data:', data);
            const editionId = data['works'][0].key;
            // console.log('Edition ID:', editionId);
            const workId = editionId.slice(9, -1);
            // console.log('Work ID:', workId);
            return workId; 
        } catch (error) {
            console.error('Error:', error);
            return undefined; 
        }
    }

    function toggleAllBooks() {
        document.querySelector('th.toggle-all input').addEventListener('click', function () {
            const isChecked = this.checked; 
            document.querySelectorAll('input.add-book').forEach(function (input) {
                input.checked = isChecked; 
            });
            updateImportNumber();
        });
    }

    function toggleSingleBook() {
        document.querySelectorAll('input.add-book').forEach(function (input) {
            input.addEventListener('click', function () {
                if (this.checked) {
                    this.setAttribute('checked', 'checked');
                }
                else {
                    this.removeAttribute('checked');
                }
                updateImportNumber();
            });
        }
    )};

    function updateImportNumber() {
        const l = document.querySelectorAll('input.add-book:checked').length;
        document.querySelector('.import-submit').setAttribute('value', `Import ${l} Books`);       
    } 

    // const hasFailure = () => {
    //     return $(`[isbn=${value['ISBN']}]`).hasClass('import-failure');
    // };
    const fail = (reason) => {
        if (!hasFailure()) {
            const notice = $(`[isbn=${value['ISBN']}]`);
            notice.append(`<td class="error-imported">Error</td><td class="error-imported">${reason}</td>'`)
            notice.removeClass('selected');
            notice.addClass('import-failure');
            return 'Failure Notice Given';
        }
        return 'Failure Notice Not Given';
    };

    toggleAllBooks();
    toggleSingleBook();
    awaitSubmit();

}