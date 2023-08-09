import { clearCreateListForm, syncReadingLogDropdownRemoveWithPrimaryButton } from '../../../openlibrary/plugins/openlibrary/js/lists/index.js';
import { createActiveShowcaseItem, ShowcaseItem } from '../../../openlibrary/plugins/openlibrary/js/lists/ShowcaseItem.js';
import { CreateListForm } from '../../../openlibrary/plugins/openlibrary/js/my-books/CreateListForm.js'

import { readingLogDropperForm } from './html-test-data';
import { listCreationForm, filledListCreationForm, showcaseI18nInput, subjectShowcase, authorShowcase, workShowcase, editionShowcase, activeListShowcase, listsSectionShowcase } from './sample-html/lists-test-data'

// Start : Legacy tests
describe('clearCreateListForm', () => {
    test('Clears form when called', () => {
        // Set up
        document.body.innerHTML = filledListCreationForm
        const listName = document.querySelector('#list_label')
        const listDesc = document.querySelector('#list_desc')

        // Form should be filled initially
        expect(listName.value.length).toBeGreaterThan(0)
        expect(listDesc.value.length).toBeGreaterThan(0)

        // Test clearing the form
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
// End : Legacy tests

describe('CreateListForm class tests', () => {
    test('CreateListForm fields correctly set', () => {
        document.body.innerHTML = listCreationForm
        const formElem = document.querySelector('form')
        const listForm = new CreateListForm(formElem)

        const createListButton = document.querySelector('#create-list-button')
        expect(listForm.createListButton === createListButton).toBe(true)

        const listTitleInput = document.querySelector('#list_label')
        expect(listForm.listTitleInput === listTitleInput).toBe(true)

        const listDescriptionInput = document.querySelector('#list_desc')
        expect(listForm.listDescriptionInput === listDescriptionInput).toBe(true)
    })

    test('`resetForm()` clears a filled form', () => {
        document.body.innerHTML = listCreationForm
        const formElem = document.querySelector('form')
        const listForm = new CreateListForm(formElem)

        // Initial checks
        expect(listForm.listTitleInput.value).not.toBeTruthy()
        expect(listForm.listDescriptionInput.value).not.toBeTruthy()

        // After setting input values
        listForm.listTitleInput.value = 'New List'
        listForm.listDescriptionInput.value = 'My new list.'
        expect(listForm.listTitleInput.value).toBeTruthy()
        expect(listForm.listDescriptionInput.value).toBeTruthy()

        // After clearing the form:
        listForm.resetForm()
        expect(listForm.listTitleInput.value).not.toBeTruthy()
        expect(listForm.listDescriptionInput.value).not.toBeTruthy()
    })

    it('should have empty inputs after instantiation', () => {
        document.body.innerHTML = filledListCreationForm
        const formElem = document.querySelector('form')
        const titleInput = formElem.querySelector('#list_label')
        const descriptionInput = formElem.querySelector('#list_desc')

        // Form is initially filled
        expect(titleInput.value).toBeTruthy()
        expect(descriptionInput.value).toBeTruthy()

        // Creating new CreateListForm should clear the form
        // eslint-disable-next-line no-unused-vars
        const listForm = new CreateListForm(formElem)
        expect(titleInput.value).not.toBeTruthy()
        expect(descriptionInput.value).not.toBeTruthy()
    })
})

describe('createActiveShowcaseItem() tests', () => {
    test('createActiveShowcaseItem() results are as expected', () => {
        document.body.innerHTML = showcaseI18nInput
        const listKey = '/people/openlibrary/lists/OL1L'
        const seedKey = '/books/OL3421846M'
        const listTitle = 'My First List'
        const coverUrl = '/images/icons/avatar_book-sm.png'

        const li = createActiveShowcaseItem(listKey, seedKey, listTitle, coverUrl)
        const anchors = li.querySelectorAll('a')
        const [imageLink, titleLink, removeLink] = anchors
        const inputs = li.querySelectorAll('input')
        const [titleInput, seedKeyInput, seedTypeInput] = inputs


        // Must have `actionable-item` class
        expect(li.classList.contains('actionable-item')).toBe(true)

        // List key has been set
        expect(removeLink.dataset.listKey === listKey).toBe(true)
        expect(imageLink.href.endsWith(listKey)).toBe(true)
        expect(titleLink.href.endsWith(listKey)).toBe(true)
        expect(removeLink.href.endsWith(listKey)).toBe(true)

        // Seed key has been set
        expect(seedKeyInput.value === seedKey).toBe(true)
        expect(seedTypeInput.value === 'edition').toBe(true)

        // List title has been set
        expect(titleLink.dataset.listTitle === listTitle).toBe(true)
        expect(titleLink.textContent === listTitle).toBe(true)
        expect(titleInput.value === listTitle).toBe(true)

        // Cover URL has been set
        expect(imageLink.children[0].src.endsWith(coverUrl)).toBe(true)
    })

    test('createActiveShowcaseItem() sets the correct seed type', () => {
        const listKey = '/people/openlibrary/lists/OL1L'
        const listTitle = 'My First List'
        const coverUrl = '/images/icons/avatar_book-sm.png'

        const editionKey = '/books/OL3421846M'
        const workKey = '/works/OL54120W'
        const authorKey = '/authors/OL18319A'
        const subjectKey = 'quotations'
        const bogusKey = '/bogus/OL38475839B'

        const editionItem = createActiveShowcaseItem(listKey, editionKey, listTitle, coverUrl)
        expect(editionItem.querySelector('input[name=seed-type]').value).toBe('edition')

        const workItem = createActiveShowcaseItem(listKey, workKey, listTitle, coverUrl)
        expect(workItem.querySelector('input[name=seed-type]').value).toBe('work')

        const authorItem = createActiveShowcaseItem(listKey, authorKey, listTitle, coverUrl)
        expect(authorItem.querySelector('input[name=seed-type]').value).toBe('author')

        const subjectItem = createActiveShowcaseItem(listKey, subjectKey, listTitle, coverUrl)
        expect(subjectItem.querySelector('input[name=seed-type]').value).toBe('subject')

        const bogusItem = createActiveShowcaseItem(listKey, bogusKey, listTitle, coverUrl)
        expect(bogusItem.querySelector('input[name=seed-type]').value).toBe('undefined')
    })

    it('sets the correct default value for `coverUrl`', () => {
        document.body.innerHTML = showcaseI18nInput
        const listKey = '/people/openlibrary/lists/OL1L'
        const seedKey = '/books/OL3421846M'
        const listTitle = 'My First List'

        const li = createActiveShowcaseItem(listKey, seedKey, listTitle)
        const coverImage = li.querySelector('img')

        const expectedCoverUrl = '/images/icons/avatar_book-sm.png'
        expect(coverImage.src.endsWith(expectedCoverUrl)).toBe(true)
    })
})

describe('ShowcaseItem class tests', () => {
    test('ShowcaseItem fields correctly set', () => {
        document.body.innerHTML = activeListShowcase
        const showcaseElem = document.querySelector('.actionable-item')
        const showcase = new ShowcaseItem(showcaseElem)
        const removeAffordance = showcaseElem.querySelector('.remove-from-list')

        expect(showcase.showcaseElem === showcaseElem).toBe(true)
        expect(showcase.isActiveShowcase).toBe(true)
        expect(showcase.removeFromListAffordance === removeAffordance).toBe(true)
        expect(showcase.listKey === '/people/openlibrary/lists/OL1L').toBe(true)
        expect(showcase.seedKey === '/works/OL54120W').toBe(true)
        expect(showcase.type).toBe('work')
        expect(showcase.seed).toMatchObject({key: '/works/OL54120W'})
    })

    it('correctly infers if it is an active showcase', () => {
        document.body.innerHTML = activeListShowcase + listsSectionShowcase
        const [activeShowcaseElem, otherShowcaseElem] = document.querySelectorAll('.actionable-item')
        const activeShowcase = new ShowcaseItem(activeShowcaseElem)
        const otherShowcase = new ShowcaseItem(otherShowcaseElem)

        expect(activeShowcase.isActiveShowcase).toBe(true)
        expect(otherShowcase.isActiveShowcase).toBe(false)
    })

    describe('Seed type inference', () => {
        const cases = [
            {markup: subjectShowcase, expectedType: 'subject', expectedIsWorkValue: false, expectedIsSubjectValue: true},
            {markup: authorShowcase, expectedType: 'author', expectedIsWorkValue: false, expectedIsSubjectValue: false},
            {markup: workShowcase, expectedType: 'work', expectedIsWorkValue: true, expectedIsSubjectValue: false},
            {markup: editionShowcase, expectedType: 'edition', expectedIsWorkValue: false, expectedIsSubjectValue: false}
        ]

        test.each(cases)('Type is $expectedType', ({markup, expectedType}) => {
            document.body.innerHTML = markup
            const showcaseElem = document.querySelector('.actionable-item')
            const showcase = new ShowcaseItem(showcaseElem)
            expect(showcase.type).toBe(expectedType)
        })

        test.each(cases)('`isWork` value expected to be $expectedIsWorkValue', ({markup, expectedIsWorkValue}) => {
            document.body.innerHTML = markup
            const showcaseElem = document.querySelector('.actionable-item')
            const showcase = new ShowcaseItem(showcaseElem)
            expect(showcase.isWork).toBe(expectedIsWorkValue)
        })

        test.each(cases)('`isSubject` value expected to be $expectedIsSubjectValue', ({markup, expectedIsSubjectValue}) => {
            document.body.innerHTML = markup
            const showcaseElem = document.querySelector('.actionable-item')
            const showcase = new ShowcaseItem(showcaseElem)
            expect(showcase.isSubject).toBe(expectedIsSubjectValue)
        })
    })

    // XXX : test : removeSelf() fails safely when myBooksStore has not been created?
})
