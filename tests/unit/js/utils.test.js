import { childlessElem, multiChildElem, elemWithDescendants } from './sample-html/utils-test-data';
import { removeChildren } from '../../../openlibrary/plugins/openlibrary/js/utils';

describe('`removeChildren()` tests', () => {
    it('changes nothing if element has no children', () => {
        document.body.innerHTML = childlessElem
        const elem = document.querySelector('.remove-tests')
        const clonedElem = elem.cloneNode(true)

        // Initial checks
        expect(elem.childElementCount).toBe(0)
        expect(elem.isEqualNode(clonedElem)).toBe(true)

        // Element should be unchanged after function call
        removeChildren(elem)
        expect(elem.childElementCount).toBe(0)
        expect(elem.isEqualNode(clonedElem)).toBe(true)
    })

    it('removes all of an element\'s children', () => {
        document.body.innerHTML = multiChildElem
        const elem = document.querySelector('.remove-tests')
        const clonedElem = elem.cloneNode(true)

        // Initial checks
        expect(elem.childElementCount).toBe(2)
        expect(elem.isEqualNode(clonedElem)).toBe(true)

        // After removing children
        removeChildren(elem)
        expect(elem.childElementCount).toBe(0)
        expect(elem.isEqualNode(clonedElem)).toBe(false)
    })

    it('removes children if they have children of their own', () => {
        document.body.innerHTML = elemWithDescendants
        const elem = document.querySelector('.remove-tests')
        const clonedElem = elem.cloneNode(true)

        // Inital checks
        expect(elem.childElementCount).toBe(1)
        expect(elem.children[0].childElementCount).toBe(1)
        expect(elem.isEqualNode(clonedElem)).toBe(true)

        // After removing children
        removeChildren(elem)
        expect(elem.childElementCount).toBe(0)
        expect(elem.isEqualNode(clonedElem)).toBe(false)
    })

    it('handles multiple parameters correctly', () => {
        document.body.innerHTML = elemWithDescendants + multiChildElem
        const elems = document.querySelectorAll('.remove-tests')

        // Initial checks:
        expect(elems.length).toBe(2)
        expect(elems[0].childElementCount).toBe(1)
        expect(elems[1].childElementCount).toBe(2)

        // After removing children:
        removeChildren(...elems)
        expect(elems[0].childElementCount).toBe(0)
        expect(elems[1].childElementCount).toBe(0)
    })
})
