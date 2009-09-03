
function twitterOn() {
// SHOW TWITTER NAME INPUT IF PRE-CHECKED
    if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
// SHOW TWITTER NAME INPUT IF CHECKED
    $("input[type=radio]").click(function(){
        if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
    });
};

