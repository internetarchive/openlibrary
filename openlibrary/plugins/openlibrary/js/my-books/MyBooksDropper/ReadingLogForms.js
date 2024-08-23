/**
 * Defines functionality related to the My Books dropper's reading log forms.
 * @module my-books/MyBooksDropper/ReadingLogForms
 */


/**
 * @typedef {string} ReadingLogShelf
 */
/**
 * Enum for reading log shelf values.
 * @readonly
 * @enum {ReadingLogShelf}
 */
export const ReadingLogShelves = {
    WANT_TO_READ: '1',
    CURRENTLY_READING: '2',
    ALREADY_READ: '3'
}

/**
 * Class representing a dropper's reading log forms.
 *
 * Each reading log button is nested within a reading log form.  Each form also
 * contains hidden fields that are used to determine whether a book is being added
 * or removed to/from a shelf, and which shelf.
 *
 * A dropper will have one primary reading log form, which contains the dropper's
 * primary button. The primary form's hidden fields change as books are added or
 * removed from shelves. If a book is on a shelf, the primary form has an "active"
 * status, and the primary button will have a checkmark.
 *
 * All other, non-primary, reading log forms can be found in the dropper's dropdown
 * content.  The hidden inputs of these forms do not change. However, the visibility
 * of these buttons changes depending on the primary form's hidden fields.
 *
 * @class
 */
export class ReadingLogForms {
    /**
     * Adds functionality to a single dropper's reading log forms.
     *
     * @param {HTMLElement} dropper
     * @param {import('./ReadDateComponents')} readDateComponents
     * @param {Record<string, CallableFunction>} dropperActionCallbacks
     */
    constructor(dropper, readDateComponents, dropperActionCallbacks) {
        /**
         * Contains references to the parent dropper's close and
         * toggle functions.  These functions are bound to the
         * parent dropper element.
         *
         * @member {Record<string, CallableFunction>}
         */
        this.dropperActions = dropperActionCallbacks

        /**
         * Reference to each reading log submit button.  This includes the
         * primary dropper button and the buttons in the dropdown.
         *
         * @member {NodeList<HTMLElement>}
         */
        this.submitButtons = dropper.querySelectorAll('.reading-log button')

        /**
         * Reference to this dropper's primary form.
         *
         * @member {HTMLFormElement}
         */
        this.primaryForm = null;

        /**
         * Reference to this dropper's primary button.
         *
         * @member {HTMLButtonElement}
         */
        this.primaryButton = null;

        /**
         * Reference to this dropper's "Remove from shelf" button.
         *
         * @member {HTMLButtonElement}
         */
        this.removeButton = null;

        for (const button of this.submitButtons) {
            if (button.classList.contains('primary-action')) {
                this.primaryButton = button
                this.primaryForm = button.closest('form')
            }
            else if (button.classList.contains('remove-from-list')) {  // XXX : Rename class `remove-from-shelf`?
                this.removeButton = button
            }
        }

        if (!this.primaryButton) {  // This dropper only contains list affordances
            this.primaryButton = dropper.querySelector('.primary-action')
        }

        /**
         * Reference to the dropper's read date prompt and display components.
         *
         * @member {import('./ReadDateComponents') | null}
         */
        this.readDateComponents = readDateComponents

        this.readingLogForms = dropper.querySelectorAll('form.reading-log')
        this.isDropperDisabled = dropper.classList.contains('generic-dropper--disabled')
    }

    /**
     * Adds click listeners to each of the form's submit buttons.
     *
     * If dropper is disabled, no event listeners will be added.
     */
    initialize() {
        if (!this.isDropperDisabled) {
            if (this.readingLogForms.length) {
                for (const form of this.readingLogForms) {
                    const submitButton = form.querySelector('button[type=submit]')
                    submitButton.addEventListener('click', (event) => {
                        event.preventDefault()
                        this.updateReadingLog(form)

                        // Close the dropper
                        this.dropperActions.closeDropper()
                    })
                }
            } else {
                // Toggle the dropper when there is no "Reading Log" primary action:
                this.primaryButton.addEventListener('click', () => {
                    this.dropperActions.toggleDropper()
                })
            }
        }
    }

    /**
     * POSTs the given form and updates the dropper accordingly.
     *
     * @param {HTMLFormElement} form
     */
    updateReadingLog(form) {
        let newPrimaryButtonText = this.primaryButton.querySelector('.btn-text').innerText
        // XXX: Use i18n strings
        this.updatePrimaryButtonText('saving...')

        const formData = new FormData(form)
        const url = form.getAttribute('action')

        const hasAddedBook = formData.get('action') === 'add'

        let canUpdateShelf = true

        if (!hasAddedBook && this.readDateComponents && this.readDateComponents.hasReadDate()) {
            // XXX: Use i18n strings
            canUpdateShelf = confirm('Removing this book from your shelves will delete your check-ins for this work.  Continue?')
        }

        if (canUpdateShelf) {
            fetch(url, {
                method: 'post',
                body: formData
            })
                .then(response => response.json())
                .then((data) => {
                    if (!('error' in data)) {  // XXX: Serve correct HTTP codes to avoid this
                        this.updateActivatedStatus(hasAddedBook)

                        if (hasAddedBook) {
                            const primaryButtonClicked = form.classList.contains('primary-action')
                            const newBookshelfId = form.querySelector('input[name=bookshelf_id]').value

                            if (!primaryButtonClicked) {
                                // A book has been added to a shelf chosen from the dropdown.
                                // The primary form and dropdown selections must now be updated.
                                const clickedButton = form.querySelector('button[type=submit]')
                                newPrimaryButtonText = clickedButton.innerText

                                this.updatePrimaryBookshelfId(newBookshelfId)

                                this.updateDropdownButtonVisibility(clickedButton)
                            }

                            // Update check-ins:
                            if (this.readDateComponents) {
                                if (!this.readDateComponents.hasReadDate() && newBookshelfId === ReadingLogShelves.ALREADY_READ) {
                                    this.readDateComponents.showDatePrompt()
                                } else {
                                    this.readDateComponents.hideDatePrompt()
                                }
                            }

                        } else if (this.readDateComponents) {
                            // Update check-ins:
                            this.readDateComponents.hideDatePrompt()
                            this.readDateComponents.hideReadDate()
                        }
                    }

                    // Remove "saving..." message from button:
                    this.updatePrimaryButtonText(newPrimaryButtonText)
                })
        } else {
            // Remove "saving..." message from button if shelf cannot be updated:
            this.updatePrimaryButtonText(newPrimaryButtonText)
        }
    }

    /**
     * Updates "active" status of the primary form.
     *
     * An "active" dropper will display a checkmark in the primary button, and a remove
     * button in the dropdown.
     *
     * The primary form's `action` input is "remove" when the dropper is active, and
     * "add" otherwise.
     *
     * @param {boolean} isActivated `true` if the dropper is changing to an "active" status
     */
    updateActivatedStatus(isActivated) {
        if (isActivated) {
            this.primaryButton.querySelector('.activated-check').classList.remove('hidden')
            this.removeButton.classList.remove('hidden')
            this.primaryForm.querySelector('input[name=action]').value = 'remove'
        } else {
            this.primaryButton.querySelector('.activated-check').classList.add('hidden')
            this.removeButton.classList.add('hidden')
            this.primaryForm.querySelector('input[name=action]').value = 'add'
        }

        this.primaryButton.classList.toggle('activated')
        this.primaryButton.classList.toggle('unactivated')
    }

    /**
     * Sets that primary button's text to the given string.
     *
     * @param {string} newText
     */
    updatePrimaryButtonText(newText) {
        this.primaryButton.querySelector('.btn-text').innerText = newText
    }

    /**
     * Changes value of primary form's `bookshelf_id` input to the given number.
     *
     * @param {number} newId
     */
    updatePrimaryBookshelfId(newId) {
        this.primaryForm.querySelector('input[name=bookshelf_id]').value = newId
    }

    /**
     * Updates the visibility of dropdown buttons, hiding the given button.
     *
     * All other dropdown buttons will be visible after this method exits.
     *
     * @param {HTMLButtonElement} transitioningButton
     */
    updateDropdownButtonVisibility(transitioningButton) {
        for (const button of this.submitButtons) {
            button.classList.remove('hidden')
        }

        transitioningButton.classList.add('hidden')
    }

    /**
     * Returns the display string used to denote the given reading log shelf ID.
     *
     * @param shelfId {ReadingLogShelf}
     */
    getDisplayString(shelfId) {
        const matchingFormElem = Array.from(this.readingLogForms).find(elem => {
            if (elem === this.primaryForm) {
                return false
            }
            const bookshelfInput = elem.querySelector('input[name=bookshelf_id]')
            return shelfId === bookshelfInput.value
        })

        const formButton = matchingFormElem.querySelector('button')
        return formButton.textContent
    }
}
