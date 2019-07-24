import jquery from 'jquery';
import sinon from 'sinon';
import { initReadingListFeature } from '../../../openlibrary/plugins/openlibrary/js/ol';

let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    sandbox.stub(global, '$').callsFake(jquery);
});

test('initReadingListFeature binds events to HTML added after initialisation', () => {
    const spy = sinon.spy();
    initReadingListFeature(() => spy);
    $(document.body).html(`<div>
    <div class="dropclick">test</div>
    <a class="add-to-list"></a>
</div>
    `);
    // trigger a click event
    $('.dropclick').trigger('click');
    // check the event handler was called
    expect(spy.callCount).toBe(1);
    $('.dropclick').trigger('click');
    // check the dropclick event handler was called
    expect(spy.callCount).toBe(2);
});
