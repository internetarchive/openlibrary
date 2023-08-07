/**
 * Defines functionality related to Open Library's My Books dropper components.
 * @module my-books/MyBooksDropper
 */
import myBooksStore from './store'
import { ReadDateComponents } from './MyBooksDropper/ReadDateComponents'
import { ReadingLists } from './MyBooksDropper/ReadingLists'
import { ReadingLogForms } from './MyBooksDropper/ReadingLogForms'
import { Dropper } from '../dropper/Dropper'

/**
 * Represents a single My Books Dropper.
 *
 * The My Books Dropper component provides the patron with a number of actions
 * that they can perform on a single book or author.
 *
 * At the very least, My Books droppers will contain affordances for managing one's
 * lists. If the dropper is linked to a book, and the book has a work key, the dropper
 * will contain affordances for reading log shelf and last read date management.
 *
 * @see `/openlibrary/templates/my_books/dropper.html` for base template of this component.
 * @class
 * @augments Dropper
 */
export class MyBooksDropper extends Dropper {
    /**
     * Creates references to the given dropper's reading log forms, read date affordances, and
     * list affordances.
     *
     * @param {HTMLElement} dropper
     */
    constructor(dropper) {
        super(dropper)

        const dropperActionCallbacks = {
            closeDropper: this.closeDropper.bind(this),
            toggleDropper: this.toggleDropper.bind(this)
        }

        /**
         * Reference to this dropper's list content.
         * @member {ReadingLists}
         */
        this.readingLists = new ReadingLists(dropper, dropperActionCallbacks)

        /**
         * Reference to the dropper's list loading indicator.
         *
         * This is only rendered when the patron is logged in.
         * @member {HTMLElement|null}
         */
        this.loadingIndicator = dropper.querySelector('.list-loading-indicator')

        /**
         * Reference to the interval ID of the animation `setInterval` call.
         * @member {NodeJS.Timer|undefined}
         */
        this.loadingAnimationId

        /**
         * References this dropper's reading log buttons.
         * @member {ReadingLogForms}
         */
        this.readingLogForms = new ReadingLogForms(dropper, this.readDateComponents, dropperActionCallbacks)

        /**
         * References this dropper's read date prompt and display.
         * @member {ReadDateComponents}
         */
        this.readDateComponents = new ReadDateComponents(dropper)
    }

    /**
     * Hydrates dropper contents and loads patron's lists.
     */
    initialize() {
        super.initialize()

        this.readingLogForms.initialize()
        this.readingLists.initialize()

        this.loadingAnimationId = this.initLoadingAnimation(this.dropper.querySelector('.loading-ellipsis'))
    }

    /**
     * Creates loading animation for list loading indicator.
     *
     * @param {HTMLElement} loadingIndicator
     * @returns {NodeJS.Timer}
     */
    initLoadingAnimation(loadingIndicator) {
        let count = 0
        const intervalId = setInterval(function() {
            let ellipsis = ''
            for (let i = 0; i < count % 4; ++i) {
                ellipsis += '.'
            }
            loadingIndicator.innerText = ellipsis
            ++count
        }, 1500)

        return intervalId
    }

    // XXX : jsdoc
    updateReadingLists(partialHtml) {
        clearInterval(this.loadingAnimationId)
        this.replaceLoadingIndicators(this.loadingIndicator, partialHtml)
    }

    /**
     * Object returned by the list partials endpoint.
     *
     * @typedef {Object} ListPartials
     * @property {string} dropper HTML string for dropdown list content
     * @property {string} active HTML string for patron's active lists
     */
    /**
     * Replaces list loading indicators with the given partially rendered HTML.
     *
     * @param {HTMLElement} dropperListsPlaceholder Loading indicator found inside of the dropdown content
     * @param {ListPartials} partials
     */
    replaceLoadingIndicators(dropperListsPlaceholder, partialHTML) {
        const dropperParent = dropperListsPlaceholder ? dropperListsPlaceholder.parentElement : null

        if (dropperParent) {
            this.removeChildren(dropperParent)
            dropperParent.insertAdjacentHTML('afterbegin', partialHTML)

            const anchors = this.dropper.querySelectorAll('.modify-list')
            this.readingLists.initModifyListAffordances(anchors)
        }
    }

    /**
     * Removes children of each given element.
     *
     * @param  {Array<HTMLElement>} elements
     */
    removeChildren(...elements) {
        for (const elem of elements) {
            if (elem) {
                while (elem.firstChild) {
                    elem.removeChild(elem.firstChild)
                }
            }
        }
    }

    /**
     * Closes dropper if opened; opens dropper if closed.
     *
     * If the dropper is open, the store is updated with
     * a reference to the dropper and the seed identifier
     * @override
     */
    toggleDropper() {
        super.toggleDropper()

        if (!this.isDropperDisabled && this.isDropperOpen) {
            myBooksStore.set('OPEN_DROPPER', this)
            myBooksStore.set('LIST_SEED', this.readingLists.getSeed())
        }
    }
}
