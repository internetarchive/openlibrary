import { initNewAccountsReview } from '../../../openlibrary/plugins/openlibrary/js/admin.js';

function setup() {
    document.body.innerHTML = `
        <form class="new-accounts__form">
            <input type="checkbox" class="new-accounts__select-all">
            <span class="new-accounts__selected">Select all</span>
            <ol-button class="new-accounts__bulk-action" value="block_account"><button type="submit">Block</button></ol-button>
            <ol-button class="new-accounts__bulk-action" value="mark_trusted"><button type="submit">Mark trusted</button></ol-button>
            <table>
                <tr><td><input type="checkbox" name="username" value="a"></td></tr>
                <tr><td><input type="checkbox" name="username" value="b"></td></tr>
            </table>
        </form>`;
    const form = document.querySelector('form');
    initNewAccountsReview(form);
    return form;
}

afterEach(() => {
    delete window.OL_I18N;
    vi.restoreAllMocks();
});

describe('initNewAccountsReview', () => {
    test('counts the ticked accounts in the page language', () => {
        window.OL_I18N = { '%(count)s selected': '%(count)s seleccionadas', 'Select all': 'Seleccionar todo' };
        const form = setup();
        const status = form.querySelector('.new-accounts__selected');
        expect(status.textContent).toBe('Seleccionar todo');

        form.querySelector('input[value="a"]').click();
        expect(status.textContent).toBe('1 seleccionadas');
    });

    test("confirms with the clicked action's own message", () => {
        window.OL_I18N = { 'Block the selected accounts?': '¿Bloquear las cuentas seleccionadas?' };
        const form = setup();
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        const submitter = form.querySelector('ol-button[value="block_account"] button');

        const event = new SubmitEvent('submit', { cancelable: true, submitter });
        form.dispatchEvent(event);

        expect(confirm).toHaveBeenCalledWith('¿Bloquear las cuentas seleccionadas?');
        expect(event.defaultPrevented).toBe(true);
    });
});
