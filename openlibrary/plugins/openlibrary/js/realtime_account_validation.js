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

    function renderError(inputId, errorDiv, errorMsg) {
        $(`#${inputId}`).addClass('invalid');
        $(`label[for=${inputId}]`).addClass('invalid');
        $(errorDiv).addClass('invalid').text(errorMsg);
    }

    function clearError(inputId, errorDiv) {
        $(`#${inputId}`).removeClass('invalid');
        $(`label[for=${inputId}]`).removeClass('invalid');
        $(errorDiv).removeClass('invalid').text('');
    }

    function validateUsername() {
        var value = $(this).val();
        if (value !== '') {
            $.ajax({
                url: `/account/validate?username=${value}`,
                type: 'GET',
                success: function(errors) {
                    if (errors.username) {
                        renderError('username', '#usernameMessage', errors.username);
                    } else {
                        clearError('username', '#usernameMessage');
                    }
                }
            });
        }
        else {
            clearError('username', '#usernameMessage');
        }
    }

    function validateEmail() {
        var value_email = $(this).val();
        if (!value_email === '') {
            $.ajax({
                url: `/account/validate?email=${encodeURIComponent(value_email)}`,
                type: 'GET',
                success: function(errors) {
                    if (errors.email) {
                        renderError('emailAddr', '#emailAddrMessage', errors.email);
                    } else {
                        clearError('emailAddr', '#emailAddrMessage');
                    }
                }
            });
        }
        else {
            clearError('emailAddr', '#emailAddrMessage');
        }
    }

    function validatePasswords() {
        // NOTE: Outdated two-password implementation to be fixed by issue #9165
        var value = document.getElementById('password').value;
        var value2 = document.getElementById('password2').value;
        if (value && value2) {
            if (value2 !== value) {
                renderError('password', '#passwordMessage', 'Passwords didn\'t match');
            }
            else {
                clearError('password', '#passwordMessage')
            }
        }
        else {
            clearError('password', '#passwordMessage')
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
