/* global importBooksFromUrl, importBooksFromIsbns, getLoggedInUsername, fetchUserLists, createList, addEditionsToList */
/* eslint-disable no-console, no-unused-vars */
/**
 * Bulk Import UI
 * UI rendering and interaction functions for the bulk import page
 * Depends on: isbn-utils.js, list-api.js
 */

/**
 * Detect input type: URL, Edition IDs, or ISBNs.
 * @param {string} input - User input
 * @returns {'url'|'edition_ids'|'isbns'} Input type
 */
function detectInputType(input) {
    const trimmed = input.trim();
    if (/^https?:\/\//i.test(trimmed)) return 'url';
    if (/\/books\/OL\d+M/i.test(trimmed)) return 'edition_ids';
    return 'isbns';
}

/**
 * Parse Edition IDs from text (e.g., /books/OL25083437M).
 * @param {string} input - Text containing edition IDs
 * @returns {Array} Array of edition objects
 */
function parseEditionIds(input) {
    const regex = /\/books\/(OL\d+M)/gi;
    const matches = [...input.matchAll(regex)];
    const uniqueIds = [...new Set(matches.map(m => m[1]))];

    return uniqueIds.map(id => ({
        editionKey: `/books/${id}`,
        workKey: null,
        title: `Edition ${id}`,
        coverId: null,
        matchedIsbn: 'N/A'
    }));
}

/**
 * Process any input type and return editions.
 * @param {string} input - URL, ISBNs, or Edition IDs
 * @param {function} onProgress - Optional progress callback
 * @returns {Promise<Array>} Array of edition objects
 */
async function processInput(input, onProgress) {
    const type = detectInputType(input);

    if (onProgress) onProgress(`Detected input type: ${type}`);

    switch (type) {
    case 'url':
        return await importBooksFromUrl(input);
    case 'edition_ids':
        return parseEditionIds(input);
    case 'isbns':
        return await importBooksFromIsbns(input);
    default:
        throw new Error('Unknown input type');
    }
}

/**
 * Generate cover image URL from cover ID.
 * @param {number|null} coverId
 * @param {string} size - 'S', 'M', or 'L'
 */
function getCoverUrl(coverId, size = 'S') {
    if (!coverId) return '/images/icons/avatar_book-sm.png';
    return `https://covers.openlibrary.org/b/id/${coverId}-${size}.jpg`;
}

/**
 * Render preview table with checkboxes, covers, and titles.
 * @param {Array} editions - Edition objects
 * @param {HTMLElement} container - Container element
 */
function renderPreviewTable(editions, container) {
    if (!editions || editions.length === 0) {
        container.innerHTML = '<p>No editions found.</p>';
        return;
    }

    const table = document.createElement('table');
    table.className = 'bulk-import-preview';
    table.style.cssText = 'width:100%; border-collapse:collapse; margin:1rem 0;';

    table.innerHTML = `
        <thead>
            <tr style="background:#f5f5f5;">
                <th style="padding:8px; width:40px;">
                    <input type="checkbox" id="selectAll" aria-label="Select all editions" checked>
                </th>
                <th style="padding:8px; width:40px;">#</th>
                <th style="padding:8px; width:50px;">Cover</th>
                <th style="padding:8px; text-align:left;">Title</th>
                <th style="padding:8px; width:120px;">ISBN</th>
            </tr>
        </thead>
        <tbody>
            ${editions.map((ed, i) => `
                <tr style="border-bottom:1px solid #ddd;">
                    <td style="padding:8px; text-align:center;">
                        <input type="checkbox" class="edition-checkbox" data-index="${i}" aria-label="Select ${ed.title || `edition ${i + 1}`}" checked>
                    </td>
                    <td style="padding:8px; text-align:center; color:#666;">${i + 1}</td>
                    <td style="padding:8px;">
                        <img src="${getCoverUrl(ed.coverId)}" alt="" style="height:40px; width:auto;">
                    </td>
                    <td style="padding:8px;">
                        <a href="${ed.editionKey}" target="_blank">${ed.title || 'Unknown Title'}</a>
                    </td>
                    <td style="padding:8px; font-family:monospace; font-size:0.85em;">
                        ${ed.matchedIsbn}
                    </td>
                </tr>
            `).join('')}
        </tbody>
    `;

    container.innerHTML = '';

    // Wrap table in scrollable container
    const wrapper = document.createElement('div');
    wrapper.className = 'bulk-import-preview-wrapper';
    wrapper.style.cssText = 'max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; margin: 1rem 0;';
    wrapper.appendChild(table);
    container.appendChild(wrapper);

    // Select all functionality
    const selectAll = table.querySelector('#selectAll');
    const checkboxes = table.querySelectorAll('.edition-checkbox');

    selectAll.addEventListener('change', () => {
        checkboxes.forEach(cb => cb.checked = selectAll.checked);
    });

    // Store editions on container for later retrieval
    container._editions = editions;
}

/**
 * Render list selector dropdown.
 * @param {HTMLElement} container - Container element
 * @param {string} username - Logged in username
 */
async function renderListSelector(container, username) {
    const lists = await fetchUserLists(username);

    const wrapper = document.createElement('div');
    wrapper.className = 'list-selector';
    wrapper.style.cssText = 'margin:1rem 0; padding:1rem; background:#f9f9f9; border-radius:8px;';

    wrapper.innerHTML = `
        <label for="listSelect" style="display:block; margin-bottom:0.5rem; font-weight:bold;">Add to:</label>
        <select id="listSelect" style="width:100%; padding:8px; margin-bottom:1rem; font-size:1rem;">
            <option value="__new__">➕ Create new list...</option>
            ${lists.entries.map(list => `
                <option value="${list.url || list.full_url}">${list.name} (${list.seed_count || 0} items)</option>
            `).join('')}
        </select>

        <div id="newListFields" style="margin-bottom:1rem;">
            <input type="text" id="newListName" placeholder="New list name"
                   style="width:100%; padding:8px; font-size:1rem; margin-bottom:0.5rem;">
            <input type="text" id="newListDesc" placeholder="Description (optional)"
                   style="width:100%; padding:8px; font-size:1rem;">
        </div>

        <button id="addToListBtn" style="background:#0074d9; color:white; padding:10px 20px; border:none; border-radius:4px; cursor:pointer; font-size:1rem;">
            Add Selected to List
        </button>
        <span id="statusMessage" style="margin-left:1rem;"></span>
    `;

    container.appendChild(wrapper);

    // Toggle new list fields visibility
    const listSelect = wrapper.querySelector('#listSelect');
    const newListFields = wrapper.querySelector('#newListFields');

    listSelect.addEventListener('change', () => {
        newListFields.style.display = listSelect.value === '__new__' ? 'block' : 'none';
    });

    return wrapper;
}

/**
 * Handle adding selected editions to list.
 * @param {HTMLElement} previewContainer - Container with preview table
 * @param {HTMLElement} selectorContainer - Container with list selector
 * @param {string} username - Logged in username
 */
async function handleAddToList(previewContainer, selectorContainer, username) {
    const editions = previewContainer._editions;
    const checkboxes = previewContainer.querySelectorAll('.edition-checkbox:checked');
    const selectedIndices = [...checkboxes].map(cb => parseInt(cb.dataset.index));
    const selectedEditions = selectedIndices.map(i => editions[i]);

    if (selectedEditions.length === 0) {
        alert('Please select at least one edition.');
        return;
    }

    const listSelect = selectorContainer.querySelector('#listSelect');
    const statusMsg = selectorContainer.querySelector('#statusMessage');
    const btn = selectorContainer.querySelector('#addToListBtn');

    btn.disabled = true;
    statusMsg.textContent = 'Adding...';
    statusMsg.style.color = '#666';

    try {
        let listKey;

        if (listSelect.value === '__new__') {
            const name = selectorContainer.querySelector('#newListName').value.trim();
            const desc = selectorContainer.querySelector('#newListDesc').value.trim();

            if (!name) {
                throw new Error('Please enter a list name.');
            }

            const list = await createList(username, name, desc);
            listKey = list.key || list.url;
            statusMsg.textContent = `Created list: ${name}`;
        } else {
            listKey = listSelect.value;
        }

        await addEditionsToList(listKey, selectedEditions);

        statusMsg.textContent = `✓ Added ${selectedEditions.length} editions! Redirecting...`;
        statusMsg.style.color = 'green';

        // Redirect to the list
        setTimeout(() => {
            window.location.href = listKey;
        }, 1000);

    } catch (e) {
        statusMsg.textContent = `✖ Error: ${e.message}`;
        statusMsg.style.color = 'red';
    } finally {
        btn.disabled = false;
    }
}

/**
 * Initialize the bulk import UI.
 * @param {string} containerSelector - CSS selector for container element
 */
async function initBulkImportUI(containerSelector) {
    const container = document.querySelector(containerSelector);
    if (!container) {
        console.error(`Container not found: ${containerSelector}`);
        return;
    }

    // Check login
    const username = await getLoggedInUsername();
    if (!username) {
        container.innerHTML = '<p style="color:red;">Please log in to use this feature.</p>';
        return;
    }

    // Build UI
    container.innerHTML = `
        <div style="font-family: sans-serif; max-width: 800px; margin: 0 auto;">
            <h2>Bulk Import Books</h2>
            <p>Enter a URL, list of ISBNs, or Edition IDs:</p>

            <textarea id="bulkInput" rows="5"
                      style="width:100%; padding:10px; font-size:1rem; font-family:monospace;"
                      placeholder="https://example.com/bookshelf&#10;OR&#10;978-0-13-468599-1, 0-596-51774-1&#10;OR&#10;/books/OL25083437M, /books/OL27448799M"></textarea>

            <button id="processBtn" style="margin-top:1rem; padding:10px 20px; font-size:1rem; cursor:pointer;">
                🔍 Process Input
            </button>

            <div id="previewContainer" style="margin-top:1rem;"></div>
            <div id="listSelectorContainer"></div>
        </div>
    `;

    const input = container.querySelector('#bulkInput');
    const processBtn = container.querySelector('#processBtn');
    const previewContainer = container.querySelector('#previewContainer');
    const listSelectorContainer = container.querySelector('#listSelectorContainer');

    processBtn.addEventListener('click', async () => {
        const value = input.value.trim();
        if (!value) {
            alert('Please enter a URL, ISBNs, or Edition IDs.');
            return;
        }

        // Check if user is logged in
        const currentUser = await getLoggedInUsername();
        if (!currentUser) {
            window.location.href = '/account/login?redirect=/account/import/bulk';
            return;
        }

        processBtn.disabled = true;
        processBtn.textContent = '⏳ Processing...';
        listSelectorContainer.innerHTML = '';

        // Animated loading indicator
        let dots = 0;
        const loadingEl = document.createElement('p');
        loadingEl.style.cssText = 'font-size: 1.1rem; color: #666;';
        loadingEl.textContent = 'Processing';
        previewContainer.innerHTML = '';
        previewContainer.appendChild(loadingEl);

        const loadingInterval = setInterval(() => {
            dots = (dots + 1) % 4;
            loadingEl.textContent = `Loading${'.'.repeat(dots || 1)}`;
        }, 400);

        try {
            const editions = await processInput(value);
            clearInterval(loadingInterval);
            renderPreviewTable(editions, previewContainer);

            const selectorWrapper = await renderListSelector(listSelectorContainer, username);

            // Wire up the add button
            const addBtn = selectorWrapper.querySelector('#addToListBtn');
            addBtn.addEventListener('click', () => {
                handleAddToList(previewContainer, selectorWrapper, username);
            });

        } catch (e) {
            clearInterval(loadingInterval);
            previewContainer.innerHTML = `<p style="color:red;">Error: ${e.message}</p>`;
        } finally {
            processBtn.disabled = false;
            processBtn.textContent = '🔍 Process Input';
        }
    });

    console.log('%c✓ Bulk Import UI initialized', 'color: green; font-weight: bold;');
}
