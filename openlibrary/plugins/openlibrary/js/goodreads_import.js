import { slice } from "lodash";

class GoodreadsImport {
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
        this.attempted = 1;
        this.submit();
    }

    async submit() {
        document.querySelector('.import-submit').addEventListener('click', async (event) => {
            document.querySelector('input.import-submit').classList.add('hidden');
            document.getElementById('myProgress').classList.remove('hidden');
            const response = await this.batchAddToBookshelves(await this.parseReadingList());
            const reporter = new Reporter(
                response, this.isbnNotInCollection, 
                this.workIdToIsbn, this.isbnToWorkId
            );
            reporter.handleReport();
        })
    }
    
    async batchAddToBookshelves(readingList) {
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
            this.updateProgress();
            if (!row.hasAttribute('isbn')) {
                console.log('No ISBN');
                continue;
            }

            if (!row.querySelector('input.add-book').checked) {
                console.log('Not checked');
                continue;
            }
    
            const shelf = row.querySelector('[key="Exclusive Shelf"]').innerText;
            const shelf_id = shelves[shelf];
            if (shelf_id === undefined) {
                console.log('Custom shelves are not supported');
                Reporter.createNotice({
                    workId: null,
                    status: 'error',
                    isbn: null,
                    message: 'Custom shelves are not supported',
                    row: row
                });
                continue;
            }
    
            const workId = await this.getWorkId(row.getAttribute('isbn'));
            // console.log('Work ID:', workId);
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
            this.isbnToWorkId[isbn] = workId; 
            this.workIdToIsbn[workId] = isbn;
            return workId; 
        } catch (error) {
            this.isbnNotInCollection.push(isbn);
            return undefined; 
        }
    }

    updateProgress() {
        if (this.attempted === 1) {
            document.querySelector('input.import-submit').classList.add('hidden');
            document.getElementById('myProgress').classList.remove('hidden');
        }
        else {
            Reporter.updateProgressBar(this.attempted);
        }
        this.attempted++;
    }
}

class Toggler {
    constructor() {
        this.toggleAllBooks();
        this.toggleSingleBook();
    }

    toggleAllBooks() {
        document.querySelector('th.toggle-all input').addEventListener('click', (event) => {
            const isChecked = event.target.checked; 
            document.querySelectorAll('input.add-book').forEach((input) => {
                input.checked = isChecked; 
            });
            this.updateImportNumber();
        });
    }

    toggleSingleBook() {
        document.querySelectorAll('input.add-book').forEach((input) => {
            input.addEventListener('click', () => {
                this.updateImportNumber();
            });
        }
    )};

    updateImportNumber() {
        const checked = document.querySelectorAll('input.add-book:checked').length;
        document.querySelector('.import-submit').setAttribute('value', `Import ${checked} Books`);       
    } 
}

class Reporter {
    constructor(response, isbnNotInCollection, workIdToIsbn, isbnToWorkId) {
        this.successfully_added = response.successfully_added;
        this.unsuccessfully_added = response.unsuccessfully_added;
        this.isbnNotInCollection = isbnNotInCollection;
        this.workIdToIsbn = workIdToIsbn;
        this.isbnToWorkId = isbnToWorkId;
    }

    handleReport() {
        if (this.successfully_added) {
            this.successfully_added.forEach((workId) => {
                Reporter.createNotice({
                    workId: workId,
                    status: 'success',
                    isbn: this.workIdToIsbn[workId],
                    message: 'Success'
                });
            })
        }
        if (this.unsuccessfully_added) {
            this.unsuccessfully_added.forEach((workId) => {
                Reporter.createNotice({
                    workId: workId,
                    status: 'error',
                    isbn: this.workIdToIsbn[workId],
                    message: 'Likely already on shelf'
                });
            });
        }
        if (this.isbnNotInCollection) {
            this.isbnNotInCollection.forEach((isbn) => {
                Reporter.createNotice({
                    workId: this.isbnToWorkId[isbn],
                    status: 'not-in-collection',
                    isbn: isbn,
                    message: 'Not in Collection'

                });
            });
        }
    }

    static updateProgressBar(attempted) {
        const totalBooks = document.querySelectorAll('input.add-book:checked').length;
        const progressBar = document.getElementById('myProgressBar');
        const progress = (attempted / totalBooks) * 100;
        progressBar.style.width = `${progress}%`;
        progressBar.innerHTML = `${attempted} Books`;
        if (progress >= 100) {
            Reporter.goToReadingLog();
        }
    }

    static goToReadingLog() {
        const progressBar = document.getElementById('myProgressBar');
        progressBar.innerHTML = '';
        const link = document.createElement('a');
        link.href = '/account/books';
        link.style.color = 'white';
        link.innerText = 'Go to your Reading Log';
        progressBar.appendChild(link);
        document.querySelector('.cancel-button').classList.add('hidden');
    }

    static createNotice(parameters) {
        const notice = document.createElement('td');
        notice.classList.add(`${parameters.status}-imported`);
        notice.innerText = parameters.message;
        const isbn = parameters.isbn
        const row = 
            parameters.row
            ?? document.querySelector(`[isbn="${isbn}"]`);
        row.appendChild(notice);
        row.classList.remove('selected');
    }
}




export async function initGoodreadsImport() {
    function init() {
        const toggler = new Toggler();
        const goodreadsImport = new GoodreadsImport();
    }
    init();
}