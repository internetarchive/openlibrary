/**
 * Defines functionality related to the Reading Check-Ins components.
 * @module my-books/MyBooksDropper/ReadDateComponents
 */
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
 * Class representing a dropper's Reading Check-Ins components.
 *
 * The read date prompt is displayed when a book is added to a patron's "Already
 * Read" shelf (only if no read date exists for the associated book).
 *
 * The date display is visible when a patron has previously submitted a read date
 * for the associated book.
 *
 * At any given time, no more than one of these components will be visible beneath
 * the dropper.
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

        const dropperWorkKey = dropper.querySelector('input[name=work_id]').value
        const dropperWorkOlid = dropperWorkKey.split('/').slice(-1).pop()

        /**
         * @type {HTMLElement}
         */
        const readDateContainer = document.querySelector(`#check-in-container-${dropperWorkOlid}`)

        /**
         * Reference to the component that prompts the patron for a read date.
         *
         * @param {HTMLElement}
         */
        this.datePrompt = readDateContainer.querySelector('.check-in-prompt')

        /**
         * Reference to the component that displays the last read date.
         *
         * @param {HTMLElement}
         */
        this.readDate = readDateContainer.querySelector('.last-read-date')

        /**
         * References element that will be displayed in last read date form modal.
         * Set during form initialization.
         *
         * @type {HTMLElement|undefined}
         */
        this.modalContent = undefined

        /**
         * Reference form for last read dates.
         * Set during form initialization.
         *
         * @type {HTMLFormElement|undefined}
         */
        this.form = undefined

        /**
         * Reference to hidden `event_id` form input.
         * Set during form initialization.
         *
         * @type {HTMLInputElement|undefined}
         */
        this.eventIdInput = undefined

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
        this.config = JSON.parse(readDateContainer.dataset.config)
    }

    initialize() {
        this.initDatePrompt()
        this.initCheckInEdits()
        this.initCheckInForm()
    }

    // START : Component initialization methods
    /**
     * Adds click listeners to the read date prompt component.
     */
    initDatePrompt() {
        const yearLink = this.datePrompt.querySelector('.prompt-current-year')
        yearLink.addEventListener('click', () => this.onReadThisYearClick())

        const todayLink = this.datePrompt.querySelector('.prompt-today')
        todayLink.addEventListener('click', () => this.onReadTodayClick())

        const customDateLink = this.datePrompt.querySelector('.prompt-custom')
        customDateLink.addEventListener('click', () => this.openModal())
    }

    /**
     * Adds click listener to "Edit" affordance in read date display component.
     */
    initCheckInEdits() {
        const editDateButton = this.readDate.querySelector('.prompt-edit-date')
        editDateButton.addEventListener('click', () => this.openModal())
    }

    /**
     * Creates, initializes, and hydrates the read date form, and the modal
     * that displays it.
     */
    initCheckInForm() {
        // Create form from template
        const modalContent = this.createModalContentFromTemplate()

        // Attach modal content to DOM
        /*  XXX : This hidden container of modal content seems a bit odd...
                 Alternatively, an HTML string can be passed to colorbox.
                 If this is done, all form elements would need to be hydrated
                 each time the modal is opened.
        */
        let hiddenModalContentContainer = document.querySelector('#hidden-modal-content-container')
        if (!hiddenModalContentContainer) {
            hiddenModalContentContainer = document.createElement("div")
            hiddenModalContentContainer.classList.add('hidden')
            hiddenModalContentContainer.id = 'hidden-modal-content-container'
            document.body.appendChild(hiddenModalContentContainer)
        }
        hiddenModalContentContainer.appendChild(modalContent)
        this.modalContent = hiddenModalContentContainer.querySelector(`#modal-content-${this.config.workOlid}`)

        this.form = this.modalContent.querySelector('form')
        this.form.action = `/works/${this.config.workOlid}/check-ins.json`
        this.eventIdInput = this.form.querySelector('input[name=event_id]')
        if (this.config.eventId) {
            this.updateEventId(this.config.eventId)
            this.showDeleteButton()
        }

        // Update form with last read date
        const readDate = this.config.lastReadDate
        const [year, month, day] = readDate ? readDate.split('-') : [null, null, null]
        this.updateReadDateForm(Number(year), Number(month), Number(day))

        // Add listeners
        const deleteButton = this.form.querySelector('.check-in__delete-btn')
        deleteButton.addEventListener('click', (event) => this.onDeleteClick(event))

        const submitButton = this.form.querySelector('.check-in__submit-btn')
        submitButton.addEventListener('click', (event) => this.onSubmitClick(event))

        const yearSelect = this.form.querySelector('select[name=year]')
        const currentYear = new Date().getFullYear();
        const hiddenYear = yearSelect.querySelector('.show-if-local-year')
        // The year selector has a hidden option for next year.  This option is
        // shown on 1 January if the client's local year is different from
        // the server's local year.
        if (Number(hiddenYear.value) === currentYear) {
            hiddenYear.classList.remove('hidden')
        }

        yearSelect.addEventListener('change', () => this.onDateSelectionChange())

        const monthSelect = this.form.querySelector('select[name=month]')
        monthSelect.addEventListener('change', () => this.onDateSelectionChange())

        const todayLink = this.form.querySelector('.check-in__today')
        todayLink.addEventListener('click', () => this.onUseTodayClick())

        const closeModalElem = this.modalContent.querySelector('.dialog--close')
        closeModalElem.addEventListener('click', () => {$.colorbox.close()})
    }
    // END : Component initialization methods

    // START : Event listener callbacks

    // Listeners on the read date components
    /**
     * Submits a read event with today's date.
     */
    onReadTodayClick() {
        // Get today's date
        const now = new Date()
        const year = now.getFullYear()
        const month = now.getMonth() + 1
        const day =  now.getDate()

        this.doSubmitEventAndUpdateView(year, month, day)
    }

    /**
     * Submits a read event with the current year.
     */
    onReadThisYearClick() {
        // Get the current year
        const year = new Date().getFullYear()

        this.doSubmitEventAndUpdateView(year)
    }

    // Listeners on the form
    /**
     * Updates form controls based on the currently selected date.
     */
    onDateSelectionChange() {
        const yearSelect = this.form.querySelector('select[name=year]')
        const monthSelect = this.form.querySelector('select[name=month]')
        const daySelect = this.form.querySelector('select[name=day]')
        const year = yearSelect.selectedIndex ? Number(yearSelect.value) : null
        this.updateReadDateForm(year, monthSelect.selectedIndex, daySelect.selectedIndex)
    }

    /**
     * Updates form to use the current date.
     */
    onUseTodayClick() {
        // Get today's date
        const now = new Date()
        const year = now.getFullYear()
        const month = now.getMonth() + 1
        const day =  now.getDate()

        this.updateReadDateForm(year, month, day)
    }

    /**
     * Sends request to delete a read event, then updates the UI.
     *
     * @param {Event} event
     */
    onDeleteClick(event) {
        event.preventDefault()

        const eventId = this.eventIdInput.value

        try {
            this.deleteEvent(eventId)

            // Show date prompt
            this.hideReadDate()
            this.showDatePrompt()

            // Reset the form
            this.resetForm()
        } catch (e) {
            new PersistentToast('Failed to delete check-in.  Please try again in a few moments.').show()
        }

        $.colorbox.close()
    }

    /**
     * Submits a read event with the form's currently selected date, and updates the UI.
     *
     * @param {Event} event
     */
    onSubmitClick(event) {
        event.preventDefault()

        const dayField = this.form.querySelector('select[name=day]')
        const day = dayField.value ? Number(dayField.value) : null
        const monthField = this.form.querySelector('select[name=month]')
        const month = monthField.value ? Number(monthField.value) : null
        const yearField = this.form.querySelector('select[name=year]')
        const year = Number(yearField.value)

        this.doSubmitEventAndUpdateView(year, month, day)

        // close the modal
        $.colorbox.close()
    }
    // END : Event listener callbacks

    // START : API calls and helpers
    /**
     * Submits a read date event request with the given information, and updates views.
     *
     * If the request was successful, the read date display will be made visible.
     *
     * @param {number} year
     * @param {number|null} month
     * @param {number|null} day
     */
    doSubmitEventAndUpdateView(year, month = null, day = null) {
        const eventData = this.prepareEventRequest(year, month, day)
        try {
            // Submit the form
            this.postEvent(eventData, this.form.action)

            // Update last read date display
            this.updateReadDateDisplay(year, month, day)

            // Toggle components
            this.hideDatePrompt()
            this.showReadDate()

            // Update submission form
            this.updateReadDateForm(eventData.year, eventData.month, eventData.day)
            // this.updateEventId(respEventId)
            this.showDeleteButton()
        } catch (e) {
            new PersistentToast('Failed to submit check-in.  Please try again in a few moments.').show()
        }
    }

    /**
     * @typedef {object} ReadEventPostRequestData
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
     * @param {ReadEventPostRequestData} eventData
     * @param {string} url
     * @throws Will throw an error when form submission fails
     */
    postEvent(eventData, url) {
        $.ajax({
            type: 'POST',
            url: url,
            contentType: 'application/json',
            data: JSON.stringify(eventData),
            dataType: 'json',
            async: false,
            beforeSend: function(xhr) {
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('Accept', 'application/json');
            },
            // success: success,
            success: (resp) => {
                this.updateEventId(resp.id)
            },
            error: function() {
                throw Error("Form submission failed")
            }
        });
    }

    /**
     * Prepares data for a `postEvent` call.
     *
     * @param {number} year
     * @param {number|null} month
     * @param {number|null} day
     * @returns {ReadEventPostRequestData}
     */
    prepareEventRequest(year, month = null, day = null) {
        //  Get event id
        const eventId = this.eventIdInput.value

        // Get event type
        const eventTypeInput = this.form.querySelector('input[name=event_type]')
        const eventType = eventTypeInput.value

        const eventRequest = {
            event_id: eventId ? Number(eventId) : null,
            event_type: Number(eventType),
            year: year,
            month: month,
            day: day
        }

        const editionField = this.form.querySelector('input[name=edition_key]')
        const editionKey = editionField ? editionField.value : null
        if (editionKey) {
            eventRequest.edition_key = editionKey
        }

        return eventRequest
    }

    /**
     * Posts request to delete the read date record with the given ID.
     *
     * @param {string} eventId
     * @throws Will throw an error when the delete request fails
     */
    deleteEvent(eventId) {
        $.ajax({
            type: 'DELETE',
            url: `/check-ins/${eventId}`,
            error: function() {
                throw Error("Read date delete request failed")
            }
        })
    }
    // END : API calls

    // START : UI update functions
    /**
     * Opens a modal containing the form associated with these read date components.
     */
    openModal() {
        $.colorbox({
            width: '100%',
            maxWidth: '640px',
            inline: true,
            opacity: '0.5',
            href: `#modal-content-${this.config.workOlid}`,
        })
    }

    /**
     * Hides the date prompt component.
     */
    hideDatePrompt() {
        this.datePrompt.classList.add('hidden')
    }

    /**
     * Shows date prompt if no read date exists.
     */
    showDatePrompt() {
        if (!this.hasReadDate()) {
            this.datePrompt.classList.remove('hidden')
        }
    }

    /**
     * Hides the read date display, and resets the date submission form.
     */
    hideReadDate() {
        this.readDate.classList.add('hidden')
    }

    /**
     * Shows the read date display.
     */
    showReadDate() {
        this.readDate.classList.remove('hidden')
    }

    /**
     * Updates the date in the read date display component.
     *
     * @param {number} year
     * @param {number|null} month
     * @param {number|null} day
     */
    updateReadDateDisplay(year, month = null, day = null) {
        let date = year
        if (month) {
            date += `-${String(month).padStart(2, '0')}`
            if (day) {
                date += `-${String(day).padStart(2, '0')}`
            }
        }
        const dateField = this.readDate.querySelector('.check-in-date')
        dateField.textContent = date
    }
    // END : UI update functions

    // START: Form operations
    /**
     *
     * @returns {Element}
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
     * Unsets the read date form's event ID, and hides the form's delete button.
     *
     * Meant to be used when a read date has been deleted.
     */
    resetForm() {
        this.eventIdInput.value = ''

        // Reset dates and submit button
        this.updateReadDateForm()

        // Update buttons
        this.hideDeleteButton()
    }

    /**
     * Updates read date form elements based on the given year, month, and day.
     *
     * @param {number|null} year
     * @param {number|null} month
     * @param {number|null} day
     */
    updateReadDateForm(year = null, month= null, day = null) {
        if (!month) {
            day = null
        }
        if (!year) {
            month = null
            day = null
        }

        const yearSelect = this.form.querySelector('select[name=year]')
        const monthSelect = this.form.querySelector('select[name=month]')
        const daySelect = this.form.querySelector('select[name=day]')
        const submitButton = this.form.querySelector('.check-in__submit-btn')

        if (year) {
            yearSelect.value = year
            monthSelect.disabled = false
            submitButton.disabled = false
        } else {
            yearSelect.selectedIndex = 0
            monthSelect.disabled = true
            submitButton.disabled = true
        }
        if (month) {
            monthSelect.value = month
            daySelect.disabled = false

            // Update daySelect options for month/leap year
            let daysInMonth = DAYS_IN_MONTH[month - 1]
            if (month === 2 && isLeapYear(year)) {
                ++daysInMonth
            }
            this.updateDayOptions(daysInMonth)
        } else {
            monthSelect.selectedIndex = 0
            daySelect.disabled = true
        }
        if (day) {
            const daysInMonth = DAYS_IN_MONTH[monthSelect.selectedIndex - 1]
            daySelect.value = day > daysInMonth ? 1 : day
        } else {
            daySelect.selectedIndex = 0
        }
    }

    /**
     * Updates day selector options, hiding days greater than the given amount.
     *
     * @param daysInMonth
     */
    updateDayOptions(daysInMonth) {
        const daySelect = this.form.querySelector('select[name=day]')
        for (let i = 0; i < daySelect.options.length; ++i) {
            if (i <= daysInMonth) {
                daySelect.options[i].classList.remove('hidden')
            } else {
                daySelect.options[i].classList.add('hidden')
            }
        }
    }

    /**
     * Sets the value of the form's `event_id` input element.
     *
     * @param eventId
     */
    updateEventId(eventId) {
        this.eventIdInput.value = eventId || ''
    }

    /**
     * Shows the form's delete button.
     */
    showDeleteButton() {
        const deleteButton = this.form.querySelector('.check-in__delete-btn')
        deleteButton.classList.remove('invisible')
    }

    /**
     * Hides the form's delete button.
     */
    hideDeleteButton() {
        const deleteButton = this.form.querySelector('.check-in__delete-btn')
        deleteButton.classList.add('invisible')
    }
    // END: Form operations

    /**
     * Returns `true` if the associated work has a read date.
     *
     * @returns {boolean}
     */
    hasReadDate() {
        return !this.readDate.classList.contains('hidden')
    }
}
