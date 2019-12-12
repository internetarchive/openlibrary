import { getWorksAndEditionsFromElements } from '../../../openlibrary/plugins/openlibrary/js/availability';

const sinon = require('sinon');
const jquery = require('jquery');
let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    sandbox.stub(global, '$').callsFake(jquery);
});

describe('getWorksAndEditionsFromElements', () => {

    test('URL with multiple occurences of param', () => {
        [
            [
                $('<a href="/works/OL15095146W?edition=best"></a>'),
                {
                    works: [ 'OL15095146W' ],
                    editions: []
                }
            ],
            [
                $('<a href="/books/OL15095146W"></a>'),
                {
                    works: [],
                    editions: ['OL15095146W']
                }
            ]
        ].forEach((test) => {
            const worksAndEditions = getWorksAndEditionsFromElements(test[0]);
            expect(worksAndEditions).toStrictEqual(test[1]);
        });
    })
});
