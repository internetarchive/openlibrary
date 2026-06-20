import { childlessElem, multiChildElem, elemWithDescendants } from './sample-html/utils-test-data';
import { removeChildren, queueAction } from '../../../openlibrary/plugins/openlibrary/js/utils';

describe('`removeChildren()` tests', () => {
    it('changes nothing if element has no children', () => {
        document.body.innerHTML = childlessElem;
        const elem = document.querySelector('.remove-tests');
        const clonedElem = elem.cloneNode(true);

        // Initial checks
        expect(elem.childElementCount).toBe(0);
        expect(elem.isEqualNode(clonedElem)).toBe(true);

        // Element should be unchanged after function call
        removeChildren(elem);
        expect(elem.childElementCount).toBe(0);
        expect(elem.isEqualNode(clonedElem)).toBe(true);
    });

    it('removes all of an element\'s children', () => {
        document.body.innerHTML = multiChildElem;
        const elem = document.querySelector('.remove-tests');
        const clonedElem = elem.cloneNode(true);

        // Initial checks
        expect(elem.childElementCount).toBe(2);
        expect(elem.isEqualNode(clonedElem)).toBe(true);

        // After removing children
        removeChildren(elem);
        expect(elem.childElementCount).toBe(0);
        expect(elem.isEqualNode(clonedElem)).toBe(false);
    });

    it('removes children if they have children of their own', () => {
        document.body.innerHTML = elemWithDescendants;
        const elem = document.querySelector('.remove-tests');
        const clonedElem = elem.cloneNode(true);

        // Inital checks
        expect(elem.childElementCount).toBe(1);
        expect(elem.children[0].childElementCount).toBe(1);
        expect(elem.isEqualNode(clonedElem)).toBe(true);

        // After removing children
        removeChildren(elem);
        expect(elem.childElementCount).toBe(0);
        expect(elem.isEqualNode(clonedElem)).toBe(false);
    });

    it('handles multiple parameters correctly', () => {
        document.body.innerHTML = elemWithDescendants + multiChildElem;
        const elems = document.querySelectorAll('.remove-tests');

        // Initial checks:
        expect(elems.length).toBe(2);
        expect(elems[0].childElementCount).toBe(1);
        expect(elems[1].childElementCount).toBe(2);

        // After removing children:
        removeChildren(...elems);
        expect(elems[0].childElementCount).toBe(0);
        expect(elems[1].childElementCount).toBe(0);
    });
});

describe('`queueAction()` tests', () => {
    let originalCookie;

    beforeAll(() => {
        originalCookie = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie') ||
                     Object.getOwnPropertyDescriptor(HTMLDocument.prototype, 'cookie');
    });

    beforeEach(() => {
        Object.defineProperty(document, 'cookie', {
            value: '',
            writable: true,
            configurable: true,
        });
    });

    afterAll(() => {
        if (originalCookie) {
            Object.defineProperty(document, 'cookie', originalCookie);
        }
    });

    it('sets the pending_action cookie with all provided parameters', () => {
        queueAction('borrow', 'The Great Gatsby', '/books/OL12345W', 'book');

        const expectedData = {
            name: 'The Great Gatsby',
            url: '/books/OL12345W',
            action: 'borrow',
            type: 'book'
        };

        const expectedCookieValue = encodeURIComponent(JSON.stringify(expectedData));
        const expectedCookieString = `pending_action=${expectedCookieValue}; path=/; max-age=129600; samesite=lax`;

        expect(document.cookie).toBe(expectedCookieString);
    });

    it('falls back to "item" for itemType if not provided', () => {
        queueAction('read', '1984', '/books/OL98765W');

        const expectedData = {
            name: '1984',
            url: '/books/OL98765W',
            action: 'read',
            type: 'item'
        };

        const expectedCookieValue = encodeURIComponent(JSON.stringify(expectedData));
        const expectedCookieString = `pending_action=${expectedCookieValue}; path=/; max-age=129600; samesite=lax`;

        expect(document.cookie).toBe(expectedCookieString);
    });

    it('correctly URL encodes special characters in the payload', () => {
        queueAction('save', 'A book & a movie?', '/path?param=1');

        const expectedData = {
            name: 'A book & a movie?',
            url: '/path?param=1',
            action: 'save',
            type: 'item'
        };

        const cookieAssignment = document.cookie;
        const cookieValueString = cookieAssignment.split(';')[0].replace('pending_action=', '');
        const decodedData = JSON.parse(decodeURIComponent(cookieValueString));

        expect(decodedData).toEqual(expectedData);
    });
});
