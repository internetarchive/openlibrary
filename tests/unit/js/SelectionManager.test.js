import SelectionManager from '../../../openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.js';

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
    sm.ile = { $statusImages: { append: jest.fn() } };
    sm.selectedItems = { work: [] };
    sm.updateToolbar = jest.fn();
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

        listItem.addEventListener('click', sm.processClick);

        expect(listItem.classList.contains('ile-selected')).toBe(false);
        link.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);

        jest.clearAllMocks();
    });

    test('processClick - clicking on listItem', () => {
        const sm = setupSelectionManager();
        const { listItem } = createTestElementsForProcessClick();

        listItem.addEventListener('click', sm.processClick);

        expect(listItem.classList.contains('ile-selected')).toBe(false);
        listItem.click();
        expect(listItem.classList.contains('ile-selected')).toBe(true);
        listItem.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);

        jest.clearAllMocks();
    });

    test('processClick - clicking a button inside a web component', () => {
        const sm = setupSelectionManager();
        const { listItem } = createTestElementsForProcessClick();

        // The button lives in a shadow root, so the row sees the host as the target.
        const host = document.createElement('ol-shelf-button');
        const button = document.createElement('button');
        host.attachShadow({ mode: 'open' }).appendChild(button);
        listItem.appendChild(host);
        listItem.addEventListener('click', sm.processClick);

        button.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);
        host.click();
        expect(listItem.classList.contains('ile-selected')).toBe(true);

        jest.clearAllMocks();
    });
});
