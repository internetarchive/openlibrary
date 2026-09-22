import SelectionManager from '../../../openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.js';
import { IntegratedLibrarianEnvironment } from '../../../openlibrary/plugins/openlibrary/js/ile/index.js';

function createTestElementsForProcessClick() {
    const listItem = document.createElement('li');
    listItem.classList.add('searchResultItem', 'ile-selectable');

    const link = document.createElement('a');
    listItem.appendChild(link);

    const bookTitle = document.createElement('div');
    bookTitle.classList.add('booktitle');
    const bookLink = document.createElement('a');
    bookLink.href = 'OL12345W'; // Mock href value
    bookTitle.appendChild(bookLink);

    listItem.appendChild(bookTitle);

    return {listItem, link};
}

function setupSelectionManager() {
    const sm = new SelectionManager(null, '/search');
    sm.ile = { $statusImages: { append: vi.fn() } };
    sm.selectedItems = { work: [] };
    sm.updateToolbar = vi.fn();
    return sm;
}

describe('SelectionManager', () => {
    afterEach(() => {
        window.sessionStorage.clear();
    });

    test('getSelectedItems initializes selected item types', () => {
        const sm = new SelectionManager(null, '/search');
        sm.getSelectedItems();
        expect(sm.selectedItems).toEqual({
            work: [],
            edition: [],
            author: [],
        });
    });

    test('addSelectedItem', () => {
        const sm = new SelectionManager(null, '/search');
        sm.getSelectedItems(); // to initialize types for push to work
        sm.addSelectedItem('OL1W');
        expect(sm.selectedItems).toEqual({
            work: ['OL1W'],
            edition: [],
            author: [],
        });
    });


    test('processClick - clicking on a link or button', () => {
        const sm = setupSelectionManager();
        const { listItem, link } = createTestElementsForProcessClick();

        link.addEventListener('click', () => {
            sm.processClick({ target: link, currentTarget: listItem });
        });

        expect(listItem.classList.contains('ile-selected')).toBe(false);
        link.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);

        vi.clearAllMocks();
    });

    test('processClick - clicking on listItem', () => {
        const sm = setupSelectionManager();
        const { listItem } = createTestElementsForProcessClick();

        listItem.addEventListener('click', () => {
            sm.processClick({ target: listItem, currentTarget: listItem });
        });

        expect(listItem.classList.contains('ile-selected')).toBe(false);
        listItem.click();
        expect(listItem.classList.contains('ile-selected')).toBe(true);
        listItem.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);

        vi.clearAllMocks();
    });
});

/**
 * Selecting an element sets `draggable` and binds drag listeners as well as
 * adding the class, so clearing has to undo all three. When it only dropped
 * the class, the link stayed draggable and the browser kept starting a native
 * drag on it -- which is why an author's name could not be selected as text
 * after "Clear Selections".
 */
describe('IntegratedLibrarianEnvironment.reset', () => {
    /** @returns {HTMLAnchorElement} an author link, in the document so $() finds it */
    function createAuthorLink() {
        const link = document.createElement('a');
        link.href = '/authors/OL1A';
        link.textContent = 'Some Author';
        document.body.appendChild(link);
        return link;
    }

    afterEach(() => {
        document.body.innerHTML = '';
        window.sessionStorage.clear();
    });

    test('clears draggable, not just the class', () => {
        const ile = new IntegratedLibrarianEnvironment();
        const link = createAuthorLink();

        ile.selectionManager.setElementSelectionAttributes(link, true);
        expect(link.classList.contains('ile-selected')).toBe(true);
        expect(link.draggable).toBe(true);

        ile.reset();

        expect(link.classList.contains('ile-selected')).toBe(false);
        expect(link.draggable).toBe(false);
    });

    test('unbinds both drag listeners', () => {
        const ile = new IntegratedLibrarianEnvironment();
        const link = createAuthorLink();
        // Swapped in before selecting, so these are the references that get
        // bound -- and the ones reset() must pass to removeEventListener.
        ile.selectionManager.dragStart = vi.fn();
        ile.selectionManager.dragEnd = vi.fn();

        ile.selectionManager.setElementSelectionAttributes(link, true);
        ile.reset();
        link.dispatchEvent(new Event('dragstart'));
        link.dispatchEvent(new Event('dragend'));

        expect(ile.selectionManager.dragStart).not.toHaveBeenCalled();
        expect(ile.selectionManager.dragEnd).not.toHaveBeenCalled();
    });

    test('"Clear Selections" clears the drag state of every selected element', () => {
        const ile = new IntegratedLibrarianEnvironment();
        const first = createAuthorLink();
        const second = createAuthorLink();
        ile.selectionManager.getSelectedItems();

        for (const link of [first, second]) {
            ile.selectionManager.setElementSelectionAttributes(link, true);
        }
        ile.selectionManager.clearSelectedItems();

        for (const link of [first, second]) {
            expect(link.classList.contains('ile-selected')).toBe(false);
            expect(link.draggable).toBe(false);
        }
    });
});
