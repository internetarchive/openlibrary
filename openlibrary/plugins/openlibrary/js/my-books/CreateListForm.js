/**
 * Defines functionality related to the My Books dropper's list
 * creation form.
 * @module my-books/CreateListForm.js
 */
import myBooksStore from './store'
import { websafe } from '../jsdef'
import { createList } from '../lists/ListService'

/**
 * Represents the list creation form displayed when a patron
 * clicks the "Create new list" button, found in the My Book's
 * dropper.
 *
 * The form is designed such that there is only one rendered per
 * page.
 *
 * @class
 */
export class CreateListForm {

    /**
     * Creates a new `CreateListForm` object.
     *
     * Sets references to form inputs and "Create List" button.
     *
     * @param {HTMLElement} form
     */
    constructor(form) {
        /**
         * References this form's "Create List" button.
         *
         * @member {HTMLElement}
         */
        this.createListButton = form.querySelector('#create-list-button')

        /**
         * References the form's list title input field.
         *
         * @member {HTMLElement}
         */
        this.listTitleInput = form.querySelector('#list_label')

        /**
         * References the form's list description input field.
         *
         * @member {HTMLElement}
         */
        this.listDescriptionInput = form.querySelector('#list_desc')
    }

    /**
     * Attaches click listener to the "Create List" button.
     */
    initialize() {
        this.createListButton.addEventListener('click', (event) =>{
            event.preventDefault()
            this.createNewList()
        })
    }

    /**
     * Creates a new patron list.
     *
     * When a new list is created, the list's title and description
     * are pulled from the form. The patron's user key and the seed
     * identifier of the first list item are provided by the open dropper
     * referenced in the shared My Books store.
     *
     * On success, updates all My Books droppers on the page,
     * resets the list creation form fields, and closes the
     * modal containing the form.
     *
     * @async
     */
    async createNewList() {
        // Construct seed object for first list item:
        const listTitle = websafe(this.listTitleInput.value)
        const listDescription = websafe(this.listDescriptionInput.value)

        const openDropper = myBooksStore.get('OPEN_DROPPER')
        const seed = openDropper.readingLists.getSeed()

        const data = {
            name: listTitle,
            description: listDescription,
            seeds: [seed]
        }

        // Call list creation service with seed object:
        await createList(myBooksStore.get('USER_KEY'), data)
            .then(response => response.json())
            .then((data) => {
                // Update all droppers with new list data
                this.updateDroppersOnListCreation(data['key'], listTitle)
                // Clear list creation form fields, nullify seed
                this.resetForm()
            })
            .finally(() => {
                // Close the modal
                $.colorbox.close()
            })
    }

    /**
     * Updates lists section of each dropper with a new list.
     *
     * @param {string} listKey Key of the newly created list
     * @param {string} listTitle Title of the new list
     */
    updateDroppersOnListCreation(listKey, listTitle) {
        const droppers = myBooksStore.get('DROPPERS')
        const openDropper = myBooksStore.get('OPEN_DROPPER')

        for (const dropper of droppers) {
            const isActive = dropper === openDropper
            dropper.readingLists.onListCreationSuccess(listKey, listTitle, isActive)
        }
    }

    /**
     * Clears the list title and desciption fields in the form.
     */
    resetForm() {
        this.listTitleInput.value = ''
        this.listDescriptionInput.value = ''
    }
}
