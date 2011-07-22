// FIX IE FADE PROBLEMS
// COURTESY: Ben Novakovic http://blog.bmn.name/2008/03/jquery-fadeinfadeout-ie-cleartype-glitch/
(function($) {
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
})(jQuery);
// ADD FADE TOGGLE
// COURTESY: Karl Swedberg http://www.learningjquery.com/2006/09/slicker-show-and-hide
jQuery.fn.fadeToggle = function(speed, easing, callback) { 
    return this.animate({opacity: 'toggle'}, speed, easing, callback); 
};
// ADD TEXT TOGGLE 
jQuery.fn.toggleText = function(a, b) {
	return this.each(function() {
		jQuery(this).text(jQuery(this).text() == a ? b : a);
	});
};
function bookCovers(){
$.fn.fixBroken=function(){return this.each(function(){$(this).error(function(){$(this).parent().parent().hide();$(this).parent().parent().next(".SRPCoverBlank").show();});});};
};