import jquery from 'jquery';
import { more, less } from '../../../openlibrary/plugins/openlibrary/js/search.js';

/** Creates a dummy HTML document with a list of 'facetEntry' element and a
 * 'facetMoreLess' section.
 */
function setDocument(totalFacet = 2, visibleFacet = 2, minVisibleFacet = 2) {
    document.body.innerHTML = `
        <div id="searchFacets" data-config="">
            <div class="facet test">
                <h4 class="facetHead">Facet Label</h4>
            </div>
        </div>
    `

    const divTestFacet = document.querySelector('div.test');
    for (let i = 0; i < totalFacet; i++) {
        let facetNb = i + 1;
        divTestFacet.innerHTML += `
            <div class="facetEntry">
                <span><a>facet_${facetNb}</a></span>
            </div>
        `;
        if (i >= visibleFacet) {
            divTestFacet.lastElementChild.classList.add('ui-helper-hidden');
        }
    }

    divTestFacet.innerHTML += `
        <div class="facetMoreLess">
            <span class="header_more small" data-header="test">
                <a id="test_more">more</a>
            </span>
            <span id="test_bull" class="header_bull">&bull;</span>
            <span class="header_less small" data-header="test">
                <a id="test_less">less</a>
            </span>
        </div>
    `;

    if (visibleFacet == minVisibleFacet) {
        document.getElementById('test_bull').style.display = 'none';
        document.getElementById('test_less').style.display = 'none';
    }
    if (visibleFacet == totalFacet) {
        document.getElementById('test_more').style.display = 'none';
        document.getElementById('test_bull').style.display = 'none';
    }
}

/** Runs visibility tests for all 'facetEntry' elements in document.
 *
 * @param {Number} totalFacet           total number of facet
 * @param {Number} expectedVisibleFacet expected number of visible facet
 */
function checkFacetVisibility(totalFacet, expectedVisibleFacet) {
    const facetEntryList = document.getElementsByClassName('facetEntry');

    test('facetEntry element number', () => {
        expect(facetEntryList).toHaveLength(totalFacet);
    });

    for (let i = 0; i < totalFacet; i++) {
        if (i < expectedVisibleFacet) {
            test(`element "facet_${i+1}" displayed`, () => {
                expect(facetEntryList[i].classList.contains('ui-helper-hidden')).toBe(false);
            });
        } else {
            test(`element "facet_${i+1}" hidden`, () => {
                expect(facetEntryList[i].classList.contains('ui-helper-hidden')).toBe(true);
            });
        }
    }
}

/** Runs visibility tests for 'less', 'bull' and 'more' elements in document
 *
 * @param {Number} totalFacet           total number of facet
 * @param {Number} minVisibleFacet      minimum visible facet number
 * @param {Number} expectedVisibleFacet expected number of visible facet
 */
function checkFacetMoreLessVisibility(totalFacet, minVisibleFacet, expectedVisibleFacet) {
    if (expectedVisibleFacet <= minVisibleFacet) {
        test('element "test_more"', () => {
            expect(document.getElementById('test_more').style.display).not.toBe('none');
        });
        test('element "test_bull"', () => {
            expect(document.getElementById('test_bull').style.display).toBe('none');
        });
        test('element "test_less"', () => {
            expect(document.getElementById('test_less').style.display).toBe('none');
        });
    } else if (expectedVisibleFacet >= totalFacet) {
        test('element "test_more"', () => {
            expect(document.getElementById('test_more').style.display).toBe('none');
        });
        test('element "test_bull"', () => {
            expect(document.getElementById('test_bull').style.display).toBe('none');
        });
        test('element "test_less"', () => {
            expect(document.getElementById('test_less').style.display).not.toBe('none');
        });
    } else {
        test('element "test_more"', () => {
            expect(document.getElementById('test_more').style.display).not.toBe('none');
        });
        test('element "test_bull"', () => {
            expect(document.getElementById('test_bull').style.display).not.toBe('none');
        });
        test('element "test_less"', () => {
            expect(document.getElementById('test_less').style.display).not.toBe('none');
        });
    }
}

beforeAll(() => {
    global.$ = jquery;

    // Replace getClientRects to enable jQuery ':hidden' selector used by 'more' and 'less' functions
    window.Element.prototype.getClientRects = function() {
        let node = this;
        while (node) {
            if (node === document) {
                break;
            }
            if (!node.style || node.style.display === 'none' || node.style.visibility === 'hidden' || node.classList.contains('ui-helper-hidden')) {
                return [];
            }
            node = node.parentNode;
        }
        return [{width: 1, height: 1}];
    };
});

describe.each`
    totalFacet | minVisibleFacet | facetInc | visibleFacet | expectedVisibleFacet
    ${7}       | ${2}            | ${3}     | ${2}         | ${5}
    ${9}       | ${2}            | ${3}     | ${5}         | ${8}
    ${7}       | ${2}            | ${3}     | ${5}         | ${7}
    ${7}       | ${2}            | ${3}     | ${7}         | ${7}
`('more', ({totalFacet, minVisibleFacet, facetInc, visibleFacet, expectedVisibleFacet}) => {
    beforeAll(() => {
        setDocument(totalFacet, visibleFacet, minVisibleFacet);
        more('test', minVisibleFacet, facetInc);
    });

    checkFacetVisibility(totalFacet, expectedVisibleFacet);
    checkFacetMoreLessVisibility(totalFacet, minVisibleFacet, expectedVisibleFacet);
});

describe.each`
    totalFacet | minVisibleFacet | facetInc | visibleFacet | expectedVisibleFacet
    ${5}       | ${2}            | ${3}     | ${2}         | ${2}
    ${7}       | ${2}            | ${3}     | ${5}         | ${2}
    ${9}       | ${2}            | ${3}     | ${8}         | ${5}
    ${7}       | ${2}            | ${3}     | ${7}         | ${5}
`('less', ({totalFacet, minVisibleFacet, facetInc, visibleFacet, expectedVisibleFacet}) => {
    beforeAll(() => {
        setDocument(totalFacet, visibleFacet, minVisibleFacet);
        less('test', minVisibleFacet, facetInc);
    });

    checkFacetVisibility(totalFacet, expectedVisibleFacet);
    checkFacetMoreLessVisibility(totalFacet, minVisibleFacet, expectedVisibleFacet);
});
