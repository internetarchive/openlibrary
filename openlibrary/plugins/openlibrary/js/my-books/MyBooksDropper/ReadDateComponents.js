/**
 * Defines functionality related to the My Books dropper's read date affordances.
 * @module my-books/MyBooksDropper/ReadDateComponents
 */
import { CheckInEvent } from '../../check-ins'

/**
 * Class representing a dropper's read date prompt and display affordances.
 *
 * The read date prompt is displayed when a book is added to a patron's "Already
 * Read" shelf (only if no read date exists for the associated book).
 *
 * The date display is visible when a patron has previously submitted a read date
 * for the associated book.
 *
 * At any given time, no more than one of these affordances will be visible beneath
 * the dropper.  This class mainly concerns itself with toggling the visibility of
 * the read date affordances.
 *
 * @class
 */
export class ReadDateComponents {
  /**
     * Add functionality to the given dropper's read date components.
     * @param {HTMLElement} dropper
     */
  constructor(dropper) {
    const workIdField = dropper.querySelector('input[name=work_id]')

    // If there is no work ID field, there will be no check-ins for this document
    if (!workIdField) {
      return
    }

    const workKey = dropper.querySelector('input[name=work_id]').value
    const workOlid = workKey.split('/').slice(-1).pop()

    /**
         * References the modal that contains the full read date submission form.
         *
         * @param {HTMLElement}
         */
    this.modal = document.querySelector(`#check-in-dialog-${workOlid}`)

    /**
         * Reference to the component that prompts the patron for a read date.
         *
         * @param {HTMLElement}
         */
    this.datePrompt = document.querySelector(`#prompt-${workOlid}`)

    /**
         * Reference to the component that displays the last read date.
         *
         * @param {HTMLElement}
         */
    this.readDate = document.querySelector(`#check-in-display-${workOlid}`)
  }

  /**
     * Hides the date prompt component.
     */
  hideDatePrompt() {
    this.datePrompt.classList.add('hidden')
  }

  /**
     * Sets up date submission form.  Shows date prompt if no read date exists.
     */
  showDatePrompt() {
    const readDateForm = this.modal.querySelector('.check-in')
    readDateForm.dataset.eventType = CheckInEvent.FINISH

    if (!this.hasReadDate()) {
      this.datePrompt.classList.remove('hidden')
    }
  }

  /**
     * Hides the read date display, and resets the date submission form.
     */
  hideReadDate() {
    this.readDate.classList.add('hidden')
    this.resetForm()
  }

  /**
     * Unsets the read date form's event ID, and hides the form's delete button.
     *
     * Meant to be used when a read date has been deleted.
     */
  resetForm() {
    this.modal.querySelector('input[name=event_id]').value = ''
    this.modal.querySelector('.check-in__delete-btn').classList.add('invisible')
  }

  /**
     * Returns `true` if the associated work has a read date.
     *
     * @returns {boolean}
     */
  hasReadDate() {
    return !this.readDate.classList.contains('hidden')
  }
}
