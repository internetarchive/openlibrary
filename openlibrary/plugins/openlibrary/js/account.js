// used in templates/account/email.html
export function validateEmail() {
    $('form.email').validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            var message;
            if (errors) {
                message = errors == 1 ? 'Hang on... You forgot to provide an updated email address.' : 'Hang on... You forgot to provide an updated email address.';
                $('div#contentMsg span').html(message);
                $('div#contentMsg').show().fadeTo(3000, 1).slideUp();
                $('span.remind').css('font-weight', '700').css('text-decoration', 'underline');
            } else {
                $('div#contentMsg').hide();
            }
        },
        errorClass: 'invalid',
        validClass: 'success',
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find(`label[for=${element.id}]`)
                .addClass(errorClass);
        }
    });
    $('#email').rules('add', {
        required: true,
        email: true,
        messages: {
            required: '',
            email: 'Are you sure that\'s an email address?'
        }
    });
}

// used in templates/account/password.html
export function validatePassword() {
    $('form.password').validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            var message;
            if (errors) {
                message = errors == 1 ? 'Hang on... you missed a field.': 'Hang on... to change your password, we need your current and your new one.';
                $('div#contentMsg span').html(message);
                $('div#contentMsg').show().fadeTo(3000, 1).slideUp();
                $('span.remind').css('font-weight', '700').css('text-decoration', 'underline');
            } else {
                $('div#contentMsg').hide();
            }
        },
        errorClass: 'invalid',
        validClass: 'success',
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find(`label[for=${element.id}]`)
                .addClass(errorClass);
        }
    });
    $('#password').rules('add', {
        required: true,
        messages: {
            required: '.'
        }
    });
    $('#new_password').rules('add', {
        required: true,
        messages: {
            required: ''
        }
    });
}
