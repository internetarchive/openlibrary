import SelectionManager from '../../../openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.js';


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

    test('processClick - clicking on ctaDiv', () => {
        const sm = setupSelectionManager();
        const { listItem, ctaDiv } = createTestElementsForToggleSelected();

        ctaDiv.addEventListener('click', () => {
            sm.processClick({ target: ctaDiv, currentTarget: listItem });
        });

        expect(listItem.classList.contains('ile-selected')).toBe(false);
        ctaDiv.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);
        ctaDiv.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);

        jest.clearAllMocks();
    });

    test('processClick - clicking on listItem', () => {
        const sm = setupSelectionManager();
        const { listItem } = createTestElementsForToggleSelected();

        listItem.addEventListener('click', () => {
            sm.processClick({ target: listItem, currentTarget: listItem });
        });

        expect(listItem.classList.contains('ile-selected')).toBe(false);
        listItem.click();
        expect(listItem.classList.contains('ile-selected')).toBe(true);
        listItem.click();
        expect(listItem.classList.contains('ile-selected')).toBe(false);

        jest.clearAllMocks();
    });
});
