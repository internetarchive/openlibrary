/**
 * Browser-mode tests for Library Explorer's Vue components.
 *
 * The components directory has 54 .vue files and this is their first test
 * coverage. The rules are the same as the Lit suites next door: real layout,
 * real observers, trusted input, nothing stubbed except the network.
 *
 * <ol-carousel> is the Vue sibling of the Lit carousel tested in
 * OlCarousel.browser.test.js — note the case, don't rename either file.
 * Its whole reason to exist is that it must not fetch until a real scroll
 * brings it into view, which only a real IntersectionObserver can prove.
 */
import { expect, test } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-vue';
import { reactive } from 'vue';
import OLCarousel from '../../openlibrary/components/LibraryExplorer/components/OLCarousel.vue';
import ClassSlider from '../../openlibrary/components/LibraryExplorer/components/ClassSlider.vue';

const NUM_FOUND = 45;

/** Solr-shaped docs. No cover id, so FlatBookCover draws a title card. */
function docs(start, count) {
    return Array.from({ length: count }, (_, i) => ({
        key: `/works/OL${start + i + 1}W`,
        title: `Book ${start + i + 1}`,
        author_name: ['An Author'],
    }));
}

/** Answer Solr pagination from a fixture, recording every request URL. */
function stubSearchApi(pages) {
    const calls = [];
    window.fetch = async(url) => {
        const request = new URL(url, location.href);
        calls.push(request);
        const offset = Number(request.searchParams.get('offset')) || 0;
        return {
            ok: true,
            json: async() => ({ numFound: NUM_FOUND, docs: pages[offset] ?? [] }),
        };
    };
    return calls;
}

/**
 * The carousel records its offset on `node.requests[query].offset`, and Vue
 * props are only shallowly reactive — a plain object prop would swallow the
 * write. Production passes a node out of Shelf's reactive `data()` tree, so
 * mirror that here.
 */
function renderCarousel(props) {
    return render(OLCarousel, { props: { node: reactive({ requests: {} }), ...props } });
}

test('a carousel below the fold fetches nothing until a real scroll brings it into view', async() => {
    const calls = stubSearchApi({ 0: docs(0, 20) });

    await renderCarousel({ query: 'crime', limit: 20 });

    // Park it a viewport and a half down the page.
    const root = document.querySelector('.ol-carousel');
    root.style.marginTop = '1200px';

    // Long enough for a wrongly-eager IntersectionObserver to have fired.
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(calls).toHaveLength(0);

    // The scroll is what unlocks it.
    root.scrollIntoView();
    await expect.element(page.getByText('Book 1')).toBeInTheDocument();
    expect(calls).toHaveLength(1);
});

test('Load next pages forward through the results, updating the readout and controls', async() => {
    const calls = stubSearchApi({ 0: docs(0, 20), 20: docs(20, 25) });

    await renderCarousel({ query: 'crime', limit: 20 });

    // Starts in view, so it loads straight away.
    await expect.element(page.getByText('Book 1')).toBeInTheDocument();
    await expect.element(page.getByText('0-20 of 45')).toBeInTheDocument();
    await expect.element(page.getByRole('button', { name: 'Load previous' })).not.toBeInTheDocument();

    await page.getByRole('button', { name: 'Load next' }).click();

    // Both book-ends now carry the readout; the first is the "previous" one.
    await expect.element(page.getByText('20-45 of 45').first()).toBeInTheDocument();
    await expect.element(page.getByRole('button', { name: 'Load previous' })).toBeInTheDocument();
    await expect.element(page.getByRole('button', { name: 'Load next' })).toBeDisabled();

    // One request per page, at the right offsets.
    expect(calls.map((request) => request.searchParams.get('offset'))).toEqual(['0', '20']);
});

test('the class slider walks the classification tree and stops at the last shelf', async() => {
    await render(ClassSlider, {
        props: {
            node: {
                position: 'root',
                short: 'ALL',
                name: 'All subjects',
                children: [
                    { short: '000', name: 'Computer science' },
                    { short: '100', name: 'Philosophy' },
                ],
            },
        },
    });

    // The root is not a shelf, so there is nothing to go back to — the only
    // arrow is next, named by the shelf it leads to.
    await expect.element(page.getByText('All subjects')).toBeInTheDocument();
    await expect.element(page.getByTitle('000')).toBeInTheDocument();
    expect(page.getByRole('button').elements()).toHaveLength(1);

    await page.getByTitle('000').click();
    await expect.element(page.getByText('Computer science')).toBeInTheDocument();

    await page.getByTitle('100').click();
    await expect.element(page.getByText('Philosophy')).toBeInTheDocument();

    // The last shelf offers no forward arrow, only the way back.
    expect(page.getByRole('button').elements()).toHaveLength(1);

    await page.getByRole('button').last().click();
    await expect.element(page.getByText('Computer science')).toBeInTheDocument();
});
