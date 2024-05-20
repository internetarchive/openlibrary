import { initRealTimeValidation } from '../../../openlibrary/plugins/openlibrary/js/realtime_account_validation';

beforeEach(() => {
    document.body.innerHTML = `
    <form id="signup" name="signup" data-i18n={}>
      <input type="text" id="username">
      <input type="text" id="emailAddr">
      <div id="passwordMessage"></div>
      <label for="password">Label for password</label>
      <input type="password" class="required" id="password">
    </form>
  `;
});

describe('Password tests', () => {
    let label, passwordField, passwordMessage

    beforeEach(() => {
        // call the function
        initRealTimeValidation();

        //declare the elements
        label = document.querySelector('label[for="password"]');
        passwordField = document.getElementById('password');
        passwordMessage = document.getElementById('passwordMessage');
    })

    test('validatePassword should update elements correctly on success', () => {
        // set the password value
        passwordField.value = 'password123';

        // Trigger the blur event on the password field
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('required')).toBe(true);
        expect(passwordField.classList.contains('invalid')).toBe(false);
        expect(label.classList.length).toBe(0);
    });

    test('validatePassword should update elements correctly for empty fields', () => {
        // set the password value
        passwordField.value = '';

        // Trigger the blur event on the password field
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('required')).toBe(true);
        expect(passwordField.classList.contains('invalid')).toBe(false);
        expect(label.classList.contains('invalid')).toBe(false);
        expect(passwordMessage.textContent).toBe('');
    });

    test('validatePassword should update elements correctly for passwords over 20 chars', () => {
        // set the password values
        passwordField.value = 'password1234567891011';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('required')).toBe(true);
        expect(passwordField.classList.contains('invalid')).toBe(true);
        expect(label.classList.contains('invalid')).toBe(true);
        expect(passwordMessage.classList.contains('invalid')).toBe(true);
    });

    test('validatePassword should update elements correctly for passwords under 3 chars', () => {
        // set the password values
        passwordField.value = 'pa';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('required')).toBe(true);
        expect(passwordField.classList.contains('invalid')).toBe(true);
        expect(label.classList.contains('invalid')).toBe(true);
        expect(passwordMessage.classList.contains('invalid')).toBe(true);
    });
});
