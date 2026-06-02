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
            subject: [],
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
            subject: [],
        });
    });

    test('getSelectedItems adds new selected item types to stored sessions', () => {
        sessionStorage.setItem('ile-items', JSON.stringify({
            work: ['OL1W'],
            edition: [],
            author: [],
        }));
        const sm = new SelectionManager(null, '/search');
        sm.getSelectedItems();
        expect(sm.selectedItems).toEqual({
            work: ['OL1W'],
            edition: [],
            author: [],
            subject: [],
        });
    });

    test('getOlidsFromSelectionList preserves subject identifiers', () => {
        const sm = new SelectionManager(null, '/search/subjects');
        expect(sm.getOlidsFromSelectionList(['history', 'person:tolkien', 'OL1W:OL2M'])).toEqual(['history', 'person:tolkien', 'OL1W']);
    });

    test('subject search provider extracts subject id from data attribute', () => {
        const sm = new SelectionManager(null, '/search/subjects');
        const listItem = document.createElement('li');
        listItem.classList.add('searchResultItem');
        listItem.dataset.subjectId = 'place:new_york';

        const provider = sm.getProvider(listItem);

        expect(provider.type).toEqual(['subject']);
        expect(provider.data(listItem)).toBe('place:new_york');
    });

    test('processClick selects subject search item', () => {
        const sm = new SelectionManager(null, '/search/subjects');
        sm.ile = { $statusImages: { append: jest.fn() } };
        sm.selectedItems = {
            work: [],
            edition: [],
            author: [],
            subject: [],
        };
        sm.updateToolbar = jest.fn();
        const listItem = document.createElement('li');
        listItem.classList.add('searchResultItem', 'ile-selectable');
        listItem.dataset.subjectId = 'history';

        listItem.addEventListener('click', () => {
            sm.processClick({ target: listItem, currentTarget: listItem });
        });
        listItem.click();

        expect(listItem.classList.contains('ile-selected')).toBe(true);
        expect(sm.selectedItems.subject).toEqual(['history']);
        expect(sm.updateToolbar).toHaveBeenCalled();
    });

    test('Merge Subjects action builds subject merge URL', () => {
        const action = SelectionManager.ACTIONS.find(action => action.name === 'Merge Subjects...');

        expect(action.href(['history', 'person:tolkien'])).toBe('/subjects/merge?records=history,person:tolkien');
    });

    test('updateToolbar adds Merge Subjects action for multiple selected subjects', () => {
        const appendedActions = [];
        const sm = new SelectionManager(null, '/search/subjects');
        sm.selectedItems = {
            work: [],
            edition: [],
            author: [],
            subject: ['history', 'person:tolkien'],
        };
        sm.ile = {
            $actions: {
                empty: jest.fn(),
                append: jest.fn(action => appendedActions.push(action)),
            },
            $selectionActions: {
                empty: jest.fn(),
                append: jest.fn(),
            },
            bulkTagger: {
                hideTaggingMenu: jest.fn(),
            },
            setStatusText: jest.fn(),
        };

        sm.updateToolbar();

        const mergeAction = appendedActions.find(action => action.text() === 'Merge Subjects...');
        expect(sm.ile.setStatusText).toHaveBeenCalledWith('2 subjects selected');
        expect(mergeAction.attr('href')).toBe('/subjects/merge?records=history,person:tolkien');
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

        jest.clearAllMocks();
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

        jest.clearAllMocks();
    });
});
