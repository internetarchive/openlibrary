/**
 * @param {string} container
 */
function getIsbnToElementMap(container) {
    const reISBN = /(978)?[0-9]{9}[0-9X]/i;
    const elements = Array.from(document.querySelectorAll(container));
    const isbnElementMap = {};
    elements.forEach((e) => {
        const isbnMatches = e.outerHTML.match(reISBN);
        if (isbnMatches) {
            isbnElementMap[isbnMatches[0]] = e;
        }
    })
    return isbnElementMap;
}

/**
 * @param {string[]} isbnList
 * @returns {Promise<Array>}
 */
async function getAvailabilityDataFromOpenLibrary(isbnList) {
    const apiBaseUrl = 'https://openlibrary.org/search.json';
    const apiUrl = `${apiBaseUrl}?fields=*,availability&q=isbn:${isbnList.join('+OR+')}`;
    const response = await fetch(apiUrl);
    const jsonResponse = await response.json();
    const olDocs = jsonResponse.docs;
    const isbnToAvailabilityDataMap = {};
    olDocs.forEach((doc) => {
        const isbnList = doc.isbn;
        isbnList.forEach((isbn) => {
            isbnToAvailabilityDataMap[isbn] = doc?.availability;
        });
    });
    return isbnToAvailabilityDataMap;
}

/**
 * @param {object} options
 * @param {string} options.bookContainer class name of the HTML element associated with a book. We will try to find a book identifier (eg ISBN) in each of these.
 * @param {string} [options.selectorToPlaceBtnIn] The class name of the HTML element that we will add the Open Library button to. Each `bookContainer` should have one of these. If not specified, will just append to `bookContainer`.
 * @param {string} [options.textOnBtn] The text on the button
 *
 * @example
 * addOpenLibraryButtons({
 *    bookContainer: ".book-container",
 *    selectorToPlaceBtnIn: ".btn-container",
 *    textOnBtn: "Open Library!"
 * });
 */
async function addOpenLibraryButtons(options) {
    const {bookContainer, selectorToPlaceBtnIn, textOnBtn} = options
    if (bookContainer === undefined) {
        throw Error(
            'book container must be specified in options for open library buttons to populate!'
        )
    }
    const foundIsbnElementsMap = getIsbnToElementMap(bookContainer);
    const availabilityResults = await getAvailabilityDataFromOpenLibrary(Object.keys(foundIsbnElementsMap))
    Object.keys(foundIsbnElementsMap).map((isbn) => {
        const availability = availabilityResults[isbn]
        if (availability && availability.status !== 'error') {
            const e = foundIsbnElementsMap[isbn]
            const buttons = selectorToPlaceBtnIn ? e.querySelector(selectorToPlaceBtnIn) : e;
            const openLibraryBtnLink = document.createElement('a')
            openLibraryBtnLink.href = `https://openlibrary.org/works/${availability.openlibrary_work}`
            openLibraryBtnLink.text = textOnBtn || 'Open Library'
            openLibraryBtnLink.classList.add('openlibrary-btn')
            buttons.append(openLibraryBtnLink);
        }
    })
}

// Expose globally so clients can use this method
window.addOpenLibraryButtons = addOpenLibraryButtons;
