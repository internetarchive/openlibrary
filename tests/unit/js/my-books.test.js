import { listCreationForm } from './sample-html/lists-test-data'
import { CreateListForm } from '../../../openlibrary/plugins/openlibrary/js/my-books/CreateListForm'

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
