class GoodreadsImport {
    constructor() {
        this.isbnToWorkId = {};
        this.workIdToIsbn = {};
        this.isbnNotInCollection = [];
        this.shelves = { read: 3, 'currently-reading': 2, 'to-read': 1 };
        this.readingList = {
            1: [],
            2: [],
            3: []
        };
        this.attempted = 1;
        this.submit();
    }

    async submit() {
        document.querySelector('.import-submit').addEventListener('click', async () => {
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
            const response = await fetch('/works/batch/bookshelves.json', {
                method: 'POST',
                body: JSON.stringify({
                    reading_list: readingList,
                }),
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            return data;
        } catch (error) {
            return null;
        }
    }

    /*
    This function parses a readingList from the Goodreads Import page.
    It returns a dictionary with the following structure:
    {
        '1': [{workId: number, editionId: number}, ...], // to-read
        '2': [{workId: number, editionId: number}, ...], // currently-reading
        '3': [{workId: number, editionId: number}, ...]  // read
    }
    */
    async parseReadingList() {
        const shelves = { read: 3, 'currently-reading': 2, 'to-read': 1 };
        const readingList = {
            1: [],
            2: [],
            3: []
        };

        const rows = document.querySelectorAll('.table-row');
        for (const row of rows) {
            this.updateProgress();
            if (!row.hasAttribute('isbn')) {
                continue;
            }

            if (!row.querySelector('input.add-book').checked) {
                continue;
            }

            this.attempted++;

            const shelf = row.querySelector('[key="Exclusive Shelf"]').innerText;
            const shelf_id = shelves[shelf];
            if (shelf_id === undefined) {
                Reporter.createNotice({
                    workId: null,
                    status: 'error',
                    isbn: null,
                    message: 'Custom shelves are not supported',
                    row: row
                });
                continue;
            }

            const workId = await this.getIdSet(row.getAttribute('isbn'));
            if (workId) {
                readingList[shelf_id].push(workId);
            }
        }
        return readingList;
    }

    /*
    This function fetches the workId and editionId for a given ISBN.
    return type: { workId: number, editionId: number }
    */
    async getIdSet(isbn) {
        try {
            const response = await fetch(`/isbn/${isbn}.json`);
            const data = await response.json();
            const workId = data['works'][0].key;
            const workIdNumber = workId.slice(9, -1);
            const editionId = data.key.slice(9, -1);
            this.isbnToWorkId[isbn] = workId;
            this.workIdToIsbn[workIdNumber] = isbn;
            return {
                workId: +workIdNumber,
                editionId: +editionId
            };
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
        )}

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
        new Toggler();
        new GoodreadsImport();
    }
    init();
}
