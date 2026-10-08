import { initWikipediaCitation } from '../../../openlibrary/plugins/openlibrary/js/wikipedia-citation.js';

describe('Wikipedia citation copy', () => {
    let copyButton;

    beforeEach(() => {
        document.body.innerHTML = `
            <ol-popover class="wikipedia-citation-popover">
                <button slot="trigger" type="button">Wikipedia citation</button>
                <div class="wikipedia-citation-popover__well">
                    <code> {{cite book|title=Test}} </code>
                    <button type="button" data-wikipedia-citation-copy></button>
                </div>
            </ol-popover>
        `;
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText: vi.fn().mockResolvedValue(undefined) },
        });
        initWikipediaCitation();
        copyButton = document.querySelector('[data-wikipedia-citation-copy]');
    });

    afterEach(() => {
        document.body.innerHTML = '';
        vi.restoreAllMocks();
    });

    it('copies the trimmed citation and shows copied feedback', async() => {
        copyButton.click();

        await vi.waitFor(() => expect(copyButton.classList.contains('is-copied')).toBe(true));
        expect(navigator.clipboard.writeText).toHaveBeenCalledWith('{{cite book|title=Test}}');
    });

    it('leaves the button untouched when the clipboard write fails', async() => {
        navigator.clipboard.writeText.mockRejectedValue(new Error('denied'));

        copyButton.click();

        expect(navigator.clipboard.writeText).toHaveBeenCalled();
        await new Promise(resolve => setTimeout(resolve)); // let the rejection settle
        expect(copyButton.classList.contains('is-copied')).toBe(false);
    });
});
