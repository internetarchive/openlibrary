const sinon = require('sinon');
const jquery = require('jquery');
const { urlencode, Subject,
    renderTag, slice } = require('../../../openlibrary/plugins/openlibrary/js/subjects');
let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    sandbox.stub(global, '$').callsFake(jquery);
});

describe('urlencode', () => {
    test('empty array', () => {
        expect(urlencode([])).toEqual('');
    });
    test('array of 1', () => {
        expect(urlencode(['apple'])).toEqual('0=apple');
    });
    test('array of 3', () => {
        expect(urlencode(['apple', 'grapes', 'orange'])).toEqual('0=apple&1=grapes&2=orange');
    });
});

describe('renderTag', () => {
    test('empty tag', () => {
        expect(renderTag('', {id: 'hello'}, '')).toEqual('< id="hello" ></>');
    });
    test('center tag', () => {
        expect(renderTag('center', {id: 'hello'}, '')).toEqual('<center id="hello" ></center>');
    });
    test('img tag', () => {
        expect(renderTag('img', {id: 'hello'}, '')).toEqual('<img id="hello" />');
    });
    test('img tag without no key values', () => {
        expect(renderTag('img', {}, '')).toEqual('<img />');
    });
    test('img tag with multiple key values', () => {
        expect(renderTag('img', {id: 'hello', class: 'bye'}, '')).toEqual('<img id="hello" class="bye" />');
    });
    test('img tag with key values and one child', () => {
        expect(renderTag('img', {id: 'hello', class: 'bye'}, 'child')).toEqual('<img id="hello" class="bye" />');
    });
});

describe('slice', () => {
    test('empty array', () => {
        expect(slice([], 0, 0)).toEqual([]);
    });
    test('array of 2', () => {
        expect(slice([1, 2], 0, 1)).toEqual([1]);
    });
    test('arr length less than end', () => {
        expect(slice([1, 2, 3], 0, 5)).toEqual([1, 2, 3]);
    });
    test('beginning greater than end', () => {
        expect(slice([1, 2, 3, 4, 5], 4, 3)).toEqual([]);
    });
    test('array of 5', () => {
        expect(slice([1, 2, 3, 4, 5], 0, 3)).toEqual([1, 2, 3]);
    });
});


describe('Subject', () => {
    test('constructor (not readable)', () => {
        const data = { name: 'Harry Potter', works: [] },
            subject = new Subject(data, {});
        expect(subject._pages[0]).toBeDefined();
    });
    test('constructor (readable)', () => {
        const data = { name: 'Harry Potter', works: [] },
            subject = new Subject(data, { readable: true });
        expect(subject._pages[0]).toBeUndefined();
    });
});
