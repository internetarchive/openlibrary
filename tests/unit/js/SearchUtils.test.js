import sinon from 'sinon';
import * as SearchUtils from '../../../openlibrary/plugins/openlibrary/js/SearchUtils';

describe('PersistentValue', () => {
    const PV = SearchUtils.PersistentValue;
    afterEach(() => {
        sessionStorage.clear();
        localStorage.clear();
    });

    test('Saves to sessionStorage', () => {
        const pv = new PV('foo');
        pv.write('bar');
        expect(sessionStorage.getItem('foo')).toBe('bar');
    });

    test('Reads from sessionStorage', () => {
        sessionStorage.setItem('foo', 'bar');
        const pv = new PV('foo');
        expect(pv.read()).toBe('bar');
    });

    test('Writes default on init', () => {
        const pv = new PV('foo', { default: 'blue' });
        expect(pv.read()).toBe('blue');
    });

    test('Does not writes default on init if already set', () => {
        sessionStorage.setItem('foo', 'green');
        const pv = new PV('foo', { default: 'blue' });
        expect(pv.read()).toBe('green');
    });

    test('Writes default on invalid init', () => {
        sessionStorage.setItem('foo', 'anything');
        const pv = new PV('foo', {
            default: 'blue',
            initValidation: () => false
        });
        expect(pv.read()).toBe('blue');
    });

    test('Writes null on invalid init', () => {
        sessionStorage.setItem('foo', 'anything');
        const pv = new PV('foo', {
            initValidation: () => false
        });
        expect(pv.read()).toBe(null);
    });

    test('Does not writes default on valid init', () => {
        sessionStorage.setItem('foo', 'anything');
        const pv = new PV('foo', {
            default: 'blue',
            initValidation: () => true
        });
        expect(pv.read()).toBe('anything');
    });

    test('Writing applies transformation', () => {
        sessionStorage.setItem('foo', 'blue');
        const pv = new PV('foo', {
            writeTransformation: (newVal, oldVal) => oldVal + newVal
        });
        pv.write('green');
        expect(pv.read()).toBe('bluegreen');
    });

    test('Writing removes when null', () => {
        const pv = new PV('foo');
        pv.write(null);
        expect(pv.read()).toBe(null);
    });

    test('Writing triggers on change', () => {
        const pv = new PV('foo');
        pv.write('a');
        const spy = sinon.spy();
        pv.sync(spy, false);
        pv.write('b');
        expect(spy.callCount).toBe(1);
        expect(spy.args[0]).toEqual(['b']);
    });

    test('Writing does not trigger when same', () => {
        const pv = new PV('foo');
        pv.write('a');
        const spy = sinon.spy();
        pv.sync(spy, false);
        pv.write('a');
        expect(spy.callCount).toBe(0);
    });

    test('Change fires automatically if so specified', () => {
        const pv = new PV('foo');
        pv.write('a');
        const spy = sinon.spy();
        pv.sync(spy, true);
        expect(spy.callCount).toBe(1);
        expect(spy.args[0]).toEqual(['a']);
    });
});
