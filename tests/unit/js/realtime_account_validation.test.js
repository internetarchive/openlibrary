import { initRealTimeValidation } from '../../../openlibrary/plugins/openlibrary/js/realtime_account_validation';

beforeEach(() => {
    document.body.innerHTML = `
    <form id="signup">
      <input type="text" id="username">
      <input type="text" id="emailAddr">
      <input type="password" id="password">
      <input type="password" id="password2">
      <div id="password2Message"></div>
      <label for="password2" class="default">Label for password2</label>
    </form>
  `;
});

describe('Password tests', () => {
    let label, passwordField, passwordField2, passwordMessage2

    beforeEach(() => {
        // call the function
        initRealTimeValidation();

        //declare the elements
        label = document.querySelector('label[for="password2"]');
        passwordField = document.getElementById('password');
        passwordField2 = document.getElementById('password2');
        passwordMessage2 = document.getElementById('password2Message');
    })

    test('validatePassword should update elements correctly on success', () => {
        // set the password values
        passwordField.value = 'password123';
        passwordField2.value = 'password123';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));
        passwordField2.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField2.classList.contains('required')).toBe(true);
        expect(passwordField2.classList.contains('invalid')).toBe(false);
        expect(label.classList.length).toBe(0);
        expect(passwordMessage2.classList.contains('darkgreen')).toBe(true);
    });

    test('validatePassword should update elements correctly for empty fields', () => {
        // set the password values
        passwordField.value = '';
        passwordField2.value = '';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));
        passwordField2.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField2.classList.contains('required')).toBe(true);
        expect(passwordField2.classList.contains('invalid')).toBe(false);
        expect(label.classList.length).toBe(0);
        expect(passwordMessage2.textContent).toBe('');
    });

    test('validatePassword should update elements correctly for passwords not matching', () => {
        // set the password values
        passwordField.value = 'password123';
        passwordField2.value = 'password321';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));
        passwordField2.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField2.classList.contains('required')).toBe(true);
        expect(passwordField2.classList.contains('invalid')).toBe(true);
        expect(label.classList.contains('default')).toBe(false);
        expect(label.classList.contains('invalid')).toBe(true);
        expect(passwordMessage2.classList.contains('invalid')).toBe(true);
        expect(passwordMessage2.textContent).toBe('Passwords didnt match');
    });
});
