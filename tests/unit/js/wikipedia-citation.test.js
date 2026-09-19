import { initWikipediaCitation } from '../../../openlibrary/plugins/openlibrary/js/wikipedia-citation.js';

describe('Wikipedia citation copy', () => {
    beforeEach(() => {
        document.body.innerHTML = `
    <ol-popover class="wikipedia-citation-popover">
        <a id="wikilink" href="#">Wikipedia citation</a>
        <button type="button" data-wikipedia-citation-copy>
            <code>{{cite book|title=Test}}</code>
        </button>
    </ol-popover>
`;
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
                writeText: vi.fn().mockResolvedValue(undefined),
            },
        });
    });

    afterEach(() => {
        document.body.innerHTML = '';
        vi.restoreAllMocks();
    });

    it('copies the citation and shows copied feedback', async() => {
        initWikipediaCitation();

        const copyButton = document.querySelector('[data-wikipedia-citation-copy]');

        copyButton.click();
        await Promise.resolve();

        expect(navigator.clipboard.writeText).toHaveBeenCalledWith('{{cite book|title=Test}}');
        expect(copyButton.classList.contains('is-copied')).toBe(true);
    });
});
