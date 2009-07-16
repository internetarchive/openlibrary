/**
 * Copyright (c) 2006-2007, Bill W. Scott
 * All rights reserved.
 *
 * This work is licensed under the Creative Commons Attribution 2.5 License. To view a copy 
 * of this license, visit http://creativecommons.org/licenses/by/2.5/ or send a letter to 
 * Creative Commons, 543 Howard Street, 5th Floor, San Francisco, California, 94105, USA.
 *
 * This work was created by Bill Scott (billwscott.com, looksgoodworkswell.com).
 * 
 * The only attribution I require is to keep this notice of copyright & license 
 * in this original source file.
 *
 * Version 1.0 - 10.21.2008
 *
 */
YAHOO.namespace("extension");

/**
* @class 
* The carousel class manages a content list (a set of LI elements within an UL list)  that can be displayed horizontally or vertically. The content can be scrolled back and forth  with or without animation. The content can reference static HTML content or the list items can  be created dynamically on-the-fly (with or without Ajax). The navigation and event handling  can be externalized from the class.
* @param {object|string} carouselElementID The element ID (id name or id object) of the DIV that will become a carousel
* @param {object} carouselCfg The configuration object literal containing the configuration that should be set for this module. See configuration documentation for more details.
* @constructor
*/
YAHOO.extension.Carousel = function(carouselElementID, carouselCfg) {
 		this.init(carouselElementID, carouselCfg);
	};

YAHOO.extension.Carousel.prototype = {


	/**
	 * Constant denoting that the carousel size is unbounded (no limits set on scrolling)
	 * @type number
	 */
	UNBOUNDED_SIZE: 1000000,
	
	/**
	 * Initializes the carousel object and all of its local members.
     * @param {object|string} carouselElementID The element ID (id name or id object) 
     * of the DIV that will become a carousel
     * @param {object} carouselCfg The configuration object literal containing the 
     * configuration that should be set for this module. See configuration documentation for more details.
	 */
	init: function(carouselElementID, carouselCfg) {

		var oThis = this;
		
		/**
		 * For deprecation.
		 * getItem is the replacement for getCarouselItem
		 */
		this.getCarouselItem = this.getItem;
		
		// CSS style classes
		var carouselListClass = "carousel-list";
		var carouselClipRegionClass = "carousel-clip-region";
		var carouselNextClass = "carousel-next";
		var carouselPrevClass = "carousel-prev";

 		this._carouselElemID = carouselElementID;
 		this.carouselElem = YAHOO.util.Dom.get(carouselElementID);

 		this._prevEnabled = true;
 		this._nextEnabled = true;
 		
 		// Create the config object
 		this.cfg = new YAHOO.util.Config(this);

		/**
		 * scrollBeforeAmount property. 
		 * Normally, set to 0, this is how much you are allowed to
		 * scroll below the first item. Setting it to 2 allows you
		 * to scroll to the -1 position. 
		 * However, the load handlers will not be asked to load anything
		 * below 1.
		 *
		 * A good example is the spotlight example which treats the middle item
		 * as the "selected" item. It sets scrollBeforeAmount to 2 and 
		 * scrollAfterAmount to 2.
		 *
		 * The actual items loaded would be from 1 to 15 (size=15),
		 * but scrolling range would be -1 to 17.
		 */
		this.cfg.addProperty("scrollBeforeAmount", { 
			value:0, 
			handler: function(type, args, carouselElem) {
			},
			validator: oThis.cfg.checkNumber
		} );		

		/**
		 * scrollAfterAmount property. 
		 * Normally, set to 0, this is how much you are allowed to
		 * scroll past the size. Setting it to 2 allows you
		 * to scroll to the size+scrollAfterAmount position. 
		 * However, the load handlers will not be asked to load anything
		 * beyond size.
		 *
		 * A good example is the spotlight example which treats the middle item
		 * as the "selected" item. It sets scrollBeforeAmount to 2 and 
		 * scrollAfterAmount to 2.
		 *
		 * The actual items loaded would be from 1 to 15 (size=15),
		 * but scrolling range would be -1 to 17.
		 */
		this.cfg.addProperty("scrollAfterAmount", { 
			value:0, 
			handler: function(type, args, carouselElem) {
			},
			validator: oThis.cfg.checkNumber
		} );		

		/**
		 * loadOnStart property. 
		 * If true, will call loadInitHandler on startup.
		 * If false, will not. Useful for delaying the initialization
		 * of the carousel for a later time after creation.
		 */
		this.cfg.addProperty("loadOnStart", { 
			value:true, 
			handler: function(type, args, carouselElem) {
				// no action, only affects startup
			},
			validator: oThis.cfg.checkBoolean
		} );		

		/**
		 * orientation property. 
		 * Either "horizontal" or "vertical". Changes carousel from a 
		 * left/right style carousel to a up/down style carousel.
		 */
		this.cfg.addProperty("orientation", { 
			value:"horizontal", 
			handler: function(type, args, carouselElem) {
				oThis.reload();
			},
			validator: function(orientation) {
			    if(typeof orientation == "string") {
			        return ("horizontal,vertical".indexOf(orientation.toLowerCase()) != -1);
			    } else {
					return false;
				}
			}
		} );		

		/**
		 * size property. 
		 * The upper bound for scrolling in the 'next' set of content. 
		 * Set to a large value by default (this means unlimited scrolling.) 
		 */
		this.cfg.addProperty("size", { 
			value:this.UNBOUNDED_SIZE,
			handler: function(type, args, carouselElem) {
				oThis.reload();
			},
			validator: oThis.cfg.checkNumber
		} );

		/**
		 * numVisible property. 
		 * The number of items that will be visible.
		 */
		this.cfg.addProperty("numVisible", { 
			value:3,
			handler: function(type, args, carouselElem) {
				oThis.reload();
			},
			validator: oThis.cfg.checkNumber
		} );

		/**
		 * firstVisible property. 
		 * Sets which item should be the first visible item in the carousel. Use to set which item will
		 * display as the first element when the carousel is first displayed. After the carousel is created,
		 * you can manipulate which item is the first visible by using the moveTo() or scrollTo() convenience
		 * methods. Can be < 1 or greater than size if the scrollBeforeAmount or scrollAmountAfter has been set
		 * to non-zero values.
		 */
		this.cfg.addProperty("firstVisible", { 
			value:1,
			handler: function(type, args, carouselElem) {
				oThis.moveTo(args[0]);
			},
			validator: oThis.cfg.checkNumber
		} );

		/**
		 * scrollInc property. 
		 * The number of items to scroll by. Think of this as the page increment.
		 */
		this.cfg.addProperty("scrollInc", { 
			value:3,
			handler: function(type, args, carouselElem) {
			},
			validator: oThis.cfg.checkNumber
		} );
		
		/**
		 * animationSpeed property. 
		 * The time (in seconds) it takes to complete the scroll animation. 
		 * If set to 0, animated transitions are turned off and the new page of content is 
		 * moved immdediately into place.
		 */
		this.cfg.addProperty("animationSpeed", { 
			value:0.25,
			handler: function(type, args, carouselElem) {
				oThis.animationSpeed = args[0];
			},
			validator: oThis.cfg.checkNumber
		} );

		/**
		 * animationMethod property. 
		 * The <a href="http://developer.yahoo.com/yui/docs/animation/YAHOO.util.Easing.html">YAHOO.util.Easing</a> 
		 * method.
		 */
		this.cfg.addProperty("animationMethod", { 
			value:  YAHOO.util.Easing.easeOut,
			handler: function(type, args, carouselElem) {
			}
		} );
		
		/**
		 * animationCompleteHandler property. 
		 * JavaScript function that is called when the Carousel finishes animation 
		 * after a next or previous nagivation. 
		 * Only invoked if animationSpeed > 0. 
		 * Two parameters are passed: type (set to 'onAnimationComplete') and 
		 * args array (args[0] = direction [either: 'next' or 'previous']).
		 */
		this.cfg.addProperty("animationCompleteHandler", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._animationCompleteEvt) {
					oThis._animationCompleteEvt.unsubscribe(oThis._currAnimationCompleteHandler, oThis);
				}
				oThis._currAnimationCompleteHandler = args[0];
				if(oThis._currAnimationCompleteHandler) {
					if(!oThis._animationCompleteEvt) {
						oThis._animationCompleteEvt = new YAHOO.util.CustomEvent("onAnimationComplete", oThis);
					}
					oThis._animationCompleteEvt.subscribe(oThis._currAnimationCompleteHandler, oThis);
				}
			}
		} );
		
		/**
		 * autoPlay property. 
		 * Specifies how many milliseconds to periodically auto scroll the content. 
		 * If set to 0 (default) then autoPlay is turned off. 
		 * If the user interacts by clicking left or right navigation, autoPlay is turned off. 
		 * You can restart autoPlay by calling the <em>startAutoPlay()</em>. 
		 * If you externally control navigation (with your own event handlers) 
		 * then you may want to turn off the autoPlay by calling<em>stopAutoPlay()</em>
		 */
		this.cfg.addProperty("autoPlay", { 
			value:0,
			handler: function(type, args, carouselElem) {
				var autoPlay = args[0];
				if(autoPlay > 0)
					oThis.startAutoPlay();
				else
					oThis.stopAutoPlay();
			}
		} );
		
		/**
		 * wrap property. 
		 * Specifies whether to wrap when at the end of scrolled content. When the end is reached,
		 * the carousel will scroll backwards to the item 1 (the animationSpeed parameter is used to 
		 * determine how quickly it should animate back to the start.)
		 * Ignored if the <em>size</em> attribute is not explicitly set 
		 * (i.e., value equals YAHOO.extension.Carousel.UNBOUNDED_SIZE)
		 */
		this.cfg.addProperty("wrap", { 
			value:false,
			handler: function(type, args, carouselElem) {
			},
			validator: oThis.cfg.checkBoolean
		} );
		
		/**
		 * navMargin property. 
		 * The margin space for the navigation controls. This is only useful for horizontal carousels 
		 * in which you have embedded navigation controls. 
		 * The <em>navMargin</em> allocates space between the left and right margins 
		 * (each navMargin wide) giving space for the navigation controls.
		 */
		this.cfg.addProperty("navMargin", { 
			value:0,
			handler: function(type, args, carouselElem) {
				oThis.calculateSize();		
			},
			validator: oThis.cfg.checkNumber
		} );
		
		/**
		 * revealAmount property. 
		 * The amount to reveal of what comes before and what comes after the firstVisible and
		 * the lastVisible items. Setting this will provide a slight preview that something 
		 * exists before and after, providing an additional hint for the user.
		 * The <em>revealAmount</em> will reveal the specified number of pixels for any item
		 * before the firstVisible and an item after the lastVisible. Additionall, the
		 * loadNextHandler and loadPrevHandler methods will be passed a start or end that guarantees
		 * the revealed item will be loaded (if set to non-zero).
		 */
		this.cfg.addProperty("revealAmount", { 
			value:0,
			handler: function(type, args, carouselElem) {
				oThis.reload();
			},
			validator: oThis.cfg.checkNumber
		} );
		
		// For backward compatibility. Deprecated.
		this.cfg.addProperty("prevElementID", { 
			value: null,
			handler: function(type, args, carouselElem) {
				if(oThis._carouselPrev) {
					YAHOO.util.Event.removeListener(oThis._carouselPrev, "click", oThis._scrollPrev);
				} 
				oThis._prevElementID = args[0];
				if(oThis._prevElementID == null) {
					oThis._carouselPrev = YAHOO.util.Dom.getElementsByClassName(carouselPrevClass, 
														"div", oThis.carouselElem)[0];
				} else {
					oThis._carouselPrev = YAHOO.util.Dom.get(oThis._prevElementID);
				}
				YAHOO.util.Event.addListener(oThis._carouselPrev, "click", oThis._scrollPrev, oThis);
			}
		});
		
		/**
		 * prevElement property. 
		 * An element or elements that will provide the previous navigation control.
		 * prevElement may be a single element or an array of elements. The values may be strings denoting
		 * the ID of the element or the object itself.
		 * If supplied, then events are wired to this control to fire scroll events to move the carousel to
		 * the previous content. 
		 * You may want to provide your own interaction for controlling the carousel. If
		 * so leave this unset and provide your own event handling mechanism.
		 */
		this.cfg.addProperty("prevElement", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._carouselPrev) {
					YAHOO.util.Event.removeListener(oThis._carouselPrev, "click", oThis._scrollPrev);
				} 
				oThis._prevElementID = args[0];
				if(oThis._prevElementID == null) {
					oThis._carouselPrev = YAHOO.util.Dom.getElementsByClassName(carouselPrevClass, 
														"div", oThis.carouselElem)[0];
				} else {
					oThis._carouselPrev = YAHOO.util.Dom.get(oThis._prevElementID);
				}
				YAHOO.util.Event.addListener(oThis._carouselPrev, "click", oThis._scrollPrev, oThis);
			}
		} );
		
		// For backward compatibility. Deprecated.
		this.cfg.addProperty("nextElementID", { 
			value: null,
			handler: function(type, args, carouselElem) {
				if(oThis._carouselNext) {
					YAHOO.util.Event.removeListener(oThis._carouselNext, "click", oThis._scrollNext);
				} 
				oThis._nextElementID = args[0];
				if(oThis._nextElementID == null) {
					oThis._carouselNext = YAHOO.util.Dom.getElementsByClassName(carouselNextClass, 
														"div", oThis.carouselElem);
				} else {
					oThis._carouselNext = YAHOO.util.Dom.get(oThis._nextElementID);
				}
				if(oThis._carouselNext) {
					YAHOO.util.Event.addListener(oThis._carouselNext, "click", oThis._scrollNext, oThis);
				} 
			}
		});
		
		/**
		 * nextElement property. 
		 * An element or elements that will provide the next navigation control.
		 * nextElement may be a single element or an array of elements. The values may be strings denoting
		 * the ID of the element or the object itself.
		 * If supplied, then events are wired to this control to fire scroll events to move the carousel to
		 * the next content. 
		 * You may want to provide your own interaction for controlling the carousel. If
		 * so leave this unset and provide your own event handling mechanism.
		 */
		this.cfg.addProperty("nextElement", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._carouselNext) {
					YAHOO.util.Event.removeListener(oThis._carouselNext, "click", oThis._scrollNext);
				} 
				oThis._nextElementID = args[0];
				if(oThis._nextElementID == null) {
					oThis._carouselNext = YAHOO.util.Dom.getElementsByClassName(carouselNextClass, 
														"div", oThis.carouselElem);
				} else {
					oThis._carouselNext = YAHOO.util.Dom.get(oThis._nextElementID);
				}
				if(oThis._carouselNext) {
					YAHOO.util.Event.addListener(oThis._carouselNext, "click", oThis._scrollNext, oThis);
				} 
			}
		} );

		/**
		 * disableSelection property. 
		 * Suggestion by Jenny Mok.
		 * Specifies whether to turn off browser text selection within the carousel. Default is true.
		 * If true, nothing inside the browser may be text selected. This prevents the ugly effect of
		 * the user accidentally clicking and starting a text selection for the elements in the carousel.
		 * If false, selection is allowed. You might want to turn this on if you want the items within
		 * a carousel to be selectable by the browser.
		 */
		this.cfg.addProperty("disableSelection", { 
			value:true,
			handler: function(type, args, carouselElem) {
			},
			validator: oThis.cfg.checkBoolean
		} );
		

		/**
		 * loadInitHandler property. 
		 * JavaScript function that is called when the Carousel needs to load 
		 * the initial set of visible items. Two parameters are passed: 
		 * type (set to 'onLoadInit') and an argument array (args[0] = start index, args[1] = last index).
		 */
		this.cfg.addProperty("loadInitHandler", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._loadInitHandlerEvt) {
					oThis._loadInitHandlerEvt.unsubscribe(oThis._currLoadInitHandler, oThis);
				}
				oThis._currLoadInitHandler = args[0];
				if(oThis._currLoadInitHandler) {
					if(!oThis._loadInitHandlerEvt) {
						oThis._loadInitHandlerEvt = new YAHOO.util.CustomEvent("onLoadInit", oThis);
					}
					oThis._loadInitHandlerEvt.subscribe(oThis._currLoadInitHandler, oThis);
				}
			}
		} );
		
		/**
		 * loadNextHandler property. 
		 * JavaScript function that is called when the Carousel needs to load 
		 * the next set of items (in response to the user navigating to the next set.) 
		 * Two parameters are passed: type (set to 'onLoadNext') and 
		 * args array (args[0] = start index, args[1] = last index).
		 */
		this.cfg.addProperty("loadNextHandler", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._loadNextHandlerEvt) {
					oThis._loadNextHandlerEvt.unsubscribe(oThis._currLoadNextHandler, oThis);
				}
				oThis._currLoadNextHandler = args[0];
				if(oThis._currLoadNextHandler) {
					if(!oThis._loadNextHandlerEvt) {
						oThis._loadNextHandlerEvt = new YAHOO.util.CustomEvent("onLoadNext", oThis);
					}
					oThis._loadNextHandlerEvt.subscribe(oThis._currLoadNextHandler, oThis);
				}
			}
		} );
				
		/**
		 * loadPrevHandler property. 
		 * JavaScript function that is called when the Carousel needs to load 
		 * the previous set of items (in response to the user navigating to the previous set.) 
		 * Two parameters are passed: type (set to 'onLoadPrev') and args array 
		 * (args[0] = start index, args[1] = last index).
		 */
		this.cfg.addProperty("loadPrevHandler", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._loadPrevHandlerEvt) {
					oThis._loadPrevHandlerEvt.unsubscribe(oThis._currLoadPrevHandler, oThis);
				}
				oThis._currLoadPrevHandler = args[0];
				if(oThis._currLoadPrevHandler) {
					if(!oThis._loadPrevHandlerEvt) {
						oThis._loadPrevHandlerEvt = new YAHOO.util.CustomEvent("onLoadPrev", oThis);
					}
					oThis._loadPrevHandlerEvt.subscribe(oThis._currLoadPrevHandler, oThis);
				}
			}
		} );
		
		/**
		 * prevButtonStateHandler property. 
		 * JavaScript function that is called when the enabled state of the 
		 * 'previous' control is changing. The responsibility of 
		 * this method is to enable or disable the 'previous' control. 
		 * Two parameters are passed to this method: <em>type</em> 
		 * (which is set to "onPrevButtonStateChange") and <em>args</em>, 
		 * an array that contains two values. 
		 * The parameter args[0] is a flag denoting whether the 'previous' control 
		 * is being enabled or disabled. The parameter args[1] is the element object 
		 * derived from the <em>prevElement</em> parameter.
		 * If you do not supply a prevElement then you will need to track
		 * the elements that you would want to enable/disable while handling the state change.
		 */
		this.cfg.addProperty("prevButtonStateHandler", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._currPrevButtonStateHandler) {
					oThis._prevButtonStateHandlerEvt.unsubscribe(oThis._currPrevButtonStateHandler, oThis);
				}

				oThis._currPrevButtonStateHandler = args[0];
				
				if(oThis._currPrevButtonStateHandler) {
					if(!oThis._prevButtonStateHandlerEvt) {
						oThis._prevButtonStateHandlerEvt = new YAHOO.util.CustomEvent("onPrevButtonStateChange", oThis);
					}
					oThis._prevButtonStateHandlerEvt.subscribe(oThis._currPrevButtonStateHandler, oThis);
				}
			}
		} );
		
		/**
		 * nextButtonStateHandler property. 
		 * JavaScript function that is called when the enabled state of the 
		 * 'next' control is changing. The responsibility of 
		 * this method is to enable or disable the 'next' control. 
		 * Two parameters are passed to this method: <em>type</em> 
		 * (which is set to "onNextButtonStateChange") and <em>args</em>, 
		 * an array that contains two values. 
		 * The parameter args[0] is a flag denoting whether the 'next' control 
		 * is being enabled or disabled. The parameter args[1] is the element object 
		 * derived from the <em>nextElement</em> parameter.
		 * If you do not supply a nextElement then you will need to track
		 * the elements that you would want to enable/disable while handling the state change.
		 */
		this.cfg.addProperty("nextButtonStateHandler", { 
			value:null,
			handler: function(type, args, carouselElem) {
				if(oThis._currNextButtonStateHandler) {
					oThis._nextButtonStateHandlerEvt.unsubscribe(oThis._currNextButtonStateHandler, oThis);
				}
				oThis._currNextButtonStateHandler = args[0];
				
				if(oThis._currNextButtonStateHandler) {
					if(!oThis._nextButtonStateHandlerEvt) {
						oThis._nextButtonStateHandlerEvt = new YAHOO.util.CustomEvent("onNextButtonStateChange", oThis);
					}
					oThis._nextButtonStateHandlerEvt.subscribe(oThis._currNextButtonStateHandler, oThis);
				}
			}
		} );
		
		
 		if(carouselCfg) {
 			this.cfg.applyConfig(carouselCfg);
 		}
		YAHOO.util.Event.addListener(this.carouselElem, 'mousedown', this._handleMouseDownForSelection, this, true);
		
		this._origFirstVisible = this.cfg.getProperty("firstVisible");
		
		// keep a copy of curr handler so it can be removed when a new handler is set
		this._currLoadInitHandler = this.cfg.getProperty("loadInitHandler");
		this._currLoadNextHandler = this.cfg.getProperty("loadNextHandler");
		this._currLoadPrevHandler = this.cfg.getProperty("loadPrevHandler");
		this._currPrevButtonStateHandler = this.cfg.getProperty("prevButtonStateHandler");
		this._currNextButtonStateHandler = this.cfg.getProperty("nextButtonStateHandler");
		this._currAnimationCompleteHandler = this.cfg.getProperty("animationCompleteHandler");
		
		this._nextElementID = this.cfg.getProperty("nextElementID");
		if(!this._nextElementID) 
			this._nextElementID = this.cfg.getProperty("nextElement");
		
		this._prevElementID = this.cfg.getProperty("prevElementID");
		if(!this._prevElementID) 
			this._prevElementID = this.cfg.getProperty("prevElement");

		this._autoPlayTimer = null;
		this._priorLastVisible = this._priorFirstVisible = this.cfg.getProperty("firstVisible");
		this._lastPrebuiltIdx = 0;
// this._currSize = 0;
		 		
 		// prefetch elements
 		this.carouselList = YAHOO.util.Dom.getElementsByClassName(carouselListClass, 
												"ul", this.carouselElem)[0];
							
		if(this._nextElementID == null) {
			this._carouselNext = YAHOO.util.Dom.getElementsByClassName(carouselNextClass, 
												"div", this.carouselElem)[0];
		} else {
			this._carouselNext = YAHOO.util.Dom.get(this._nextElementID);
		}

		if(this._prevElementID == null) {
 			this._carouselPrev = YAHOO.util.Dom.getElementsByClassName(carouselPrevClass, 
												"div", this.carouselElem)[0];
		} else {
			this._carouselPrev = YAHOO.util.Dom.get(this._prevElementID);
		}
		
		this._clipReg = YAHOO.util.Dom.getElementsByClassName(carouselClipRegionClass, 
												"div", this.carouselElem)[0];
												
		// add a style class dynamically so that the correct styles get applied for a vertical carousel
		if(this.isVertical()) {
			YAHOO.util.Dom.addClass(this.carouselList, "carousel-vertical");
		}
		
		// initialize the animation objects for next/previous
 		this._scrollNextAnim = new YAHOO.util.Motion(this.carouselList, this.scrollNextParams, 
   								this.cfg.getProperty("animationSpeed"), this.cfg.getProperty("animationMethod"));
 		this._scrollPrevAnim = new YAHOO.util.Motion(this.carouselList, this.scrollPrevParams, 
   								this.cfg.getProperty("animationSpeed"), this.cfg.getProperty("animationMethod"));
		
		// If they supplied a nextElementID then wire an event listener for the click
		if(this._carouselNext) {
			YAHOO.util.Event.addListener(this._carouselNext, "click", this._scrollNext, this);
		} 
		
		// If they supplied a prevElementID then wire an event listener for the click
		if(this._carouselPrev) {
			YAHOO.util.Event.addListener(this._carouselPrev, "click", this._scrollPrev, this);
		}
				
		// Wire up the various event handlers that they might have supplied
		var loadInitHandler = this.cfg.getProperty("loadInitHandler");
		if(loadInitHandler) {
			this._loadInitHandlerEvt = new YAHOO.util.CustomEvent("onLoadInit", this);
			this._loadInitHandlerEvt.subscribe(loadInitHandler, this);
		}
		var loadNextHandler = this.cfg.getProperty("loadNextHandler");
		if(loadNextHandler) {
			this._loadNextHandlerEvt = new YAHOO.util.CustomEvent("onLoadNext", this);
			this._loadNextHandlerEvt.subscribe(loadNextHandler, this);
		}
		var loadPrevHandler = this.cfg.getProperty("loadPrevHandler");
		if(loadPrevHandler) {
			this._loadPrevHandlerEvt = new YAHOO.util.CustomEvent("onLoadPrev", this);
			this._loadPrevHandlerEvt.subscribe(loadPrevHandler, this);
		}
		var animationCompleteHandler = this.cfg.getProperty("animationCompleteHandler");
		if(animationCompleteHandler) {
			this._animationCompleteEvt = new YAHOO.util.CustomEvent("onAnimationComplete", this);
			this._animationCompleteEvt.subscribe(animationCompleteHandler, this);
		}
		var prevButtonStateHandler = this.cfg.getProperty("prevButtonStateHandler");
		if(prevButtonStateHandler) {
			this._prevButtonStateHandlerEvt = new YAHOO.util.CustomEvent("onPrevButtonStateChange", 
							this);
			this._prevButtonStateHandlerEvt.subscribe(prevButtonStateHandler, this);
		}
		var nextButtonStateHandler = this.cfg.getProperty("nextButtonStateHandler");
		if(nextButtonStateHandler) {
			this._nextButtonStateHandlerEvt = new YAHOO.util.CustomEvent("onNextButtonStateChange", this);
			this._nextButtonStateHandlerEvt.subscribe(nextButtonStateHandler, this);
		}
			
		// Since loading may take some time, wire up a listener to fire when at least the first
		// element actually gets loaded
		var visibleExtent = this._calculateVisibleExtent();
  		YAHOO.util.Event.onAvailable(this._carouselElemID + "-item-"+
					visibleExtent.start,  this._calculateSize, this);
  		

  		// Call the initial loading sequence
		if(this.cfg.getProperty("loadOnStart"))
			this._loadInitial();	

	},
	
	// this set to carousel
	_handleMouseDownForSelection: function(e) {
		if(this.cfg.getProperty("disableSelection")) {
			YAHOO.util.Event.preventDefault(e);
			YAHOO.util.Event.stopPropagation(e);
		}
	},
	// /////////////////// Public API //////////////////////////////////////////

	/**
	 * Clears all items from the list and resets to the carousel to its original initial state.
	 */
	clear: function() {
		// remove all items from the carousel for dynamic content
		var loadInitHandler = this.cfg.getProperty("loadInitHandler");
		if(loadInitHandler) {
			this._removeChildrenFromNode(this.carouselList);
			this._lastPrebuiltIdx = 0;
		}
		// turn off autoplay
		this.stopAutoPlay(); // should we only turn this off for dynamic during reload?
		
		this._priorLastVisible = this._priorFirstVisible = this._origFirstVisible;
		
		// is this redundant since moveTo will set this?	
		this.cfg.setProperty("firstVisible", this._origFirstVisible, true);		
		this.moveTo(this._origFirstVisible);
	},
	
	/**
	 * Clears all items from the list and calls the loadInitHandler to load new items into the list. 
	 * The carousel size is reset to the original size set during creation.
	 * @param {number}	numVisible	Optional parameter: numVisible. 
	 * If set, the carousel will resize on the reload to show numVisible items.
	 */
	reload: function(numVisible) {
		// this should be deprecated, not needed since can be set via property change
	    if(this._isValidObj(numVisible)) {
			this.cfg.setProperty("numVisible", numVisible);
	    }
		this.clear();
		
		// clear resets back to start
		var visibleExtent = this._calculateVisibleExtent();
		YAHOO.util.Event.onAvailable(this._carouselElemID+"-item-"+visibleExtent.start,
		 								this._calculateSize, this);  		
		this._loadInitial();
		
	},

	load: function() {
		var visibleExtent = this._calculateVisibleExtent();
		
		YAHOO.util.Event.onAvailable(this._carouselElemID + "-item-"+visibleExtent.start, 
						this._calculateSize, this);  		
		this._loadInitial();
	},
		
	/**
	 * With patch from Dan Hobbs for handling unordered loading.
	 * @param {number}	idx	which item in the list to potentially create. 
	 * If item already exists it will not create a new item.
	 * @param {string}	innerHTML	The innerHTML string to use to create the contents of an LI element.
	 * @param {string}	itemClass	A class optionally supplied to add to the LI item created
	 */
	addItem: function(idx, innerHTMLOrElem, itemClass) {
		
		if(idx > this.cfg.getProperty("size")) {
			return null;
		}
		
        var liElem = this.getItem(idx);

		// Need to create the li
		if(!this._isValidObj(liElem)) {
			liElem = this._createItem(idx, innerHTMLOrElem);
			this.carouselList.appendChild(liElem);
			
		} else if(this._isValidObj(liElem.placeholder)) {		
	    	var newLiElem = this._createItem(idx, innerHTMLOrElem);
			this.carouselList.replaceChild(newLiElem, liElem);
			liElem = newLiElem;
		}
		
		// if they supplied an item class add it to the element
		if(this._isValidObj(itemClass)){
			YAHOO.util.Dom.addClass(liElem, itemClass);
		}
		
		/**
		 * Not real comfortable with this line of code. It exists for vertical
		 * carousels for IE6. For some reason LI elements are not displaying
		 * unless you after the fact set the display to block. (Even though
	     * the CSS sets vertical LIs to display:block)
	     */
		if(this.isVertical())
			setTimeout( function() { liElem.style.display="block"; }, 1 );		
				
		return liElem;

	},

	/**
	 * Inserts a new LI item before the index specified. Uses the innerHTML to create the contents of the new LI item
	 * @param {number}	refIdx	which item in the list to insert this item before. 
	 * @param {string}	innerHTML	The innerHTML string to use to create the contents of an LI element.
	 */
	insertBefore: function(refIdx, innerHTML) {
		// don't allow insertion beyond the size
		if(refIdx >= this.cfg.getProperty("size")) {
			return null;
		}
		
		if(refIdx < 1) {
			refIdx = 1;
		}
		
		var insertionIdx = refIdx - 1;
		
		if(insertionIdx > this._lastPrebuiltIdx) {
			this._prebuildItems(this._lastPrebuiltIdx, refIdx); // is this right?
		}
		
		var liElem = this._insertBeforeItem(refIdx, innerHTML);
		
		this._enableDisableControls();
		
		return liElem;
	},
	
	/**
	 * Inserts a new LI item after the index specified. Uses the innerHTML to create the contents of the new LI item
	 * @param {number}	refIdx	which item in the list to insert this item after. 
	 * @param {string}	innerHTML	The innerHTML string to use to create the contents of an LI element.
	 */
	insertAfter: function(refIdx, innerHTML) {
	
		if(refIdx > this.cfg.getProperty("size")) {
			refIdx = this.cfg.getProperty("size");
		}
		
		var insertionIdx = refIdx + 1;			
		
		// if we are inserting this item past where we have prebuilt items, then
		// prebuild up to this point.
		if(insertionIdx > this._lastPrebuiltIdx) {
			this._prebuildItems(this._lastPrebuiltIdx, insertionIdx+1);
		}

		var liElem = this._insertAfterItem(refIdx, innerHTML);		

		if(insertionIdx > this.cfg.getProperty("size")) {
			this.cfg.setProperty("size", insertionIdx, true);
		}
		
		this._enableDisableControls();

		return liElem;
	},	

	/**
	 * Simulates a next button event. Causes the carousel to scroll the next set of content into view.
	 */
	scrollNext: function() {
		this._scrollNext(null, this);
		
		// we know the timer has expired.
		//if(this._autoPlayTimer) clearTimeout(this._autoPlayTimer);
		this._autoPlayTimer = null;
		if(this.cfg.getProperty("autoPlay") !== 0) {
			this._autoPlayTimer = this.startAutoPlay();
		}
	},
	
	/**
	 * Simulates a prev button event. Causes the carousel to scroll the previous set of content into view.
	 */
	scrollPrev: function() {
		this._scrollPrev(null, this);
	},
	
	/**
	 * Scrolls the content to place itemNum as the start item in the view 
	 * (if size is specified, the last element will not scroll past the end.). 
	 * Uses current animation speed & method.
	 * @param {number}	newStart	The item to scroll to. 
	 */
	scrollTo: function(newStart) {
		this._position(newStart, true);
	},

	/**
	 * Moves the content to place itemNum as the start item in the view 
	 * (if size is specified, the last element will not scroll past the end.) 
	 * Ignores animation speed & method; moves directly to the item. 
	 * Note that you can also set the <em>firstVisible</em> property upon initialization 
	 * to get the carousel to start at a position different than 1.	
	 * @param {number}	newStart	The item to move directly to. 
	 */
	moveTo: function(newStart) {
		this._position(newStart, false);
	},

	/**
	 * Starts up autoplay. If autoPlay has been stopped (by calling stopAutoPlay or by user interaction), 
	 * you can start it back up by using this method.
	 * @param {number}	interval	optional parameter that sets the interval 
	 * for auto play the next time that autoplay fires. 
	 */
	startAutoPlay: function(interval) {
		// if interval is passed as arg, then set autoPlay to this interval.
		if(this._isValidObj(interval)) {
			this.cfg.setProperty("autoPlay", interval, true);
		}
		
		// if we already are playing, then do nothing.
		if(this._autoPlayTimer !== null) {
			return this._autoPlayTimer;
		}
				
		var oThis = this;  
		var autoScroll = function() { oThis.scrollNext(); };
		this._autoPlayTimer = setTimeout( autoScroll, this.cfg.getProperty("autoPlay") );
		
		return this._autoPlayTimer;
	},

	/**
	 * Stops autoplay. Useful for when you want to control what events will stop the autoplay feature. 
	 * Call <em>startAutoPlay()</em> to restart autoplay.
	 */
	stopAutoPlay: function() {
		if (this._autoPlayTimer !== null) {
			clearTimeout(this._autoPlayTimer);
			this._autoPlayTimer = null;
		}
	},
	
	/**
	 * Returns whether the carousel's orientation is set to vertical.
	 */
	isVertical: function() {
		return (this.cfg.getProperty("orientation") != "horizontal");
	},
	
	
	/**
	 * Check to see if an element (by index) has been loaded or not. If the item is simply pre-built, but not
	 * loaded this will return false. If the item has not been pre-built it will also return false.
	 * @param {number}	idx	Index of the element to check load status for. 
	 */
	isItemLoaded: function(idx) {
		var liElem = this.getItem(idx);
		
		// if item exists and is not a placeholder, then it is already loaded.
		if(this._isValidObj(liElem) && !this._isValidObj(liElem.placeholder)) {
			return true;
		}
		
		return false;
	},
	
	/**
	 * Lookup the element object for a carousel list item by index.
	 * @param {number}	idx	Index of the element to lookup. 
	 */
	getItem: function(idx) {
		var elemName = this._carouselElemID + "-item-" + idx;
 		var liElem = YAHOO.util.Dom.get(elemName);
		return liElem;	
	},
	
	show: function() {
		YAHOO.util.Dom.setStyle(this.carouselElem, "display", "block");
		this.calculateSize();
	},
	
	hide: function() {
		YAHOO.util.Dom.setStyle(this.carouselElem, "display", "none");
	},

	calculateSize: function() {
 		var ulKids = this.carouselList.childNodes;
 		var li = null;
		for(var i=0; i<ulKids.length; i++) {
		
			li = ulKids[i];
			if(li.tagName == "LI" || li.tagName == "li") {
				break;
			}
		}

		var navMargin = this.cfg.getProperty("navMargin");
		var numVisible = this.cfg.getProperty("numVisible");
		var firstVisible = this.cfg.getProperty("firstVisible");
		var pl = this._getStyleVal(li, "paddingLeft");
		var pr = this._getStyleVal(li, "paddingRight");
		var ml = this._getStyleVal(li, "marginLeft");
		var mr = this._getStyleVal(li, "marginRight");
		var pt = this._getStyleVal(li, "paddingTop");
		var pb = this._getStyleVal(li, "paddingBottom");
		var mt = this._getStyleVal(li, "marginTop");
		var mb = this._getStyleVal(li, "marginBottom");

		YAHOO.util.Dom.removeClass(this.carouselList, "carousel-vertical");
		YAHOO.util.Dom.removeClass(this.carouselList, "carousel-horizontal");
		if(this.isVertical()) {
			var liPaddingMarginWidth = pl + pr + ml + mr;
			YAHOO.util.Dom.addClass(this.carouselList, "carousel-vertical");
			var liPaddingMarginHeight = pt + pb + mt + mb;
			
			var upt = this._getStyleVal(this.carouselList, "paddingTop");
			var upb = this._getStyleVal(this.carouselList, "paddingBottom");
			var umt = this._getStyleVal(this.carouselList, "marginTop")
			var umb = this._getStyleVal(this.carouselList, "marginBottom")
			var ulPaddingHeight = upt + upb + umt + umb;

			// try to reveal the amount taking into consideration the margin & padding.
			// This guarantees that this.revealAmount of pixels will be shown on both sides
			var revealAmt = (this._isExtraRevealed()) ?
			 			(this.cfg.getProperty("revealAmount")+(liPaddingMarginHeight)/2) : 0;

			// get the height from the height computed style not the offset height
			// The reason is that on IE the offsetHeight when some part of the margin is
			// explicitly set to 'auto' can cause accessing that value to crash AND
			// on FF, in certain cases the actual value used for the LI's height is fractional
			// For example, while li.offsetHeight might return 93, YAHOO.util.Dom.getStyle(li, "height") 
			// would return "93.2px". This fractional value will affect the scrolling, so it must be
			// factored in for FF.
			// The caveat is that for IE, you will need to set the LI's height explicitly
			// REPLACED: this.scrollAmountPerInc = (li.offsetHeight + liPaddingMarginHeight);
			// WITH:
			var liHeight = this._getStyleVal(li, "height", true);
			this.scrollAmountPerInc = (liHeight + liPaddingMarginHeight);
			
			var liWidth = this._getStyleVal(li, "width");
			this.carouselElem.style.width = (liWidth + liPaddingMarginWidth) + "px";			
			this._clipReg.style.height = 
					(this.scrollAmountPerInc * numVisible + revealAmt*2 + 
					ulPaddingHeight) + "px";
//alert(this._clipReg.style.height);
			this.carouselElem.style.height = 
				(this.scrollAmountPerInc * numVisible + revealAmt*2 + navMargin*2 +
					ulPaddingHeight) + "px";

			// possible that the umt+upt is needed... need to test this.
			var revealTop = (this._isExtraRevealed()) ? 
					(revealAmt - (Math.abs(mt-mb)+Math.abs(pt-pb))/2
					) : 
					0;
			YAHOO.util.Dom.setStyle(this.carouselList, "position", "relative");
			YAHOO.util.Dom.setStyle(this.carouselList, "top", "" + revealTop + "px");

			// if we set the initial start > 1 then this will adjust the scrolled location
			var currY = YAHOO.util.Dom.getY(this.carouselList);	
			YAHOO.util.Dom.setY(this.carouselList, currY - this.scrollAmountPerInc*(firstVisible-1));

		// --- HORIZONTAL
		} else {
			YAHOO.util.Dom.addClass(this.carouselList, "carousel-horizontal");

			var upl = this._getStyleVal(this.carouselList, "paddingLeft");
			var upr = this._getStyleVal(this.carouselList, "paddingRight");
			var uml = this._getStyleVal(this.carouselList, "marginLeft")
			var umr = this._getStyleVal(this.carouselList, "marginRight")
			var ulPaddingWidth = upl + upr + uml + umr;

			var liMarginWidth = ml + mr;
			var liPaddingMarginWidth = liMarginWidth + pr + pl;
			
			// try to reveal the amount taking into consideration the margin & padding.
			// This guarantees that this.revealAmount of pixels will be shown on both sides
			var revealAmt = (this._isExtraRevealed()) ?
			 					(this.cfg.getProperty("revealAmount")+(liPaddingMarginWidth)/2) : 0;
			
			var liWidth = li.offsetWidth; 
			this.scrollAmountPerInc = liWidth + liMarginWidth;
			
			this._clipReg.style.width = 
					(this.scrollAmountPerInc*numVisible + revealAmt*2) + "px";
			this.carouselElem.style.width =
			 		(this.scrollAmountPerInc*numVisible + navMargin*2 + revealAmt*2 + 
					ulPaddingWidth) + "px";
			
			var revealLeft = (this._isExtraRevealed()) ? 
					(revealAmt - (Math.abs(mr-ml)+Math.abs(pr-pl))/2 - (uml+upl)
					) : 
					0;
			YAHOO.util.Dom.setStyle(this.carouselList, "position", "relative");
			YAHOO.util.Dom.setStyle(this.carouselList, "left", "" + revealLeft + "px");

			// if we set the initial start > 1 then this will adjust the scrolled location
			var currX = YAHOO.util.Dom.getX(this.carouselList);
			YAHOO.util.Dom.setX(this.carouselList, currX - this.scrollAmountPerInc*(firstVisible-1));
		}
	},
	
	// Hides the cfg object
	setProperty: function(property, value, silent) {
		this.cfg.setProperty(property, value, silent);
	},
	
	getProperty: function(property) {
		return this.cfg.getProperty(property);
	},
	
	getFirstItemRevealed: function() {
		return this._firstItemRevealed;
	},
	getLastItemRevealed: function() {
		return this._lastItemRevealed;
	},
	
	// Just for convenience and to be symmetrical with getFirstVisible
	getFirstVisible: function() {
		return this.cfg.getProperty("firstVisible");
	},
	
	getLastVisible: function() {
		var firstVisible = this.cfg.getProperty("firstVisible");
		var numVisible = this.cfg.getProperty("numVisible");
		
		return firstVisible + numVisible - 1;
	},
	
	// /////////////////// PRIVATE API //////////////////////////////////////////
	_getStyleVal : function(li, style, returnFloat) {
		var styleValStr = YAHOO.util.Dom.getStyle(li, style);
		
		var styleVal = returnFloat ? parseFloat(styleValStr) : parseInt(styleValStr, 10);
		if(style=="height" && isNaN(styleVal)) {
			styleVal = li.offsetHeight;
		} else if(isNaN(styleVal)) {
			styleVal = 0;
		}
		return styleVal;
	},
	
	_calculateSize: function(me) {
		me.calculateSize();
		me.show();
		//YAHOO.util.Dom.setStyle(me.carouselElem, "visibility", "visible");
	},

	// From Mike Chambers: http://weblogs.macromedia.com/mesh/archives/2006/01/removing_html_e.html
	_removeChildrenFromNode: function(node)
	{
		if(!this._isValidObj(node))
		{
      		return;
		}
   
		var len = node.childNodes.length;
   
		while (node.hasChildNodes())
		{
			node.removeChild(node.firstChild);
		}
	},
	
	_prebuildLiElem: function(idx) {
		if(idx < 1) return;
		
		
		var liElem = document.createElement("li");
		liElem.id = this._carouselElemID + "-item-" + idx;
		// this is default flag to know that we're not really loaded yet.
		liElem.placeholder = true;   
		this.carouselList.appendChild(liElem);
		
		this._lastPrebuiltIdx = (idx > this._lastPrebuiltIdx) ? idx : this._lastPrebuiltIdx;
	},
	
	_createItem: function(idx, innerHTMLOrElem) {
		if(idx < 1) return;
		
		
		var liElem = document.createElement("li");
		liElem.id = this._carouselElemID + "-item-" + idx;

		// if String then assume innerHTML, else an elem object
		if(typeof(innerHTMLOrElem) === "string") {
			liElem.innerHTML = innerHTMLOrElem;
		} else {
			liElem.appendChild(innerHTMLOrElem);
		}
		
		return liElem;
	},
	
	// idx is the location to insert after
	_insertAfterItem: function(refIdx, innerHTMLOrElem) {
		return this._insertBeforeItem(refIdx+1, innerHTMLOrElem);
	},
	
	
	_insertBeforeItem: function(refIdx, innerHTMLOrElem) {

		var refItem = this.getItem(refIdx);
		var size = this.cfg.getProperty("size");
		if(size != this.UNBOUNDED_SIZE) {
			this.cfg.setProperty("size", size + 1, true);
		}
				
		for(var i=this._lastPrebuiltIdx; i>=refIdx; i--) {
			var anItem = this.getItem(i);
			if(this._isValidObj(anItem)) {
				anItem.id = this._carouselElemID + "-item-" + (i+1);
			}
		}

		var liElem = this._createItem(refIdx, innerHTMLOrElem);
		
		var insertedItem = this.carouselList.insertBefore(liElem, refItem);
		this._lastPrebuiltIdx += 1;
		
		return liElem;
	},
	
	// TEST THIS... think it has to do with prebuild
	insertAfterEnd: function(innerHTMLOrElem) {
		return this.insertAfter(this.cfg.getProperty("size"), innerHTMLOrElem);
	},
		
	_position: function(newStart, showAnimation) {
		// do we bypass the isAnimated check?
		var currStart = this._priorFirstVisible;
		if(newStart > currStart) {
			var inc = newStart - currStart;
			this._scrollNextInc(inc, showAnimation);
		} else {
			var dec = currStart - newStart;
			this._scrollPrevInc(dec, showAnimation);
		}
	},

	_scrollPrev: function(e, carousel) {
		if(e !== null) { // event fired this so disable autoplay
			carousel.stopAutoPlay();
		}
		carousel._scrollPrevInc(carousel.cfg.getProperty("scrollInc"), 
							(carousel.cfg.getProperty("animationSpeed") !== 0));
	},
	
	// event handler
	_scrollNext: function(e, carousel) {		
		if(e !== null) { // event fired this so disable autoplay
			carousel.stopAutoPlay();
		}

		carousel._scrollNextInc(carousel.cfg.getProperty("scrollInc"), 
								(carousel.cfg.getProperty("animationSpeed") !== 0));
	},
	
	
	_handleAnimationComplete: function(type, args, argList) {
		var carousel = argList[0];
		var direction = argList[1];
		
		carousel._animationCompleteEvt.fire(direction);

		
	},
	
	// If EVERY item is already loaded in the range then return true
	// Also prebuild whatever is not already created.
	_areAllItemsLoaded: function(first, last) {
		var itemsLoaded = true;
		for(var i=first; i<=last; i++) {
			var liElem = this.getItem(i);
			
			// If the li elem does not exist, then prebuild it in the correct order
			// but still flag as not loaded (just prebuilt the li item.
			if(!this._isValidObj(liElem)) {
				this._prebuildLiElem(i);
				itemsLoaded = false;
			// but if the item exists and is a placeholder, then
			// note that this item is not loaded (only a placeholder)
			} else if(this._isValidObj(liElem.placeholder)) {
				itemsLoaded = false;
			}
		}
		return itemsLoaded;
	}, 
	
	_prebuildItems: function(first, last) {
		for(var i=first; i<=last; i++) {
			var liElem = this.getItem(i);
			
			// If the li elem does not exist, then prebuild it in the correct order
			// but still flag as not loaded (just prebuilt the li item.
			if(!this._isValidObj(liElem)) {
				this._prebuildLiElem(i);
			}
		}
	}, 
	
	_isExtraRevealed: function() {
		return (this.cfg.getProperty("revealAmount") > 0);
	},

	// probably no longer need carousel passed in, this should be correct now.
	_scrollNextInc: function(inc, showAnimation) {		

		if(this._scrollNextAnim.isAnimated() || this._scrollPrevAnim.isAnimated()) {
			return false;
		}

		var numVisible = this.cfg.getProperty("numVisible");
		var currStart = this._priorFirstVisible;
		var currEnd = this._priorLastVisible;
		var size = this.cfg.getProperty("size");

		var scrollExtent = this._calculateAllowableScrollExtent();
		
		if(this.cfg.getProperty("wrap") && currEnd == scrollExtent.end) {
			this.scrollTo(scrollExtent.start); // might need to check animation is on or not
			return;
		}

		// increment start by inc
		var newStart = currStart + inc;		
		var newEnd = newStart + numVisible - 1;

		// If we are past the end, adjust or wrap
		if(newEnd > scrollExtent.end) {
			newEnd = scrollExtent.end;
			newStart = newEnd - numVisible + 1;
		}

		inc = newStart - currStart;

		// at this point the following variables are set
		// inc... amount to increment by
		// newStart... the firstVisible item after the scroll
		// newEnd... the last item visible after the scroll

		this.cfg.setProperty("firstVisible", newStart, true);


		if(inc > 0) {
			if(this._isValidObj(this.cfg.getProperty("loadNextHandler"))) {
				var visibleExtent = this._calculateVisibleExtent(newStart, newEnd);
				var cacheStart = (currEnd+1) < visibleExtent.start ? (currEnd+1) : visibleExtent.start;						
				var alreadyCached = this._areAllItemsLoaded(cacheStart, visibleExtent.end);
				this._loadNextHandlerEvt.fire(visibleExtent.start, visibleExtent.end, alreadyCached);
			}

			if(showAnimation) {
	 			var nextParams = { points: { by: [-this.scrollAmountPerInc*inc, 0] } };
	 			if(this.isVertical()) {
	 				nextParams = { points: { by: [0, -this.scrollAmountPerInc*inc] } };
	 			}

	 			this._scrollNextAnim = new YAHOO.util.Motion(this.carouselList, 
	 							nextParams, 
   								this.cfg.getProperty("animationSpeed"), 
								this.cfg.getProperty("animationMethod"));

// is this getting added multiple times?
				if(this.cfg.getProperty("animationCompleteHandler")) {
					this._scrollNextAnim.onComplete.subscribe(this._handleAnimationComplete, [this, "next"]);
				}
				this._scrollNextAnim.animate();
			} else {
				if(this.isVertical()) {
					var currY = YAHOO.util.Dom.getY(this.carouselList);

					YAHOO.util.Dom.setY(this.carouselList, 
								currY - this.scrollAmountPerInc*inc);
				} else {
					var currX = YAHOO.util.Dom.getX(this.carouselList);
					YAHOO.util.Dom.setX(this.carouselList, 
								currX - this.scrollAmountPerInc*inc);
				}
			}

		}
		this._priorFirstVisible = newStart;
		this._priorLastVisible = newEnd;	

		this._enableDisableControls();
		return false;
	},

	// firstVisible is already set
	_scrollPrevInc: function(dec, showAnimation) {

		if(this._scrollNextAnim.isAnimated() || this._scrollPrevAnim.isAnimated()) {
			return false;
		}

		var numVisible = this.cfg.getProperty("numVisible");
		var currStart = this._priorFirstVisible;
		var currEnd = this._priorLastVisible;
		var size = this.cfg.getProperty("size");

		// decrement start by dec
		var newStart = currStart - dec;	

		var scrollExtent = this._calculateAllowableScrollExtent();
	
		// How to decide whether to stop at 1 or not
		newStart = (newStart < scrollExtent.start) ? scrollExtent.start : newStart;
		
		// if we are going to extend past the end, then we need to correct the start
		var newEnd = newStart + numVisible - 1;
		if(newEnd > scrollExtent.end) {
			newEnd = scrollExtent.end;
			newStart = newEnd - numVisible + 1;
		}
				
		dec = currStart - newStart;

		// at this point the following variables are set
		// dec... amount to decrement by
		// newStart... the firstVisible item after the scroll
		// newEnd... the last item visible after the scroll
		this.cfg.setProperty("firstVisible", newStart, true);
				
		// if we are decrementing
		if(dec > 0) {			
			if(this._isValidObj(this.cfg.getProperty("loadPrevHandler"))) {	
				var visibleExtent = this._calculateVisibleExtent(newStart, newEnd);
				var cacheEnd = (currStart-1) > visibleExtent.end ? (currStart-1) : visibleExtent.end;						
				var alreadyCached = this._areAllItemsLoaded(visibleExtent.start, cacheEnd);
				
				this._loadPrevHandlerEvt.fire(visibleExtent.start, visibleExtent.end, alreadyCached);
			}

			if(showAnimation) {
	 			var prevParams = { points: { by: [this.scrollAmountPerInc*dec, 0] } };
	 			if(this.isVertical()) {
	 				prevParams = { points: { by: [0, this.scrollAmountPerInc*dec] } };
	 			}
 		
	 			this._scrollPrevAnim = new YAHOO.util.Motion(this.carouselList,
	 							prevParams, 
   								this.cfg.getProperty("animationSpeed"), this.cfg.getProperty("animationMethod"));
				if(this.cfg.getProperty("animationCompleteHandler")) {
					this._scrollPrevAnim.onComplete.subscribe(this._handleAnimationComplete, [this, "prev"]);
				}
				this._scrollPrevAnim.animate();
			} else {
				if(this.isVertical()) {
					var currY = YAHOO.util.Dom.getY(this.carouselList);
					YAHOO.util.Dom.setY(this.carouselList, currY + 
							this.scrollAmountPerInc*dec);				
				} else {
					var currX = YAHOO.util.Dom.getX(this.carouselList);
					YAHOO.util.Dom.setX(this.carouselList, currX + 
							this.scrollAmountPerInc*dec);
				}
			}
		}
		this._priorFirstVisible = newStart;
		this._priorLastVisible = newEnd;	
		
		this._enableDisableControls();

		return false;
	},
	
	// Check for all cases and enable/disable controls as needed by current state
	_enableDisableControls: function() {
	
		var firstVisible = this.cfg.getProperty("firstVisible");
		var lastVisible = this.getLastVisible();
		var scrollExtent = this._calculateAllowableScrollExtent();
				
		// previous arrow is turned on. Check to see if we need to turn it off
		if(this._prevEnabled) {
			if(firstVisible === scrollExtent.start) {
				this._disablePrev();
			}
		}

		// previous arrow is turned off. Check to see if we need to turn it on
		if(this._prevEnabled === false) {
			if(firstVisible > scrollExtent.start) {
				this._enablePrev();
			}
		}
	
		// next arrow is turned on. Check to see if we need to turn it off
		if(this._nextEnabled) {
			if(lastVisible === scrollExtent.end) {
				this._disableNext();
			}
		}

		// next arrow is turned off. Check to see if we need to turn it on
		if(this._nextEnabled === false) {
			if(lastVisible < scrollExtent.end) {
				this._enableNext();
			}
		}	
	},
	
	/**
	 * _loadInitial looks at firstItemVisible for the start (not necessarily 1)
	 */
	_loadInitial: function() {
		var firstVisible = this.cfg.getProperty("firstVisible");
		this._priorLastVisible = this.getLastVisible();
		// Load from 1 to the last visible
		// The _calculateSize method will adjust the scroll position
		// for starts > 1
		if(this._loadInitHandlerEvt) {
			var visibleExtent = this._calculateVisibleExtent(firstVisible, this._priorLastVisible);
			// still treat the first real item as starting at 1 
			var alreadyCached = this._areAllItemsLoaded(1, visibleExtent.end);
			
			this._loadInitHandlerEvt.fire(visibleExtent.start, visibleExtent.end, alreadyCached); 
		}
		
		if(this.cfg.getProperty("autoPlay") !== 0) {
			this._autoPlayTimer = this.startAutoPlay();
		}	
		
		this._enableDisableControls();	
    },
	
	_calculateAllowableScrollExtent: function() {
		var scrollBeforeAmount = this.cfg.getProperty("scrollBeforeAmount");
		var scrollAfterAmount = this.cfg.getProperty("scrollAfterAmount");
		var size = this.cfg.getProperty("size");
		
		var extent = {start: 1-scrollBeforeAmount, end: size+scrollAfterAmount};
		return extent;
		
	},
	
	_calculateVisibleExtent: function(start, end) {
		if(!start) {
			start = this.cfg.getProperty("firstVisible");
			end = this.getLastVisible();
		}
		
		var size = this.cfg.getProperty("size");
		
		// we ignore the firstItem property... this method is used
		// for prebuilding the cache and signaling the developer
		// what to render on a given scroll.
		start = start<1?1:start;
		end = end>size?size:end;
		
		var extent = {start: start, end: end};
		
		// set up the indices for revealed items. If there is no item revealed, then set
		// the index to -1
		this._firstItemRevealed = -1;
		this._lastItemRevealed = -1;
		if(this._isExtraRevealed()) {
			if(start > 1) {
				this._firstItemRevealed = start - 1;
				extent.start = this._firstItemRevealed;
			}
			if(end < size) {
				this._lastItemRevealed = end + 1;
				extent.end = this._lastItemRevealed;
			}
		}

		return extent;
	},
	
	_disablePrev: function() {
		this._prevEnabled = false;
		if(this._prevButtonStateHandlerEvt) {
			this._prevButtonStateHandlerEvt.fire(false, this._carouselPrev);
		}
		if(this._isValidObj(this._carouselPrev)) {
			YAHOO.util.Event.removeListener(this._carouselPrev, "click", this._scrollPrev);
		}
	},
	
	_enablePrev: function() {
		this._prevEnabled = true;
		if(this._prevButtonStateHandlerEvt) {
			this._prevButtonStateHandlerEvt.fire(true, this._carouselPrev);
		}
		if(this._isValidObj(this._carouselPrev)) {
			YAHOO.util.Event.addListener(this._carouselPrev, "click", this._scrollPrev, this);
		}
	},
		
	_disableNext: function() {
		if(this.cfg.getProperty("wrap")) {
			return;
		}
		this._nextEnabled = false;
		if(this._isValidObj(this._nextButtonStateHandlerEvt)) {
			this._nextButtonStateHandlerEvt.fire(false, this._carouselNext);
		}
		if(this._isValidObj(this._carouselNext)) {
			YAHOO.util.Event.removeListener(this._carouselNext, "click", this._scrollNext);
		}
	},
	
	_enableNext: function() {
		this._nextEnabled = true;
		if(this._isValidObj(this._nextButtonStateHandlerEvt)) {
			this._nextButtonStateHandlerEvt.fire(true, this._carouselNext);
		}
		if(this._isValidObj(this._carouselNext)) {
			YAHOO.util.Event.addListener(this._carouselNext, "click", this._scrollNext, this);
		}
	},
		
	_isValidObj: function(obj) {

		if (null == obj) {
			return false;
		}
		if ("undefined" == typeof(obj) ) {
			return false;
		}
		return true;
	}
};









/** moved from bookreader demo **/


/**
 * Custom inital load handler. Called when the carousel loads the initial
 * set of data items. Specified to the carousel as the configuration
 * parameter: loadInitHandler
 **/
var loadInitialItems = function(type, args) {

	var start = args[0];
	var last = args[1]; 
	load(this, start, last);	
};

/**
 * Custom load next handler. Called when the carousel loads the next
 * set of data items. Specified to the carousel as the configuration
 * parameter: loadNextHandler
 **/
var loadNextItems = function(type, args) {	

	var start = args[0];
	var last = args[1]; 
	var alreadyCached = args[2];
	
	if(!alreadyCached) {
		load(this, start, last);
	}
};

/**
 * Custom load previous handler. Called when the carousel loads the previous
 * set of data items. Specified to the carousel as the configuration
 * parameter: loadPrevHandler
 **/
var loadPrevItems = function(type, args) {
	var start = args[0];
	var last = args[1]; 
	var alreadyCached = args[2];
	
	if(!alreadyCached) {
		load(this, start, last);
	}
};  

var load = function(carousel, start, last) {
	for(var i=start;i<=last;i++) {
		var randomIndex = getRandom(18, lastRan);
		lastRan = randomIndex;
		carousel.addItem(i, fmtItem(imageList[randomIndex], "#", "Number " + i));
	}
};

var getRandom = function(max, last) {
	var randomIndex;
	do {
		randomIndex = Math.floor(Math.random()*max);
	} while(randomIndex == last);
	
	return randomIndex;
};

/**
 * Custom button state handler for enabling/disabling button state. 
 * Called when the carousel has determined that the previous button
 * state should be changed.
 * Specified to the carousel as the configuration
 * parameter: prevButtonStateHandler
 **/
var handlePrevButtonState = function(type, args) {

	var enabling = args[0];
	var upImage = args[1];

	if(enabling) {
		upImage.src = "images/up-enabled.gif";
	} else {
		upImage.src = "images/up-disabled.gif";
	}
	
};




/** my nifty little iframe resize  **/

function ReSize(id,w){
 var obj=document.getElementById(id);
 obj.style.marginRight=w+'px';
 document.getElementById.value='margin-right '+w+'px';
}
