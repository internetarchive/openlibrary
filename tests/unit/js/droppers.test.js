import sinon from 'sinon';
import { initDroppers } from '../../../openlibrary/plugins/openlibrary/js/dropper';
import { Dropper } from '../../../openlibrary/plugins/openlibrary/js/dropper/Dropper';
import { legacyBookDropperMarkup, openDropperMarkup, closedDropperMarkup, disabledDropperMarkup, defineStubPopover } from './sample-html/dropper-test-data';
import * as nonjquery_utils from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';

defineStubPopover();

describe('initDroppers', () => {
    test('dropdown changes arrow direction on click', () => {
        // Stub debounce to avoid have to manipulate time (!)
        const stub = sinon.stub(nonjquery_utils, 'debounce').callsFake(fn => fn);

        $(document.body).html(legacyBookDropperMarkup);
        const $dropclick = $('.dropclick');
        const $arrow = $dropclick.find('.arrow');
        initDroppers(document.querySelectorAll('.dropper'));

        for (let i = 0; i < 2; i++) {
            $dropclick.trigger('click');
            expect($arrow.hasClass('up')).toBe(true);

            $dropclick.trigger('click');
            expect($arrow.hasClass('up')).toBe(false);
        }

        stub.restore();
    });
});

describe('Generic Droppers', () => {
    test('Clicking the dropclick element toggles the popover', () => {
        document.body.innerHTML = closedDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const dropper = new Dropper(wrapper);
        dropper.initialize();

        const dropClick = wrapper.querySelector('.generic-dropper__dropclick');
        const popover = wrapper.querySelector('ol-popover');

        expect(popover.open).toBe(false);
        expect(dropper.isDropperOpen).toBe(false);

        dropClick.click();
        expect(popover.open).toBe(true);
        expect(dropper.isDropperOpen).toBe(true);

        dropClick.click();
        expect(popover.open).toBe(false);
        expect(dropper.isDropperOpen).toBe(false);
    });

    test('Disabled droppers cannot be opened by clicking the dropclick', () => {
        document.body.innerHTML = disabledDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const dropper = new Dropper(wrapper);
        dropper.initialize();

        const dropClick = wrapper.querySelector('.generic-dropper__dropclick');
        const popover = wrapper.querySelector('ol-popover');

        // Sanity checks
        expect(wrapper.classList.contains('generic-dropper--disabled')).toBe(true);
        expect(popover.open).toBe(false);

        // The dropper swallows the click before the popover can act on it.
        dropClick.click();

        expect(popover.open).toBe(false);
        expect(dropper.isDropperOpen).toBe(false);
    });
});

describe('Dropper.js class', () => {
    test('Dropper references set correctly on instantiation', () => {
        document.body.innerHTML = closedDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const dropper = new Dropper(wrapper);

        // Reference to component root stored
        expect(dropper.dropper === wrapper).toBe(true);

        // Dropclick reference stored
        const dropClick = wrapper.querySelector('.generic-dropper__dropclick');
        expect(dropper.dropClick === dropClick).toBe(true);

        // Popover reference stored
        const popover = wrapper.querySelector('ol-popover');
        expect(dropper.popover === popover).toBe(true);

        // Dropper is closed
        expect(dropper.isDropperOpen).toBe(false);

        // This dropper is not disabled
        expect(dropper.isDropperDisabled).toBe(false);
    });

    it('reads its initial open state from the popover', () => {
        document.body.innerHTML = openDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const dropper = new Dropper(wrapper);

        expect(dropper.isDropperOpen).toBe(true);
    });

    it('does not track popover state until initialize() is called', () => {
        document.body.innerHTML = closedDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const dropClick = wrapper.querySelector('.generic-dropper__dropclick');
        const popover = wrapper.querySelector('ol-popover');

        const dropper = new Dropper(wrapper);
        const onOpenFn = jest.spyOn(dropper, 'onOpen');

        // The popover self-manages, so the panel still opens — but the dropper
        // is not listening yet, so none of its hooks run.
        dropClick.click();
        expect(popover.open).toBe(true);
        expect(dropper.isDropperOpen).toBe(false);
        expect(onOpenFn).not.toHaveBeenCalled();

        // Test again after initialization:
        popover.open = false;
        dropper.initialize();
        dropClick.click();
        expect(dropper.isDropperOpen).toBe(true);
        expect(onOpenFn).toHaveBeenCalled();

        jest.restoreAllMocks();
    });

    it('can be closed if not disabled', () => {
        document.body.innerHTML = openDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const popover = wrapper.querySelector('ol-popover');

        const dropper = new Dropper(wrapper);
        dropper.initialize();

        // Check initial state:
        expect(dropper.isDropperDisabled).toBe(false);
        expect(dropper.isDropperOpen).toBe(true);
        expect(popover.open).toBe(true);

        // Check again after closing:
        dropper.closeDropper();
        expect(dropper.isDropperOpen).toBe(false);
        expect(popover.open).toBe(false);
    });

    it('can be toggled if not disabled', () => {
        document.body.innerHTML = closedDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const popover = wrapper.querySelector('ol-popover');

        const dropper = new Dropper(wrapper);
        dropper.initialize();

        // Check initial state:
        expect(dropper.isDropperDisabled).toBe(false);
        expect(dropper.isDropperOpen).toBe(false);
        expect(popover.open).toBe(false);

        // Check after toggling open:
        dropper.toggleDropper();
        expect(dropper.isDropperOpen).toBe(true);
        expect(popover.open).toBe(true);

        // Check after toggling once more:
        dropper.toggleDropper();
        expect(dropper.isDropperOpen).toBe(false);
        expect(popover.open).toBe(false);
    });

    it('cannot be opened while disabled', () => {
        document.body.innerHTML = disabledDropperMarkup;
        const wrapper = document.querySelector('.generic-dropper-wrapper');
        const popover = wrapper.querySelector('ol-popover');
        const dropper = new Dropper(wrapper);
        dropper.initialize();

        // Check initial state:
        expect(dropper.isDropperDisabled).toBe(true);
        expect(popover.open).toBe(false);

        // Check state after toggling:
        dropper.toggleDropper();
        expect(popover.open).toBe(false);
        expect(dropper.isDropperOpen).toBe(false);
    });

    describe('Dropper event methods', () => {
        afterEach(() => {
            jest.clearAllMocks();
        });

        it('calls `onDisabledClick()` when dropper is clicked while disabled', () => {
            document.body.innerHTML = disabledDropperMarkup;
            const wrapper = document.querySelector('.generic-dropper-wrapper');
            const dropper = new Dropper(wrapper);
            dropper.initialize();

            const onDisabledClickFn = jest.spyOn(dropper, 'onDisabledClick');

            // Check initial state:
            expect(dropper.isDropperDisabled).toBe(true);
            expect(onDisabledClickFn).not.toHaveBeenCalled();

            // Check state after toggling:
            dropper.toggleDropper();
            expect(dropper.isDropperDisabled).toBe(true);
            expect(onDisabledClickFn).toHaveBeenCalledTimes(1);

            // Check state after closing:
            dropper.closeDropper();
            expect(dropper.isDropperDisabled).toBe(true);
            expect(onDisabledClickFn).toHaveBeenCalledTimes(2);
        });

        it('calls `onDisabledClick()` when the dropclick of a disabled dropper is clicked', () => {
            document.body.innerHTML = disabledDropperMarkup;
            const wrapper = document.querySelector('.generic-dropper-wrapper');
            const dropper = new Dropper(wrapper);
            dropper.initialize();

            const onDisabledClickFn = jest.spyOn(dropper, 'onDisabledClick');

            wrapper.querySelector('.generic-dropper__dropclick').click();

            expect(onDisabledClickFn).toHaveBeenCalledTimes(1);
        });

        it('calls `onClose()` when active dropper is closed', () => {
            document.body.innerHTML = openDropperMarkup;
            const wrapper = document.querySelector('.generic-dropper-wrapper');
            const dropper = new Dropper(wrapper);
            dropper.initialize();

            const onCloseFn = jest.spyOn(dropper, 'onClose');

            // Check initial state:
            expect(dropper.isDropperOpen).toBe(true);
            expect(onCloseFn).not.toHaveBeenCalled();

            // Check state after closing:
            dropper.closeDropper();
            expect(dropper.isDropperOpen).toBe(false);
            expect(onCloseFn).toHaveBeenCalledTimes(1);

            // Check state after toggling open then closed:
            dropper.toggleDropper();
            expect(dropper.isDropperOpen).toBe(true);
            expect(onCloseFn).toHaveBeenCalledTimes(1); // Should not be called when dropper is opened

            dropper.toggleDropper();
            expect(dropper.isDropperOpen).toBe(false);
            expect(onCloseFn).toHaveBeenCalledTimes(2);
        });

        test('toggling dropper results in correct event method being called', () => {
            document.body.innerHTML = closedDropperMarkup;
            const wrapper = document.querySelector('.generic-dropper-wrapper');
            const dropper = new Dropper(wrapper);
            dropper.initialize();

            const onCloseFn = jest.spyOn(dropper, 'onClose');
            const onOpenFn = jest.spyOn(dropper, 'onOpen');

            // Check initial state:
            expect(dropper.isDropperOpen).toBe(false);
            expect(onCloseFn).not.toHaveBeenCalled();
            expect(onOpenFn).not.toHaveBeenCalled();

            // Check after toggling open:
            dropper.toggleDropper();
            expect(dropper.isDropperOpen).toBe(true);
            expect(onCloseFn).toHaveBeenCalledTimes(0);
            expect(onOpenFn).toHaveBeenCalledTimes(1);

            // Check after toggling closed:
            dropper.toggleDropper();
            expect(dropper.isDropperOpen).toBe(false);
            expect(onCloseFn).toHaveBeenCalledTimes(1);
            expect(onOpenFn).toHaveBeenCalledTimes(1);
        });

        it('runs the close hooks when the popover dismisses itself', () => {
            document.body.innerHTML = openDropperMarkup;
            const wrapper = document.querySelector('.generic-dropper-wrapper');
            const popover = wrapper.querySelector('ol-popover');
            const dropper = new Dropper(wrapper);
            dropper.initialize();

            const onCloseFn = jest.spyOn(dropper, 'onClose');

            // Escape / outside click / swipe all land here.
            popover.open = false;

            expect(dropper.isDropperOpen).toBe(false);
            expect(onCloseFn).toHaveBeenCalledTimes(1);
        });
    });
});
