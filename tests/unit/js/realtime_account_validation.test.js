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
    test('validatePassword should update elements correctly on success', () => {
        // call the function
        initRealTimeValidation();

        //declare the elements
        const label = document.querySelector('label[for="password2"]');
        const passwordField = document.getElementById('password');
        const password2Field = document.getElementById('password2');
        const password2Message = document.getElementById('password2Message');
        
        // set the password values
        passwordField.value = 'password123';
        password2Field.value = 'password123';
    
        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));
        password2Field.dispatchEvent(new Event('blur'));
        
        // Assert that the elements have the expected classes
        expect(password2Field.classList.contains('required')).toBe(true);
        expect(password2Field.classList.contains('invalid')).toBe(false);
        expect(label.classList.length).toBe(0);
        expect(password2Message.classList.contains('darkgreen')).toBe(true);
    });

    test('validatePassword should update elements correctly for empty fields', () => {
        // call the function
        initRealTimeValidation();

        //declare the elements
        const label = document.querySelector('label[for="password2"]');
        const passwordField = document.getElementById('password');
        const password2Field = document.getElementById('password2');
        const password2Message = document.getElementById('password2Message');
        
        // set the password values
        passwordField.value = '';
        password2Field.value = '';
    
        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));
        password2Field.dispatchEvent(new Event('blur'));
    
        // Assert that the elements have the expected classes
        expect(password2Field.classList.contains('required')).toBe(true);
        expect(password2Field.classList.contains('invalid')).toBe(false);
        expect(label.classList.length).toBe(0);
        expect(password2Message.textContent).toBe("");
    });

    test('validatePassword should update elements correctly for passwords not matching', () => {
        // call the function
        initRealTimeValidation();

        //declare the elements
        const label = document.querySelector('label[for="password2"]');
        const passwordField = document.getElementById('password');
        const password2Field = document.getElementById('password2');
        const password2Message = document.getElementById('password2Message');

        // set the password values
        passwordField.value = 'password123';
        password2Field.value = 'password321';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));
        password2Field.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(password2Field.classList.contains('required')).toBe(true);
        expect(password2Field.classList.contains('invalid')).toBe(true);
        expect(label.classList.contains('default')).toBe(false);
        expect(label.classList.contains('invalid')).toBe(true);
        expect(password2Message.classList.contains('invalid')).toBe(true);
        expect(password2Message.textContent).toBe("Passwords didnt match");
    });
});