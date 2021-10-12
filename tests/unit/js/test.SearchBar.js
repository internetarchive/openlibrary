import sinon from 'sinon';
import { SearchBar } from '../../../openlibrary/plugins/openlibrary/js/SearchBar';
import $ from 'jquery';
import * as SearchUtils from '../../../openlibrary/plugins/openlibrary/js/SearchUtils';
import * as nonjquery_utils from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';

describe('SearchBar', () => {
    const DUMMY_COMPONENT_HTML = `
        <div>
            <form class="search-bar-input" action="https://openlibrary.org/search?q=foo">
                <input type="text">
            </form>
        </div>`;

    describe('initFromUrlParams', () => {
        let sb;
        beforeEach(() => {
            sb = new SearchBar($(DUMMY_COMPONENT_HTML));
        });
        afterEach(() => localStorage.clear());
        test('Does not throw on empty params', () => {
            sb.initFromUrlParams({});
        });

        test('Updates facet from params', () => {
            expect(sb.facet.read()).not.toBe('title');
            sb.initFromUrlParams({facet: 'title'});
            expect(sb.facet.read()).toBe('title');
        });

        test('Ignore invalid facets', () => {
            const originalValue = sb.facet.read();
            sb.initFromUrlParams({facet: 'spam'});
            expect(sb.facet.read()).toBe(originalValue);
        });

        test('Sets input value from q param', () => {
            sb.initFromUrlParams({q: 'Harry Potter'});
            expect(sb.$input.val()).toBe('Harry Potter');
        });

        test('Remove title prefix from q param', () => {
            sb.initFromUrlParams({q: 'title:"Harry Potter"', facet: 'title'});
            expect(sb.$input.val()).toBe('Harry Potter');
            sb.initFromUrlParams({q: 'title: "Harry"', facet: 'title'});
            expect(sb.$input.val()).toBe('Harry');
        });

        test('Persists value in url param', () => {
            expect(localStorage.getItem('facet')).not.toBe('title');
            sb.initFromUrlParams({facet: 'title'});
            expect(localStorage.getItem('facet')).toBe('title');
        });
    });

    describe('submitForm', () => {
        let sb;
        beforeEach(() => {
            sb = new SearchBar($(DUMMY_COMPONENT_HTML));
        });
        afterEach(() => localStorage.clear());

        test('Queries are marshalled before submit for titles', () => {
            sb.initFromUrlParams({facet: 'title'});
            const spy = sinon.spy(SearchBar, 'marshalBookSearchQuery');
            sb.submitForm();
            expect(spy.callCount).toBe(1);
            spy.restore();
        });

        test('Form action is updated on submit', () => {
            sb.initFromUrlParams({facet: 'title'});
            const originalAction = sb.$form[0].action;
            sb.submitForm();
            expect(sb.$form[0].action).not.toBe(originalAction);
        });

        test('Special inputs are added to the form on submit', () => {
            const spy = sinon.spy(SearchUtils, 'addModeInputsToForm')
            sb.submitForm();
            expect(spy.callCount).toBe(1);
        });
    });

    describe('toggleCollapsibleModeForSmallScreens', () => {
        /** @type {SearchBar?} */
        let sb;
        beforeEach(() => sb = new SearchBar($(DUMMY_COMPONENT_HTML)));
        afterEach(() => localStorage.clear());

        test('Only enters collapsible mode if not already there', () => {
            sb.inCollapsibleMode = true;
            const spy = sinon.spy(sb, 'enableCollapsibleMode');
            sb.toggleCollapsibleModeForSmallScreens(100);
            expect(spy.callCount).toBe(0);
        });

        test('Only exits collapsible mode if not already exited', () => {
            sb.inCollapsibleMode = false;
            const spy = sinon.spy(sb, 'disableCollapsibleMode');
            sb.toggleCollapsibleModeForSmallScreens(1000);
            expect(spy.callCount).toBe(0);
        });
    });

    describe('marshalBookSearchQuery', () => {
        const fn = SearchBar.marshalBookSearchQuery;
        test('Empty string', () => {
            expect(fn('')).toBe('');
        });

        test('Adds title prefix to plain strings', () => {
            expect(fn('Harry Potter')).toBe('title: "Harry Potter"');
        });

        test('Does not add title prefix to lucene-style queries', () => {
            expect(fn('author:"Harry Potter"')).toBe('author:"Harry Potter"');
            expect(fn('"Harry Potter"')).toBe('"Harry Potter"');
        });
    });

    describe('Misc', () => {
        const sandbox = sinon.createSandbox();
        afterEach(() => {
            sandbox.restore();
            localStorage.clear();
        });

        test('When localStorage empty, defaults to facet=all', () => {
            localStorage.clear();
            const sb = new SearchBar($(DUMMY_COMPONENT_HTML));
            expect(sb.facet.read()).toBe('all');
        });

        test('Facet persists between page loads', () => {
            localStorage.setItem('facet', 'title');
            const sb = new SearchBar($(DUMMY_COMPONENT_HTML));
            expect(sb.facet.read()).toBe('title');
            const sb2 = new SearchBar($(DUMMY_COMPONENT_HTML));
            expect(sb2.facet.read()).toBe('title');
        });

        test('Advanced facet triggers redirect', () => {
            const sb = new SearchBar($(DUMMY_COMPONENT_HTML));
            const navigateToStub = sandbox.stub(sb, 'navigateTo');
            const event = Object.assign(new $.Event(), { target: { value: 'advanced' }});
            sb.handleFacetSelectChange(event);
            expect(navigateToStub.callCount).toBe(1);
            expect(navigateToStub.args[0]).toEqual(['/advancedsearch']);
        });

        for (const facet of ['title', 'author', 'all']) {
            test(`Facet "${facet}" searches tigger autocomplete`, () => {
                // Stub debounce to avoid have to manipulate time (!)
                sandbox.stub(nonjquery_utils, 'debounce').callsFake(fn => fn);
                const sb = new SearchBar($(DUMMY_COMPONENT_HTML), { facet });
                const getJSONStub = sandbox.stub($, 'getJSON');

                sb.$input.val('Harry');
                sb.$input.triggerHandler('focus');
                expect(getJSONStub.callCount).toBe(1);
            });
        }

        test('Title searches tigger autocomplete even if containing title: prefix', () => {
            // Stub debounce to avoid have to manipulate time (!)
            sandbox.stub(nonjquery_utils, 'debounce').callsFake(fn => fn);
            const sb = new SearchBar($(DUMMY_COMPONENT_HTML), {facet: 'title'});
            const getJSONStub = sandbox.stub($, 'getJSON');
            sb.$input.val('title:"Harry"');
            sb.$input.triggerHandler('focus');
            expect(getJSONStub.callCount).toBe(1);
        });

        test('Focussing on input when empty does not trigger autocomplete', () => {
            // Stub debounce to avoid have to manipulate time (!)
            sandbox.stub(nonjquery_utils, 'debounce').callsFake(fn => fn);
            const sb = new SearchBar($(DUMMY_COMPONENT_HTML), {facet: 'title'});
            const getJSONStub = sandbox.stub($, 'getJSON');
            sb.$input.val('');
            sb.$input.triggerHandler('focus');
            expect(getJSONStub.callCount).toBe(0);
        });

        for (const facet of ['lists', 'subject', 'text']) {
            test(`Facet "${facet}" does not tigger autocomplete`, () => {
                // Stub debounce to avoid have to manipulate time (!)
                sandbox.stub(nonjquery_utils, 'debounce').callsFake(fn => fn);
                const sb = new SearchBar($(DUMMY_COMPONENT_HTML));
                const getJSONStub = sandbox.stub($, 'getJSON');

                sb.$input.val('foo bar');
                sb.facet.write(facet);
                sb.$input.triggerHandler('focus');
                expect(getJSONStub.callCount).toBe(0);
            });
        }
    });
});
