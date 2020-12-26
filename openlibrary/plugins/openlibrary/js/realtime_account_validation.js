import { ugettext } from './i18n';

export function initRealTimeValidation() {

    $('#username').on('keyup', function(){
        var value = $(this).val();
        $('#userUrl').addClass('darkgreen').text(value).css('font-weight','700');
    });

    function validateUsername() {
        var value = $(this).val();
        if (!value=='') {
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
        if (!value_email=='') {
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
            if (value2==value) {
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
        if (! (window.grecaptcha && window.grecaptcha.getResponse().length)) {
            alert(ugettext('Please complete all fields and click the reCAPTCHA checkbox before proceeding.'));
            return;
        }
        validateEmail();
        validateUsername();
        validatePasswords();
        $(this).closest('form').submit();
    });
}
