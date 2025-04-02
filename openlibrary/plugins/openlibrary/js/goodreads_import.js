import { create, slice } from "lodash";

export default class GoodreadsImport {
    constructor() {
        this.isbnToWorkId = {};
        this.workIdToIsbn = {};
        this.isbnNotInCollection = [];
        this.shelves = { 'read': 3, 'currently-reading': 2, 'to-read': 1 };
        this.readingList = {
            '1': [],
            '2': [],
            '3': []
        };
        this.count = 0;
        this.toggleAllBooks();
        this.toggleSingleBook();
        this.submit();
    }

    async submit() {
        document.querySelector('.import-submit').addEventListener('click', async (event) => {
            event.preventDefault();
            const response = await this.batchAddToBookshelves(await this.parseReadingList());
            this.handleReport(response);
        })
    }
    
    async batchAddToBookshelves(readingList) {
        // console.log('Batch Adding to Bookshelves:', readingList);
    
        try {
            const response = await fetch("/works/batch/bookshelves.json", {
                method: 'POST',
                body: JSON.stringify({
                    "reading_list": readingList,
                }),
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            });
    
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
    
            const data = await response.json(); 
            // console.log('Response Data:', data); 
            return data; 
        } catch (error) {
            console.error('Error in batchAddToBookshelves:', error);
            return null; 
        }
    }

    async parseReadingList() {
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
                this.createNotice({
                    workId: null,
                    status: 'error',
                    isbn: null,
                    message: 'Custom shelves are not supported',
                    row: row
                });
                continue;
            }
    
            const workId = await this.getWorkId(row.getAttribute('isbn'));
            console.log('Work ID:', workId);
            if (workId) {
                readingList[shelf_id].push(+workId);
            }
        }
    
        return readingList;
    }

    async getWorkId(isbn) {
        try {
            const response = await fetch(`/isbn/${isbn}.json`);
            const data = await response.json();
            const editionId = data['works'][0].key;
            const workId = editionId.slice(9, -1);
            this.isbnToWorkId[isbn] = workId; // Store the mapping
            this.workIdToIsbn[workId] = isbn; // Store the reverse mapping
            return workId; 
        } catch (error) {
            this.isbnNotInCollection.push(isbn);
            return undefined; 
        }
    }

    handleReport(response) {
        if (response.successfully_added) {
            response.successfully_added.forEach((workId) => {
                this.createNotice({
                    workId: workId,
                    status: 'success',
                    isbn: null,
                    message: 'Success'
                });
            })
        }
        if (response.unsuccessfully_added) {
            response.unsuccessfully_added.forEach((workId) => {
                this.createNotice({
                    workId: workId,
                    status: 'error',
                    isbn: null,
                    message: 'Likely already on shelf'
                });
            });
        }
        if (this.isbnNotInCollection) {
            this.isbnNotInCollection.forEach((isbn) => {
                this.createNotice({
                    workId: null,
                    status: 'not-in-collection',
                    isbn: isbn,
                    message: 'Not in Collection'

                });
            });
        }
    }

    createNotice(parameters) {
        const notice = document.createElement('td', { class: `${parameters.status}-imported` });        
        notice.innerText = parameters.message;
        if (!parameters.row) {
            const isbn = this.workIdToIsbn[parameters.workId] ?? parameters.isbn;
            const row = document.querySelector(`[isbn="${isbn}"]`);
            row.appendChild(notice);
            row.classList.remove('selected');
        } 
        else {
            parameters.row.appendChild(notice);
            parameters.row.classList.remove('selected');
        }
    }


    toggleAllBooks() {
        document.querySelector('th.toggle-all input').addEventListener('click', function () {
            const isChecked = this.checked; 
            document.querySelectorAll('input.add-book').forEach(function (input) {
                input.checked = isChecked; 
            });
            updateImportNumber();
        });
    }

    toggleSingleBook() {
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

    updateImportNumber() {
        const l = document.querySelectorAll('input.add-book:checked').length;
        document.querySelector('.import-submit').setAttribute('value', `Import ${l} Books`);       
    } 

    hasFailure() {
        return $(`[isbn=${value['ISBN']}]`).hasClass('import-failure');
    };

    fail(reason) {
        if (!hasFailure()) {
            const notice = $(`[isbn=${value['ISBN']}]`);
            notice.append(`<td class="error-imported">Error</td><td class="error-imported">${reason}</td>'`)
            notice.removeClass('selected');
            notice.addClass('import-failure');
            return 'Failure Notice Given';
        }
        return 'Failure Notice Not Given';
    };
}


export async function initGoodreadsImport() {
    function init() {
        const goodreadsImport = new GoodreadsImport();
    }
    init();
}