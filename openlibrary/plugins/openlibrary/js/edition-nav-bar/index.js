import { debounce } from '../nonjquery_utils'

export function initNavbar(navbarElem) {
    const listItems = navbarElem.querySelectorAll('li');
    const linkedSections = []
    let selectedSection

    // Add click listeners
    for (let i = 0; i < listItems.length; ++i) {
        const index = i;
        listItems[i].addEventListener('click', function() {
            debounce(selectElement(listItems[i], index), 300, false)
        })

        linkedSections.push(document.querySelector(listItems[i].children[0].hash))
        if (listItems[i].classList.contains('selected')) {
            selectedSection = linkedSections[linkedSections.length - 1]
        }
    }

    function selectElement(selectedElem, targetIndex) {
        for (const li of listItems) {
            li.classList.remove('selected')
        }
        selectedElem.classList.add('selected')
        selectedSection = linkedSections[targetIndex];
    }

    // Add scroll listener
    document.addEventListener('scroll', function() {
        const navbarBoundingRect = navbarElem.getBoundingClientRect()
        const selectedBoundingRect = selectedSection.getBoundingClientRect();

        // Check if navbar is not within selected element's bounds:
        if (selectedBoundingRect.bottom < navbarBoundingRect.top ||
            selectedBoundingRect.top > navbarBoundingRect.bottom) {
            for (let i = 0; i < linkedSections.length; ++i) {
                // Do not do bounds check on selected item:
                if (linkedSections[i].id !== selectedSection.id) {
                    const br = linkedSections[i].getBoundingClientRect()
                    if (br.top < navbarBoundingRect.bottom && br.bottom > navbarBoundingRect.bottom) {
                        selectElement(listItems[i], i)
                        break;
                    }
                }
            }
        }
    })
}


