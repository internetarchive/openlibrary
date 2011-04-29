// ColorBox v1.3.3 - a full featured, light-weight, customizable lightbox based on jQuery 1.3
// c) 2009 Jack Moore - www.colorpowered.com - jack@colorpowered.com
// Licensed under the MIT license: http://www.opensource.org/licenses/mit-license.php

(function ($) {
	// Shortcuts (to increase compression)
	var colorbox = 'colorbox',
	hover = 'hover',
	TRUE = true,
	FALSE = false,
	cboxPublic,
	isIE = !$.support.opacity,
	isIE6 = isIE && !window.XMLHttpRequest,

	// Event Strings (to increase compression)
	cbox_click = 'click.colorbox',
	cbox_open = 'cbox_open',
	cbox_load = 'cbox_load',
	cbox_complete = 'cbox_complete',
	cbox_cleanup = 'cbox_cleanup',
	cbox_closed = 'cbox_closed',
	cbox_resize = 'resize.cbox_resize',

	// Cached jQuery Object Variables
	$overlay,
	$cbox,
	$wrap,
	$content,
	$topBorder,
	$leftBorder,
	$rightBorder,
	$bottomBorder,
	$related,
	$window,
	$loaded,
	$loadingOverlay,
	$loadingGraphic,
	$title,
	$current,
	$slideshow,
	$next,
	$prev,
	$close,

	// Variables for cached values or use across multiple functions
	interfaceHeight,
	interfaceWidth,
	loadedHeight,
	loadedWidth,
	element,
	index,
	settings,
	open,
	active,
	callback,
	
	// ColorBox Default Settings.	
	// See http://colorpowered.com/colorbox for details.
	defaults = {
		transition: "elastic",
		speed: 350,
		width: FALSE,
		height: FALSE,
		innerWidth: FALSE,
		innerHeight: FALSE,
		initialWidth: "400",
		initialHeight: "400",
		maxWidth: FALSE,
		maxHeight: FALSE,
		scalePhotos: TRUE,
		scrolling: TRUE,
		inline: FALSE,
		html: FALSE,
		iframe: FALSE,
		photo: FALSE,
		href: FALSE,
		title: FALSE,
		rel: FALSE,
		opacity: 0.9,
		preloading: TRUE,
		current: "image {current} of {total}",
		previous: "previous",
		next: "next",
		close: "close",
		open: FALSE,
		overlayClose: TRUE,
		slideshow: FALSE,
		slideshowAuto: TRUE,
		slideshowSpeed: 2500,
		slideshowStart: "start slideshow",
		slideshowStop: "stop slideshow",
		preloadIMG: TRUE
	};

	// ****************
	// HELPER FUNCTIONS
	// ****************
		
	// Convert % values to pixels
	function setSize (size, dimension) {
		dimension = dimension === 'x' ? document.documentElement.clientWidth : document.documentElement.clientHeight;
		return (typeof size === 'string') ? Math.round((size.match(/%/) ? (dimension / 100) * parseInt(size, 10) : parseInt(size, 10))) : size;
	}

	// Checks an href to see if it is a photo.
	// There is a force photo option (photo: true) for hrefs that cannot be matched by this regex.
	function isImage (url) {
		return settings.photo || url.match(/\.(gif|png|jpg|jpeg|bmp)(?:\?([^#]*))?(?:#(\.*))?$/i);
	}
	
	// Assigns functions results to their respective settings.  This allows functions to be used to set ColorBox options.
	function process () {
		for (var i in settings) {
			if (typeof(settings[i]) === 'function') {
			    settings[i] = settings[i].call(element);
			}
		}
	}

	// ****************
	// PUBLIC FUNCTIONS
	// Usage format: $.fn.colorbox.close();
	// Usage from within an iframe: parent.$.fn.colorbox.close();
	// ****************
	
	cboxPublic = $.fn.colorbox = function (options, custom_callback) {
		
		if (this.length) {
			this.each(function () {
				var data = $(this).data(colorbox) ? $.extend({},
					$(this).data(colorbox), options) : $.extend({}, defaults, options);
				$(this).data(colorbox, data).addClass("cboxelement");
			});
		} else {
			$(this).data(colorbox, $.extend({}, defaults, options));
		}
		
		$(this).unbind(cbox_click).bind(cbox_click, function (e) {
			
			element = this;
			
			settings = $(element).data(colorbox);
			
			// Convert functions to their returned values.
			process();
			
			callback = custom_callback || FALSE;
			
			var rel = settings.rel || element.rel;
			
			if (rel && rel !== 'nofollow') {
				$related = $('.cboxelement').filter(function () {
					var relRelated = $(this).data(colorbox).rel || this.rel;
					return (relRelated === rel);
				});
				index = $related.index(element);
				
				// Check direct calls to ColorBox.
				if (index < 0) { 
					$related = $related.add(element);
					index = $related.length - 1;
				}
			
			} else {
				$related = $(element);
				index = 0;
			}
			if (!open) {
				open = TRUE;
				
				active = TRUE; // Prevents the page-change action from queuing up if the visitor holds down the left or right keys.
				
				// Set Navigation Key Bindings
				$().bind("keydown.cbox_close", function (e) {
					if (e.keyCode === 27) {
						e.preventDefault();
						cboxPublic.close();
					}
				}).bind("keydown.cbox_arrows", function(e) {
					if (e.keyCode === 37) {
						e.preventDefault();
						$prev.click();
					} else if (e.keyCode === 39) {
						e.preventDefault();
						$next.click();
					}
				});
				
				if (settings.overlayClose) {
					$overlay.css({"cursor": "pointer"}).one('click', cboxPublic.close);
				}
				
				// Remove the focus from the anchor to prevent accidentally calling
				// ColorBox multiple times (by pressing the 'Enter' key after colorbox has opened, but before the user has clicked on anything else)
				element.blur();
				
				$.event.trigger(cbox_open);
				
				$close.html(settings.close);
				
				$overlay.css({"opacity": settings.opacity}).show();
				
				// Opens inital empty ColorBox prior to content being loaded.
				settings.w = setSize(settings.initialWidth, 'x');
				settings.h = setSize(settings.initialHeight, 'y');
				cboxPublic.position(0);
				
				if (isIE6) {
					$window.bind('resize.cboxie6 scroll.cboxie6', function () {
						$overlay.css({width: $window.width(), height: $window.height(), top: $window.scrollTop(), left: $window.scrollLeft()});
					}).trigger("scroll.cboxie6");
				}
			}
			cboxPublic.slideshow();
			
			cboxPublic.load();
			
			e.preventDefault();
		});
		
		if (options && options.open) {
			$(this).triggerHandler(cbox_click);
		}
		
		return this;
	};

	// Initialize ColorBox: store common calculations, preload the interface graphics, append the html.
	// This preps colorbox for a speedy open when clicked, and lightens the burdon on the browser by only
	// having to run once, instead of each time colorbox is opened.
	cboxPublic.init = function () {
		
		// jQuery object generator to save a bit of space
		function $div(id) {
			return $('<div id="cbox' + id + '"/>');
		}
		
		// Create & Append jQuery Objects
		$window = $(window);
		$cbox = $('<div id="colorbox"/>');
		$overlay = $div("Overlay").hide();
		$wrap = $div("Wrapper");
		$content = $div("Content").append(
			$loaded = $div("LoadedContent").css({width: 0, height: 0}),
			$loadingOverlay = $div("LoadingOverlay"),
			$loadingGraphic = $div("LoadingGraphic"),
			$title = $div("Title"),
			$current = $div("Current"),
			$slideshow = $div("Slideshow"),
			$next = $div("Next"),
			$prev = $div("Previous"),
			$close = $div("Close")
		);
		$wrap.append( // The 3x3 Grid that makes up ColorBox
			$('<div/>').append(
				$div("TopLeft"),
				$topBorder = $div("TopCenter"),
				$div("TopRight")
			),
			$('<div/>').append(
				$leftBorder = $div("MiddleLeft"),
				$content,
				$rightBorder = $div("MiddleRight")
			),
			$('<div/>').append(
				$div("BottomLeft"),
				$bottomBorder = $div("BottomCenter"),
				$div("BottomRight")
			)
		).children().children().css({'float': 'left'});
		$('body').prepend($overlay, $cbox.append($wrap));
				
		if (isIE) {
			$cbox.addClass('cboxIE');
			if (isIE6) {
				$overlay.css('position', 'absolute');
			}
		}
		
		// Add rollover event to navigation elements
		$content.children()
		.addClass(hover)
		.mouseover(function () { $(this).addClass(hover); })
		.mouseout(function () { $(this).removeClass(hover); })
		.hide();
		
		// Cache values needed for size calculations
		interfaceHeight = $topBorder.height() + $bottomBorder.height() + $content.outerHeight(TRUE) - $content.height();//Subtraction needed for IE6
		interfaceWidth = $leftBorder.width() + $rightBorder.width() + $content.outerWidth(TRUE) - $content.width();
		loadedHeight = $loaded.outerHeight(TRUE);
		loadedWidth = $loaded.outerWidth(TRUE);
		
		// Setting padding to remove the need to do size conversions during the animation step.
		$cbox.css({"padding-bottom": interfaceHeight, "padding-right": interfaceWidth}).hide();
		
		// Setup button & key events.
		$next.click(cboxPublic.next);
		$prev.click(cboxPublic.prev);
		$close.click(cboxPublic.close);
		
		// Adding the 'hover' class allowed the browser to load the hover-state
		// background graphics.  The class can now can be removed.
		$content.children().removeClass(hover);
	};

	cboxPublic.position = function (speed, loadedCallback) {
		var
		animate_speed,
		winHeight = document.documentElement.clientHeight,
		// keeps the top and left positions within the browser's viewport.
		posTop = Math.max(winHeight - settings.h - loadedHeight - interfaceHeight,0)/2 + $window.scrollTop(),
		posLeft = Math.max(document.documentElement.clientWidth - settings.w - loadedWidth - interfaceWidth,0)/2 + $window.scrollLeft();
		
		// setting the speed to 0 to reduce the delay between same-sized content.
		animate_speed = ($cbox.width() === settings.w+loadedWidth && $cbox.height() === settings.h+loadedHeight) ? 0 : speed;
		
		// this gives the wrapper plenty of breathing room so it's floated contents can move around smoothly,
		// but it has to be shrank down around the size of div#colorbox when it's done.  If not,
		// it can invoke an obscure IE bug when using iframes.
		$wrap[0].style.width = $wrap[0].style.height = "9999px";
		
		function modalDimensions (that) {
			// loading overlay size has to be sure that IE6 uses the correct height.
			$topBorder[0].style.width = $bottomBorder[0].style.width = $content[0].style.width = that.style.width;
			$loadingGraphic[0].style.height = $loadingOverlay[0].style.height = $content[0].style.height = $leftBorder[0].style.height = $rightBorder[0].style.height = that.style.height;
		}
		
		$cbox.dequeue().animate({width:settings.w+loadedWidth, height:settings.h+loadedHeight, top:posTop, left:posLeft}, {duration: animate_speed,
			complete: function(){
				modalDimensions(this);
				
				active = FALSE;
				
				// shrink the wrapper down to exactly the size of colorbox to avoid a bug in IE's iframe implementation.
				$wrap[0].style.width = (settings.w+loadedWidth+interfaceWidth) + "px";
				$wrap[0].style.height = (settings.h+loadedHeight+interfaceHeight) + "px";
				
				if (loadedCallback) {loadedCallback();}
			},
			step: function(){
				modalDimensions(this);
			}
		});
	};

	cboxPublic.resize = function (object) {
		if(!open){ return; }
		
		var topMargin,
		prev,
		prevSrc,
		next,
		nextSrc,
		photo,
		timeout,
		speed = settings.transition==="none" ? 0 : settings.speed;
		
		$window.unbind(cbox_resize);
		
		if(!object){
			timeout = setTimeout(function(){ // timer allows IE to render the dimensions before attempting to calculate the height
				var $child = $loaded.wrapInner("<div style='overflow:auto'></div>").children(); // temporary wrapper to get an accurate estimate of just how high the total content should be.
				settings.h = $child.height();
				$loaded.css({height:settings.h});
				$child.replaceWith($child.children()); // ditch the temporary wrapper div used in height calculation
				cboxPublic.position(speed);
			}, 1);
			return;
		}
		
		$loaded.remove();
		$loaded = $('<div id="cboxLoadedContent"/>').html(object);
		
		function getWidth(){
			settings.w = settings.w || $loaded.width();
			return settings.w;
		}
		function getHeight(){
			settings.h = settings.h || $loaded.height();
			return settings.h;
		}
		
		$loaded.hide()
		.appendTo($overlay)// content has to be appended to the DOM for accurate size calculations.  Appended to an absolutely positioned element, rather than BODY, which avoids an extremely brief display of the vertical scrollbar in Firefox that can occur for a small minority of websites.
		.css({width:getWidth(), overflow:settings.scrolling ? 'auto' : 'hidden'})
		.css({height:getHeight()})// sets the height independently from the width in case the new width influences the value of height.
		.prependTo($content);
		
		$('#cboxPhoto').css({cssFloat:'none'});// floating the IMG removes the bottom line-height and fixed a problem where IE miscalculates the width of the parent element as 100% of the document width.
		
		// Hides SELECT elements in IE6 because they would otherwise sit on top of the overlay.
		if (isIE6) {
			$('select:not(#colorbox select)').filter(function(){
				return this.style.visibility !== 'hidden';
			}).css({'visibility':'hidden'}).one(cbox_cleanup, function(){
				this.style.visibility = 'inherit';
			});
		}
				
		function setPosition (s) {
			cboxPublic.position(s, function(){
				if (!open) { return; }
				
				if (isIE) {
					//This fadeIn helps the bicubic resampling to kick-in.
					if( photo ){$loaded.fadeIn(100);}
					//IE adds a filter when ColorBox fades in and out that can cause problems if the loaded content contains transparent pngs.
					$cbox[0].style.removeAttribute("filter");
				}
				
				$content.children().show();
				
				//Waited until the iframe is added to the DOM & it is visible before setting the src.
				//This increases compatability with pages using DOM dependent JavaScript.
				if(settings.iframe){
					$loaded.append("<iframe id='cboxIframe'" + (settings.scrolling ? " " : "scrolling='no'") + " name='iframe_"+new Date().getTime()+"' frameborder=0 src='"+(settings.href || element.href)+"' />");
				}
				
				$loadingOverlay.hide();
				$loadingGraphic.hide();
				$slideshow.hide();
				
				if ($related.length>1) {
					$current.html(settings.current.replace(/\{current\}/, index+1).replace(/\{total\}/, $related.length));
					$next.html(settings.next);
					$prev.html(settings.previous);
					
					if(settings.slideshow){
						$slideshow.show();
					}
				} else {
					$current.hide();
					$next.hide();
					$prev.hide();
				}
				
				$title.html(settings.title || element.title);
				
				$.event.trigger(cbox_complete);
				
				if (callback) {
					callback.call(element);
				}
				
				if (settings.transition === 'fade'){
					$cbox.fadeTo(speed, 1, function(){
						if(isIE){$cbox[0].style.removeAttribute("filter");}
					});
				}
				
				$window.bind(cbox_resize, function(){
					cboxPublic.position(0);
				});
			});
		}
		
		if((settings.transition === 'fade' && $cbox.fadeTo(speed, 0, function(){setPosition(0);})) || setPosition(speed)){}
		
		// Preloads images within a rel group
		if (settings.preloading && $related.length>1) {
			prev = index > 0 ? $related[index-1] : $related[$related.length-1];
			next = index < $related.length-1 ? $related[index+1] : $related[0];
			nextSrc = $(next).data(colorbox).href || next.href;
			prevSrc = $(prev).data(colorbox).href || prev.href;
			
			if(isImage(nextSrc)){
				$('<img />').attr('src', nextSrc);
			}
			
			if(isImage(prevSrc)){
				$('<img />').attr('src', prevSrc);
			}
		}
	};

	cboxPublic.load = function () {
		var href, img, setResize, resize = cboxPublic.resize;
		
		active = TRUE;
		
		// Preload loops through the HTML to find IMG elements and loads their sources.
		// This allows the resize method to accurately estimate the dimensions of the new content.
		function preload(html){
			var
			$ajax = $(html),
			$imgs = $ajax.find('img'),
			x = $imgs.length;
			
			function loadloop(){
				var img = new Image();
				x = x-1;
				if(x >= 0 && settings.preloadIMG){
					img.onload = loadloop;
					img.src = $imgs[x].src;
				} else {
					resize($ajax);
				}
			}
			
			loadloop();
		}
		
		element = $related[index];
		
		settings = $(element).data(colorbox);
		
		//convert functions to static values
		process();
		
		$.event.trigger(cbox_load);
		
		// Evaluate the height based on the optional height and width settings.
		settings.h = settings.height ?
				setSize(settings.height, 'y') - loadedHeight - interfaceHeight :
				settings.innerHeight ?
					setSize(settings.innerHeight, 'y') :
					FALSE;
		settings.w = settings.width ?
				setSize(settings.width, 'x') - loadedWidth - interfaceWidth :
				settings.innerWidth ?
					setSize(settings.innerWidth, 'x') :
					FALSE;
		
		// Sets the minimum dimensions for use in image scaling
		settings.mw = settings.w;
		settings.mh = settings.h;
		
		// Re-evaluate the minimum width and height based on maxWidth and maxHeight values.
		// If the width or height exceed the maxWidth or maxHeight, use the maximum values instead.
		if(settings.maxWidth){
			settings.mw = setSize(settings.maxWidth, 'x') - loadedWidth - interfaceWidth;
			settings.mw = settings.w && settings.w < settings.mw ? settings.w : settings.mw;
		}
		if(settings.maxHeight){
			settings.mh = setSize(settings.maxHeight, 'y') - loadedHeight - interfaceHeight;
			settings.mh = settings.h && settings.h < settings.mh ? settings.h : settings.mh;
		}
		
		href = settings.href || $(element).attr("href");
		
		$loadingOverlay.show();
		$loadingGraphic.show();
		$close.show();
				
		if (settings.inline) {
			// Inserts an empty placeholder where inline content is being pulled from.
			// An event is bound to put inline content back when ColorBox closes or loads new content.
			$('<div id="cboxInlineTemp" />').hide().insertBefore($(href)[0]).bind(cbox_load+' '+cbox_cleanup, function(){
				$(this).replaceWith($loaded.children());
			});
			resize($(href));
		} else if (settings.iframe) {
			// IFrame element won't be added to the DOM until it is ready to be displayed,
			// to avoid problems with DOM-ready JS that might be trying to run in that iframe.
			resize(" ");
		} else if (settings.html) {
			preload(settings.html);
		} else if (isImage(href)){
			img = new Image();
			img.onload = function(){
				var percent;
				
				img.onload = null;
				
				img.id = 'cboxPhoto';
				
				$(img).css({margin:'auto', border:'none', display:'block', cssFloat:'left'});
				
				if(settings.scalePhotos){
					setResize = function(){
						img.height -= img.height * percent;
						img.width -= img.width * percent;	
					};
					if(settings.mw && img.width > settings.mw){
						percent = (img.width - settings.mw) / img.width;
						setResize();
					}
					if(settings.mh && img.height > settings.mh){
						percent = (img.height - settings.mh) / img.height;
						setResize();
					}
				}
				
				if (settings.h) {
					img.style.marginTop = Math.max(settings.h - img.height,0)/2 + 'px';
				}
				
				resize(img);
				
				if($related.length > 1){
					$(img).css({cursor:'pointer'}).click(cboxPublic.next);
				}
				
				if(isIE){
					img.style.msInterpolationMode='bicubic';
				}
			};
			img.src = href;
		} else {
			$('<div />').load(href, function(data, textStatus){
				if(textStatus === "success"){
					preload(this);
				} else {
					resize($("<p>Request unsuccessful.</p>"));
				}
			});
		}
	};

	// Navigates to the next page/image in a set.
	cboxPublic.next = function () {
		if(!active){
			index = index < $related.length-1 ? index+1 : 0;
			cboxPublic.load();
		}
	};
	
	cboxPublic.prev = function () {
		if(!active){
			index = index > 0 ? index-1 : $related.length-1;
			cboxPublic.load();
		}
	};

	cboxPublic.slideshow = function () {
		var stop, timeOut, className = 'cboxSlideshow_';
		
		$slideshow.bind(cbox_closed, function(){
			$slideshow.unbind();
			clearTimeout(timeOut);
			$cbox.removeClass(className+"off"+" "+className+"on");
		});
		
		function start(){
			$slideshow
			.text(settings.slideshowStop)
			.bind(cbox_complete, function(){
				timeOut = setTimeout(cboxPublic.next, settings.slideshowSpeed);
			})
			.bind(cbox_load, function(){
				clearTimeout(timeOut);	
			}).one("click", function(){
				stop();
				$(this).removeClass(hover);
			});
			$cbox.removeClass(className+"off").addClass(className+"on");
		}
		
		stop = function(){
			clearTimeout(timeOut);
			$slideshow
			.text(settings.slideshowStart)
			.unbind(cbox_complete+' '+cbox_load)
			.one("click", function(){
				start();
				timeOut = setTimeout(cboxPublic.next, settings.slideshowSpeed);
				$(this).removeClass(hover);
			});
			$cbox.removeClass(className+"on").addClass(className+"off");
		};
		
		if(settings.slideshow && $related.length>1){
			if(settings.slideshowAuto){
				start();
			} else {
				stop();
			}
		}
	};

	// Note: to use this within an iframe use the following format: parent.$.fn.colorbox.close();
	cboxPublic.close = function () {
		$.event.trigger(cbox_cleanup);
		open = FALSE;
		$().unbind("keydown.cbox_close keydown.cbox_arrows");
		$window.unbind(cbox_resize+' resize.cboxie6 scroll.cboxie6');
		$overlay.css({cursor: 'auto'}).fadeOut('fast');
		
		$cbox
		.stop(TRUE, FALSE)
		.fadeOut('fast', function () {
			$loaded.remove();
			$cbox.css({'opacity': 1});
			$content.children().hide();
			$.event.trigger(cbox_closed);
		});
	};

	// A method for fetching the current element ColorBox is referencing.
	// returns a jQuery object.
	cboxPublic.element = function(){ return $(element); };

	cboxPublic.settings = defaults;

	// Initializes ColorBox when the DOM has loaded
	$(cboxPublic.init);

}(jQuery));
