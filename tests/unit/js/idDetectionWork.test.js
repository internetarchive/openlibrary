import {
    detectTypeFromWorkId
} from '../../../openlibrary/plugins/openlibrary/js/idDetection.js';

const validWorkData = [
    {
        id: 'Q53828903',
        type: 'wikidata',
        comment: '',
    },
    {
        id: 'ba4d2cfd-4ed5-4b59-a1d5-0aaebbef005f',
        type: 'storygraph',
        comment: '',
    },
];

const invalidWorkData = [
    {
        id: 'Q5',
        comment: 'a valid wikidata id but too short/generic to match'
    },
    {
        id: '5976042',
        comment: 'a valid librarything work, but too generic to match'
    },
];

describe('detectTypeFromWorkId', () => {
    for (let i = 0; i < validWorkData.length; i += 1) {
        const testcase = validWorkData[i];
        it(`detect ${testcase.id} as ${testcase.type} ${testcase.comment}`, () => {
            expect(detectTypeFromWorkId(testcase.id)).toBe(testcase.type);
        });
    }
    for (let i = 0; i < invalidWorkData.length; i += 1) {
        const testcase = invalidWorkData[i];
        it(`not detect ${testcase.id} as a known id type ${testcase.comment}`, () => {
            expect(detectTypeFromWorkId(testcase.id)).toBe(null);
        });
    }
})
