export function initRealTimeValidation() {

    $('#username').on('keyup', function(){
        var value = $(this).val();
        $('#userUrl').addClass('darkgreen').text(value);
    });

    $('#username').on('blur', function(){
        var value = $(this).val();
        if (!value=='') {
        $.ajax({
                url: '/account/sceenname/rtverify?name='+value,
                type: 'GET',
                success: function(result) {
                    console.log(result);
                    if (result.output == true) {
                        $('#usernameMessage').removeClass().addClass('darkgreen').html(result.message+' <br/>');
                        $('label[for="username"]').removeClass();
                        $(document.getElementById('username')).removeClass().addClass('required');
                    }
                    else {
                        $(document.getElementById('username')).removeClass().addClass('required invalid');
                        $('label[for="username"]').removeClass().addClass('invalid');
                        $('#usernameMessage').removeClass().addClass('invalid').html(result.message+' <br/>');
                    }
                }
            });
        }
        else {
            $('label[for="username"]').removeClass();
            $(document.getElementById('username')).removeClass().addClass('required');
            $('#usernameMessage').removeClass().html('<br/>');
        }
    });

    $('#password, #password2').on('blur', function(){
        var value = document.getElementById('password').value;
        var value2 = document.getElementById('password2').value;
        if (!value2=='' && !value=='') {
            if (value2==value) {
                $('#password2Message').removeClass().addClass('darkgreen').text('Passwords Match');
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
    });
    
    $('#emailAddr').on('blur', function(){
        var value_email = $(this).val();
        if (!value_email=='') {
        $.ajax({
                url: '/account/email/rtverify?email='+value_email,
                type: 'GET',
                success: function(result) {
                    if (result.output == true) {
                        console.log(result);
                        $('#emailAddrMessage').removeClass().addClass('darkgreen').text(result.message);
                        $('label[for="emailAddr"]').removeClass();
                        $(document.getElementById('emailAddr')).removeClass().addClass('required');
                    }
                    else {
                        $(document.getElementById('emailAddr')).removeClass().addClass('required invalid');
                        $('label[for="emailAddr"]').removeClass().addClass('invalid');
                        $('#emailAddrMessage').removeClass().addClass('invalid').text(result.message);
                    }
                }
            });
        }
        else {
            $('label[for="emailAddr"]').removeClass();
            $(document.getElementById('emailAddr')).removeClass().addClass('required');
            $('#emailAddrMessage').removeClass().text('');
        }
    });
}
