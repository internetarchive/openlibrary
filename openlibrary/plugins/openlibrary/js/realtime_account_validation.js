import { debounce } from './nonjquery_utils.js';

export function initRealTimeValidation() {
    const signupForm = document.querySelector('form[name=signup]');
    const i18nStrings = JSON.parse(signupForm.dataset.i18n);
    const validationFns = {
        emailAddr: validateEmail,
        username: validateUsername,
        password: validatePassword
    }

    if (window.grecaptcha) {
        // Callback that is called when grecaptcha.execute() is successful
        // Checks whether reportValidity exists for cross-browser compatibility
        // Includes invalid input count to account for checks not covered by reportValidity
        function submitCreateAccountForm() {
            const submitBtn = $('button[name=signup]');
            submitBtn.prop('disabled', true).text(i18nStrings['loading_text']);

            const numInvalidInputs = signupForm.querySelectorAll('input.invalid').length;
            const isFormattingValid = !signupForm.reportValidity || signupForm.reportValidity()

            if (numInvalidInputs === 0 && isFormattingValid) {
                signupForm.submit();
            }
        }
        window.submitCreateAccountForm = submitCreateAccountForm
    }

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
        if (value_username !== '') {
            $.ajax({
                url: '/account/validate',
                data: { username: value_username },
                type: 'GET',
                success: function(errors) {
                    if (errors.username) {
                        renderError('#username', '#usernameMessage', errors.username);
                    } else {
                        clearError('#username', '#usernameMessage');
                    }
                }
            });
        }
        else {
            clearError('#username', '#usernameMessage');
        }
    }

    function validateEmail() {
        const value_email = $('#emailAddr').val();
        if (value_email !== '') {
            $.ajax({
                url: '/account/validate',
                data: { email: value_email },
                type: 'GET',
                success: function(errors) {
                    if (errors.email) {
                        renderError('#emailAddr', '#emailAddrMessage', errors.email);
                    } else {
                        clearError('#emailAddr', '#emailAddrMessage');
                    }
                }
            });
        }
        else {
            clearError('#emailAddr', '#emailAddrMessage');
        }
    }

    function validatePassword() {
        const value_password = $('#password').val();
        if (value_password !== '' && (value_password.length < 3 || value_password.length > 20)) {
            renderError('#password', '#passwordMessage', i18nStrings['password_length_err']);
        }
        else clearError('#password', '#passwordMessage');
    }

    function validateInput(input) {
        const id = $(input).attr('id');
        const validate = validationFns[id];
        validate();
    }

    // Validates previously empty or valid inputs on blur
    $('input').on('blur', function() {
        if (!$(this).hasClass('invalid')) {
            validateInput(this);
        }
    });

    // Validates previously invalid inputs on keyup
    $('input').on('keyup', debounce(function(){
        if ($(this).hasClass('invalid')) {
            validateInput(this);
        }
    }, 50));
}
