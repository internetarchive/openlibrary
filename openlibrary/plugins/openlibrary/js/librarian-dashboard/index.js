let i18nStrings;

/**
 * Initializes the given librarian dashboard component.
 *
 * Adds click listener to root details element of the dashboard that
 * triggers the data quality queries.
 *
 * @param {HTMLDetailsElement} rootElement
 */
export function initLibrarianDashboard(rootElement) {
    i18nStrings = JSON.parse(rootElement.dataset.i18n)
    const table = rootElement.querySelector(".dq-table")
    rootElement.addEventListener("click", () => {
        populateTable(table)
    }, {once: true})
}

/**
 * Updates each row of the given data quality table.
 *
 * @param {HTMLTableElement} table
 * @returns {Promise<void>}
 */
async function populateTable(table) {
    const bookCount = Number(table.dataset.totalBooks)
    const rows = table.querySelectorAll(".dq-table__row")

    for (const row of rows) {
        updateRow(row, bookCount)
        // Wait before updating next row
        await new Promise(resolve => setTimeout(resolve, 500))
    }
}

/**
 * Fetches data quality information and updates the given row accordingly.
 *
 * @param {HTMLTableRowElement} row A row in the data quality table
 * @param {number} totalCount Total number of search results
 * @returns {Promise<void>}
 */
async function updateRow(row, totalCount) {
    const apiUrl = row.dataset.apiUrl
    const searchPageUrl = row.dataset.searchUiUrl

    // Make query
    const data = await fetch(apiUrl)
        .then((resp) => {
            if (!resp.ok) {
                throw new Error(`Data quality response status : ${resp.status}`)
            }
            return resp.json()
        })
        .catch(() => {
            return null;
        })

    // Update row with results
    let newCellMarkup
    if (data === null) {
        newCellMarkup = renderErrorCell(row)
    } else {
        newCellMarkup = renderResultsCells(row, data, totalCount, searchPageUrl)
    }

    newCellMarkup += renderRetryCell()

    const mutableCells = row.querySelectorAll("td:not(.dq-table__criterion-cell)")
    for (const cell of mutableCells) {
        cell.remove()
    }

    const template = document.createElement("template")
    template.innerHTML = newCellMarkup
    row.append(...template.content.children)

    // Add listener to retry affordance
    const retryAffordance = row.querySelector(".dqs-run-again")
    retryAffordance.addEventListener("click", () => {
        // Update view to "pending"
        const oldCells = row.querySelectorAll("td:not(.dq-table__criterion-cell)")
        for (const cell of oldCells) {
            cell.remove()
        }
        template.innerHTML = renderPendingCell()
        row.append(...template.content.children)

        // Retry query
        updateRow(row, totalCount)
    })
}

/**
 * Returns an HTML string containing the data quality results of the given row.
 *
 * @param {Record} results Search results
 * @param {Number} totalCount Total number of results
 * @param {string} failingHref URL of the `/search` page for the row's query
 *
 * @returns {string} HTML string
 */
function renderResultsCells(row, results, totalCount, failingHref) {
    const numFound = results.numFound
    const percentage = Math.floor(((totalCount - numFound) / totalCount) * 100)

    return `<td class="dq-table__results-cell">
        <meter title="${numFound} of ${totalCount}" min="0" max="100" value="${percentage}"></meter>
        <span>${percentage}%</span>
    </td>
    <td style="text-align:right">
        <a href="${failingHref}">${numFound} ${i18nStrings['failing']}</a>
    </td>`
}

/**
 * Returns an HTML string containing a retry button.
 *
 * @returns {string} HTML string
 */
function renderRetryCell() {
    return `<td>
        <button class="dqs-run-again" title="${i18nStrings['retry']}">
            ${i18nStrings["retry"]}
        </button>
    </td>`
}

/**
 * Returns an HTML string containing an error message.
 *
 * @param {string} href
 * @returns {string}
 */
function renderErrorCell(href) {
    return `<td colspan="2">
        <a href="${href}">${i18nStrings['error']}</a>
    </td>`
}

/**
 * Returns an HTML string containing a loading message.
 *
 * @returns {string}
 */
function renderPendingCell() {
    return `<td colspan="3">${i18nStrings['loading']}</td>`
}
