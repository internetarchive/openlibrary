import { ugettext } from './i18n';

export function initRealTimeValidation() {

    $('#username').on('keyup', function(){
        var value = $(this).val();
        $('#userUrl').addClass('darkgreen').text(value).css('font-weight','700');
    });

    function validateUsername() {
        var value = $(this).val();
        if (!value === '') {
            $.ajax({
                url: `/account/validate?username=${value}`,
                type: 'GET',
                success: function(errors) {
                    if (errors.username) {
                        $(document.getElementById('username')).removeClass().addClass('required invalid');
                        $('label[for="username"]').removeClass().addClass('invalid');
                        $('#usernameMessage').removeClass().addClass('invalid').html(`${errors.username}<br>`);
                    } else {
                        $('#usernameMessage').removeClass().addClass('darkgreen').html('<br>');
                        $('label[for="username"]').removeClass();
                        $(document.getElementById('username')).removeClass().addClass('required');
                    }
                }
            });
        }
        else {
            $('label[for="username"]').removeClass();
            $(document.getElementById('username')).removeClass().addClass('required');
            $('#usernameMessage').removeClass().html('<br>');
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
                        $(document.getElementById('emailAddr')).removeClass().addClass('required invalid');
                        $('label[for="emailAddr"]').removeClass().addClass('invalid');
                        $('#emailAddrMessage').removeClass().addClass('invalid').text(errors.email);
                    } else {
                        $('#emailAddrMessage').removeClass().addClass('darkgreen').html('');
                        $('label[for="emailAddr"]').removeClass();
                        $(document.getElementById('emailAddr')).removeClass().addClass('required');
                    }
                }
            });
        }
        else {
            $('label[for="emailAddr"]').removeClass();
            $(document.getElementById('emailAddr')).removeClass().addClass('required');
            $('#emailAddrMessage').removeClass().text('');
        }
    }

    function validatePasswords() {
        var value = document.getElementById('password').value;
        var value2 = document.getElementById('password2').value;
        if (value && value2) {
            if (value2 === value) {
                $(document.getElementById('password2')).removeClass('required invalid');
                $('label[for="password2"]').removeClass('invalid');
                $('#password2Message').removeClass('invalid').addClass('darkgreen').text('');
            }
            else {
                $(document.getElementById('password2')).addClass('required invalid');
                $('label[for="password2"]').addClass('invalid');
                $('#password2Message').removeClass('darkgreen').addClass('invalid').text('Passwords do not match');
            }
        }
        else {
            if (!value) {
                $(document.getElementById('password')).addClass('required');
                $('label[for="password"]').removeClass('invalid');
                $('#passwordMessage').removeClass('invalid').text('');
            }
            $(document.getElementById('password2')).addClass('required');
            $('label[for="password2"]').removeClass('invalid');
            $('#password2Message').removeClass('invalid').text('');
        }
    }

    $('#username').on('blur', validateUsername);
    $('#emailAddr').on('blur', validateEmail);
    $('#password, #password2').on('blur', validatePasswords);

    $('#signup').on('click', function(e) {
        e.preventDefault();
        if (! (window.grecaptcha && window.grecaptcha.getResponse().length)) {
            alert(ugettext('Please complete all fields and click the reCAPTCHA checkbox before proceeding.'));
            return;
        }
        validateEmail();
        validateUsername();
        validatePasswords();
        $(this).closest('form').trigger('submit');
    });
}
