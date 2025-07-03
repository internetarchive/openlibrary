import { listCreationForm } from './sample-html/lists-test-data'
import { checkInForm } from './sample-html/checkIns-test-data'
import { CreateListForm } from '../../../openlibrary/plugins/openlibrary/js/my-books/CreateListForm'
import { CheckInForm } from '../../../openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/CheckInComponents'

jest.mock('jquery-ui/ui/widgets/dialog', () => {});

describe('CreateListForm.js class', () => {
    let form
    let formElem

    beforeEach(() => {
        document.body.innerHTML = listCreationForm
        formElem = document.querySelector('form')
        form = new CreateListForm(formElem)
    })

    test('References are set correctly', () => {
        const createListButton = formElem.querySelector('#create-list-button')
        const nameInput = formElem.querySelector('#list_label')
        const descriptionInput = formElem.querySelector('#list_desc')

        expect(createListButton === form.createListButton).toBe(true)
        expect(nameInput === form.listTitleInput).toBe(true)
        expect(descriptionInput === form.listDescriptionInput).toBe(true)
    })

    it('it clears the form after a resetForm() call', () => {
        const nameInput = document.querySelector('#list_label')
        const descriptionInput = document.querySelector('#list_desc')

        // Form should be empty initially
        expect(nameInput.value.length).toBe(0)
        expect(descriptionInput.value.length).toBe(0)

        // Add values to each input
        nameInput.value = 'My New List'
        descriptionInput.value = 'The best list ever'
        expect(nameInput.value.length).toBeGreaterThan(0)
        expect(descriptionInput.value.length).toBeGreaterThan(0)

        // After clearing the form
        form.resetForm()
        expect(nameInput.value.length).toBe(0)
        expect(descriptionInput.value.length).toBe(0)
    })
})

describe('CheckInForm class', () => {
    let formElem = undefined
    let submitButton = undefined
    let yearSelect = undefined
    let monthSelect = undefined
    let daySelect = undefined

    const workOlid = 'OL123W'
    const editionKey = '/books/OL456M'



    beforeEach(() => {
        document.body.innerHTML = checkInForm
        formElem = document.querySelector('form')
        submitButton = document.querySelector('.check-in__submit-btn')
        yearSelect = document.querySelector('select[name=year]')
        monthSelect = document.querySelector('select[name=month]')
        daySelect = document.querySelector('select[name=day]')
    })

    test('Submit button, month select, and day select are initially disabled when read date is absent', () => {
        const form = new CheckInForm(formElem, workOlid, editionKey)
        form.initialize()
        expect(submitButton.disabled).toBe(true)
        expect(monthSelect.disabled).toBe(true)
        expect(daySelect.disabled).toBe(true)

        expect(yearSelect.disabled).toBe(false)
        expect(yearSelect.value).toBe('')
    })

    it('Sets correct values and enables selects and submit button', () => {
        const form = new CheckInForm(formElem, workOlid, editionKey)
        form.initialize()
        form.updateSelectedDate(2022, 1, 31)
        expect(submitButton.disabled).toBe(false)
        expect(monthSelect.disabled).toBe(false)
        expect(daySelect.disabled).toBe(false)

        expect(yearSelect.value).toBe('2022')
        expect(monthSelect.value).toBe('1')
        expect(daySelect.value).toBe('31')
    })

    it('Hides impossible day options', () => {
        const form = new CheckInForm(formElem, workOlid, editionKey)
        form.initialize()
        form.updateSelectedDate(2022, 2, 20)

        // The 28th day should be visible:
        expect(daySelect.options[28].classList.contains('hidden')).toBe(false)

        // Subsequent days should not be visible
        expect(daySelect.options[29].classList.contains('hidden')).toBe(true)
        expect(daySelect.options[30].classList.contains('hidden')).toBe(true)
        expect(daySelect.options[31].classList.contains('hidden')).toBe(true)
    })

    it('Shows 29 days in February when there is a leap year', () => {
        const form = new CheckInForm(formElem, workOlid, editionKey)
        form.initialize()
        form.updateSelectedDate(2020, 2, 1)

        expect(daySelect.options[29].classList.contains('hidden')).toBe(false)
        expect(daySelect.options[30].classList.contains('hidden')).toBe(true)
        expect(daySelect.options[31].classList.contains('hidden')).toBe(true)
    })

    it('Associates labels with select elements during initialization', () => {
        const form = new CheckInForm(formElem, workOlid, editionKey)

        // Get reference to each label:
        const yearLabel = formElem.querySelector('.check-in__year-label')
        const monthLabel = formElem.querySelector('.check-in__month-label')
        const dayLabel = formElem.querySelector('.check-in__day-label')

        // Verify labels have no `for` initially:
        expect(yearLabel.htmlFor).toBe('')
        expect(monthLabel.htmlFor).toBe('')
        expect(dayLabel.htmlFor).toBe('')

        // Verify select elements have no `id` initially:
        expect(yearSelect.id).toBe('')
        expect(monthSelect.id).toBe('')
        expect(daySelect.id).toBe('')

        // Verify labels associated with selects after initialization:
        form.initialize()

        const expectedYearId = `year-select-${workOlid}`
        const expectedMonthId = `month-select-${workOlid}`
        const expectedDayId = `day-select-${workOlid}`

        expect(yearLabel.htmlFor).toBe(expectedYearId)
        expect(monthLabel.htmlFor).toBe(expectedMonthId)
        expect(dayLabel.htmlFor).toBe(expectedDayId)

        expect(yearSelect.id).toBe(expectedYearId)
        expect(monthSelect.id).toBe(expectedMonthId)
        expect(daySelect.id).toBe(expectedDayId)
    })
})
