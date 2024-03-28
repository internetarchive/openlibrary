import {
    extractWorkIdFromUrl,
} from '../../../openlibrary/plugins/openlibrary/js/idExtraction.js';

const validWorkData = [
    {
        desc: 'wikidata url',
        url: 'https://www.wikidata.org/wiki/Q42',
        type: 'wikidata',
        id: 'Q42',
    },
    {
        desc: 'viaf url with #',
        url: 'https://viaf.org/viaf/113230702/#Adams,_Douglas,_1952-2001.',
        type: 'viaf',
        id: '113230702',
    },
    {
        desc: 'viaf url with /',
        url: 'https://viaf.org/viaf/113230702/',
        type: 'viaf',
        id: '113230702',
    },
    {
        desc: 'viaf url without /',
        url: 'https://viaf.org/viaf/113230702',
        type: 'viaf',
        id: '113230702',
    },
    {
        desc: 'storygraph work',
        url: 'https://app.thestorygraph.com/books/1df3abd0-184c-4016-8fe7-8e22d7fcb265',
        type: 'storygraph',
        id: '1df3abd0-184c-4016-8fe7-8e22d7fcb265',
    },
    {
        desc: 'goodreads work',
        url: 'https://www.goodreads.com/work/editions/54031496-rotherweird',
        type: 'goodreads',
        id: '54031496',
    },
    {
        desc: 'librarything work',
        url: 'https://www.librarything.com/work/12241832',
        type: 'librarything',
        id: '12241832',
    },
];

const invalidWorkData = [
    {
        desc: 'storygraph author',
        url: 'https://app.thestorygraph.com/authors/79e1fcbf-ab67-4e33-a8bd-9ecf3caf5a9c',
        comment: 'not a work so should return null',
    },
    {
        desc: 'goodreads edition',
        url: 'https://www.goodreads.com/en/book/show/33299154',
        comment: 'not a work so should return null',
    },
    {
        desc: 'random string',
        url: 'Anything random',
        comment: 'not a url so should return null',
    },
    {
        desc: 'goodreads author',
        url: 'https://www.goodreads.com/author/show/16616431.Andrew_Caldecott',
        comment: 'not a work so should return null',
    },
    {
        desc: 'librarything author',
        url: 'https://www.librarything.com/author/faganjenni',
        comment: 'not a work so should return null',
    },
];

describe('extractWorkIdFromUrl', () => {
    for (let i = 0; i < validWorkData.length; i += 1) {
        const testcase = validWorkData[i];
        it(`parse ${testcase.desc} e.g. ${testcase.url}`, () => {
            expect(extractWorkIdFromUrl(testcase.url)).toStrictEqual([testcase.id, testcase.type]);
        });
    }
    for (let i = 0; i < invalidWorkData.length; i += 1) {
        const testcase = invalidWorkData[i];
        it(`reject ${testcase.desc} e.g. ${testcase.url}`, () => {
            expect(extractWorkIdFromUrl(testcase.url)).toStrictEqual([null, null]);
        });
    }
})
