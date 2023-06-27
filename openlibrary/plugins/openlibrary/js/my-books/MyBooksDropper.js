import ReadDateComponents from './ReadDateComponents'
import ReadingLists from './ReadingLists'
import ReadingLogForms from './ReadingLogForms'
import { fetchPartials } from '../lists/ListService'

export default class MyBooksDropper {
    /**
     * Creates references to the given dropper's reading log forms, read date affordances, and
     * list affordances.
     *
     * @param {HTMLElement} dropper
     */
    constructor(dropper) {
        this.dropper = dropper

        /**
         * References this dropper's read date prompt and display.
         * @param {ReadDateComponents}
         */
        this.readDateComponents = new ReadDateComponents(dropper)

        /**
         * References this dropper's reading log buttons.
         * @param {ReadingLogForms}
         */
        this.readingLogForms = new ReadingLogForms(dropper, this.readDateComponents)

        this.readingLists = new ReadingLists(dropper)

        this.initialize()
    }

    initialize() {
        this.loadLists()
    }

    // XXX: Will not work on search results pages
    loadLists() {
        const dropperListPlaceholder = this.dropper.querySelector('.list-loading-indicator')

        // Already lists --- assuming one per page
        const listDisplayPlaceholder = document.querySelector('.list-overview-loading-indicator')

        const loadingIndicators = dropperListPlaceholder ? [dropperListPlaceholder.querySelector('.loading-ellipsis')] : []
        if (listDisplayPlaceholder) {
            loadingIndicators.push(listDisplayPlaceholder.querySelector('.loading-ellipsis'))
        }
        const intervalId = this.initLoadingAnimation(loadingIndicators)

        let key
        if (dropperListPlaceholder) {  // Not defined for logged-out patrons
            if (dropperListPlaceholder.dataset.editionKey) {
                key = dropperListPlaceholder.dataset.editionKey
            } else if (dropperListPlaceholder.dataset.workKey) {
                key = dropperListPlaceholder.dataset.workKey
            }
        }

        if (key) {
            fetchPartials(key, (data) => {
                clearInterval(intervalId)
                this.replaceLoadingIndicators(dropperListPlaceholder, listDisplayPlaceholder, JSON.parse(data))
            })
        } else {
            this.removeChildren(dropperListPlaceholder, listDisplayPlaceholder)
        }
    }

    initLoadingAnimation(loadingIndicators) {
        let count = 0
        const intervalId = setInterval(function() {
            let ellipsis = ''
            for (let i = 0; i < count % 4; ++i) {
                ellipsis += '.'
            }
            for (const elem of loadingIndicators) {
                elem.innerText = ellipsis
            }
            ++count
        }, 1500)

        return intervalId
    }

    replaceLoadingIndicators(dropperLists, activeLists, partials) {
        const dropperParent = dropperLists ? dropperLists.parentElement : null
        const activeListsParent = activeLists ? activeLists.parentElement : null

        if (dropperParent) {
            this.removeChildren(dropperParent)
            dropperParent.insertAdjacentHTML('afterbegin', partials['dropper'])

            const anchors = this.dropper.querySelectorAll('.add-to-list')
            this.readingLists.initAddToListAnchors(anchors)
        }

        if (activeListsParent) {
            this.removeChildren(activeListsParent)
            activeListsParent.insertAdjacentHTML('afterbegin', partials['active'])
            const actionableListItems = activeListsParent.querySelectorAll('.actionable-item')
            this.readingLists.registerListItems(actionableListItems)
        }
    }

    removeChildren(...elements) {
        for (const elem of elements) {
            if (elem) {
                while (elem.firstChild) {
                    elem.removeChild(elem.firstChild)
                }
            }
        }
    }
}