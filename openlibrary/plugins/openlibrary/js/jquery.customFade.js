// FIX IE FADE PROBLEMS
// COURTESY: Ben Novakovic http://blog.bmn.name/2008/03/jquery-fadeinfadeout-ie-cleartype-glitch/
export default function addFadeInFunctionsTojQuery($) {
    $.fn.customFadeIn = function(speed, callback) {
        $(this).fadeIn(speed, function() {
            if(jQuery.browser.msie)
                $(this).get(0).style.removeAttribute('filter');
            if(callback != undefined)
                callback();
        });
    };
    $.fn.customFadeOut = function(speed, callback) {
        $(this).fadeOut(speed, function() {
            if(jQuery.browser.msie)
                $(this).get(0).style.removeAttribute('filter');
            if(callback != undefined)
                callback();
        });
    };
    $.fn.CustomFadeTo = function(options) {
        if (options)
            $(this)
                .show()
                .each(function() {
                    if (jQuery.browser.msie) {
                        $(this).attr('oBgColor', $(this).css('background-color'));
                        $(this).css({ 'background-color': (options.bgColor ? options.bgColor : '#fff') })
                    }
                })
                .fadeTo(options.speed, options.opacity, function() {
                    if (jQuery.browser.msie) {
                        if (options.opacity == 0 || options.opacity == 1) {
                            $(this).css({ 'background-color': $(this).attr('oBgColor') }).removeAttr('oBgColor');
                            $(this).get(0).style.removeAttribute('filter');
                        }
                    }
                    if (options.callback != undefined) options.callback();
                });
    };
}
