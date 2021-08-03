/**
 * @param {string} container
 */
function getIsbnToElementMap(container) {
    const reISBN = /((978)?[0-9][0-9]{10}[0-9xX])|((978)?[0-9]{9}[0-9Xx])/;
    const elements = document.getElementsByClassName(container);
    const isbnElementMap = {};
    elements.forEach((e) => {
        const isbnMatches = e.innerHTML.match(reISBN);
        if (isbnMatches) {
            isbnElementMap[isbnMatches[0]] = e;
        }
    })
    return isbnElementMap;
};

export const getAvailabilityDataFromArchiveOrg = async isbnList => {
    const apiBaseUrl = 'https://archive.org/services/availability'
    const apiUrl = `${apiBaseUrl}?isbn=${isbnList.join(',')}`;
    const response = await fetch(apiUrl);
    const jsonResponse = await response.json();
    return jsonResponse.responses;
};

export const addOpenLibraryButtons = async options => {
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
