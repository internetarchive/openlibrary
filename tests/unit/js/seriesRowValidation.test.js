import { initSeriesRowValidation } from '../../../openlibrary/plugins/openlibrary/js/edit.js';

const MESSAGE = 'Please choose a series from the suggestions';

// One row as rendered by templates/books/series-autocomplete.html
function renderSeriesForm({ name = '', key = '', position = '' }) {
    document.body.innerHTML = `
        <form id="addWork">
            <div class="multi-input-autocomplete multi-input-autocomplete--series" data-i18n='{"no_series_selected": "${MESSAGE}"}'>
                <div class="input ac-input mia__input">
                    <label><input class="ac-input__visible" name="series--0" type="text" value="${name}"></label>
                    <input class="ac-input__value" name="work--series--0--series--key" type="hidden" value="${key}">
                    <label class="floating-label mias__position"><input name="work--series--0--position" type="text" value="${position}"></label>
                </div>
            </div>
            <button type="submit" name="_save">Save</button>
        </form>`;
    const container = document.querySelector('.multi-input-autocomplete--series');
    initSeriesRowValidation(container);
    return { form: document.getElementById('addWork'), nameInput: container.querySelector('.ac-input__visible') };
}

function submit(form) {
    const event = new Event('submit', { bubbles: true, cancelable: true });
    form.dispatchEvent(event);
    return event;
}

describe('series row validation (#12309)', () => {
    test('blocks saving a typed series name with no series picked', () => {
        const { form, nameInput } = renderSeriesForm({ name: 'Unpicked Saga', position: '3' });
        expect(submit(form).defaultPrevented).toBe(true);
        expect(nameInput.validationMessage).toBe(MESSAGE);
    });

    test('blocks saving a position with no series', () => {
        const { form } = renderSeriesForm({ position: '3' });
        expect(submit(form).defaultPrevented).toBe(true);
    });

    test('allows saving a row with a series picked', () => {
        const { form, nameInput } = renderSeriesForm({ name: 'Existing Saga', key: '/series/OL1L', position: '1' });
        expect(submit(form).defaultPrevented).toBe(false);
        expect(nameInput.validationMessage).toBe('');
    });

    test('allows saving an empty row', () => {
        const { form } = renderSeriesForm({});
        expect(submit(form).defaultPrevented).toBe(false);
    });

    test('typing in the row clears the message so a later save is not stuck', () => {
        const { form, nameInput } = renderSeriesForm({ name: 'Unpicked Saga' });
        submit(form);
        nameInput.dispatchEvent(new Event('input', { bubbles: true }));
        expect(nameInput.validationMessage).toBe('');
    });
});
