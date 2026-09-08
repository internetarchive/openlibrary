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

function textTransfer(text) {
    return { types: ['text/plain'], dropEffect: '', getData: jest.fn().mockReturnValue(text) };
}

describe('SearchModal trigger drag-and-drop', () => {
    test('dragover shows the copy cursor without opening the modal', () => {
        const { modal, trigger } = setup();
        const dataTransfer = textTransfer('dune');

        const preventDefault = dispatch(trigger, 'dragover', dataTransfer);

        expect(preventDefault).toHaveBeenCalled();
        expect(dataTransfer.dropEffect).toBe('copy');
        expect(modal._openModal).not.toHaveBeenCalled();
        expect(modal._applyDroppedText).not.toHaveBeenCalled();
    });

    test('drop opens the modal and forwards the dropped text', () => {
        const { modal, trigger } = setup();
        const dataTransfer = textTransfer('dune');

        const preventDefault = dispatch(trigger, 'drop', dataTransfer);

        expect(preventDefault).toHaveBeenCalled();
        expect(modal._openModal).toHaveBeenCalledWith('drag');
        expect(modal._applyDroppedText).toHaveBeenCalledWith('dune');
    });

    test('drop does not reopen an already-open modal', () => {
        const { modal, trigger } = setup();
        modal.open = true;
        const dataTransfer = textTransfer('dune');

        dispatch(trigger, 'drop', dataTransfer);

        expect(modal._openModal).not.toHaveBeenCalled();
        expect(modal._applyDroppedText).toHaveBeenCalledWith('dune');
    });

    test('drop with no text does not forward anything', () => {
        const { modal, trigger } = setup();
        const dataTransfer = textTransfer('');

        dispatch(trigger, 'drop', dataTransfer);

        expect(modal._openModal).not.toHaveBeenCalled();
        expect(modal._applyDroppedText).not.toHaveBeenCalled();
    });

    test.each([
        ['a file', ['Files']],
        ['an image', ['text/uri-list', 'text/html']],
        ['an ILE book selection', ['text/plain', 'application/x.ile+json']],
    ])('ignores a drag of %s', (_label, types) => {
        const { modal, trigger } = setup();
        const dataTransfer = { types, dropEffect: '', getData: jest.fn().mockReturnValue('{"x":1}') };

        const dragover = dispatch(trigger, 'dragover', dataTransfer);
        const drop = dispatch(trigger, 'drop', dataTransfer);

        expect(dragover).not.toHaveBeenCalled();
        expect(dataTransfer.dropEffect).toBe('');
        expect(drop).not.toHaveBeenCalled();
        expect(modal._openModal).not.toHaveBeenCalled();
        expect(modal._applyDroppedText).not.toHaveBeenCalled();
    });
});
