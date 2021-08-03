/**
 * @param {string} container
 */
function getIsbnToElementMap(container) {
    const reISBN = /((978)?[0-9][0-9]{10}[0-9xX])|((978)?[0-9]{9}[0-9Xx])/;
    const elements = Array.from(document.getElementsByClassName(container));
    const isbnElementMap = {};
    elements.forEach((e) => {
        const isbnMatches = e.innerHTML.match(reISBN);
        if (isbnMatches) {
            isbnElementMap[isbnMatches[0]] = e;
        }
    })
    return isbnElementMap;
};

/**
 * @param {string[]} isbnList
 * @returns {Promise<Array>}
 */
async function getAvailabilityDataFromArchiveOrg(isbnList) {
    const apiBaseUrl = 'https://archive.org/services/availability'
    const apiUrl = `${apiBaseUrl}?isbn=${isbnList.join(',')}`;
    const response = await fetch(apiUrl);
    const jsonResponse = await response.json();
    return jsonResponse.responses;
};

/**
 * @param {object} options
 * @param {string} options.bookContainer class name of the HTML element associated with a book. We will try to find a book identifier (eg ISBN) in each of these.
 * @param {string} options.selectorToPlaceBtnIn The class name of the HTML element that we will add the Open Library button to. Each `bookContainer` should have one of these.
 * @param {string} [options.textOnBtn] The text on the button
 *
 * @example
 * addOpenLibraryButtons({
 *    bookContainer: "book-container",
 *    selectorToPlaceBtnIn: "btn-container",
 *    textOnBtn: "Open Library!"
 * });
 */
async function addOpenLibraryButtons(options) {
    const {bookContainer, selectorToPlaceBtnIn, textOnBtn} = options
    if (bookContainer === undefined || selectorToPlaceBtnIn === undefined) {
        throw Error(
            'book container and button parent must be specified in options for open library buttons to populate!'
        )
    }
    const foundIsbnElementsMap = getIsbnToElementMap(bookContainer);
    const availabilityResults = await getAvailabilityDataFromArchiveOrg(Object.keys(foundIsbnElementsMap))
    Object.keys(foundIsbnElementsMap).map((isbn) => {
        const availability = availabilityResults[isbn];
        if (availability && availability.status !== 'error') {
            const e = foundIsbnElementsMap[isbn];
            const buttons = e.getElementsByClassName(selectorToPlaceBtnIn)[0];
            const openLibraryBtnDiv = `<div>
                <a 
                    class="openlibrary-btn" 
                    href="https://openlibrary.org/borrow/ia/${availability.identifier}?ref=">
                    ${textOnBtn || 'Open Library'}
                </a>
            </div>`
            buttons.innerHTML = `${buttons.innerHTML}${openLibraryBtnDiv}`;
        }
    })
};

// Expose globally so clients can use this method
window.addOpenLibraryButtons = addOpenLibraryButtons;
