/**
 * Defines functionality related to the My Books dropper's reading log forms.
 * @module my-books/ReadingLogForms
 */

import {fireDropperCloseEvent, fireDropperToggleEvent} from '../droppers';

/**
 * Enum for reading log shelf values.
 * @readonly
 * @enum {string}
 */
const ReadingLogShelves = {
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
export default class ReadingLogForms {
    /**
     * Adds functionality to a single dropper's reading log forms.
     *
     * @param {HTMLElement} dropper
     * @param {import('./ReadDateComponents')} readDateComponents
     */
    constructor(dropper, readDateComponents) {
        /**
         * Reference to each reading log submit button.  This includes the
         * primary dropper button and the buttons in the dropdown.
         *
         * @param {NodeList<HTMLElement>}
         */
        this.submitButtons = dropper.querySelectorAll('.reading-log button')

        /**
         * Reference to this dropper's primary form.
         *
         * @param {HTMLFormElement}
         */
        this.primaryForm = null;

        /**
         * Reference to this dropper's primary button.
         *
         * @param {HTMLButtonElement}
         */
        this.primaryButton = null;

        /**
         * Reference to this dropper's "Remove from shelf" button.
         *
         * @param {HTMLButtonElement}
         */
        this.removeButton = null;

        for (const button of this.submitButtons) {
            if (button.classList.contains('primary-action')) {
                this.primaryButton = button
                this.primaryForm = button.closest('form')
            }
            else if (button.classList.contains('remove-from-list')) {
                this.removeButton = button
            }
        }

        if (!this.primaryButton) {
            this.primaryButton = dropper.querySelector('.primary-action')
        }

        /**
         * Reference to the dropper's read date prompt and display components.
         *
         * @param {import('./ReadDateComponents')}
         */
        this.readDateComponents = readDateComponents

        const readingLogForms = dropper.querySelectorAll('form.reading-log')
        const isDropperDisabled = dropper.classList.contains('g-dropper--disabled')
        this.initialize(readingLogForms, isDropperDisabled)
    }

    /**
     * Adds click listeners to each of the given form's submit buttons.
     *
     * @param {NodeList<HTMLFormElement>} readingLogForms
     * @param {boolean} isDropperDisabled
     */
    initialize(readingLogForms, isDropperDisabled) {
        if (!isDropperDisabled) {
            if (readingLogForms.length) {
                for (const form of readingLogForms) {
                    const submitButton = form.querySelector('button[type=submit]')
                    submitButton.addEventListener('click', (event) => {
                        event.preventDefault()
                        this.updateReadingLog(form)

                        // Close the dropper
                        fireDropperCloseEvent(this.primaryForm)
                    })
                }
            } else {
                this.primaryButton.addEventListener('click', () => {
                    fireDropperToggleEvent(this.primaryButton)
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
        this.updatePrimaryButtonText('saving...') // XXX: Use i18n strings

        const formData = new FormData(form)
        const url = form.getAttribute('action')

        const hasAddedBook = formData.get('action') === 'add'

        let canUpdateShelf = true

        if (!hasAddedBook && this.readDateComponents.hasReadDate()) {
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
                            if (!this.readDateComponents.hasReadDate() && newBookshelfId === ReadingLogShelves.ALREADY_READ) {
                                this.readDateComponents.showDatePrompt()
                            } else {
                                this.readDateComponents.hideDatePrompt()
                            }

                        } else {
                            // Update check-ins:
                            this.readDateComponents.hideDatePrompt()
                            this.readDateComponents.hideReadDate()
                        }
                    }

                    // Remove "saving..." message from button:
                    this.updatePrimaryButtonText(newPrimaryButtonText)
                })
        } else {
            // Remove "saving..." message from button:
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
}
