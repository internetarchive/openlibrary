import { debounce } from './nonjquery_utils.js';

export function initSignupForm() {
    const signupForm = document.querySelector('form[name=signup]');
    const submitBtn = document.querySelector('button[name=signup]')
    const i18nStrings = JSON.parse(signupForm.dataset.i18n);
    const emailLoadingIcon = $('.ol-signup-form__input--emailAddr .ol-signup-form__icon--loading');
    const usernameLoadingIcon = $('.ol-signup-form__input--username .ol-signup-form__icon--loading');
    const emailSuccessIcon = $('.ol-signup-form__input--emailAddr .ol-signup-form__icon--success');
    const usernameSuccessIcon = $('.ol-signup-form__input--username .ol-signup-form__icon--success');

    // Keep the same with openlibrary/plugins/upstream/forms.py
    const VALID_EMAIL_RE = /^.*@.*\..*$/;
    const VALID_USERNAME_RE = /^[a-z0-9-_]{3,20}$/i;
    const PASSWORD_MINLENGTH = 3;
    const PASSWORD_MAXLENGTH = 20;
    const USERNAME_MINLENGTH = 3;
    const USERNAME_MAXLENGTH = 20;

    if (window.grecaptcha) {
        // Callback that is called when grecaptcha.execute() is successful
        function submitCreateAccountForm() {
            signupForm.submit();
        }
        window.submitCreateAccountForm = submitCreateAccountForm
    }

    // Checks whether reportValidity exists for cross-browser compatibility
    // Includes invalid input count to account for checks not covered by reportValidity
    $(signupForm).on('submit', function(e) {
        e.preventDefault();
        const numInvalidInputs = signupForm.querySelectorAll('input.invalid').length;
        const isFormattingValid = !signupForm.reportValidity || signupForm.reportValidity();
        if (numInvalidInputs === 0 && isFormattingValid && window.grecaptcha) {
            $(submitBtn).prop('disabled', true).text(i18nStrings['loading_text']);
            window.grecaptcha.execute();
        }
    });

    $('#username').on('keyup', function(){
        const value = $(this).val();
        $('#userUrl').addClass('darkgreen').text(value).css('font-weight','700');
    });

    /**
     * Renders an error message for a given input in a given error div.
     *
     * @param {string} inputId The ID (incl #) of the input the error relates to
     * @param {string} errorDiv The ID (incl #) of the div where the error msg will be rendered
     * @param {string} errorMsg The error message text
     */
    function renderError(inputId, errorDiv, errorMsg) {
        $(inputId).addClass('invalid');
        $(`label[for=${inputId.slice(1)}]`).addClass('invalid');
        $(errorDiv).text(errorMsg);
    }

    /**
     * Clears error styling and message for a given input and error div.
     *
     * @param {string} inputId The ID (incl #) of the input the error relates to
     * @param {string} errorDiv The ID (incl #) of the div where the error msg is currently rendered
     */
    function clearError(inputId, errorDiv) {
        $(inputId).removeClass('invalid');
        $(`label[for=${inputId.slice(1)}]`).removeClass('invalid');
        $(errorDiv).text('');
    }

    function validateUsername() {
        const value_username = $('#username').val();

        usernameSuccessIcon.hide();

        if (value_username === '') {
            clearError('#username', '#usernameMessage');
            return;
        }

        if (value_username.length < USERNAME_MINLENGTH || value_username.length > USERNAME_MAXLENGTH) {
            renderError('#username', '#usernameMessage', i18nStrings['username_length_err']);
            return;
        }

        if (!(VALID_USERNAME_RE.test(value_username))) {
            renderError('#username', '#usernameMessage', i18nStrings['username_char_err']);
            return;
        }

        usernameLoadingIcon.show();

        $.ajax({
            url: '/account/validate',
            data: { username: value_username },
            type: 'GET',
            success: function(errors) {
                usernameLoadingIcon.hide();

                if (errors.username) {
                    renderError('#username', '#usernameMessage', errors.username);
                } else {
                    clearError('#username', '#usernameMessage');
                    usernameSuccessIcon.show();
                }
            }
        });
    }

    function validateEmail() {
        const value_email = $('#emailAddr').val();

        emailSuccessIcon.hide();

        if (value_email === '') {
            clearError('#emailAddr', '#emailAddrMessage');
            return;
        }

        if (!VALID_EMAIL_RE.test(value_email)) {
            renderError('#emailAddr', '#emailAddrMessage', i18nStrings['invalid_email_format']);
            return;
        }

        emailLoadingIcon.show();

        $.ajax({
            url: '/account/validate',
            data: { email: value_email },
            type: 'GET',
            success: function(errors) {
                emailLoadingIcon.hide();

                if (errors.email) {
                    renderError('#emailAddr', '#emailAddrMessage', errors.email);
                } else {
                    clearError('#emailAddr', '#emailAddrMessage');
                    emailSuccessIcon.show();
                }
            }
        });
    }

    function validatePassword() {
        const value_password = $('#password').val();

        if (value_password === '') {
            clearError('#password', '#passwordMessage');
            return;
        }

        if (value_password.length < PASSWORD_MINLENGTH || value_password.length > PASSWORD_MAXLENGTH) {
            renderError('#password', '#passwordMessage', i18nStrings['password_length_err']);
            return;
        }

        clearError('#password', '#passwordMessage');
    }

    // Maps input ID attribute to corresponding validation function
    function validateInput(input) {
        const id = $(input).attr('id');
        if (id === 'emailAddr') {
            validateEmail();
        } else if (id === 'username') {
            validateUsername();
        } else if (id === 'password') {
            validatePassword();
        } else {
            throw new Error('Input validation function not found');
        }
    }

    // Validates inputs already marked as invalid on value change
    $('form[name=signup] input').on('input', debounce(function(){
        if ($(this).hasClass('invalid')) {
            validateInput(this);
        }
    }, 50));

    // Validates all other inputs (i.e. not already marked as invalid) on blur
    $('form[name=signup] input').on('blur', function() {
        if (!$(this).hasClass('invalid')) {
            validateInput(this);
        }
    });
}

export function initLoginForm() {
    const loginForm = $('form[name=login]');
    const loadingText = loginForm.data('i18n')['loading_text'];

    loginForm.on('submit', () => {
        $('button[type=submit]').prop('disabled', true).text(loadingText);
    })
}
