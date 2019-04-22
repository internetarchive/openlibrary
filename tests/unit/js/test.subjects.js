const sinon = require('sinon');
const $ = require('../mockjQuery');
window.$ = $;
const subject = require('../../../openlibrary/plugins/openlibrary/js/subjects');

beforeEach(() => {
    window.$ = $;
});

afterEach(() => {
    window.$ = undefined;
    sinon.restore()
});

describe('subjects: urlencode', () => {
    test('empty array', () => {
        expect(subject.urlencode([])).toEqual('');
    });
    test('array of 1', () => {
        expect(subject.urlencode(['apple'])).toEqual('0=apple');
    });
    test('array of 3', () => {
        expect(subject.urlencode(['apple', 'grapes', 'orange'])).toEqual('0=apple&1=grapes&2=orange');
    });
});

describe('subjects: urlencode', () => {
    test('empty tag', () => {
        expect(subject.renderTag('', {id: "hello"}, '')).toEqual('< id="hello" ></>');
    });
    test('center tag', () => {
        expect(subject.renderTag('center', {id: "hello"}, '')).toEqual('<center id="hello" ></center>');
    });
    test('img tag', () => {
        expect(subject.renderTag('img', {id: "hello"}, '')).toEqual('<img id="hello" />');
    });
    test('img tag without no key values', () => {
        expect(subject.renderTag('img', {}, '')).toEqual('<img />');
    });
    test('img tag with multiple key values', () => {
        expect(subject.renderTag('img', {id: "hello", class: "bye"}, '')).toEqual('<img id="hello" class="bye" />');
    });
    test('img tag with key values and one child', () => {
        expect(subject.renderTag('img', {id: "hello", class: "bye"}, 'child')).toEqual('<img id="hello" class="bye" />');
    });
});

describe('subjects: slice', () => {
    test('empty array', () => {
        expect(subject.slice([], 0, 0)).toEqual([]);
    });
    test('array of 2', () => {
        expect(subject.slice([1, 2], 0, 1)).toEqual([1]);
    });
    test('arr length less than end', () => {
        expect(subject.slice([1, 2, 3], 0, 5)).toEqual([1, 2, 3]);
    });
    test('beginning greater than end', () => {
        expect(subject.slice([1, 2, 3, 4, 5], 4, 3)).toEqual([]);
    });
    test('array of 5', () => {
        expect(subject.slice([1, 2, 3, 4, 5], 0, 3)).toEqual([1, 2, 3]);
    });
});


describe('subjects: Subject', () => {
    test('trial', () => {
        let data = { name: "Harry Potter/\s+/g" };
        let options = {};
        // let stub = sinon.stub(subject.Subject, "init");
        expect(subject.Subject(data,options)).toHaveBeenCalledWith(data,options);
    });
});
