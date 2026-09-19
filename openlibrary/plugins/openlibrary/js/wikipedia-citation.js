export function initWikipediaCitation() {
    const popover = document.querySelector('.wikipedia-citation-popover');

    if (!popover) return;

    document.addEventListener(
        'click',
        async(event) => {
            const path = event.composedPath();

            const copyButton = path.find(
                element =>
                    element instanceof HTMLElement
                    && element.matches('[data-wikipedia-citation-copy]')
            );

            if (!copyButton || !path.includes(popover)) return;

            const citation = copyButton.querySelector('code')?.textContent?.trim();
            if (!citation) return;

            try {
                await navigator.clipboard.writeText(citation);
            } catch (error) {
                return;
            }

            copyButton.classList.add('is-copied');
            setTimeout(() => copyButton.classList.remove('is-copied'), 1200);
        },
        true
    );
}
