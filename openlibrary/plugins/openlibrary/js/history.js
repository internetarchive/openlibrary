/**
 * Handles arbitrary A/B comparison on the history page.
 * When both an A and B radio are selected, injects a comparison link
 * into the Pick cell of the lower-numbered revision's row.
 * @param {HTMLElement} pageHistoryElement
 */
export function initHistory(pageHistoryElement){
    const radios = pageHistoryElement.querySelectorAll('input[name="a"], input[name="b"]');
    const i18nStrings = JSON.parse(pageHistoryElement.dataset.i18n);

    function updateCompareButton() {
        const checkedRadioA = pageHistoryElement.querySelector('input[name="a"]:checked');
        const checkedRadioB = pageHistoryElement.querySelector('input[name="b"]:checked');

        const compareBtns = pageHistoryElement.querySelectorAll('.compare-arbitrary-btn');
        compareBtns.forEach(btn => btn.remove());

        // Clear any previous A/B row highlights before re-applying.
        pageHistoryElement.querySelectorAll('tr.pick-ab-selected')
            .forEach(row => row.classList.remove('pick-ab-selected'));

        if (checkedRadioA && checkedRadioB){
            const valA = parseInt(checkedRadioA.value, 10);
            const valB = parseInt(checkedRadioB.value, 10);

            const higherRev = Math.max(valA, valB);
            const lowerRev = Math.min(valA, valB);

            // Highlight the rows currently chosen as A and B.
            checkedRadioA.closest('tr').classList.add('pick-ab-selected');
            checkedRadioB.closest('tr').classList.add('pick-ab-selected');

            const href = `?m=diff&a=${lowerRev}&b=${higherRev}`;

            const link = document.createElement('a');
            link.href = href;
            link.textContent = i18nStrings.compare_label
                .replace('%(a)s', lowerRev)
                .replace('%(b)s', higherRev);
            link.className = 'compare-arbitrary-btn';

            const lowerRadio = pageHistoryElement.querySelector(`input[name="a"][value="${lowerRev}"]`);
            const pickCell = lowerRadio.closest('tr').querySelector('.pick-ab');
            pickCell.appendChild(link);
        }
    }

    radios.forEach(radio => radio.addEventListener('change', updateCompareButton));
    updateCompareButton();
}
