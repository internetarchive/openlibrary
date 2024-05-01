export function initRealTimeValidation() {
    if (window.grecaptcha) {
        // Callback that is called when grecaptcha.execute() is successful
        function submitCreateAccountForm() {
            const signupForm = document.querySelector('form[name=signup]')
            signupForm.submit()
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
        $(errorDiv).addClass('invalid').text(errorMsg);
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
        $(errorDiv).removeClass('invalid').text('');
    }

    function validateUsername() {
        const value_username = $(this).val();
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
        const value_email = $(this).val();
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

    function validatePasswords() {
        // NOTE: Outdated two-password implementation to be replaced and helper functions to be added in issue #9165
        var value = document.getElementById('password').value;
        var value2 = document.getElementById('password2').value;
        if (value && value2) {
            if (value2 === value) {
                $('#password2Message').removeClass().addClass('darkgreen').text('');
                $('label[for="password2"]').removeClass();
                $(document.getElementById('password2')).removeClass().addClass('required');
            }
            else {
                $(document.getElementById('password2')).removeClass().addClass('required invalid');
                $('label[for="password2"]').removeClass().addClass('invalid');
                $('#password2Message').removeClass().addClass('invalid').text('Passwords didnt match');
            }
        }
        else {
            $('label[for="password2"]').removeClass();
            $(document.getElementById('password2')).removeClass().addClass('required');
            $('#password2Message').removeClass().text('');
        }
    }

    $('#username').on('blur', validateUsername);
    $('#emailAddr').on('blur', validateEmail);
    $('#password, #password2').on('blur', validatePasswords);

    $('#signup').on('click', function(e) {
        e.preventDefault();
        if (window.grecaptcha) {
            window.grecaptcha.execute()
        }
    });
}
