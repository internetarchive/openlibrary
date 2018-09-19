/*Scroll to top when arrow up clicked BEGIN*/
$(window).scroll(function() {
    var height = $(window).scrollTop();
    if (height > (window.innerHeight*2)) {
        $('#back2Top').fadeIn();//make the back to top button visible
    } else {
        $('#back2Top').fadeOut();//hide the back to top button  
    }
});
$ (function() {
    $("html, body").animate({ scrollTop: 0 }, "slow");
        return false;
});
