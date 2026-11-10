/**
 * Book page subject rows: show a few lines of chips (`--subject-row-lines`), then a "+N" chip that reveals the rest.
 * @param {NodeListOf<HTMLElement>} lists - `.subject-row__chips` elements
 */
export async function initSubjectRows(lists) {
    // Chips change size when they upgrade, so measure after.
    await customElements.whenDefined('ol-chip');
    for (const list of lists) {
        const more = list.querySelector('.subject-row__more');
        const chips = [...list.children].filter(el => el !== more);
        const label = list.dataset.moreLabel;
        let lastWidth = 0;

        const fit = () => {
            chips.forEach(chip => (chip.hidden = false));
            more.hidden = true;
            const lines = parseInt(getComputedStyle(list).getPropertyValue('--subject-row-lines')) || 1;
            const tops = [...new Set(chips.map(chip => chip.offsetTop))];
            if (tops.length <= lines) return;
            const lastLine = tops[lines - 1];
            let shown = chips.findIndex(chip => chip.offsetTop > lastLine);

            // Hide chips from the end until the "+N" chip fits on the last line too.
            more.hidden = false;
            for (; shown > 0; shown--) {
                chips.forEach((chip, i) => (chip.hidden = i >= shown));
                more.textContent = `+${chips.length - shown}`;
                if (more.offsetTop <= lastLine) break;
            }
            more.accessibleLabel = label.replace('{count}', chips.length - shown);
        };

        const observer = new ResizeObserver(([entry]) => {
            const width = entry.contentRect.width;
            if (width === lastWidth) return;
            lastWidth = width;
            fit();
        });
        observer.observe(list);

        more.addEventListener('ol-chip-select', () => {
            observer.disconnect();
            const firstHidden = chips.find(chip => chip.hidden);
            chips.forEach(chip => (chip.hidden = false));
            more.remove();
            list.classList.add('subject-row__chips--expanded');
            firstHidden?.focus();
        });

        list.classList.add('subject-row__chips--fitted');
    }
}
