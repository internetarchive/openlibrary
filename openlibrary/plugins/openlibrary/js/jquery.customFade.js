// FIX IE FADE PROBLEMS
// COURTESY: Ben Novakovic http://blog.bmn.name/2008/03/jquery-fadeinfadeout-ie-cleartype-glitch/
export default function addFadeInFunctionsTojQuery($) {
    // books/edit/edition.html, publishers/view.html and subjects.html
    $.fn.customFadeIn = function(speed, callback) {
        $(this).fadeIn(speed, function() {
            if(jQuery.browser.msie)
                $(this).get(0).style.removeAttribute('filter');
            if(callback != undefined)
                callback();
        });
    };
    // books/edit/edition.html
    // covers/change.html
    $.fn.customFadeOut = function(speed, callback) {
        $(this).fadeOut(speed, function() {
            if(jQuery.browser.msie)
                $(this).get(0).style.removeAttribute('filter');
            if(callback != undefined)
                callback();
        });
    };
}
