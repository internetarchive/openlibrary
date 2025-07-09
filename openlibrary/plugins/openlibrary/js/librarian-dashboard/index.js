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
    const table = rootElement.querySelector('.dq-table')
    rootElement.addEventListener('click', () => {
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
    const rows = table.querySelectorAll('.dq-table__row')

    await Promise.all([...rows].map(row => updateRow(row, bookCount)))
}

/**
 * Fetches data quality information and updates the given row accordingly.
 *
 * @param {HTMLTableRowElement} row A row in the data quality table
 * @param {number} totalCount Total number of search results
 * @returns {Promise<void>}
 */
async function updateRow(row, totalCount) {
    const queryFragment = row.dataset.queryFragment
    const apiUrl = buildUrl(queryFragment, false)
    const searchPageUrl = buildUrl(queryFragment)

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

    // Render status cell markup
    let newCellMarkup
    if (data === null) {
        newCellMarkup = renderErrorCell(searchPageUrl)
    } else {
        newCellMarkup = renderResultsCells(data, totalCount, searchPageUrl)
    }

    // Include retry affordance, regardless of result
    newCellMarkup += renderRetryCell()

    replaceStatusCells(row, newCellMarkup)

    // Add listener to retry affordance
    const retryAffordance = row.querySelector('.dqs-run-again')
    retryAffordance.addEventListener('click', () => {
        // Update view to "pending"
        replaceStatusCells(row, renderPendingCell())

        // Retry query
        updateRow(row, totalCount)
    })
}

/**
 * Constructs a search API or page URL containing the given query fragment.
 *
 * @param {string} queryFragment
 * @param {boolean} forUi
 */
function buildUrl(queryFragment, forUi = true) {
    const match = window.location.pathname.match(/authors\/(OL\d+A)/)
    const queryParamString = match ? `?q=author_key:${match[1]}` : window.location.search

    const params = new URLSearchParams(queryParamString)
    params.set('q', `${params.get('q')} ${queryFragment}`)
    return `/search${forUi ? '' : '.json'}?${params.toString()}`
}

/**
 * Replaces the "status" cells of the given row with the given rendered HTML
 *
 * @param {HTMLTableRowElement} row
 * @param {string} newCellMarkup Markup for the new status cells
 */
function replaceStatusCells(row, newCellMarkup) {
    const statusCells = row.querySelectorAll('td:not(.dq-table__criterion-cell)')
    for (const cell of statusCells) {
        cell.remove()
    }

    const template = document.createElement('template')
    template.innerHTML = newCellMarkup
    row.append(...template.content.children)
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
function renderResultsCells(results, totalCount, failingHref) {
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
        <button class="dqs-run-again">
            ${i18nStrings['reload']}
        </button>
    </td>`
}

/**
 * Returns an HTML string containing an error message.
 *
 * @param {string} href Link to search page for failing query
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
