/**
 * Defines functionality related to the Reading Check-Ins components.
 * @module my-books/MyBooksDropper/CheckInComponents
 */
import { initDialogClosers } from "../../dialog";
import { PersistentToast } from '../../Toast'

/**
 * Array of days for each month, listed in order starting with January.
 * Assumes that it is not a leap year.
 *
 * @readonly
 * @type {array<number>}
 */
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

/**
 * Determines if the given year is a leap year.
 *
 * @param {Number} year
 * @returns `true` if the given year is a leap year.
 */
function isLeapYear(year) {
    return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
}

/**
 * Represents a dropper's read date Check-In components.
 *
 * This class is responsible for the following:
 * 1. Making API calls to the check-in handlers whenever a check-in event occurs.
 * 2. Updating the view when a check-in event occurs.
 *
 * @see `/templates/my_books/check_ins/check_in_prompt.html` for the base HTML
 * template for these components
 *
 * @class
 */
export class CheckInComponents {
    /**
     * @param checkInContainer
     */
    constructor(checkInContainer) {
        // HTML for the check-in components is not rendered if
        // the patron is unauthenticated, or if the dropper
        // is for an orphaned edition.
        if (!checkInContainer) {
            return
        }

        /**
         * @typedef {object} ReadDateConfig
         * @property {string} workOlid
         * @property {string} [editionKey]
         * @property {string} [lastReadDate]
         * @property {number} [eventId]
         */
        /**
         * @param {ReadDateConfig}
         */
        this.config = JSON.parse(checkInContainer.dataset.config)

        const checkInPromptElem = checkInContainer.querySelector('.check-in-prompt')
        /**
         * @type {CheckInPrompt}
         */
        this.checkInPrompt = new CheckInPrompt(checkInPromptElem)

        const checkInDisplayElem = checkInContainer.querySelector('.last-read-date')
        /**
         * @type {CheckInDisplay}
         */
        this.checkInDisplay = new CheckInDisplay(checkInDisplayElem)

        /**
         * References element that will be displayed in last read date form modal.
         * Set during form initialization.
         *
         * @type {HTMLElement|undefined}
         */
        this.modalContent = undefined

        /**
         * @type {CheckInForm|undefined}
         */
        this.checkInForm = undefined
    }

    initialize() {
        this.checkInPrompt.initialize()
        this.checkInPrompt.getRootElement().addEventListener('submit-check-in', (event) => {
            const year = event.detail.year
            const month = event.detail.month
            const day = event.detail.day

            const eventData = this.prepareEventRequest(year, month, day)
            this.postCheckIn(eventData, this.checkInForm.getFormAction())
                .then((resp) => {
                    if (!resp.ok) {
                        throw Error(`Check-in request failed. Status: ${resp.status}`)
                    }
                    this.updateDateAndShowDisplay(year, month, day)
                })
                .catch(() => {
                    new PersistentToast('Failed to submit check-in.  Please try again in a few moments.').show()
                })
        })

        let hiddenModalContentContainer = document.querySelector('#hidden-modal-content-container')
        if (!hiddenModalContentContainer) {
            hiddenModalContentContainer = document.createElement("div")
            hiddenModalContentContainer.classList.add('hidden')
            hiddenModalContentContainer.id = 'hidden-modal-content-container'
            document.body.appendChild(hiddenModalContentContainer)
        }

        const modalContent = this.createModalContentFromTemplate()
        hiddenModalContentContainer.appendChild(modalContent)

        this.modalContent = hiddenModalContentContainer.querySelector(`#modal-content-${this.config.workOlid}`)

        const formElem = this.modalContent.querySelector('form')
        this.checkInForm = new CheckInForm(formElem, this.config.workOlid, this.config.editionKey || '', this.config.lastReadDate || '', this.config.eventId)
        this.checkInForm.initialize()
        this.checkInForm.getRootElement().addEventListener('delete-check-in', () => {
            this.deleteCheckIn(this.checkInForm.getEventId())
                .then(resp => {
                    if (!resp.ok) {
                        throw Error(`Check-in delete request failed. Status: ${resp.status}`)
                    }

                    this.checkInForm.resetForm()
                    this.checkInDisplay.hide()
                    this.checkInPrompt.show()
                })
                .catch(err => {
                    // TODO : Use localized strings
                    new PersistentToast('Failed to delete check-in.  Please try again in a few moments.').show()
                })
                .finally(() => {
                    this.closeModal()
                })
        })
        this.checkInForm.getRootElement().addEventListener('submit-check-in', (event) => {
            const year = event.detail.year
            const month = event.detail.month
            const day = event.detail.day

            const eventData = this.prepareEventRequest(year, month, day)
            this.postCheckIn(eventData, this.checkInForm.getFormAction())
                .then((resp) => {
                    if (!resp.ok) {
                        throw Error(`Check-in request failed. Status: ${resp.status}`)
                    }
                    this.updateDateAndShowDisplay(year, month, day)
                })
                .catch(() => {
                    // TODO : Use localized strings
                    new PersistentToast('Failed to submit check-in.  Please try again in a few moments.').show()
                })
                .finally(() => {
                    this.closeModal()
                })
        })

        const closeModalElements = this.modalContent.querySelectorAll('.dialog--close')
        initDialogClosers(closeModalElements)
    }

    /**
     * Creates a new element containing the check-in form and `colorbox` modal content.
     *
     * @returns {HTMLElement}
     */
    createModalContentFromTemplate() {
        const templateElem = document.createElement('template')
        const modalContentTemplate = document.querySelector('#check-in-form-modal')
        templateElem.innerHTML = modalContentTemplate.outerHTML
        const modalContent = templateElem.content.firstElementChild
        modalContent.id = `modal-content-${this.config.workOlid}`

        return modalContent
    }

    /**
     * Updates the date display and form with the given date, and shows the display.
     *
     * @param {number} year
     * @param {number|null} month
     * @param {number|null} day
     */
    updateDateAndShowDisplay(year, month = null, day = null) {
        // Update last read date display
        let dateString = String(year)
        if (month) {
            dateString += `-${String(month).padStart(2, '0')}`
            if (day) {
                dateString += `-${String(day).padStart(2, '0')}`
            }
        }
        this.checkInDisplay.updateDateDisplay(dateString)

        // Update component visibility
        this.checkInPrompt.hide()
        this.checkInDisplay.show()

        // Update submission form
        this.checkInForm.updateDateSelectors(year, month, day)
        this.checkInForm.showDeleteButton()

    }

    /**
     * @typedef {object} CheckInEventPostRequestData
     * @property {number} event_type
     * @property {number} year
     * @property {number|null} month
     * @property {number|null} day
     * @property {number|null} event_id
     * @property {string} [edition_key]
     */
    /**
     * Posts the given data to the backend check-in handler.
     *
     * @param {CheckInEventPostRequestData} eventData
     * @param {string} url
     * @returns {Promise<Response>}
     */
    postCheckIn(eventData, url) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'content-type': 'application/x-www-form-urlencoded',
                'accept': 'application/json'
            },
            body: JSON.stringify(eventData)
        })
    }

    /**
     * Posts request to delete the read date record with the given ID.
     *
     * @param {string} eventId
     * @returns {Promise<Response>}
     */
    async deleteCheckIn(eventId) {
        return fetch(`/check-ins/${eventId}`, {
            method: 'DELETE'
        })
    }

    /**
     * Prepares data for a `postEvent` call.
     *
     * @param {number} year
     * @param {number|null} month
     * @param {number|null} day
     * @returns {CheckInEventPostRequestData}
     */
    prepareEventRequest(year, month = null, day = null) {
        //  Get event id
        const eventId = this.checkInForm.getEventId()

        // Get event type
        const eventType = this.checkInForm.getEventType()

        const eventRequest = {
            event_id: eventId ? Number(eventId) : null,
            event_type: Number(eventType),
            year: year,
            month: month,
            day: day
        }

        const editionKey = this.checkInForm.getEditionKey() || null
        if (editionKey) {
            eventRequest.edition_key = editionKey
        }

        return eventRequest
    }

    /**
     * Returns `true` if the check-in display is visible on the screen.
     *
     * @returns {boolean}
     */
    hasReadDate() {
        return !this.checkInDisplay.getRootElement().classList.contains('hidden')
    }

    /**
     * Resets the check-in form.
     */
    resetForm() {
        this.checkInForm.resetForm()
    }

    /**
     * Show the check-in display.
     */
    showCheckInDisplay() {
        this.checkInDisplay.show()
    }

    /**
     * Hide the check-in display.
     */
    hideCheckInDisplay() {
        this.checkInDisplay.hide()
    }

    /**
     * Show the check-in prompt.
     */
    showCheckInPrompt() {
        this.checkInPrompt.show()
    }

    /**
     * Hide the check-in prompt.
     */
    hideCheckInPrompt() {
        this.checkInPrompt.hide()
    }

    /**
     * Closes the opened `colorbox` modal.
     */
    closeModal() {
        $.colorbox.close()
    }
}

/**
 * Represents a prompt for check-in events.
 *
 * @class
 */
class CheckInPrompt {
    /**
     * @param {HTMLElement} checkInPrompt
     */
    constructor(checkInPrompt) {
        this.rootElem = checkInPrompt
    }

    initialize() {
        const yearLink = this.rootElem.querySelector('.prompt-current-year')
        yearLink.addEventListener('click', () => {
            // Get the current year
            const year = new Date().getFullYear()

            this.dispatchCheckInSubmission(year)
        })

        const todayLink = this.rootElem.querySelector('.prompt-today')
        todayLink.addEventListener('click', () => {
            // Get today's date
            const now = new Date()
            const year = now.getFullYear()
            const month = now.getMonth() + 1
            const day =  now.getDate()

            this.dispatchCheckInSubmission(year, month, day)
        })
    }

    /**
     * Dispatches a custom `submit-check-in` event with the given date.
     *
     * @param {number} year
     * @param {number|null} month
     * @param {number|null} day
     */
    dispatchCheckInSubmission(year, month = null, day = null) {
        const submitEvent = new CustomEvent("submit-check-in", {
            detail: {
                year: year,
                month: month,
                day: day
            }
        })
        this.rootElem.dispatchEvent(submitEvent)
    }

    /**
     * Hides this check-in prompt.
     */
    hide() {
        this.rootElem.classList.add('hidden')
    }

    /**
     * Shows this check-in prompt.
     */
    show() {
        this.rootElem.classList.remove('hidden')
    }

    /**
     * Returns reference to the root element of this check-in prompt.
     * @returns {HTMLElement}
     */
    getRootElement() {
        return this.rootElem
    }
}

/**
 * Represents a component that displays the last check-in date.
 *
 * @class
 */
class CheckInDisplay {
    /**
     * @param {HTMLElement} checkInDisplay
     */
    constructor(checkInDisplay) {
        this.rootElem = checkInDisplay
        this.dateDisplayElem = this.rootElem.querySelector('.check-in-date')
    }

    /**
     * Updates the date displayed to the given string.
     *
     * @param {string} date
     */
    updateDateDisplay(date) {
        this.dateDisplayElem.textContent = date
    }

    /**
     * Hides this date display.
     */
    hide() {
        this.rootElem.classList.add('hidden')
    }

    /**
     * Shows this date display.
     */
    show() {
        this.rootElem.classList.remove('hidden')
    }

    /**
     * @returns {HTMLElement}
     */
    getRootElement() {
        return this.rootElem
    }
}

/**
 * Represents a form with which to submit or delete a check-in event.
 *
 * The actual `form` element is created from a template.
 *
 * @see `/templates/my_books/check_ins/check_in_form.html` for form's
 * HTML template.
 *
 * @class
 */
class CheckInForm {
    /**
     * @param {HTMLFormElement} formElem
     * @param {string} workOlid
     * @param {string|null} editionKey
     * @param {string|null} lastReadDate
     * @param {number|null} eventId
     */
    constructor(formElem, workOlid, editionKey = null, lastReadDate = null, eventId = null) {
        this.rootElem = formElem
        this.workOlid = workOlid
        this.editionKey = editionKey
        this.lastReadDate = lastReadDate
        this.eventId = eventId

        /**
         * Reference to hidden `event_type` form input.
         *
         * @type {HTMLInputElement|undefined}
         */
        this.eventTypeInput = this.rootElem.querySelector('input[name=event_type]')

        /**
         * Reference to hidden `event_id` form input.
         *
         * @type {HTMLInputElement|undefined}
         */
        this.eventIdInput = this.rootElem.querySelector('input[name=event_id]')

        /**
         * Reference to hidden `edition_key` form input.
         *
         * @type {HTMLInputElement}
         */
        this.editionKeyInput = this.rootElem.querySelector('input[name=edition_key]')

        /**
         * Reference to the form's year `select` element.
         *
         * @type {HTMLSelectElement}
         */
        this.yearSelect = this.rootElem.querySelector('select[name=year]')

        /**
         * Reference to the form's month `select` element.
         *
         * @type {HTMLSelectElement}
         */
        this.monthSelect = this.rootElem.querySelector('select[name=month]')

        /**
         * Reference to the form's day `select` element.
         *
         * @type {HTMLSelectElement}
         */
        this.daySelect = this.rootElem.querySelector('select[name=day]')

        /**
         * Reference to the form's submit button.
         * @type {HTMLButtonElement}
         */
        this.submitButton = this.rootElem.querySelector('.check-in__submit-btn')

        /**
         * Reference to the form's delete button.
         *
         * @type {HTMLButtonElement}
         */
        this.deleteButton = this.rootElem.querySelector('.check-in__delete-btn')
    }

    initialize() {
        // Set form's action
        this.rootElem.action = `/works/${this.workOlid}/check-ins.json`
        // Set form's event ID
        if (this.eventId) {
            this.setEventId(this.eventId)
            this.showDeleteButton()
        }
        // Set form's edition_key
        if (this.editionKey) {
            this.editionKeyInput.value = this.editionKey
        }
        // Set date selectors to the last read date
        const [yearString, monthString, dayString] = this.lastReadDate ? this.lastReadDate.split('-') : [null, null, null]
        this.updateDateSelectors(Number(yearString), Number(monthString), Number(dayString))

        // Update form for new years day
        const currentYear = new Date().getFullYear();
        const hiddenYear = this.yearSelect.querySelector('.show-if-local-year')
        // The year selector has a hidden option for next year.  This option is
        // shown on 1 January if the client's local year is different from
        // the server's local year.
        if (Number(hiddenYear.value) === currentYear) {
            hiddenYear.classList.remove('hidden')
        }

        this.yearSelect.addEventListener('change', () => {
            this.onDateSelectionChange()
        })
        this.monthSelect.addEventListener('change', () => {
            this.onDateSelectionChange()
        })
        this.deleteButton.addEventListener('click', (event) => {
            event.preventDefault()
            const deleteEvent = new CustomEvent('delete-check-in')
            this.rootElem.dispatchEvent(deleteEvent)
        })
        this.submitButton.addEventListener('click', (event) => {
            event.preventDefault()
            const submitEvent = new CustomEvent('submit-check-in', {
                detail: {
                    year: this.getSelectedYear(),
                    month: this.getSelectedMonth(),
                    day: this.getSelectedDay()
                }
            })
            this.rootElem.dispatchEvent(submitEvent)
        })
        const todayLink = this.rootElem.querySelector('.check-in__today')
        todayLink.addEventListener('click', () => {
            // Get today's date
            const now = new Date()
            const year = now.getFullYear()
            const month = now.getMonth() + 1
            const day =  now.getDate()

            this.updateDateSelectors(year, month, day)
        })
    }

    /**
     * Gets currently selected date, then updates the form.
     */
    onDateSelectionChange() {
        const year = this.yearSelect.selectedIndex ? Number(this.yearSelect.value) : null
        this.updateDateSelectors(year, this.monthSelect.selectedIndex, this.daySelect.selectedIndex)
    }

    /**
     * Updates date selectors based on the given year, month, and day.
     *
     * @param {number|null} year
     * @param {number|null} month
     * @param {number|null} day
     */
    updateDateSelectors(year = null, month = null, day = null) {
        if (!month) {
            day = null
        }
        if (!year) {
            month = null
            day = null
        }

        if (year) {
            this.yearSelect.value = year || ''
            this.monthSelect.disabled = false
            this.submitButton.disabled = false
        } else {
            this.yearSelect.selectedIndex = 0
            this.monthSelect.disabled = true
            this.submitButton.disabled = true
        }
        if (month) {
            this.monthSelect.value = month || ''
            this.daySelect.disabled = false

            // Update daySelect options for month/leap year
            let daysInMonth = DAYS_IN_MONTH[month - 1]
            if (month === 2 && isLeapYear(year)) {
                ++daysInMonth
            }
            this.updateDayOptions(daysInMonth)
        } else {
            this.monthSelect.selectedIndex = 0
            this.daySelect.disabled = true
        }
        if (day) {
            const daysInMonth = DAYS_IN_MONTH[this.monthSelect.selectedIndex - 1]
            this.daySelect.selectedIndex = day > daysInMonth ? 0 : day
        } else {
            this.daySelect.selectedIndex = 0
        }
    }

    /**
     * Updates day selector options, hiding days greater than the given amount.
     *
     * @param {number} daysInMonth
     */
    updateDayOptions(daysInMonth) {
        for (let i = 0; i < this.daySelect.options.length; ++i) {
            if (i <= daysInMonth) {
                this.daySelect.options[i].classList.remove('hidden')
            } else {
                this.daySelect.options[i].classList.add('hidden')
            }
        }
    }

    /**
     * Resets the form.
     *
     * Unsets the `event_id` input value, hides the delete button, and
     * resets the date selectors to their default values.
     */
    resetForm() {
        this.setEventId('')
        this.updateDateSelectors()
        this.hideDeleteButton()
    }

    /**
     * Shows this form's delete button.
     */
    showDeleteButton() {
        this.deleteButton.classList.remove('invisible')
    }

    /**
     * Hides this form's delete button.
     */
    hideDeleteButton() {
        this.deleteButton.classList.add('invisible')
    }

    /**
     * Returns the numeric value of the selected year.
     *
     * @returns {number|null} The selected year, or `null` if none selected
     */
    getSelectedYear() {
        return this.yearSelect.selectedIndex ? Number(this.yearSelect.value) : null
    }

    /**
     * Returns the numeric value of the selected month.
     *
     * @returns {number|null} The selected month, or `null` if none selected
     */
    getSelectedMonth() {
        return this.monthSelect.selectedIndex || null
    }

    /**
     * Returns the numeric value of the selected day.
     *
     * @returns {number|null} The selected day, or `null` if none selected
     */
    getSelectedDay() {
        return this.daySelect.selectedIndex || null
    }

    /**
     * Returns the value of this form's `event_id` input.
     *
     * @returns {string}
     */
    getEventId() {
        return this.eventIdInput.value
    }

    /**
     * Updates the value of the form's `event_id` input.
     *
     * @param value
     */
    setEventId(value) {
        this.eventIdInput.value = value
    }

    /**
     * Returns the value of this form's `event_type` input.
     *
     * @returns {string}
     */
    getEventType() {
        return this.eventTypeInput.value
    }

    /**
     * Returns the value of the form's edition key input.
     *
     * @returns {string}
     */
    getEditionKey() {
        return this.editionKeyInput.value
    }

    /**
     * Returns this form's `action`
     *
     * @returns {string}
     */
    getFormAction() {
        return this.rootElem.action
    }

    /**
     * Returns a reference to this check-in form.
     *
     * @returns {HTMLFormElement}
     */
    getRootElement() {
        return this.rootElem
    }
}
