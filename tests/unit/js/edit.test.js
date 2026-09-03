import { initEditRow } from '../../../openlibrary/plugins/openlibrary/js/edit';

describe('profile website rows', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <form>
                <div id="clone_website" data-invalid-url="Please enter a valid URL.">
                    <input type="url" name="website#0" placeholder="https://...">
                    <button id="add_row_button" type="button">Add another</button>
                </div>
                <button type="submit">Save</button>
            </form>
        `;
        initEditRow();
    });

    test('blocks invalid website values from being added or submitted', () => {
        const input = document.querySelector('input');
        input.value = 'not-a-url';
        input.dispatchEvent(new Event('input'));

        document.querySelector('#add_row_button').click();

        expect(document.querySelectorAll('input')).toHaveLength(1);
        expect(input.validationMessage).toBe('Please enter a valid URL.');
        expect(input.form.checkValidity()).toBe(false);
    });

    test('adds another URL input after a valid website', () => {
        const input = document.querySelector('input');
        input.value = 'https://example.org';
        input.dispatchEvent(new Event('input'));

        document.querySelector('#add_row_button').click();

        const inputs = document.querySelectorAll('input');
        expect(inputs).toHaveLength(2);
        expect(inputs[1].type).toBe('url');
        expect(inputs[1].placeholder).toBe('https://...');
        expect(input.form.checkValidity()).toBe(true);
    });

    test('rejects non-HTTP URL schemes', () => {
        const input = document.querySelector('input');
        input.value = 'ftp://example.org/file';
        input.dispatchEvent(new Event('input'));

        document.querySelector('#add_row_button').click();

        expect(document.querySelectorAll('input')).toHaveLength(1);
        expect(input.validationMessage).toBe('Please enter a valid URL.');
    });

    test('blocks adding a third row when the second website is invalid', () => {
        const firstInput = document.querySelector('input');
        firstInput.value = 'https://example.org';
        firstInput.dispatchEvent(new Event('input'));
        document.querySelector('#add_row_button').click();

        const secondInput = document.querySelectorAll('input')[1];
        secondInput.value = 'not-a-url';
        secondInput.dispatchEvent(new Event('input'));
        document.querySelector('#add_row_button').click();

        expect(document.querySelectorAll('input')).toHaveLength(2);
        expect(secondInput.validationMessage).toBe('Please enter a valid URL.');
        expect(secondInput.form.checkValidity()).toBe(false);
    });
});
