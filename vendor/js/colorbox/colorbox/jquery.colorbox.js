// ColorBox v1.3.6 - a full featured, light-weight, customizable lightbox based on jQuery 1.3
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
	$loadingBay,
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
	bookmark,
	index,
	settings,
	open,
	active,
	
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
		
		onOpen: FALSE,
		onLoad: FALSE,
		onComplete: FALSE,
		onCleanup: FALSE,
		onClosed: FALSE
	};
	
	// ****************
	// HELPER FUNCTIONS
	// ****************
		
	// Convert % values to pixels
	function setSize(size, dimension) {
		dimension = dimension === 'x' ? $window.width() : $window.height();//document.documentElement.clientWidth : document.documentElement.clientHeight;
		return (typeof size === 'string') ? Math.round((size.match(/%/) ? (dimension / 100) * parseInt(size, 10) : parseInt(size, 10))) : size;
	}

	// Checks an href to see if it is a photo.
	// There is a force photo option (photo: true) for hrefs that cannot be matched by this regex.
	function isImage(url) {
		url = $.isFunction(url) ? url.call(element) : url;
		return settings.photo || url.match(/\.(gif|png|jpg|jpeg|bmp)(?:\?([^#]*))?(?:#(\.*))?$/i);
	}
	
	// Assigns functions results to their respective settings.  This allows functions to be used to set ColorBox options.
	function process() {
		for (var i in settings) {
			if ($.isFunction(settings[i]) && i.substring(0, 2) !== 'on') { // checks to make sure the function isn't one of the callbacks, they will be handled at the appropriate time.
			    settings[i] = settings[i].call(element);
			}
		}
		settings.rel = settings.rel || element.rel;
		settings.href = settings.href || element.href;
		settings.title = settings.title || element.title;
	}

	function launch(elem) {
		
		element = elem;
		
		settings = $(element).data(colorbox);
		
		process(); // Convert functions to their returned values.
		
		if (settings.rel && settings.rel !== 'nofollow') {
			$related = $('.cboxElement').filter(function () {
				var relRelated = $(this).data(colorbox).rel || this.rel;
				return (relRelated === settings.rel);
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
			
			bookmark = element;
			
			bookmark.blur(); // Remove the focus from the calling element.
			
			// Set Navigation Key Bindings
			$(document).bind("keydown.cbox_close", function (e) {
				if (e.keyCode === 27) {
					e.preventDefault();
					cboxPublic.close();
				}
			}).bind("keydown.cbox_arrows", function (e) {
				if ($related.length > 1) {
					if (e.keyCode === 37) {
						e.preventDefault();
						$prev.click();
					} else if (e.keyCode === 39) {
						e.preventDefault();
						$next.click();
					}
				}
			});
			
			if (settings.overlayClose) {
				$overlay.css({"cursor": "pointer"}).one('click', cboxPublic.close);
			}
			
			$.event.trigger(cbox_open);
			if (settings.onOpen) {
				settings.onOpen.call(element);
			}
			
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
		
		$current.add($prev).add($next).add($slideshow).add($title).hide();
		
		$close.html(settings.close).show();
		
		cboxPublic.slideshow();
		
		cboxPublic.load();
	}

	// ****************
	// PUBLIC FUNCTIONS
	// Usage format: $.fn.colorbox.close();
	// Usage from within an iframe: parent.$.fn.colorbox.close();
	// ****************
	
	cboxPublic = $.fn.colorbox = function (options, callback) {
		var $this = this;
		
		if (!$this.length) {
			if ($this.selector === '') { // empty selector means a direct call, ie: $.fn.colorbox();
				$this = $('<a/>');
				options.open = TRUE;
			} else { // else the selector didn't match anything, and colorbox should go ahead and return.
				return this;
			}
		}
		
		$this.each(function () {
			var data = $.extend({}, $(this).data(colorbox) ? $(this).data(colorbox) : defaults, options);
			
			$(this).data(colorbox, data).addClass("cboxElement");
			
			if (callback) {
				$(this).data(colorbox).onComplete = callback;
			}
		});
		
		if (options && options.open) {
			launch($this);
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
		
		$loadingBay = $("<div style='position:absolute; top:0; left:0; width:9999px; height:0;'/>");
		
		$('body').prepend($overlay, $cbox.append($wrap, $loadingBay));
				
		if (isIE) {
			$cbox.addClass('cboxIE');
			if (isIE6) {
				$overlay.css('position', 'absolute');
			}
		}
		
		// Add rollover event to navigation elements
		$content.children()
		.bind('mouseover mouseout', function(){
			$(this).toggleClass(hover);
		}).addClass(hover);
		
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
		
		$('.cboxElement').live('click', function (e) {
			if (e.button !== 0 && typeof e.button !== 'undefined') {// checks to see if it was a non-left mouse-click.
				return TRUE;
			} else {
				launch(this);			
				return FALSE;
			}
		});
	};

	cboxPublic.position = function (speed, loadedCallback) {
		var
		animate_speed,
		winHeight = $window.height(),
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
			settings.w = settings.mw && settings.mw < settings.w ? settings.mw : settings.w;
			return settings.w;
		}
		function getHeight(){
			settings.h = settings.h || $loaded.height();
			settings.h = settings.mh && settings.mh < settings.h ? settings.mh : settings.h;
			return settings.h;
		}
		
		$loaded.hide()
		.appendTo($loadingBay)// content has to be appended to the DOM for accurate size calculations.  Appended to an absolutely positioned element, rather than BODY, which avoids an extremely brief display of the vertical scrollbar in Firefox that can occur for a small minority of websites.
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
				
				//Waited until the iframe is added to the DOM & it is visible before setting the src.
				//This increases compatability with pages using DOM dependent JavaScript.
				if(settings.iframe){
					$loaded.append("<iframe id='cboxIframe'" + (settings.scrolling ? " " : "scrolling='no'") + " name='iframe_"+new Date().getTime()+"' frameborder=0 src='"+settings.href+"' " + (isIE ? "allowtransparency='true'" : '') + " />");
				}
				
				$loaded.show();
				
				$title.show().html(settings.title);
				
				if ($related.length>1) {
					$current.html(settings.current.replace(/\{current\}/, index+1).replace(/\{total\}/, $related.length)).show();
					$next.html(settings.next).show();
					$prev.html(settings.previous).show();
					
					if(settings.slideshow){
						$slideshow.show();
					}
				}
				
				$loadingOverlay.hide();
				$loadingGraphic.hide();
				
				$.event.trigger(cbox_complete);
				if (settings.onComplete) {
					settings.onComplete.call(element);
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
		
		/*
		 
		// I decided to comment this out because I can see it causing problems as users
		// really should just set the dimensions on their IMG elements instead,
		// but I'm leaving the code in as it may be useful to someone.
		// To use, uncomment the function and change 'if(textStatus === "success"){ resize(this); }'
		// to 'if(textStatus === "success"){ preload(this); }'
		
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
				if(x >= 0){
					img.onload = loadloop;
					img.src = $imgs[x].src;
				} else {
					resize($ajax);
				}
			}
			
			loadloop();
		}
		*/
		
		element = $related[index];
		
		settings = $(element).data(colorbox);
		
		//convert functions to static values
		process();
		
		$.event.trigger(cbox_load);
		if (settings.onLoad) {
			settings.onLoad.call(element);
		}
		
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
		
		href = settings.href;
		
		$loadingOverlay.show();
		$loadingGraphic.show();
		
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
			resize(settings.html);
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
			$('<div />').appendTo($loadingBay).load(href, function(data, textStatus){
				if(textStatus === "success"){
					resize(this);
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
		if (settings.onCleanup) {
			settings.onCleanup.call(element);
		}
		
		open = FALSE;
		$(document).unbind("keydown.cbox_close keydown.cbox_arrows");
		$window.unbind(cbox_resize+' resize.cboxie6 scroll.cboxie6');
		$overlay.css({cursor: 'auto'}).fadeOut('fast');
		
		$cbox
		.stop(TRUE, FALSE)
		.fadeOut('fast', function () {
			$('#colorbox iframe').attr('src', 'about:blank');
			$loaded.remove();
			$cbox.css({'opacity': 1});
			
			try{
				bookmark.focus();
			} catch (er){
				// do nothing
			}
			
			$.event.trigger(cbox_closed);
			if (settings.onClosed) {
				settings.onClosed.call(element);
			}
		});
	};

	// A method for fetching the current element ColorBox is referencing.
	// returns a jQuery object.
	cboxPublic.element = function(){ return $(element); };

	cboxPublic.settings = defaults;

	// Initializes ColorBox when the DOM has loaded
	$(cboxPublic.init);

}(jQuery));
