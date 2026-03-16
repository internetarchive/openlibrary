import { initSignupForm } from '../../../openlibrary/plugins/openlibrary/js/signup';

beforeEach(() => {
    document.body.innerHTML = `
    <form id="signup" name="signup" data-i18n={}>
      <label for="emailAddr">Email</label>
      <div id="emailAddrMessage" class="ol-signup-form__error"></div>
      <input type="email" id="emailAddr">
      <label for="username">Screen Name</label>
      <div id="usernameMessage" class="ol-signup-form__error"></div>
      <input type="text" id="username">
      <div id="passwordMessage" class="ol-signup-form__error"></div>
      <label for="password">Password</label>
      <input type="password" id="password">
      <div id="rpd-checkbox" class="ol-signup-form__checkbox">
        <input id="pd-request" type="checkbox">
        <label for="pd-request">PD Checkbox</label>
      </div>
      <div id="pda-selector" class="ol-signup-form__select hidden">
        <select id="pd_program" name="pd_program" aria-label="$_('Select qualifying program')" aria-describedby="pd-program-advisory" aria-invalid="false" aria-required="false">
            <option value="" disabled selected>"Select qualifying program"</option>
        </select>
      </div>
    </form>
  `;
});

describe('Email tests', () => {
    let emailLabel, emailField

    beforeEach(() => {
        // call the function
        initSignupForm();

        //declare the elements
        emailLabel = document.querySelector('label[for="emailAddr"]');
        emailField = document.getElementById('emailAddr');
    })

    test('validateEmail should update elements correctly on success', () => {
        // set the email value
        emailField.value = 'testemail@archive.org';

        // Trigger the blur event on the email field
        emailField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(emailField.classList.contains('invalid')).toBe(false);
        expect(emailLabel.classList.contains('invalid')).toBe(false);
    });

    test('validateEmail should update elements correctly for empty fields', () => {
        // set the email value
        emailField.value = '';

        // Trigger the blur event on the email field
        emailField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(emailField.classList.contains('invalid')).toBe(false);
        expect(emailLabel.classList.contains('invalid')).toBe(false);
    });

    test('validateEmail should update elements correctly for emails with plus signs', () => {
        // set the email value
        emailField.value = 'testemail+01@archive.org';

        // Trigger the blur event on the email field
        emailField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(emailField.classList.contains('invalid')).toBe(false);
        expect(emailLabel.classList.contains('invalid')).toBe(false);
    });

    test('validateEmail should update elements correctly for emails with no punctuation', () => {
        // set the password values
        emailField.value = 'testemail';

        // Trigger the blur event on the email fields
        emailField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(emailField.classList.contains('invalid')).toBe(true);
        expect(emailLabel.classList.contains('invalid')).toBe(true);
    });

    test('validateEmail should update elements correctly for emails with invalid punctuation', () => {
        // set the email values
        emailField.value = 'testemail@archive-org';

        // Trigger the blur event on the email fields
        emailField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(emailField.classList.contains('invalid')).toBe(true);
        expect(emailLabel.classList.contains('invalid')).toBe(true);
    });
});

describe('Username tests', () => {
    let usernameLabel, usernameField

    beforeEach(() => {
        // call the function
        initSignupForm();

        //declare the elements
        usernameLabel = document.querySelector('label[for="username"]');
        usernameField = document.getElementById('username');
    })

    test('validateUsername should update elements correctly on success', () => {
        // set the username value
        usernameField.value = 'username123';

        // Trigger the blur event on the username field
        usernameField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(usernameField.classList.contains('invalid')).toBe(false);
        expect(usernameLabel.classList.contains('invalid')).toBe(false);
    });

    test('validateUsername should update elements correctly for empty fields', () => {
        // set the username value
        usernameField.value = '';

        // Trigger the blur event on the username field
        usernameField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(usernameField.classList.contains('invalid')).toBe(false);
        expect(usernameLabel.classList.contains('invalid')).toBe(false);
    });

    test('validateUsername should update elements correctly for usernames over 20 chars', () => {
        // set the username values
        usernameField.value = 'username1234567891011';

        // Trigger the blur event on the username fields
        usernameField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(usernameField.classList.contains('invalid')).toBe(true);
        expect(usernameLabel.classList.contains('invalid')).toBe(true);
    });

    test('validateusername should update elements correctly for usernames under 3 chars', () => {
        // set the username values
        usernameField.value = 'us';

        // Trigger the blur event on the username fields
        usernameField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(usernameField.classList.contains('invalid')).toBe(true);
        expect(usernameLabel.classList.contains('invalid')).toBe(true);
    });
});


describe('Password tests', () => {
    let passwordLabel, passwordField

    beforeEach(() => {
        // call the function
        initSignupForm();

        //declare the elements
        passwordLabel = document.querySelector('label[for="password"]');
        passwordField = document.getElementById('password');
    })

    test('validatePassword should update elements correctly on success', () => {
        // set the password value
        passwordField.value = 'password123';

        // Trigger the blur event on the password field
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('invalid')).toBe(false);
        expect(passwordLabel.classList.contains('invalid')).toBe(false);
    });

    test('validatePassword should update elements correctly for empty fields', () => {
        // set the password value
        passwordField.value = '';

        // Trigger the blur event on the password field
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('invalid')).toBe(false);
        expect(passwordLabel.classList.contains('invalid')).toBe(false);
    });

    test('validatePassword should update elements correctly for passwords over 20 chars', () => {
        // set the password values
        passwordField.value = 'password1234567891011';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('invalid')).toBe(true);
        expect(passwordLabel.classList.contains('invalid')).toBe(true);
    });

    test('validatePassword should update elements correctly for passwords under 3 chars', () => {
        // set the password values
        passwordField.value = 'pa';

        // Trigger the blur event on the password fields
        passwordField.dispatchEvent(new Event('blur'));

        // Assert that the elements have the expected classes
        expect(passwordField.classList.contains('invalid')).toBe(true);
        expect(passwordLabel.classList.contains('invalid')).toBe(true);
    });
});

describe('Print disability tests', () => {
    let checkbox, selector;

    beforeEach(() => {
        initSignupForm();

        checkbox = document.querySelector('#pd-request');
        selector = document.querySelector('#pda-selector')
    })

    test('Qualifying authority selector only visible when PD checkbox is checked', () => {
        checkbox.checked = false
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        expect(selector.classList.contains('hidden')).toBe(true);

        checkbox.checked = true
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        expect(selector.classList.contains('hidden')).toBe(false);
    })
})
