/**
 * Handles arbitrary A/B comparison on the history page.
 * When both an A and B radio are selected, injects a comparison link
 * into the Pick cell of the lower-numbered revision's row.
 * @param {HTMLElement} pageHistoryElement
 */
export function initHistory(pageHistoryElement){
    console.log('initHistory called', pageHistoryElement);
    console.log('pre-checked a:', pageHistoryElement.querySelector('input[name="a"]:checked'));
    console.log('pre-checked b:', pageHistoryElement.querySelector('input[name="b"]:checked'));

    const radios = pageHistoryElement.querySelectorAll('input[name="a"], input[name="b"]');

    function updateCompareButton() {
        const checkedRadioA = pageHistoryElement.querySelector('input[name="a"]:checked');
        const checkedRadioB = pageHistoryElement.querySelector('input[name="b"]:checked');

        var compareBtns = pageHistoryElement.querySelectorAll('.compare-arbitrary-btn');
        compareBtns.forEach(btn => btn.remove());

        if (checkedRadioA && checkedRadioB){
            const valA = parseInt(checkedRadioA.value, 10);
            const valB = parseInt(checkedRadioB.value, 10);

            const higherRev = Math.max(valA, valB);
            const lowerRev = Math.min(valA, valB);

            const href = `?m=diff&a=${lowerRev}&b=${higherRev}`;

            const link = document.createElement('a');
            link.href = href;
            link.textContent = `Compare ${lowerRev} with ${higherRev}`;
            link.className = 'compare-arbitrary-btn';

            const lowerRadio = pageHistoryElement.querySelector(`input[name="a"][value="${lowerRev}"]`);
            const pickCell = lowerRadio.closest('tr').querySelector('.pick-ab');
            pickCell.appendChild(link);
        }
    }

    radios.forEach(radio => radio.addEventListener('change', updateCompareButton));
    updateCompareButton();
}
