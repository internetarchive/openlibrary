/* eslint-disable no-console, no-unused-vars */
/**
 * ISBN Utilities for Bulk Import
 * Core functions for fetching, extracting, and validating ISBNs
 */

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
