/* eslint-disable no-console, no-unused-vars */
const CORS_PROXIES = [
    url => `https://corsproxy.io/?${encodeURIComponent(url)}`,
    url => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
    url => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(url)}`
];

async function fetchWithProxy(url) {
    for (const proxyFn of CORS_PROXIES) {
        const proxyUrl = proxyFn(url);
        try {
            const response = await fetch(proxyUrl);
            if (response.ok) {
                const text = await response.text();
                console.log(`%cFetched ${text.length} bytes`, 'color: green;');
                return text;
            }
        } catch (e) {
            continue;
        }
    }
    throw new Error('All CORS proxies failed');
}

async function importBooksFromUrl(url) {
    if (!url) {
        console.error('Please provide a URL');
        return;
    }

    console.log(
        `%cStarting import from: ${url}`,
        'font-weight: bold; color: #007bff;'
    );

    let html = '';
    try {
        html = await fetchWithProxy(url);
    } catch (e) {
        console.error(`%cFetch failed: ${e.message}`, 'color: red;');
        console.log('%cTip: Copy the page source and use importBooksFromIsbns(text) instead', 'color: orange;');
        return;
    }

    const isbns = extractIsbns(html);
    console.log(`%c${isbns.length} ISBNs found`, 'color: #0d6efd; font-weight: bold;');

    if (!isbns.length) return;

    return await lookupEditions(isbns);
}

async function importBooksFromIsbns(input) {
    const isbns = extractIsbns(input);
    console.log(`%c${isbns.length} ISBNs found`, 'color: #0d6efd; font-weight: bold;');

    if (!isbns.length) return;

    return await lookupEditions(isbns);
}

function extractIsbns(text) {
    const isbnRegex = /\b(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx]\b/g;
    const matches = text.match(isbnRegex) || [];

    const uniqueIsbns = new Set();
    matches.forEach(m => {
        const clean = m.replace(/[-\s]/g, '').toUpperCase();
        if (isValidIsbn(clean)) uniqueIsbns.add(clean);
    });

    return Array.from(uniqueIsbns);
}

async function lookupEditions(isbns) {
    const chunkSize = 50;
    const editions = [];

    const totalIsbns = isbns.length;
    const totalBatches = Math.ceil(totalIsbns / chunkSize);
    let processedIsbns = 0;

    for (let i = 0; i < isbns.length; i += chunkSize) {
        const chunk = isbns.slice(i, i + chunkSize);
        const chunkSet = new Set(chunk);
        processedIsbns += chunk.length;

        const batchNum = Math.floor(i / chunkSize) + 1;
        const percentDone = ((processedIsbns / totalIsbns) * 100).toFixed(1);

        console.log(
            `%c[Batch ${batchNum}/${totalBatches}] ` +
            `Querying ${processedIsbns} / ${totalIsbns} ISBNs (${percentDone}%)`,
            'color: #6f42c1; font-weight: bold;'
        );

        const q = `isbn:(${chunk.join(' OR ')})`;
        const params = new URLSearchParams({
            q,
            fields: 'key,isbn,title,cover_i,editions,editions.key',
            limit: chunk.length
        });

        const searchUrl = `https://openlibrary.org/search.json?${params.toString()}`;

        try {
            const res = await fetch(searchUrl);
            if (!res.ok) throw new Error(`Status ${res.status}`);
            const data = await res.json();

            let editionsFoundThisBatch = 0;

            data.docs.forEach(doc => {
                const editionDocs = doc.editions?.docs;
                if (!Array.isArray(editionDocs) || editionDocs.length === 0) return;

                editionDocs.forEach(ed => {
                    if (!ed.key) return;

                    const matchedIsbns = (doc.isbn || []).filter(isbn => chunkSet.has(isbn));

                    editions.push({
                        workKey: doc.key,
                        editionKey: ed.key,
                        title: doc.title,
                        coverId: doc.cover_i || null,
                        matchedIsbn: matchedIsbns[0] || 'N/A'
                    });

                    editionsFoundThisBatch++;
                });
            });

            console.log(
                `%c→ Batch ${batchNum} returned ${data.docs.length} works, ` +
                `${editionsFoundThisBatch} editions`,
                'color: #198754;'
            );

        } catch (e) {
            console.error(
                `%c✖ Batch ${batchNum} failed: ${e.message}`,
                'color: red; font-weight: bold;'
            );
        }
    }

    console.table(
        editions.map(e => ({
            Title: e.title,
            ISBN: e.matchedIsbn,
            Edition: e.editionKey
        }))
    );

    console.log(
        `%cDone. Found ${editions.length} editions.`,
        'font-weight: bold; color: green;'
    );

    return editions;
}

function isValidIsbn(isbn) {
    if (isbn.length === 10) {
        if (!/^\d{9}[\dX]$/.test(isbn)) return false;
        let sum = 0;
        for (let i = 0; i < 9; i++) {
            sum += parseInt(isbn[i], 10) * (10 - i);
        }
        const last = isbn[9] === 'X' ? 10 : parseInt(isbn[9], 10);
        return (sum + last) % 11 === 0;
    }

    if (isbn.length === 13) {
        if (!/^\d{13}$/.test(isbn)) return false;
        let sum = 0;
        for (let i = 0; i < 12; i++) {
            sum += parseInt(isbn[i], 10) * (i % 2 === 0 ? 1 : 3);
        }
        return ((10 - (sum % 10)) % 10) === parseInt(isbn[12], 10);
    }

    return false;
}


/**
 * Get the username of the currently logged-in patron.
 * Tries multiple methods: URL redirect, page body parsing.
 * @returns {Promise<string|null>} Username or null if not logged in
 */
async function getLoggedInUsername() {
    const res = await fetch('/account', {
        credentials: 'same-origin',
        redirect: 'follow',
    });


    const url = new URL(res.url);

    // Method 1: Check if redirected to /people/{username}
    const match = url.pathname.match(/^\/people\/([^/]+)/);
    if (match) {
        return match[1];
    }

    // Method 2: Parse the page body for username (fallback)
    const html = await res.text();

    // Look for logged-in user link in the page
    const userLinkMatch = html.match(/href="\/people\/([^"]+)"/);
    if (userLinkMatch) {
        return userLinkMatch[1];
    }

    // Method 3: Check for "my-books" or account links
    const myBooksMatch = html.match(/\/people\/([^/"]+)\/books/);
    if (myBooksMatch) {
        return myBooksMatch[1];
    }

    return null;
}

/**
 * Fetch all lists for a user.
 * @param {string} username
 * @returns {Promise<Object>} Lists data
 */
async function fetchUserLists(username) {
    const res = await fetch(`/people/${username}/lists.json`, {
        credentials: 'same-origin',
    });

    if (!res.ok) {
        throw new Error(`Failed to fetch lists: ${res.status}`);
    }

    return await res.json();
}

/**
 * Create a new list for the user.
 * @param {string} username
 * @param {string} name - List name
 * @param {string} description - List description
 * @returns {Promise<Object>} Created list object
 */
async function createList(username, name, description = '') {
    const res = await fetch(`/people/${username}/lists`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ name, description }),
    });

    if (!res.ok) {
        throw new Error(`List creation failed: ${res.status}`);
    }

    const text = await res.text();
    try {
        return JSON.parse(text);
    } catch {
        throw new Error('Non-JSON response from list creation');
    }
}

/**
 * Add editions to a list.
 * @param {string} listKey - e.g. '/people/username/lists/OL123L'
 * @param {Array} editions - Array of edition objects with editionKey property
 * @returns {Promise<Object>} Response data
 */
async function addEditionsToList(listKey, editions) {
    const seeds = editions.map(e => ({ key: e.editionKey }));

    const res = await fetch(`${listKey}/seeds.json`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ add: seeds }),
    });

    if (!res.ok) {
        throw new Error(`Failed to add editions: ${res.status}`);
    }

    return await res.json();
}

/**
 * Main orchestration: Import books from URL and add to a new list.
 * @param {string} url - URL to extract ISBNs from
 * @param {string} listName - Name for the new list
 * @returns {Promise<Object>} Result with list and editions
 */
async function importAndAddToList(url, listName = 'Imported Books') {
    // 1. Get logged-in username
    console.log('%c[1/4] Checking login status...', 'color: #6f42c1; font-weight: bold;');
    const username = await getLoggedInUsername();
    if (!username) {
        throw new Error('Not logged in. Please log in to Open Library first.');
    }
    console.log(`%c✓ Logged in as: ${username}`, 'color: #198754;');

    // 2. Import editions from URL
    console.log('%c[2/4] Importing books from URL...', 'color: #6f42c1; font-weight: bold;');
    const editions = await importBooksFromUrl(url);
    if (!editions || editions.length === 0) {
        throw new Error('No editions found from the URL.');
    }

    // 3. Create new list
    console.log('%c[3/4] Creating list...', 'color: #6f42c1; font-weight: bold;');
    const list = await createList(username, listName, `Imported from ${url}`);
    const listKey = list.key || list.url;
    console.log(`%c✓ Created list: ${listKey}`, 'color: #198754;');

    // 4. Add editions to list
    console.log('%c[4/4] Adding editions to list...', 'color: #6f42c1; font-weight: bold;');
    await addEditionsToList(listKey, editions);
    console.log(
        `%c✓ Successfully added ${editions.length} editions to "${listName}"`,
        'color: #198754; font-weight: bold;'
    );

    console.log(`%c🎉 Done! View your list at: ${listKey}`, 'color: #0d6efd; font-weight: bold;');

    return { list, editions };
}

/**
 * Import books from URL and add to an existing list.
 * @param {string} url - URL to extract ISBNs from
 * @param {string} listKey - Existing list key (e.g. '/people/username/lists/OL123L')
 * @returns {Promise<Object>} Result with editions added
 */
async function importAndAddToExistingList(url, listKey) {
    // 1. Get logged-in username
    console.log('%c[1/3] Checking login status...', 'color: #6f42c1; font-weight: bold;');
    const username = await getLoggedInUsername();
    if (!username) {
        throw new Error('Not logged in. Please log in to Open Library first.');
    }
    console.log(`%c✓ Logged in as: ${username}`, 'color: #198754;');

    // 2. Import editions from URL
    console.log('%c[2/3] Importing books from URL...', 'color: #6f42c1; font-weight: bold;');
    const editions = await importBooksFromUrl(url);
    if (!editions || editions.length === 0) {
        throw new Error('No editions found from the URL.');
    }

    // 3. Add editions to existing list
    console.log('%c[3/3] Adding editions to list...', 'color: #6f42c1; font-weight: bold;');
    await addEditionsToList(listKey, editions);
    console.log(
        `%c✓ Successfully added ${editions.length} editions to list`,
        'color: #198754; font-weight: bold;'
    );

    console.log(`%c🎉 Done! View your list at: ${listKey}`, 'color: #0d6efd; font-weight: bold;');

    return { listKey, editions };
}

/**
 * Show all lists for the logged-in user.
 * Helper function to find existing list keys.
 */
async function showMyLists() {
    const username = await getLoggedInUsername();
    if (!username) {
        console.error('Not logged in.');
        return;
    }

    const data = await fetchUserLists(username);
    console.log(`%cLists for ${username}:`, 'font-weight: bold;');
    console.table(
        data.entries.map(list => ({
            Name: list.name,
            Key: list.url || list.full_url,
            Count: list.seed_count || 0
        }))
    );

    return data.entries;
}

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
    container.appendChild(table);

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
        previewContainer.innerHTML = '<p>Loading...</p>';
        listSelectorContainer.innerHTML = '';

        try {
            const editions = await processInput(value);
            renderPreviewTable(editions, previewContainer);

            const selectorWrapper = await renderListSelector(listSelectorContainer, username);

            // Wire up the add button
            const addBtn = selectorWrapper.querySelector('#addToListBtn');
            addBtn.addEventListener('click', () => {
                handleAddToList(previewContainer, selectorWrapper, username);
            });

        } catch (e) {
            previewContainer.innerHTML = `<p style="color:red;">Error: ${e.message}</p>`;
        } finally {
            processBtn.disabled = false;
            processBtn.textContent = '🔍 Process Input';
        }
    });

    console.log('%c✓ Bulk Import UI initialized', 'color: green; font-weight: bold;');
}
