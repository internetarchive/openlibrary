import { checkInForm } from './html-test-data';
import { setDate } from '../../../openlibrary/plugins/openlibrary/js/check-ins/index.js'

describe('setDate', () => {
    document.body.innerHTML = checkInForm
    const submitButton = document.querySelector('.check-in__submit-btn')
    const yearSelect = document.querySelector('select[name=year]')
    const monthSelect = document.querySelector('select[name=month]')
    const daySelect = document.querySelector('select[name=day]')

    test('Submit button, month select, and day select are initially disabled', () => {
        expect(submitButton.disabled).toBe(true)
        expect(monthSelect.disabled).toBe(true)
        expect(daySelect.disabled).toBe(true)

        expect(yearSelect.disabled).toBe(false)
        expect(yearSelect.value).toBe('')
    })

    it('Sets correct values and enables selects and submit button', () => {
        setDate(document.body, 2022, 1, 31)
        expect(submitButton.disabled).toBe(false)
        expect(monthSelect.disabled).toBe(false)
        expect(daySelect.disabled).toBe(false)

        expect(yearSelect.value).toBe('2022')
        expect(monthSelect.value).toBe('1')
        expect(daySelect.value).toBe('31')
    })

    it('Hides impossible day options', () => {
        setDate(document.body, 2022, 2, 20)

        // The 28th day should be visible:
        expect(daySelect.options[28].classList.contains('hidden')).toBe(false)

        // Subsequent days should not be visible
        expect(daySelect.options[29].classList.contains('hidden')).toBe(true)
        expect(daySelect.options[30].classList.contains('hidden')).toBe(true)
        expect(daySelect.options[31].classList.contains('hidden')).toBe(true)
    })

    it('Shows 29 days in February when there is a leap year', () => {
        setDate(document.body, 2020, 2, 1)

        expect(daySelect.options[29].classList.contains('hidden')).toBe(false)
        expect(daySelect.options[30].classList.contains('hidden')).toBe(true)
        expect(daySelect.options[31].classList.contains('hidden')).toBe(true)
    })
})
