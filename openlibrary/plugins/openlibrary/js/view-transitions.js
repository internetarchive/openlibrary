/**
 * Cross-document view transitions: morph book covers between listing and detail pages.
 * Requires Chrome 126+. https://developer.chrome.com/docs/web-platform/view-transitions/cross-document
 */
(function () {
    'use strict';

    if (
        !window.CSS?.supports?.('view-transition-name', 'none') ||
    !document.startViewTransition ||
    !window.navigation?.activation
    ) {
        return;
    }

    const nav = window.navigation;
    const IMAGE_LOAD_TIMEOUT = 8000;

    const BOOK_RE    = /^\/(works|books)\/[^/]+(\/.*)?$/;
    const SUBJ_RE    = /^\/subjects\/[^/]+(\/.*)?$/;
    const BOOK_ID_RE = /\/(works|books)\/([^/]+)/;

    const isBook    = p => BOOK_RE.test(p);
    const isHome    = p => p === '/' || p === '';
    const isListing = p => isHome(p) || SUBJ_RE.test(p);

    function toPathname(url) {
        try { return new URL(url, location.origin).pathname; } catch { return url; }
    }

    function extractBookId(path) {
        const m = path.match(BOOK_ID_RE);
        return m ? m[2] : null;
    }

    function coverLinkSelector(id) {
        return `a.book-cover-link[href^="/works/${id}"], a.book-cover-link[href^="/books/${id}"], a[href^="/works/${id}"], a[href^="/books/${id}"]`;
    }

    function findCoverImg(link) {
        return link?.querySelector('img.bookcover') ?? link?.querySelector('img') ?? null;
    }

    function detailCoverImg() {
        return (
            document.querySelector('#book-cover-detail .bookCover img') ??
      document.querySelector('.work-cover img')
        );
    }

    // Assign view-transition-name for the duration of a transition, then clear it.
    function nameForTransition(el, name, settled) {
        if (!el) return;
        el.style.viewTransitionName = name;
        settled.then(() => { el.style.viewTransitionName = ''; });
    }

    // Same as nameForTransition but waits for the image to load first.
    // Only safe to use on the outgoing page — pagereveal must be synchronous.
    function nameWhenReady(img, name, settled) {
        if (!img) return;

        let done = false;
        const apply = () => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            nameForTransition(img, name, settled);
        };

        if (img.complete && img.naturalHeight !== 0) { apply(); return; }

        img.addEventListener('load',  apply, { once: true });
        img.addEventListener('error', apply, { once: true });
        const timer = setTimeout(apply, IMAGE_LOAD_TIMEOUT);
    }

    // pageswap doesn't expose which link was clicked, so we track it ourselves.
    let lastClickedLink = null;

    document.addEventListener('click', e => {
        const link = e.target.closest('a.book-cover-link');
        if (!link) return;
        lastClickedLink = link;
        setTimeout(() => { if (lastClickedLink === link) lastClickedLink = null; }, 1000);
    }, { capture: true });

    function clickedLinkForBook(bookId) {
        if (!lastClickedLink || !bookId) return null;
        const id = extractBookId(lastClickedLink.getAttribute('href') ?? '');
        return id === bookId ? lastClickedLink : null;
    }

    window.addEventListener('pageswap', e => {
        if (!e.viewTransition || !e.activation) return;

        const from = toPathname(document.location.href);
        const to   = toPathname(e.activation.entry.url);

        if (isBook(to) && isListing(from)) {
            const bookId = extractBookId(to);
            const link   = clickedLinkForBook(bookId) ?? (bookId ? document.querySelector(coverLinkSelector(bookId)) : null);
            nameWhenReady(findCoverImg(link), 'book-cover', e.viewTransition.finished);
            return;
        }

        if (isListing(to) && isBook(from)) {
            nameForTransition(detailCoverImg(), 'book-cover', e.viewTransition.finished);
        }
    });

    window.addEventListener('pagereveal', e => {
    // Must be synchronous — browser captures the new state immediately on this event.
        if (!e.viewTransition || !nav.activation?.from) return;

        const to   = toPathname(nav.activation.entry.url);
        const from = toPathname(nav.activation.from.url);

        if (isBook(to) && isListing(from)) {
            nameForTransition(detailCoverImg(), 'book-cover', e.viewTransition.finished);
            return;
        }

        if (isListing(to) && isBook(from)) {
            const link = extractBookId(from) ? document.querySelector(coverLinkSelector(extractBookId(from))) : null;
            nameForTransition(findCoverImg(link), 'book-cover', e.viewTransition.finished);
        }
    });

    // Prefetch the large cover on hover so the detail page renders sharp.
    const prefetched = new Set();

    document.addEventListener('mouseenter', e => {
        const link = e.target.closest('a.book-cover-link');
        const img  = link?.querySelector('img');
        if (!img?.src) return;

        const large = largeCoverUrl(img.src);
        if (!large || prefetched.has(large)) return;

        prefetched.add(large);
        Object.assign(document.head.appendChild(document.createElement('link')), {
            rel: 'prefetch', as: 'image', href: large,
        });
    }, { capture: true, passive: true });

    function largeCoverUrl(src) {
    // archive.org download URL → OL cover CDN
        const m = src.match(/\/download\/([^/]+)\//);
        if (m) return `https://covers.openlibrary.org/b/ia/${m[1]}-L.jpg`;

        // Standard OL thumbnail: .../ID-{S,M}.jpg → .../ID-L.jpg
        const large = src.replace(/-[SM]\.jpg(\?.*)?$/i, '-L.jpg$1');
        return large !== src ? large : null;
    }
}());
