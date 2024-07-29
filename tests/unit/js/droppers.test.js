import sinon from 'sinon';
import { initDroppers, initGenericDroppers } from '../../../openlibrary/plugins/openlibrary/js/dropper';
import { Dropper } from '../../../openlibrary/plugins/openlibrary/js/dropper/Dropper'
import { legacyBookDropperMarkup, openDropperMarkup, closedDropperMarkup, disabledDropperMarkup } from './sample-html/dropper-test-data'
import * as nonjquery_utils from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';


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
  test('Clicking dropclick element toggles the dropper', () => {
    // Setup
    document.body.innerHTML = closedDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const dropper = new Dropper(wrapper)
    dropper.initialize()

    const dropClick = document.querySelector('.generic-dropper__dropclick')
    const arrow = dropClick.querySelector('.arrow')

    // Dropper should be closed at the start
    expect(arrow.classList.contains('up')).toBe(false)
    expect(wrapper.classList.contains('dropper-wrapper--active')).toBe(false)

    // Open dropper
    dropClick.click()
    expect(arrow.classList.contains('up')).toBe(true)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(true)

    // Close dropper
    dropClick.click()
    expect(arrow.classList.contains('up')).toBe(false)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
  })

  test('Opened droppers close if they are not the target of a click', () => {
    // Setup
    document.body.innerHTML = openDropperMarkup.concat(openDropperMarkup, openDropperMarkup)
    const wrappers = document.querySelectorAll('.generic-dropper-wrapper')
    initGenericDroppers(wrappers)


    // Ensure that all three droppers are open
    expect(wrappers.length).toBe(3)
    for (const wrapper of wrappers) {
      const arrow = wrapper.querySelector('.arrow')
      expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(true)
      expect(arrow.classList.contains('up')).toBe(true)
    }

    // After clicking the dropdown content of the first dropper:
    const dropdownContent = wrappers[0].querySelector('.generic-dropper__dropdown')
    dropdownContent.click()

    // First dropper should be open
    expect(wrappers[0].classList.contains('generic-dropper-wrapper--active')).toBe(true)
    expect(wrappers[0].querySelector('.arrow').classList.contains('up')).toBe(true)

    // ...while other droppers should be closed
    for (let i = 1; i < wrappers.length; ++i) {
      const arrow = wrappers[i].querySelector('.arrow')
      expect(wrappers[i].classList.contains('generic-dropper-wrapper--active')).toBe(false)
      expect(arrow.classList.contains('up')).toBe(false)
    }
  })

  test('Disabled droppers cannot be opened nor closed', () => {
    document.body.innerHTML = disabledDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const dropper = new Dropper(wrapper)
    dropper.initialize()
    const dropclick = wrapper.querySelector('.generic-dropper__dropclick')
    const arrow = wrapper.querySelector('.arrow')

    // Sanity checks
    expect(wrapper.classList.contains('generic-dropper--disabled')).toBe(true)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)

    // Click on the dropclick:
    dropclick.click()

    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)
  })
})

describe('Dropper.js class', () => {
  test('Dropper references set correctly on instantiation', () => {
    document.body.innerHTML = closedDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const dropper = new Dropper(wrapper)

    // Reference to component root stored
    expect(dropper.dropper === wrapper).toBe(true)

    // Dropclick reference stored
    const dropClick = wrapper.querySelector('.generic-dropper__dropclick')
    expect(dropper.dropClick === dropClick).toBe(true)

    // Dropper is closed
    expect(dropper.isDropperOpen).toBe(false)

    // This dropper is not disabled
    expect(dropper.isDropperDisabled).toBe(false)
  })

  it('is not functional until initialize() is called', () => {
    document.body.innerHTML = closedDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const dropClick = wrapper.querySelector('.generic-dropper__dropclick')
    const arrow = wrapper.querySelector('.arrow')

    const dropper = new Dropper(wrapper)
    const spy = jest.spyOn(dropper, 'toggleDropper')

    // Dropper should be closed initially:
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)

    // Clicking should not do anything yet:
    dropClick.click()
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)
    expect(spy).not.toHaveBeenCalled()

    // Test again after initialization:
    dropper.initialize()
    dropClick.click()
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(true)
    expect(arrow.classList.contains('up')).toBe(true)
    expect(spy).toHaveBeenCalled()

    jest.restoreAllMocks()
  })

  it('can be closed if not disabled', () => {
    document.body.innerHTML = openDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const arrow = wrapper.querySelector('.arrow')

    const dropper = new Dropper(wrapper)
    dropper.initialize()

    // Check initial state:
    expect(dropper.isDropperDisabled).toBe(false)
    expect(dropper.isDropperOpen).toBe(true)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(true)
    expect(arrow.classList.contains('up')).toBe(true)

    // Check again after closing:
    dropper.closeDropper()
    expect(dropper.isDropperOpen).toBe(false)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)
  })

  it('can be toggled if not disabled', () => {
    document.body.innerHTML = closedDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const arrow = wrapper.querySelector('.arrow')

    const dropper = new Dropper(wrapper)
    dropper.initialize()

    // Check initial state:
    expect(dropper.isDropperDisabled).toBe(false)
    expect(dropper.isDropperOpen).toBe(false)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)

    // Check after toggling open:
    dropper.toggleDropper()
    expect(dropper.isDropperOpen).toBe(true)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(true)
    expect(arrow.classList.contains('up')).toBe(true)

    // Check after toggling once more:
    dropper.toggleDropper()
    expect(dropper.isDropperOpen).toBe(false)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
    expect(arrow.classList.contains('up')).toBe(false)
  })

  it('cannot be opened while disabled', () => {
    document.body.innerHTML = disabledDropperMarkup
    const wrapper = document.querySelector('.generic-dropper-wrapper')
    const dropper = new Dropper(wrapper)
    dropper.initialize()
    const arrow = wrapper.querySelector('.arrow')

    // Check initial state:
    expect(dropper.isDropperDisabled).toBe(true)
    expect(arrow.classList.contains('up')).toBe(false)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)

    // Check state after toggling:
    dropper.toggleDropper()
    expect(arrow.classList.contains('up')).toBe(false)
    expect(wrapper.classList.contains('generic-dropper-wrapper--active')).toBe(false)
  })

  describe('Dropper event methods', () => {
    afterEach(() => {
      jest.clearAllMocks()
    })

    it('calls `onDisabledClick()` when dropper is clicked while disabled', () => {
      document.body.innerHTML = disabledDropperMarkup
      const wrapper = document.querySelector('.generic-dropper-wrapper')
      const dropper = new Dropper(wrapper)
      dropper.initialize()

      const onDisabledClickFn = jest.spyOn(dropper, 'onDisabledClick')

      // Check initial state:
      expect(dropper.isDropperDisabled).toBe(true)
      expect(onDisabledClickFn).not.toHaveBeenCalled()

      // Check state after toggling:
      dropper.toggleDropper()
      expect(dropper.isDropperDisabled).toBe(true)
      expect(onDisabledClickFn).toHaveBeenCalledTimes(1)

      // Check state after closing:
      dropper.closeDropper()
      expect(dropper.isDropperDisabled).toBe(true)
      expect(onDisabledClickFn).toHaveBeenCalledTimes(2)
    })

    it('calls `onClose()` when active dropper is closed', () => {
      document.body.innerHTML = openDropperMarkup
      const wrapper = document.querySelector('.generic-dropper-wrapper')
      const dropper = new Dropper(wrapper)
      dropper.initialize()

      const onCloseFn = jest.spyOn(dropper, 'onClose')

      // Check initial state:
      expect(dropper.isDropperOpen).toBe(true)
      expect(onCloseFn).not.toHaveBeenCalled()

      // Check state after closing:
      dropper.closeDropper()
      expect(dropper.isDropperOpen).toBe(false)
      expect(onCloseFn).toHaveBeenCalledTimes(1)

      // Check state after toggling open then closed:
      dropper.toggleDropper()
      expect(dropper.isDropperOpen).toBe(true)
      expect(onCloseFn).toHaveBeenCalledTimes(1) // Should not be called when dropper is closed

      dropper.toggleDropper()
      expect(dropper.isDropperOpen).toBe(false)
      expect(onCloseFn).toHaveBeenCalledTimes(2)
    })

    test('toggling dropper results in correct event method being called', () => {
      document.body.innerHTML = closedDropperMarkup
      const wrapper = document.querySelector('.generic-dropper-wrapper')
      const dropper = new Dropper(wrapper)
      dropper.initialize()

      const onCloseFn = jest.spyOn(dropper, 'onClose')
      const onOpenFn = jest.spyOn(dropper, 'onOpen')

      // Check initial state:
      expect(dropper.isDropperOpen).toBe(false)
      expect(onCloseFn).not.toHaveBeenCalled()
      expect(onOpenFn).not.toHaveBeenCalled()

      // Check after toggling open:
      dropper.toggleDropper()
      expect(dropper.isDropperOpen).toBe(true)
      expect(onCloseFn).toHaveBeenCalledTimes(0)
      expect(onOpenFn).toHaveBeenCalledTimes(1)

      // Check after toggling closed:
      dropper.toggleDropper()
      expect(dropper.isDropperOpen).toBe(false)
      expect(onCloseFn).toHaveBeenCalledTimes(1)
      expect(onOpenFn).toHaveBeenCalledTimes(1)
    })
  })
})
