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
/**
* hoverIntent r5 // 2007.03.27 // jQuery 1.1.2+
* <http://cherne.net/brian/resources/jquery.hoverIntent.html>
* 
* @param  f  onMouseOver function || An object with configuration options
* @param  g  onMouseOut function  || Nothing (use configuration options object)
* @author    Brian Cherne <brian@cherne.net>
*/
(function($){$.fn.hoverIntent=function(f,g){var cfg={sensitivity:7,interval:100,timeout:0};cfg=$.extend(cfg,g?{over:f,out:g}:f);var cX,cY,pX,pY;var track=function(ev){cX=ev.pageX;cY=ev.pageY;};var compare=function(ev,ob){ob.hoverIntent_t=clearTimeout(ob.hoverIntent_t);if((Math.abs(pX-cX)+Math.abs(pY-cY))<cfg.sensitivity){$(ob).unbind("mousemove",track);ob.hoverIntent_s=1;return cfg.over.apply(ob,[ev]);}else{pX=cX;pY=cY;ob.hoverIntent_t=setTimeout(function(){compare(ev,ob);},cfg.interval);}};var delay=function(ev,ob){ob.hoverIntent_t=clearTimeout(ob.hoverIntent_t);ob.hoverIntent_s=0;return cfg.out.apply(ob,[ev]);};var handleHover=function(e){var p=(e.type=="mouseover"?e.fromElement:e.toElement)||e.relatedTarget;while(p&&p!=this){try{p=p.parentNode;}catch(e){p=this;}}if(p==this){return false;}var ev=jQuery.extend({},e);var ob=this;if(ob.hoverIntent_t){ob.hoverIntent_t=clearTimeout(ob.hoverIntent_t);}if(e.type=="mouseover"){pX=ev.pageX;pY=ev.pageY;$(ob).bind("mousemove",track);if(ob.hoverIntent_s!=1){ob.hoverIntent_t=setTimeout(function(){compare(ev,ob);},cfg.interval);}}else{$(ob).unbind("mousemove",track);if(ob.hoverIntent_s==1){ob.hoverIntent_t=setTimeout(function(){delay(ev,ob);},cfg.timeout);}}};return this.mouseover(handleHover).mouseout(handleHover);};})(jQuery);