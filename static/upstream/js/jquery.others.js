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
// ZEBRA STRIPE TABLES 
function stripeTableOdd() {
    $(".stripeOdd tbody tr:nth-child(odd)").addClass("odd");
};
function stripeTableEven() {
    $(".stripeEven tbody tr:nth-child(even)").addClass("even");
};
function bookCovers(){
$.fn.fixBroken=function(){return this.each(function(){$(this).error(function(){$(this).parent().parent().hide();$(this).parent().parent().next(".SRPCoverBlank").show();});});};
};
//AUTODATE
function autoDate(){
var myMonths=new Array("January","February","March","April","May","June","July","August","September","October","November","December");
var myDays= new Array("Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday");
today=new Date();
thisDay=myDays[today.getDay()]
thisMonth=myMonths[today.getMonth()]
thisYear=today.getFullYear()
thisDate=today.getDate()
switch (thisDate) {
case 1:
dateSuffix="st"
break
case 21:
dateSuffix="st"
break
case 31:
dateSuffix="st"
break    
case 2:  
dateSuffix="nd"  
break    
case 22:
dateSuffix="nd"
break;   
case 3:
dateSuffix="rd"  
break     
case 23:
dateSuffix="rd"  
break      
default:   
dateSuffix="th"
}
todaysDate=thisDay+", "+thisMonth+" "+thisDate+"<sup>"+dateSuffix+"</sup> "+thisYear
document.write(todaysDate)
};
