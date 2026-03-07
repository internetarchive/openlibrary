/* global importBooksFromUrl */
/* eslint-disable no-console, no-unused-vars */
/**
 * List API for Bulk Import
 * Functions for managing Open Library lists
 */

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
