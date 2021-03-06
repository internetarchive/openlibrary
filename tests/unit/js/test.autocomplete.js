import { highlight, mapApiResultsToAutocompleteSuggestions } from '../../../openlibrary/plugins/openlibrary/js/autocomplete.js';

const sinon = require('sinon');
const jquery = require('jquery');
let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    sandbox.stub(global, '$').callsFake(jquery);
});

describe('highlight', () => {

    test('Highlights terms with strong tag', () => {
        [
            [
                'Jon Robson',
                'Jon',
                '<strong>Jon</strong> Robson'
            ],
            [
                'No match',
                'abcde',
                'No match'
            ]
        ].forEach((test) => {
            const highlightedText = highlight(test[0], test[1]);
            expect(highlightedText).toStrictEqual(test[2]);
        });
    })
});


describe('mapApiResultsToAutocompleteSuggestions', () => {
    test('API results are converted to suggestions using label function', () => {
        const suggestions = mapApiResultsToAutocompleteSuggestions(
            [
                {
                    key: 1,
                    name: 'Test'
                }
            ],
            (r) => r.name
        );

        expect(suggestions).toStrictEqual([
            {
                key: 1,
                label: 'Test',
                value: 'Test'
            }
        ]);
    });

    test('Add new item field can be added', () => {
        const suggestions = mapApiResultsToAutocompleteSuggestions(
            [
                {
                    key: 1,
                    name: 'Test'
                }
            ],
            (r) => r.name,
            'Add new item'
        );

        expect(suggestions[1]).toStrictEqual(
            {
                key: '__new__',
                label: 'Add new item',
                value: 'Add new item'
            }
        );
    })
});
