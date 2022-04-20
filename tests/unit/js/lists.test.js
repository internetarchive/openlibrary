import { clearCreateListForm } from '../../../openlibrary/plugins/openlibrary/js/lists/index.js';
import { listCreationForm } from './html-test-data';

describe('clearCreateListForm', () => {
    document.body.innerHTML = listCreationForm
    const listName = document.querySelector('#list_label')
    const listDesc = document.querySelector('#list_desc')

    test('Clears form when called', () => {
        expect(listName.value.length).toBeGreaterThan(0)
        expect(listDesc.value.length).toBeGreaterThan(0)
        clearCreateListForm()
        expect(listName.value.length).toBe(0)
        expect(listDesc.value.length).toBe(0)
    })
})
