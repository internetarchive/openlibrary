import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

function dispatch(trigger, type, dataTransfer) {
    const event = new Event(type, { bubbles: true, cancelable: true });
    event.dataTransfer = dataTransfer;
    const preventDefault = jest.spyOn(event, 'preventDefault');
    trigger.dispatchEvent(event);
    return preventDefault;
}

function setup() {
    const modal = new SearchModal();
    modal._openModal = jest.fn();
    modal._applyDroppedText = jest.fn();
    const trigger = document.createElement('button');
    modal.attachToTrigger(trigger);
    return { modal, trigger };
}

describe('SearchModal trigger drag-and-drop', () => {
    test('dragover shows the copy cursor without opening the modal', () => {
        const { modal, trigger } = setup();
        const dataTransfer = { dropEffect: '' };

        const preventDefault = dispatch(trigger, 'dragover', dataTransfer);

        expect(preventDefault).toHaveBeenCalled();
        expect(dataTransfer.dropEffect).toBe('copy');
        expect(modal._openModal).not.toHaveBeenCalled();
        expect(modal._applyDroppedText).not.toHaveBeenCalled();
    });

    test('drop opens the modal and forwards the dropped text', () => {
        const { modal, trigger } = setup();
        const dataTransfer = { getData: jest.fn().mockReturnValue('dune') };

        const preventDefault = dispatch(trigger, 'drop', dataTransfer);

        expect(preventDefault).toHaveBeenCalled();
        expect(modal._openModal).toHaveBeenCalledWith('drag');
        expect(modal._applyDroppedText).toHaveBeenCalledWith('dune');
    });

    test('drop does not reopen an already-open modal', () => {
        const { modal, trigger } = setup();
        modal.open = true;
        const dataTransfer = { getData: jest.fn().mockReturnValue('dune') };

        dispatch(trigger, 'drop', dataTransfer);

        expect(modal._openModal).not.toHaveBeenCalled();
        expect(modal._applyDroppedText).toHaveBeenCalledWith('dune');
    });

    test('drop with no text does not forward anything', () => {
        const { modal, trigger } = setup();
        const dataTransfer = { getData: jest.fn().mockReturnValue('') };

        dispatch(trigger, 'drop', dataTransfer);

        expect(modal._openModal).toHaveBeenCalledWith('drag');
        expect(modal._applyDroppedText).not.toHaveBeenCalled();
    });
});
