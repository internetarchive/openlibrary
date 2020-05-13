export function initRealTimeValidation() {
    $('#username').on('blur', function(){
        var value = $(this).val();
        if(!value==""){
        $.ajax({
                url: "/account/sceenname/rtverify?name="+value,
                type: 'GET',
                success: function(result) {
                    console.log(result);
                    if(result.output == true){
                        $('#validScreenname').removeClass().addClass('darkgreen').text("Screen name is Valid").css('font-weight','700');
                        $('#userUrl').removeClass().addClass('darkgreen').text(value).css('font-weight','700');  
                    }
                    else{
                        $('#validScreenname').removeClass().addClass('invalid').text("Screen name is not Valid").css('font-weight','700');
                        $('#userUrl').removeClass().addClass('hidden');
                    }
                }
            });
        }
        else{
            $('#validScreenname').removeClass().text("");
            $('#userUrl').removeClass().text("");
        }
    });
    $('#password, #password2').on('blur', function(){
        var value = document.getElementById("password").value;
        var value2 = document.getElementById("password2").value;
        if(!value2=='' && !value==''){
            if(value2==value){
                $('#passwordMessage').removeClass().addClass('darkgreen').text("Passwords Match").css('font-weight','700');
            }
            else{
                $('#passwordMessage').removeClass().addClass('invalid').text("Passwords dont match");
            }
        }
        else{
            $('#passwordMessage').removeClass().text("");
        }
    });
    $('#emailAddr').on('blur', function(){
        var value_email = $(this).val();
        if(!value_email==''){
        $.ajax({
                url: "/account/email/rtverify?email="+value_email,
                type: 'GET',
                success: function(result) {
                    if(result.output == true){
                        console.log(result);
                        $('#eMatch').removeClass().addClass('darkgreen').text("Email id is valid").css('font-weight','700');
                    }
                    else{
                        $('#eMatch').removeClass().addClass('invalid').text("Email id is not valid");
                    }
                }
            });
        }
        else{
            $('#eMatch').removeClass().text("");
        }
    });
}