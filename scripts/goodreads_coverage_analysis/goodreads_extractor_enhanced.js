// Extract book data from Goodreads popular books page
// Outputs TSV format for Open Library bulk search

function extractBookData(bookElement) {
    if (!bookElement || bookElement.tagName.toLowerCase() !== 'article') {
        return null;
    }

    const bookData = {
        rank: null,
        title: null,
        url: null,
        authors: [],
        averageRating: null,
        ratingsCount: null,
        shelvingsCount: null,
        coverUrl: null
    };

    const rankEl = bookElement.querySelector('.BookListItemRank h2');
    if (rankEl) {
        bookData.rank = rankEl.textContent.trim().replace('#', '');
    }

    const titleLink = bookElement.querySelector('a[data-testid="bookTitle"]');
    if (!titleLink) {
        return null;
    }
    bookData.title = titleLink.textContent.trim();
    bookData.url = titleLink.href;

    const authorEls = bookElement.querySelectorAll('.ContributorLink__name');
    authorEls.forEach(el => {
        bookData.authors.push(el.textContent.trim());
    });

    const ratingEl = bookElement.querySelector('[data-testid="ratingValue"] .Text__semibold');
    if (ratingEl) {
        bookData.averageRating = parseFloat(ratingEl.textContent.trim());
    }

    const ratingsCountEl = bookElement.querySelector('[data-testid="ratingsCount"] .Text__subdued');
    if (ratingsCountEl) {
        bookData.ratingsCount = ratingsCountEl.textContent.trim().replace(' ratings', '');
    }

    const ratingContainer = bookElement.querySelector('.BookListItemRating');
    if (ratingContainer) {
        const match = ratingContainer.textContent.match(/([\d\.]+k|[\d\.]+m)\s*shelvings/i);
        if (match) {
            bookData.shelvingsCount = match[1].trim();
        }
    }

    const coverImg = bookElement.querySelector('.BookCover__image img.ResponsiveImage');
    if (coverImg) {
        const srcset = coverImg.getAttribute('srcset');
        if (srcset) {
            bookData.coverUrl = srcset.split(',')[0].split(' ')[0];
        } else {
            bookData.coverUrl = coverImg.src;
        }
    }

    return bookData;
}

function extractAllBookData() {
    const books = document.querySelectorAll('article.BookListItem');
    const results = [];

    books.forEach(book => {
        const data = extractBookData(book);
        if (data) {
            results.push(data);
        }
    });

    return results;
}

function tsvEscape(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/\t/g, ' ').replace(/\r?\n/g, ' ');
}

function convertToTsv(books) {
    const headers = ['rank', 'title', 'url', 'author', 'averageRating', 'ratingsCount', 'shelvingsCount', 'coverUrl'];
    const rows = books.map(book => [
        tsvEscape(book.rank),
        tsvEscape(book.title),
        tsvEscape(book.url),
        tsvEscape(book.authors.join('; ')),
        tsvEscape(book.averageRating),
        tsvEscape(book.ratingsCount),
        tsvEscape(book.shelvingsCount),
        tsvEscape(book.coverUrl)
    ].join('\t'));

    return [headers.join('\t'), ...rows].join('\n');
}

function downloadTsv(filename) {
    const books = extractAllBookData();

    if (books.length === 0) {
        console.warn('No books found');
        return;
    }

    const tsv = convertToTsv(books);
    const blob = new Blob([tsv], { type: 'text/tab-separated-values;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = filename || 'goodreads_data.tsv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    console.log('Downloaded', books.length, 'books');
}

downloadTsv();

