/**
 * Cross-document View Transition API: morph cover from home carousel to book page.
 * Requires Chrome 126+. See https://developer.chrome.com/docs/web-platform/view-transitions/cross-document
 */
(function () {
    if (!window.CSS?.supports?.('view-transition-name', 'none') || !document.startViewTransition) {
        return;
    }
    const NAV = window.navigation;
    if (!NAV || !NAV.activation) {
        return;
    }

    // 8 seconds chosen to balance user patience vs network variability
    const IMAGE_LOAD_TIMEOUT = 8000;

    function pathname(u) {
        try {
            return new URL(u, location.origin).pathname;
        } catch (e) {
            return u;
        }
    }

    function isBookPage(path) {
        // Match /works/ID or /works/ID/title or /books/ID or /books/ID/title
        return /^\/works\/[^/]+(\/.*)?$/.test(path) || /^\/books\/[^/]+(\/.*)?$/.test(path);
    }

    function isHome(path) {
        return path === '/' || path === '';
    }

    function getBookLinkSelector(id) {
        return `a.book-cover-link[href^="/works/${id}"], a.book-cover-link[href^="/books/${id}"], a[href^="/works/${id}"], a[href^="/books/${id}"]`;
    }

    function findCoverImage(link) {
        return link && (link.querySelector('img.bookcover') || link.querySelector('img'));
    }

    function extractBookId(path) {
        const match = path.match(/\/(works|books)\/([^/]+)/);
        return match ? match[2] : null;
    }

    function setTemporaryViewTransitionNames(entries, vtPromise) {
        entries.forEach(([el, name]) => {
            if (el) el.style.viewTransitionName = name;
        });
        vtPromise.then(() => {
            entries.forEach(([el]) => {
                if (el) el.style.viewTransitionName = '';
            });
        });
    }

    // Wait for image load before applying transition name (with timeout fallback)
    function waitForImageAndApply(img, name, vtPromise) {
        if (!img) return Promise.resolve();

        return new Promise(resolve => {
            let applied = false;
            let timeoutId;
            const apply = () => {
                if (applied) return;
                applied = true;
                if (timeoutId) clearTimeout(timeoutId);
                setTemporaryViewTransitionNames([[img, name]], vtPromise);
                resolve();
            };

            if (img.complete && img.naturalHeight !== 0) {
                apply();
            } else {
                img.addEventListener('load', apply, { once: true });
                img.addEventListener('error', apply, { once: true });
                timeoutId = setTimeout(apply, IMAGE_LOAD_TIMEOUT);
            }
        });
    }

    window.addEventListener('pageswap', (e) => {
        // Outgoing page - images are already loaded
        if (!e.viewTransition || !e.activation) {
            return;
        }

        const targetPath = pathname(e.activation.entry.url);

        if (isBookPage(targetPath)) {
            const bookId = extractBookId(targetPath);
            const link = bookId ? document.querySelector(getBookLinkSelector(bookId)) : null;
            const img = findCoverImage(link);
            if (img) {
                setTemporaryViewTransitionNames([[img, 'book-cover']], e.viewTransition.finished);
            }
        } else if (isHome(targetPath)) {
            const coverImg = document.querySelector('#book-cover-detail .bookCover img');
            if (coverImg) {
                setTemporaryViewTransitionNames(
                    [[coverImg, 'book-cover']],
                    e.viewTransition.finished
                );
            }
        }
    });

    window.addEventListener('pagereveal', (e) => {
        // Incoming page - need to wait for images to load first
        if (!e.viewTransition || !NAV.activation || !NAV.activation.from) return;
        const currentPath = pathname(NAV.activation.entry.url);
        const fromPath = pathname(NAV.activation.from.url);

        if (isBookPage(currentPath) && isHome(fromPath)) {
            const coverImg = document.querySelector('#book-cover-detail .bookCover img');
            waitForImageAndApply(coverImg, 'book-cover', e.viewTransition.ready);
        } else if (isHome(currentPath) && isBookPage(fromPath)) {
            const bookId = extractBookId(fromPath);
            const link = bookId ? document.querySelector(getBookLinkSelector(bookId)) : null;
            const img = findCoverImage(link);
            waitForImageAndApply(img, 'book-cover', e.viewTransition.ready);
        }
    });
})();
