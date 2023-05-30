import { clearCreateListForm, syncReadingLogDropdownRemoveWithPrimaryButton } from '../../../openlibrary/plugins/openlibrary/js/lists/index.js';
import { listCreationForm, readingLogDropperForm } from './html-test-data';

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

describe('syncReadingLogDropdownRemoveWithPrimaryButton', () => {
    test('displays remove-from-shelf button only if book is on a shelf', () => {
        // Setup
        document.body.innerHTML = readingLogDropperForm
        const dropper = document.querySelector('#dropper');
        const readingLogForm = document.querySelector('.readingLog')

        // Add "remove" to the action to simulate a book on the shelf
        document.querySelector('[name=action]').value = 'remove'

        // Test
        syncReadingLogDropdownRemoveWithPrimaryButton(dropper, readingLogForm);

        // Verify
        const removalButton = dropper.querySelector('#remove-from-list button');
        expect(removalButton.classList.contains('hidden')).toBe(false);

        // Teardown
        document.body.innerHTML = '';
    });

    test('hides remove-from-shelf button if book is not on a shelf', () => {
        // Setup
        document.body.innerHTML = readingLogDropperForm
        const dropper = document.querySelector('#dropper');
        const readingLogForm = document.querySelector('.readingLog')

        // Add "add" to the action to simulate a book off the shelf
        document.querySelector('[name=action]').value = 'add'

        // Test
        syncReadingLogDropdownRemoveWithPrimaryButton(dropper, readingLogForm);

        // Verify
        const removalButton = dropper.querySelector('#remove-from-list button');
        expect(removalButton.classList.contains('hidden')).toBe(true);

        // Teardown
        document.body.innerHTML = '';
    });

    test('syncs bookshelf_id in remove-from-list form with primaryButton', () => {
        // Setup
        document.body.innerHTML = readingLogDropperForm
        const dropper = document.querySelector('#dropper');
        const readingLogForm = document.querySelector('.readingLog')

        // Sync the shelf for removal.
        document.querySelector('[name=bookshelf_id]').value = '2'

        // Test
        syncReadingLogDropdownRemoveWithPrimaryButton(dropper, readingLogForm);

        // Verify
        const removalForm = dropper.querySelector('#remove-from-list')
        const bookshelfIdInput = removalForm.querySelector('[name=bookshelf_id]');
        expect(bookshelfIdInput.value).toBe('2');

        // Teardown
        document.body.innerHTML = '';
    });
});
