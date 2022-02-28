import { debounce } from '../nonjquery_utils'

let listItems;

export function initNavbar(navbarElem) {
    listItems = navbarElem.querySelectorAll('li');

    // Add click listeners
    for (const li of listItems) {
        li.addEventListener('click', function() {
            debounce(selectELement(li), 300, false)
        })
    }
}

function selectELement(targetElem) {
    for (const li of listItems) {
        li.classList.remove('selected')
    }
    targetElem.classList.add('selected')
}
