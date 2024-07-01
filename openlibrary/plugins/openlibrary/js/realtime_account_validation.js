export function initRealTimeValidation() {
    const signupForm = document.querySelector('form[name=signup]');
    const i18nStrings = JSON.parse(signupForm.dataset.i18n);
    const VALID_EMAIL_RE = /.*@.*\..*/;
    const VALID_USERNAME_RE = /^[a-z0-9-_]{3,20}$/i;
    const PASSWORD_MINLENGTH = 3;
    const PASSWORD_MAXLENGTH = 20;
    const USERNAME_MINLENGTH = 3;
    const USERNAME_MAXLENGTH = 20;

    if (window.grecaptcha) {
        // Callback that is called when grecaptcha.execute() is successful
        // Checks whether reportValidity exists for cross-browser compatibility
        // Includes invalid input count to account for checks not covered by reportValidity
        function submitCreateAccountForm() {
            const numInvalidInputs = signupForm.querySelectorAll('input.invalid').length;
            const isFormattingValid = !signupForm.reportValidity || signupForm.reportValidity()

            if (numInvalidInputs === 0 && isFormattingValid) {
                signupForm.submit();
            }
        }
        window.submitCreateAccountForm = submitCreateAccountForm
    }

    $('#username').on('keyup', function(){
        var value = $(this).val();
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
        const value_username = $(this).val();

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

        clearError('#username', '#usernameMessage');

        $.ajax({
            url: '/account/validate',
            data: { username: value_username },
            type: 'GET',
            success: function(errors) {
                if (errors.username) {
                    renderError('#username', '#usernameMessage', errors.username);
                }
            }
        });
    }

    function validateEmail() {
        const value_email = $(this).val();

        if (value_email === '') {
            clearError('#emailAddr', '#emailAddrMessage');
            return;
        }

        if (!VALID_EMAIL_RE.test(value_email)) {
            renderError('#emailAddr', '#emailAddrMessage', i18nStrings['invalid_email_format']);
            return;
        }

        clearError('#emailAddr', '#emailAddrMessage');

        $.ajax({
            url: '/account/validate',
            data: { email: value_email },
            type: 'GET',
            success: function(errors) {
                if (errors.email) {
                    renderError('#emailAddr', '#emailAddrMessage', errors.email);
                }
            }
        });
    }

    function validatePassword() {
        const value_password = $(this).val();

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

    $('#username').on('blur', validateUsername);
    $('#emailAddr').on('blur', validateEmail);
    $('#password').on('blur', validatePassword);
}
