/*
 * jQuery wmd plugin.
 */

(function($) {
    var counter = 0;
    
    $.fn.wmd = function(_options) {
        this.each(function() {
            var defaults = {"preview": true};
            var options = $.extend({}, _options || {}, defaults);
            
            if (!options.button_bar) {
                options.button_bar = "wmd-button-bar-" + counter;
                $("<div/>")
                    .attr("class", "wmd-button-bar")
                    .attr("id", options.button_bar)
                    .insertBefore(this);
            }
                
            if (typeof(options.preview) == "boolean" && options.preview) {
                options.preview = "wmd-preview-" + counter;
                $("<div/>")
                    .attr("class", "wmd-preview")
                    .attr("id", options.preview)
                    .insertAfter(this);
            }

            if (typeof(options.output) == "boolean" && options.output) {
                options.output = "wmd-output-" + counter;
                $("<div/>")
                    .attr("class", "wmd-output")
                    .attr("id", options.output)
                    .insertAfter(this);
            }
                
            this.id = this.id || "wmd-input-" + counter;
            options.input = this.id;
            
            if (window.console)
                console.log(options);
            
            setup_wmd(options);
            counter++;
        });
    };
})(jQuery);
function setup_wmd(wmd_options) {

var Attacklab = Attacklab || {};
wmd_options = wmd_options || top.wmd_options || {};

Attacklab.wmdBase = function(){

	// A few handy aliases for readability.
	var wmd  = Attacklab;
	var doc  = top.document;
	var re   = top.RegExp;
	var nav  = top.navigator;
	
	// Some namespaces.
	wmd.Util = {};
	wmd.Position = {};
	wmd.Command = {};
	wmd.Global = {};
	wmd.buttons = {};
	
	wmd.showdown = top.Attacklab && top.Attacklab.showdown;
	
	var util = wmd.Util;
	var position = wmd.Position;
	var command = wmd.Command;
	var global = wmd.Global;
	
	
	// Used to work around some browser bugs where we can't use feature testing.
	global.isIE 		= /msie/.test(nav.userAgent.toLowerCase());
	global.isIE_5or6 	= /msie 6/.test(nav.userAgent.toLowerCase()) || /msie 5/.test(nav.userAgent.toLowerCase());
	global.isIE_7plus 	= global.isIE && !global.isIE_5or6;
	global.isOpera 		= /opera/.test(nav.userAgent.toLowerCase());
	global.isKonqueror 	= /konqueror/.test(nav.userAgent.toLowerCase());
	
	
	// -------------------------------------------------------------------
	//  YOUR CHANGES GO HERE
	//
	// I've tried to localize the things you are likely to change to 
	// this area.
	// -------------------------------------------------------------------
	
	// The text that appears on the upper part of the dialog box when
	// entering links.
	var imageDialogText = wmd_options.imageDialogText || "<p style='margin-top: 0px'><b>Enter the image URL.</b></p><p>You can also add a title, which will be displayed as a tool tip.</p><p>Example:<br />http://wmd-editor.com/images/cloud1.jpg   \"Optional title\"</p>";
	var linkDialogText = wmd_options.linkDialogText || "<p style='margin-top: 0px'><b>Enter the web address.</b></p><p>You can also add a title, which will be displayed as a tool tip.</p><p>Example:<br />http://wmd-editor.com/   \"Optional title\"</p>";
	
	// The default text that appears in the dialog input box when entering
	// links.
	var imageDefaultText = "http://";
	var linkDefaultText = "http://";
	
	// The location of your button images relative to the base directory.
	var imageDirectory = "images/";
	
	// Some intervals in ms.  These can be adjusted to reduce the control's load.
	var previewPollInterval = 500;
	var pastePollInterval = 100;
	
	// The link and title for the help button
	var helpLink = wmd_options.helpLink || "http://wmd-editor.com/";
	var helpHoverTitle = wmd_options.helpHoverTitle || "WMD website";
	var helpTarget = wmd_options.helpTarget || "_blank";
	
	// -------------------------------------------------------------------
	//  END OF YOUR CHANGES
	// -------------------------------------------------------------------
	
	// A collection of the important regions on the page.
	// Cached so we don't have to keep traversing the DOM.
	wmd.PanelCollection = function(){
		this.buttonBar = doc.getElementById(wmd_options.button_bar || "wmd-button-bar");
		this.preview = doc.getElementById(wmd_options.preview || "wmd-preview");
		this.output = doc.getElementById(wmd_options.output || "wmd-output");
		this.input = doc.getElementById(wmd_options.input || "wmd-input");
	};
	
	// This PanelCollection object can't be filled until after the page
	// has loaded.
	wmd.panels = undefined;
	
	// Internet explorer has problems with CSS sprite buttons that use HTML
	// lists.  When you click on the background image "button", IE will 
	// select the non-existent link text and discard the selection in the
	// textarea.  The solution to this is to cache the textarea selection
	// on the button's mousedown event and set a flag.  In the part of the
	// code where we need to grab the selection, we check for the flag
	// and, if it's set, use the cached area instead of querying the
	// textarea.
	//
	// This ONLY affects Internet Explorer (tested on versions 6, 7
	// and 8) and ONLY on button clicks.  Keyboard shortcuts work
	// normally since the focus never leaves the textarea.
	wmd.ieCachedRange = null;		// cached textarea selection
	wmd.ieRetardedClick = false;	// flag
	
	// Returns true if the DOM element is visible, false if it's hidden.
	// Checks if display is anything other than none.
	util.isVisible = function (elem) {
            // shamelessly copied from jQuery
            return elem.offsetWidth > 0 || elem.offsetHeight > 0;
        };
	
	// Adds a listener callback to a DOM element which is fired on a specified
	// event.
	util.addEvent = function(elem, event, listener){
		if (elem.attachEvent) {
			// IE only.  The "on" is mandatory.
			elem.attachEvent("on" + event, listener);
		}
		else {
			// Other browsers.
			elem.addEventListener(event, listener, false);
		}
	};

	
	// Removes a listener callback from a DOM element which is fired on a specified
	// event.
	util.removeEvent = function(elem, event, listener){
		if (elem.detachEvent) {
			// IE only.  The "on" is mandatory.
			elem.detachEvent("on" + event, listener);
		}
		else {
			// Other browsers.
			elem.removeEventListener(event, listener, false);
		}
	};

	// Converts \r\n and \r to \n.
	util.fixEolChars = function(text){
		text = text.replace(/\r\n/g, "\n");
		text = text.replace(/\r/g, "\n");
		return text;
	};

	// Extends a regular expression.  Returns a new RegExp
	// using pre + regex + post as the expression.
	// Used in a few functions where we have a base
	// expression and we want to pre- or append some
	// conditions to it (e.g. adding "$" to the end).
	// The flags are unchanged.
	//
	// regex is a RegExp, pre and post are strings.
	util.extendRegExp = function(regex, pre, post){
		
		if (pre === null || pre === undefined)
		{
			pre = "";
		}
		if(post === null || post === undefined)
		{
			post = "";
		}
		
		var pattern = regex.toString();
		var flags = "";
		
		// Replace the flags with empty space and store them.
		// Technically, this can match incorrect flags like "gmm".
		var result = pattern.match(/\/([gim]*)$/);
		if (result === null) {
			flags = result[0];
		}
		else {
			flags = "";
		}
		
		// Remove the flags and slash delimiters from the regular expression.
		pattern = pattern.replace(/(^\/|\/[gim]*$)/g, "");
		pattern = pre + pattern + post;
		
		return new RegExp(pattern, flags);
	}

	
	// Sets the image for a button passed to the WMD editor.
	// Returns a new element with the image attached.
	// Adds several style properties to the image.
	util.createImage = function(img){
		
		var imgPath = imageDirectory + img;
		
		var elem = doc.createElement("img");
		elem.className = "wmd-button";
		elem.src = imgPath;

		return elem;
	};
	

	// This simulates a modal dialog box and asks for the URL when you
	// click the hyperlink or image buttons.
	//
	// text: The html for the input box.
	// defaultInputText: The default value that appears in the input box.
	// makeLinkMarkdown: The function which is executed when the prompt is dismissed, either via OK or Cancel
	util.prompt = function(text, defaultInputText, makeLinkMarkdown){
	
		// These variables need to be declared at this level since they are used
		// in multiple functions.
		var dialog;			// The dialog box.
		var background;		// The background beind the dialog box.
		var input;			// The text box where you enter the hyperlink.
		

		if (defaultInputText === undefined) {
			defaultInputText = "";
		}
		
		// Used as a keydown event handler. Esc dismisses the prompt.
		// Key code 27 is ESC.
		var checkEscape = function(key){
			var code = (key.charCode || key.keyCode);
			if (code === 27) {
				close(true);
			}
		};
		
		// Dismisses the hyperlink input box.
		// isCancel is true if we don't care about the input text.
		// isCancel is false if we are going to keep the text.
		var close = function(isCancel){
			util.removeEvent(doc.body, "keydown", checkEscape);
			var text = input.value;

			if (isCancel){
				text = null;
			}
			else{
				// Fixes common pasting errors.
				text = text.replace('http://http://', 'http://');
				text = text.replace('http://https://', 'https://');
				text = text.replace('http://ftp://', 'ftp://');
				
				if (text.indexOf('http://') === -1 && text.indexOf('ftp://') === -1 && text.indexOf('https://') === -1) {
					text = 'http://' + text;
				}
			}
			
			dialog.parentNode.removeChild(dialog);
			background.parentNode.removeChild(background);
			makeLinkMarkdown(text);
			return false;
		};
		
		// Creates the background behind the hyperlink text entry box.
		// Most of this has been moved to CSS but the div creation and
		// browser-specific hacks remain here.
		var createBackground = function(){
		
			background = doc.createElement("div");
			background.className = "wmd-prompt-background";
			style = background.style;
			style.position = "absolute";
			style.top = "0";
			
			style.zIndex = "1000";
			
			// Some versions of Konqueror don't support transparent colors
			// so we make the whole window transparent.
			//
			// Is this necessary on modern konqueror browsers?
			if (global.isKonqueror){
				style.backgroundColor = "transparent";
			}
			else if (global.isIE){
				style.filter = "alpha(opacity=50)";
			}
			else {
				style.opacity = "0.5";
			}
			
			var pageSize = position.getPageSize();
			style.height = pageSize[1] + "px";
			
			if(global.isIE){
				style.left = doc.documentElement.scrollLeft;
				style.width = doc.documentElement.clientWidth;
			}
			else {
				style.left = "0";
				style.width = "100%";
			}
			
			doc.body.appendChild(background);
		};
		
		// Create the text input box form/window.
		var createDialog = function(){
		
			// The main dialog box.
			dialog = doc.createElement("div");
			dialog.className = "wmd-prompt-dialog";
			dialog.style.padding = "10px;";
			dialog.style.position = "fixed";
			dialog.style.width = "400px";
			dialog.style.zIndex = "1001";
			
			// The dialog text.
			var question = doc.createElement("div");
			question.innerHTML = text;
			question.style.padding = "5px";
			dialog.appendChild(question);
			
			// The web form container for the text box and buttons.
			var form = doc.createElement("form");
			form.onsubmit = function(){ return close(false); };
			style = form.style;
			style.padding = "0";
			style.margin = "0";
			style.cssFloat = "left";
			style.width = "100%";
			style.textAlign = "center";
			style.position = "relative";
			dialog.appendChild(form);
			
			// The input text box
			input = doc.createElement("input");
			input.type = "text";
			input.value = defaultInputText;
			style = input.style;
			style.display = "block";
			style.width = "80%";
			style.marginLeft = style.marginRight = "auto";
			form.appendChild(input);
			
			// The ok button
			var okButton = doc.createElement("input");
			okButton.type = "button";
			okButton.onclick = function(){ return close(false); };
			okButton.value = "OK";
			style = okButton.style;
			style.margin = "10px";
			style.display = "inline";
			style.width = "7em";

			
			// The cancel button
			var cancelButton = doc.createElement("input");
			cancelButton.type = "button";
			cancelButton.onclick = function(){ return close(true); };
			cancelButton.value = "Cancel";
			style = cancelButton.style;
			style.margin = "10px";
			style.display = "inline";
			style.width = "7em";

			// The order of these buttons is different on macs.
			if (/mac/.test(nav.platform.toLowerCase())) {
				form.appendChild(cancelButton);
				form.appendChild(okButton);
			}
			else {
				form.appendChild(okButton);
				form.appendChild(cancelButton);
			}

			util.addEvent(doc.body, "keydown", checkEscape);
			dialog.style.top = "50%";
			dialog.style.left = "50%";
			dialog.style.display = "block";
			if(global.isIE_5or6){
				dialog.style.position = "absolute";
				dialog.style.top = doc.documentElement.scrollTop + 200 + "px";
				dialog.style.left = "50%";
			}
			doc.body.appendChild(dialog);
			
			// This has to be done AFTER adding the dialog to the form if you
			// want it to be centered.
			dialog.style.marginTop = -(position.getHeight(dialog) / 2) + "px";
			dialog.style.marginLeft = -(position.getWidth(dialog) / 2) + "px";
			
		};
		
		createBackground();
		
		// Why is this in a zero-length timeout?
		// Is it working around a browser bug?
		top.setTimeout(function(){
		
			createDialog();

			var defTextLen = defaultInputText.length;
			if (input.selectionStart !== undefined) {
				input.selectionStart = 0;
				input.selectionEnd = defTextLen;
			}
			else if (input.createTextRange) {
				var range = input.createTextRange();
				range.collapse(false);
				range.moveStart("character", -defTextLen);
				range.moveEnd("character", defTextLen);
				range.select();
			}
			
			input.focus();
		}, 0);
	};
	
	
	// UNFINISHED
	// The assignment in the while loop makes jslint cranky.
	// I'll change it to a better loop later.
	position.getTop = function(elem, isInner){
		var result = elem.offsetTop;
		if (!isInner) {
			while (elem = elem.offsetParent) {
				result += elem.offsetTop;
			}
		}
		return result;
	};
	
	position.getHeight = function (elem) {
		return elem.offsetHeight || elem.scrollHeight;
	};

	position.getWidth = function (elem) {
		return elem.offsetWidth || elem.scrollWidth;
	};

	position.getPageSize = function(){
		
		var scrollWidth, scrollHeight;
		var innerWidth, innerHeight;
		
		// It's not very clear which blocks work with which browsers.
		if(self.innerHeight && self.scrollMaxY){
			scrollWidth = doc.body.scrollWidth;
			scrollHeight = self.innerHeight + self.scrollMaxY;
		}
		else if(doc.body.scrollHeight > doc.body.offsetHeight){
			scrollWidth = doc.body.scrollWidth;
			scrollHeight = doc.body.scrollHeight;
		}
		else{
			scrollWidth = doc.body.offsetWidth;
			scrollHeight = doc.body.offsetHeight;
		}
		
		if(self.innerHeight){
			// Non-IE browser
			innerWidth = self.innerWidth;
			innerHeight = self.innerHeight;
		}
		else if(doc.documentElement && doc.documentElement.clientHeight){
			// Some versions of IE (IE 6 w/ a DOCTYPE declaration)
			innerWidth = doc.documentElement.clientWidth;
			innerHeight = doc.documentElement.clientHeight;
		}
		else if(doc.body){
			// Other versions of IE
			innerWidth = doc.body.clientWidth;
			innerHeight = doc.body.clientHeight;
		}
		
        var maxWidth = Math.max(scrollWidth, innerWidth);
        var maxHeight = Math.max(scrollHeight, innerHeight);
        return [maxWidth, maxHeight, innerWidth, innerHeight];
	};
	
	// Watches the input textarea, polling at an interval and runs
	// a callback function if anything has changed.
	wmd.inputPoller = function(callback, interval){
	
		var pollerObj = this;
		var inputArea = wmd.panels.input;
		
		// Stored start, end and text.  Used to see if there are changes to the input.
		var lastStart;
		var lastEnd;
		var markdown;
		
		var killHandle; // Used to cancel monitoring on destruction.
		// Checks to see if anything has changed in the textarea.
		// If so, it runs the callback.
		this.tick = function(){
		
			if (!util.isVisible(inputArea)) {
				return;
			}
			
			// Update the selection start and end, text.
			if (inputArea.selectionStart || inputArea.selectionStart === 0) {
				var start = inputArea.selectionStart;
				var end = inputArea.selectionEnd;
				if (start != lastStart || end != lastEnd) {
					lastStart = start;
					lastEnd = end;
					
					if (markdown != inputArea.value) {
						markdown = inputArea.value;
						return true;
					}
				}
			}
			return false;
		};
		
		
		var doTickCallback = function(){
		
			if (!util.isVisible(inputArea)) {
				return;
			}
			
			// If anything has changed, call the function.
			if (pollerObj.tick()) {
				callback();
			}
		};
		
		// Set how often we poll the textarea for changes.
		var assignInterval = function(){
			// previewPollInterval is set at the top of the namespace.
			killHandle = top.setInterval(doTickCallback, interval);
		};
		
		this.destroy = function(){
			top.clearInterval(killHandle);
		};
		
		assignInterval();
	};
	
	// Handles pushing and popping TextareaStates for undo/redo commands.
	// I should rename the stack variables to list.
	wmd.undoManager = function(callback){
	
		var undoObj = this;
		var undoStack = []; // A stack of undo states
		var stackPtr = 0; // The index of the current state
		var mode = "none";
		var lastState; // The last state
		var poller;
		var timer; // The setTimeout handle for cancelling the timer
		var inputStateObj;
		
		// Set the mode for later logic steps.
		var setMode = function(newMode, noSave){
		
			if (mode != newMode) {
				mode = newMode;
				if (!noSave) {
					saveState();
				}
			}
			
			if (!global.isIE || mode != "moving") {
				timer = top.setTimeout(refreshState, 1);
			}
			else {
				inputStateObj = null;
			}
		};
		
		var refreshState = function(){
			inputStateObj = new wmd.TextareaState();
			poller.tick();
			timer = undefined;
		};
		
		this.setCommandMode = function(){
			mode = "command";
			saveState();
			timer = top.setTimeout(refreshState, 0);
		};
		
		this.canUndo = function(){
			return stackPtr > 1;
		};
		
		this.canRedo = function(){
			if (undoStack[stackPtr + 1]) {
				return true;
			}
			return false;
		};
		
		// Removes the last state and restores it.
		this.undo = function(){
		
			if (undoObj.canUndo()) {
				if (lastState) {
					// What about setting state -1 to null or checking for undefined?
					lastState.restore();
					lastState = null;
				}
				else {
					undoStack[stackPtr] = new wmd.TextareaState();
					undoStack[--stackPtr].restore();
					
					if (callback) {
						callback();
					}
				}
			}
			
			mode = "none";
			wmd.panels.input.focus();
			refreshState();
		};
		
		// Redo an action.
		this.redo = function(){
		
			if (undoObj.canRedo()) {
			
				undoStack[++stackPtr].restore();
				
				if (callback) {
					callback();
				}
			}
			
			mode = "none";
			wmd.panels.input.focus();
			refreshState();
		};
		
		// Push the input area state to the stack.
		var saveState = function(){
		
			var currState = inputStateObj || new wmd.TextareaState();
			
			if (!currState) {
				return false;
			}
			if (mode == "moving") {
				if (!lastState) {
					lastState = currState;
				}
				return;
			}
			if (lastState) {
				if (undoStack[stackPtr - 1].text != lastState.text) {
					undoStack[stackPtr++] = lastState;
				}
				lastState = null;
			}
			undoStack[stackPtr++] = currState;
			undoStack[stackPtr + 1] = null;
			if (callback) {
				callback();
			}
		};
		
		var handleCtrlYZ = function(event){
		
			var handled = false;
			
			if (event.ctrlKey || event.metaKey) {
			
				// IE and Opera do not support charCode.
				var keyCode = event.charCode || event.keyCode;
				var keyCodeChar = String.fromCharCode(keyCode);
				
				switch (keyCodeChar) {
				
					case "y":
						undoObj.redo();
						handled = true;
						break;
						
					case "z":
						if (!event.shiftKey) {
							undoObj.undo();
						}
						else {
							undoObj.redo();
						}
						handled = true;
						break;
				}
			}
			
			if (handled) {
				if (event.preventDefault) {
					event.preventDefault();
				}
				if (top.event) {
					top.event.returnValue = false;
				}
				return;
			}
		};
		
		// Set the mode depending on what is going on in the input area.
		var handleModeChange = function(event){
		
			if (!event.ctrlKey && !event.metaKey) {
			
				var keyCode = event.keyCode;
				
				if ((keyCode >= 33 && keyCode <= 40) || (keyCode >= 63232 && keyCode <= 63235)) {
					// 33 - 40: page up/dn and arrow keys
					// 63232 - 63235: page up/dn and arrow keys on safari
					setMode("moving");
				}
				else if (keyCode == 8 || keyCode == 46 || keyCode == 127) {
					// 8: backspace
					// 46: delete
					// 127: delete
					setMode("deleting");
				}
				else if (keyCode == 13) {
					// 13: Enter
					setMode("newlines");
				}
				else if (keyCode == 27) {
					// 27: escape
					setMode("escape");
				}
				else if ((keyCode < 16 || keyCode > 20) && keyCode != 91) {
					// 16-20 are shift, etc. 
					// 91: left window key
					// I think this might be a little messed up since there are
					// a lot of nonprinting keys above 20.
					setMode("typing");
				}
			}
		};
		
		var setEventHandlers = function(){
		
			util.addEvent(wmd.panels.input, "keypress", function(event){
				// keyCode 89: y
				// keyCode 90: z
				if ((event.ctrlKey || event.metaKey) && (event.keyCode == 89 || event.keyCode == 90)) {
					event.preventDefault();
				}
			});
			
			var handlePaste = function(){
				if (global.isIE || (inputStateObj && inputStateObj.text != wmd.panels.input.value)) {
					if (timer == undefined) {
						mode = "paste";
						saveState();
						refreshState();
					}
				}
			};
			
			// pastePollInterval is specified at the beginning of this namespace.
			poller = new wmd.inputPoller(handlePaste, pastePollInterval);
			
			util.addEvent(wmd.panels.input, "keydown", handleCtrlYZ);
			util.addEvent(wmd.panels.input, "keydown", handleModeChange);
			
			util.addEvent(wmd.panels.input, "mousedown", function(){
				setMode("moving");
			});
			wmd.panels.input.onpaste = handlePaste;
			wmd.panels.input.ondrop = handlePaste;
		};
		
		var init = function(){
			setEventHandlers();
			refreshState();
			saveState();
		};
		
		this.destroy = function(){
			if (poller) {
				poller.destroy();
			}
		};
		
		init();
	};
	
	// I think my understanding of how the buttons and callbacks are stored in the array is incomplete.
	wmd.editor = function(previewRefreshCallback){
	
		if (!previewRefreshCallback) {
			previewRefreshCallback = function(){};
		}
		
		var inputBox = wmd.panels.input;
		
		var offsetHeight = 0;
		
		var editObj = this;
		
		var mainDiv;
		var mainSpan;
		
		var div; // This name is pretty ambiguous.  I should rename this.
		
		// Used to cancel recurring events from setInterval.
		var creationHandle;
		
		var undoMgr; // The undo manager
		
		// Perform the button's action.
		var doClick = function(button){
		
			inputBox.focus();
			
			if (button.textOp) {
				
				if (undoMgr) {
					undoMgr.setCommandMode();
				}
				
				var state = new wmd.TextareaState();
				
				if (!state) {
					return;
				}
				
				var chunks = state.getChunks();
				
				// Some commands launch a "modal" prompt dialog.  Javascript
				// can't really make a modal dialog box and the WMD code
				// will continue to execute while the dialog is displayed.
				// This prevents the dialog pattern I'm used to and means
				// I can't do something like this:
				//
				// var link = CreateLinkDialog();
				// makeMarkdownLink(link);
				// 
				// Instead of this straightforward method of handling a
				// dialog I have to pass any code which would execute
				// after the dialog is dismissed (e.g. link creation)
				// in a function parameter.
				//
				// Yes this is awkward and I think it sucks, but there's
				// no real workaround.  Only the image and link code
				// create dialogs and require the function pointers.
				var fixupInputArea = function(){
				
					inputBox.focus();
					
					if (chunks) {
						state.setChunks(chunks);
					}
					
					state.restore();
					previewRefreshCallback();
				};
				
				var useDefaultText = true;
				var noCleanup = button.textOp(chunks, fixupInputArea, useDefaultText);
				
				if(!noCleanup) {
					fixupInputArea();
				}
				
			}
			
			if (button.execute) {
				button.execute(editObj);
			}
		};
			
		var setUndoRedoButtonStates = function(){
			if(undoMgr){
				setupButton(wmd.buttons["wmd-undo-button"], undoMgr.canUndo());
				setupButton(wmd.buttons["wmd-redo-button"], undoMgr.canRedo());
			}
		};
		
		var setupButton = function(button, isEnabled) {
		
			var normalYShift = "0px";
			var disabledYShift = "-20px";
			var highlightYShift = "-40px";
			
			if(isEnabled) {
				button.style.backgroundPosition = button.XShift + " " + normalYShift;
				button.onmouseover = function(){
					this.style.backgroundPosition = this.XShift + " " + highlightYShift;
				};
							
				button.onmouseout = function(){
					this.style.backgroundPosition = this.XShift + " " + normalYShift;
				};
				
				// IE tries to select the background image "button" text (it's
				// implemented in a list item) so we have to cache the selection
				// on mousedown.
				if(global.isIE) {
					button.onmousedown =  function() { 
						wmd.ieRetardedClick = true;
						wmd.ieCachedRange = document.selection.createRange(); 
					};
				}
				
				if (!button.isHelp)
				{
					button.onclick = function() {
						if (this.onmouseout) {
							this.onmouseout();
						}
						doClick(this);
						return false;
					}
				}
			}
			else {
				button.style.backgroundPosition = button.XShift + " " + disabledYShift;
				button.onmouseover = button.onmouseout = button.onclick = function(){};
			}
		}
	
		var makeSpritedButtonRow = function(){
		 	
			var buttonBar = document.getElementById(wmd_options.button_bar || "wmd-button-bar");
 	
			var normalYShift = "0px";
			var disabledYShift = "-20px";
			var highlightYShift = "-40px";
			
			var buttonRow = document.createElement("ul");
			buttonRow.className = "wmd-button-row"
			buttonRow = buttonBar.appendChild(buttonRow);
			
			var xoffset = 0;
			
			function createButton(name, title, textOp) {
			    var button = document.createElement("li");
			    wmd.buttons[name] = button;
			    button.className = "wmd-button " + name;
		        button.XShift = xoffset + "px";
		        xoffset -= 20;
			    
			    if (title)
			        button.title = title;
			        
			    if (textOp)
			        button.textOp = textOp;

			    return button;
			}
			
			function addButton(name, title, textOp) {
		        var button = createButton(name, title, textOp);

			    setupButton(button, true);
			    buttonRow.appendChild(button);
			    return button;
			}
			
			function addSpacer() {
			    var spacer = document.createElement("li");
			    spacer.className = "wmd-spacer";
			    buttonRow.appendChild(spacer);
			    return spacer;
			}
			
            var boldButton = addButton("wmd-bold-button", "Strong <strong> Ctrl+B", command.doBold);
            var italicButton = addButton("wmd-italic-button", "Emphasis <em> Ctrl+I", command.doItalic);
            var spacer1 = addSpacer();
			
			var linkButton = addButton("wmd-link-button", "Hyperlink <a> Ctrl+L", function(chunk, postProcessing, useDefaultText) {
				return command.doLinkOrImage(chunk, postProcessing, false);
			});		
			var quoteButton = addButton("wmd-quote-button", "Blockquote <blockquote> Ctrl+Q", command.doBlockquote);
			var codeButton = addButton("wmd-code-button", "Code Sample <pre><code> Ctrl+K", command.doCode);
			var imageButton = addButton("wmd-image-button", "Image <img> Ctrl+G", function(chunk, postProcessing, useDefaultText) {
				return command.doLinkOrImage(chunk, postProcessing, true);
			});
			
			var spacer2 = addSpacer();

			var olistButton = addButton("wmd-olist-button", "Numbered List <ol> Ctrl+O", function(chunk, postProcessing, useDefaultText) {
				command.doList(chunk, postProcessing, true, useDefaultText);
			});
			var ulistButton = addButton("wmd-ulist-button", "Bulleted List <ul> Ctrl+U", function(chunk, postProcessing, useDefaultText) {
				command.doList(chunk, postProcessing, false, useDefaultText);
			});
			var headingButton = addButton("wmd-heading-button", "Heading <h1>/<h2> Ctrl+H", command.doHeading);
			var hrButton = addButton("wmd-hr-button", "Horizontal Rule <hr> Ctrl+R", command.doHorizontalRule);
			var spacer3 = addSpacer();
			
			var undoButton = addButton("wmd-undo-button", "Undo - Ctrl+Z");
			undoButton.execute = function(manager){
				manager.undo();
			};
			
			var redo_title = null;
			
			var redoButton = addButton("wmd-redo-button", "Redo - Ctrl+Y");
			if (/win/.test(nav.platform.toLowerCase())) {
				redoButton.title = "Redo - Ctrl+Y";
			}
			else {
				// mac and other non-Windows platforms
				redoButton.title = "Redo - Ctrl+Shift+Z";
			}
			redoButton.execute = function(manager){
				manager.redo();
			};
			
			var helpButton = createButton("wmd-help-button");
			helpButton.isHelp = true;
		    setupButton(helpButton, true);
		    buttonRow.appendChild(helpButton);
			
			var helpAnchor = document.createElement("a");
			helpAnchor.href = helpLink;
			helpAnchor.target = helpTarget
			helpAnchor.title = helpHoverTitle;
			helpButton.appendChild(helpAnchor);
						
			setUndoRedoButtonStates();
		}
		
		var setupEditor = function(){
		
			if (/\?noundo/.test(doc.location.href)) {
				wmd.nativeUndo = true;
			}
			
			if (!wmd.nativeUndo) {
				undoMgr = new wmd.undoManager(function(){
					previewRefreshCallback();
					setUndoRedoButtonStates();
				});
			}
			
			makeSpritedButtonRow();
			
			
			var keyEvent = "keydown";
			if (global.isOpera) {
				keyEvent = "keypress";
			}
			
			util.addEvent(inputBox, keyEvent, function(key){
				
				// Check to see if we have a button key and, if so execute the callback.
				if (key.ctrlKey || key.metaKey) {
			
					var keyCode = key.charCode || key.keyCode;
					var keyCodeStr = String.fromCharCode(keyCode).toLowerCase();
					
					switch(keyCodeStr) {
						case "b":
							doClick(wmd.buttons["wmd-bold-button"]);
							break;
						case "i":
							doClick(wmd.buttons["wmd-italic-button"]);
							break;
						case "l":
							doClick(wmd.buttons["wmd-link-button"]);
							break;
						case "q":
							doClick(wmd.buttons["wmd-quote-button"]);
							break;
						case "k":
							doClick(wmd.buttons["wmd-code-button"]);
							break;
						case "g":
							doClick(wmd.buttons["wmd-image-button"]);
							break;
						case "o":
							doClick(wmd.buttons["wmd-olist-button"]);
							break;
						case "u":
							doClick(wmd.buttons["wmd-ulist-button"]);
							break;
						case "h":
							doClick(wmd.buttons["wmd-heading-button"]);
							break;
						case "r":
							doClick(wmd.buttons["wmd-hr-button"]);
							break;
						case "y":
							doClick(wmd.buttons["wmd-redo-button"]);
							break;
						case "z":
							if(key.shiftKey) {
								doClick(wmd.buttons["wmd-redo-button"]);
							}
							else {
								doClick(wmd.buttons["wmd-undo-button"]);
							}
							break;
						default:
							return;
					}
					

					if (key.preventDefault) {
						key.preventDefault();
					}
					
					if (top.event) {
						top.event.returnValue = false;
					}
				}
			});
			
			// Auto-continue lists, code blocks and block quotes when
			// the enter key is pressed.
			util.addEvent(inputBox, "keyup", function(key){
				if (!key.shiftKey && !key.ctrlKey && !key.metaKey) {
					var keyCode = key.charCode || key.keyCode;
					// Key code 13 is Enter
					if (keyCode === 13) {
						fakeButton = {};
						fakeButton.textOp = command.doAutoindent;
						doClick(fakeButton);
					}
				}
			});
			
			// Disable ESC clearing the input textarea on IE
			if (global.isIE) {
				util.addEvent(inputBox, "keydown", function(key){
					var code = key.keyCode;
					// Key code 27 is ESC
					if (code === 27) {
						return false;
					}
				});
			}
			
			if (inputBox.form) {
				var submitCallback = inputBox.form.onsubmit;
				inputBox.form.onsubmit = function(){
					convertToHtml();
					if (submitCallback) {
						return submitCallback.apply(this, arguments);
					}
				};
			}
		};
		
		// Convert the contents of the input textarea to HTML in the output/preview panels.
		var convertToHtml = function(){
		
			if (wmd.showdown) {
				var markdownConverter = new wmd.showdown.converter();
			}
			var text = inputBox.value;
			
			var callback = function(){
				inputBox.value = text;
			};
			
			if (!/markdown/.test(wmd.wmd_env.output_format.toLowerCase())) {
				if (markdownConverter) {
					inputBox.value = markdownConverter.makeHtml(text);
					top.setTimeout(callback, 0);
				}
			}
			return true;
		};
		
		
		this.undo = function(){
			if (undoMgr) {
				undoMgr.undo();
			}
		};
		
		this.redo = function(){
			if (undoMgr) {
				undoMgr.redo();
			}
		};
		
		// This is pretty useless.  The setupEditor function contents
		// should just be copied here.
		var init = function(){
			setupEditor();
		};
		
		this.destroy = function(){
			if (undoMgr) {
				undoMgr.destroy();
			}
			if (div.parentNode) {
				div.parentNode.removeChild(div);
			}
			if (inputBox) {
				inputBox.style.marginTop = "";
			}
			top.clearInterval(creationHandle);
		};
		
		init();
	};
	
	// The input textarea state/contents.
	// This is used to implement undo/redo by the undo manager.
	wmd.TextareaState = function(){
	
		// Aliases
		var stateObj = this;
		var inputArea = wmd.panels.input;
		
		this.init = function() {
		
			if (!util.isVisible(inputArea)) {
				return;
			}
				
			this.setInputAreaSelectionStartEnd();
			this.scrollTop = inputArea.scrollTop;
			if (!this.text && inputArea.selectionStart || inputArea.selectionStart === 0) {
				this.text = inputArea.value;
			}
			
		}
		
		// Sets the selected text in the input box after we've performed an
		// operation.
		this.setInputAreaSelection = function(){
		
			if (!util.isVisible(inputArea)) {
				return;
			}
			
			if (inputArea.selectionStart !== undefined && !global.isOpera) {
			
				inputArea.focus();
				inputArea.selectionStart = stateObj.start;
				inputArea.selectionEnd = stateObj.end;
				inputArea.scrollTop = stateObj.scrollTop;
			}
			else if (doc.selection) {
				
				if (doc.activeElement && doc.activeElement !== inputArea) {
					return;
				}
					
				inputArea.focus();
				var range = inputArea.createTextRange();
				range.moveStart("character", -inputArea.value.length);
				range.moveEnd("character", -inputArea.value.length);
				range.moveEnd("character", stateObj.end);
				range.moveStart("character", stateObj.start);
				range.select();
			}
		};
		
		this.setInputAreaSelectionStartEnd = function(){
		
			if (inputArea.selectionStart || inputArea.selectionStart === 0) {
			
				stateObj.start = inputArea.selectionStart;
				stateObj.end = inputArea.selectionEnd;
			}
			else if (doc.selection) {
				
				stateObj.text = util.fixEolChars(inputArea.value);
				
				// IE loses the selection in the textarea when buttons are
				// clicked.  On IE we cache the selection and set a flag
				// which we check for here.
				var range;
				if(wmd.ieRetardedClick && wmd.ieCachedRange) {
					range = wmd.ieCachedRange;
					wmd.ieRetardedClick = false;
				}
				else {
					range = doc.selection.createRange();
				}

				var fixedRange = util.fixEolChars(range.text);
				var marker = "\x07";
				var markedRange = marker + fixedRange + marker;
				range.text = markedRange;
				var inputText = util.fixEolChars(inputArea.value);
					
				range.moveStart("character", -markedRange.length);
				range.text = fixedRange;

				stateObj.start = inputText.indexOf(marker);
				stateObj.end = inputText.lastIndexOf(marker) - marker.length;
					
				var len = stateObj.text.length - util.fixEolChars(inputArea.value).length;
					
				if (len) {
					range.moveStart("character", -fixedRange.length);
					while (len--) {
						fixedRange += "\n";
						stateObj.end += 1;
					}
					range.text = fixedRange;
				}
					
				this.setInputAreaSelection();
			}
		};
		
		// Restore this state into the input area.
		this.restore = function(){
		
			if (stateObj.text != undefined && stateObj.text != inputArea.value) {
				inputArea.value = stateObj.text;
			}
			this.setInputAreaSelection();
			inputArea.scrollTop = stateObj.scrollTop;
		};
		
		// Gets a collection of HTML chunks from the inptut textarea.
		this.getChunks = function(){
		
			var chunk = new wmd.Chunks();
			
			chunk.before = util.fixEolChars(stateObj.text.substring(0, stateObj.start));
			chunk.startTag = "";
			chunk.selection = util.fixEolChars(stateObj.text.substring(stateObj.start, stateObj.end));
			chunk.endTag = "";
			chunk.after = util.fixEolChars(stateObj.text.substring(stateObj.end));
			chunk.scrollTop = stateObj.scrollTop;
			
			return chunk;
		};
		
		// Sets the TextareaState properties given a chunk of markdown.
		this.setChunks = function(chunk){
		
			chunk.before = chunk.before + chunk.startTag;
			chunk.after = chunk.endTag + chunk.after;
			
			if (global.isOpera) {
				chunk.before = chunk.before.replace(/\n/g, "\r\n");
				chunk.selection = chunk.selection.replace(/\n/g, "\r\n");
				chunk.after = chunk.after.replace(/\n/g, "\r\n");
			}
			
			this.start = chunk.before.length;
			this.end = chunk.before.length + chunk.selection.length;
			this.text = chunk.before + chunk.selection + chunk.after;
			this.scrollTop = chunk.scrollTop;
		};

		this.init();
	};
	
	// before: contains all the text in the input box BEFORE the selection.
	// after: contains all the text in the input box AFTER the selection.
	wmd.Chunks = function(){
	};
	
	// startRegex: a regular expression to find the start tag
	// endRegex: a regular expresssion to find the end tag
	wmd.Chunks.prototype.findTags = function(startRegex, endRegex){
	
		var chunkObj = this;
		var regex;
		
		if (startRegex) {
			
			regex = util.extendRegExp(startRegex, "", "$");
			
			this.before = this.before.replace(regex, 
				function(match){
					chunkObj.startTag = chunkObj.startTag + match;
					return "";
				});
			
			regex = util.extendRegExp(startRegex, "^", "");
			
			this.selection = this.selection.replace(regex, 
				function(match){
					chunkObj.startTag = chunkObj.startTag + match;
					return "";
				});
		}
		
		if (endRegex) {
			
			regex = util.extendRegExp(endRegex, "", "$");
			
			this.selection = this.selection.replace(regex,
				function(match){
					chunkObj.endTag = match + chunkObj.endTag;
					return "";
				});

			regex = util.extendRegExp(endRegex, "^", "");
			
			this.after = this.after.replace(regex,
				function(match){
					chunkObj.endTag = match + chunkObj.endTag;
					return "";
				});
		}
	};
	
	// If remove is false, the whitespace is transferred
	// to the before/after regions.
	//
	// If remove is true, the whitespace disappears.
	wmd.Chunks.prototype.trimWhitespace = function(remove){
	
		this.selection = this.selection.replace(/^(\s*)/, "");
		
		if (!remove) {
			this.before += re.$1;
		}
		
		this.selection = this.selection.replace(/(\s*)$/, "");
		
		if (!remove) {
			this.after = re.$1 + this.after;
		}
	};
	
	
	wmd.Chunks.prototype.addBlankLines = function(nLinesBefore, nLinesAfter, findExtraNewlines){
	
		if (nLinesBefore === undefined) {
			nLinesBefore = 1;
		}
		
		if (nLinesAfter === undefined) {
			nLinesAfter = 1;
		}
		
		nLinesBefore++;
		nLinesAfter++;
		
		var regexText;
		var replacementText;
		
		this.selection = this.selection.replace(/(^\n*)/, "");
		this.startTag = this.startTag + re.$1;
		this.selection = this.selection.replace(/(\n*$)/, "");
		this.endTag = this.endTag + re.$1;
		this.startTag = this.startTag.replace(/(^\n*)/, "");
		this.before = this.before + re.$1;
		this.endTag = this.endTag.replace(/(\n*$)/, "");
		this.after = this.after + re.$1;
		
		if (this.before) {
		
			regexText = replacementText = "";
			
			while (nLinesBefore--) {
				regexText += "\\n?";
				replacementText += "\n";
			}
			
			if (findExtraNewlines) {
				regexText = "\\n*";
			}
			this.before = this.before.replace(new re(regexText + "$", ""), replacementText);
		}
		
		if (this.after) {
		
			regexText = replacementText = "";
			
			while (nLinesAfter--) {
				regexText += "\\n?";
				replacementText += "\n";
			}
			if (findExtraNewlines) {
				regexText = "\\n*";
			}
			
			this.after = this.after.replace(new re(regexText, ""), replacementText);
		}
	};
	
	// The markdown symbols - 4 spaces = code, > = blockquote, etc.
	command.prefixes = "(?:\\s{4,}|\\s*>|\\s*-\\s+|\\s*\\d+\\.|=|\\+|-|_|\\*|#|\\s*\\[[^\n]]+\\]:)";
	
	// Remove markdown symbols from the chunk selection.
	command.unwrap = function(chunk){
		var txt = new re("([^\\n])\\n(?!(\\n|" + command.prefixes + "))", "g");
		chunk.selection = chunk.selection.replace(txt, "$1 $2");
	};
	
	command.wrap = function(chunk, len){
		command.unwrap(chunk);
		var regex = new re("(.{1," + len + "})( +|$\\n?)", "gm");
		
		chunk.selection = chunk.selection.replace(regex, function(line, marked){
			if (new re("^" + command.prefixes, "").test(line)) {
				return line;
			}
			return marked + "\n";
		});
		
		chunk.selection = chunk.selection.replace(/\s+$/, "");
	};
	
	command.doBold = function(chunk, postProcessing, useDefaultText){
		return command.doBorI(chunk, 2, "strong text");
	};
	
	command.doItalic = function(chunk, postProcessing, useDefaultText){
		return command.doBorI(chunk, 1, "emphasized text");
	};
	
	// chunk: The selected region that will be enclosed with */**
	// nStars: 1 for italics, 2 for bold
	// insertText: If you just click the button without highlighting text, this gets inserted
	command.doBorI = function(chunk, nStars, insertText){
	
		// Get rid of whitespace and fixup newlines.
		chunk.trimWhitespace();
		chunk.selection = chunk.selection.replace(/\n{2,}/g, "\n");
		
		// Look for stars before and after.  Is the chunk already marked up?
		chunk.before.search(/(\**$)/);
		var starsBefore = re.$1;
		
		chunk.after.search(/(^\**)/);
		var starsAfter = re.$1;
		
		var prevStars = Math.min(starsBefore.length, starsAfter.length);
		
		// Remove stars if we have to since the button acts as a toggle.
		if ((prevStars >= nStars) && (prevStars != 2 || nStars != 1)) {
			chunk.before = chunk.before.replace(re("[*]{" + nStars + "}$", ""), "");
			chunk.after = chunk.after.replace(re("^[*]{" + nStars + "}", ""), "");
		}
		else if (!chunk.selection && starsAfter) {
			// It's not really clear why this code is necessary.  It just moves
			// some arbitrary stuff around.
			chunk.after = chunk.after.replace(/^([*_]*)/, "");
			chunk.before = chunk.before.replace(/(\s?)$/, "");
			var whitespace = re.$1;
			chunk.before = chunk.before + starsAfter + whitespace;
		}
		else {
		
			// In most cases, if you don't have any selected text and click the button
			// you'll get a selected, marked up region with the default text inserted.
			if (!chunk.selection && !starsAfter) {
				chunk.selection = insertText;
			}
			
			// Add the true markup.
			var markup = nStars <= 1 ? "*" : "**"; // shouldn't the test be = ?
			chunk.before = chunk.before + markup;
			chunk.after = markup + chunk.after;
		}
		
		return;
	};
	
	command.stripLinkDefs = function(text, defsToAdd){
	
		text = text.replace(/^[ ]{0,3}\[(\d+)\]:[ \t]*\n?[ \t]*<?(\S+?)>?[ \t]*\n?[ \t]*(?:(\n*)["(](.+?)[")][ \t]*)?(?:\n+|$)/gm, 
			function(totalMatch, id, link, newlines, title){	
				defsToAdd[id] = totalMatch.replace(/\s*$/, "");
				if (newlines) {
					// Strip the title and return that separately.
					defsToAdd[id] = totalMatch.replace(/["(](.+?)[")]$/, "");
					return newlines + title;
				}
				return "";
			});
		
		return text;
	};
	
	command.addLinkDef = function(chunk, linkDef){
	
		var refNumber = 0; // The current reference number
		var defsToAdd = {}; //
		// Start with a clean slate by removing all previous link definitions.
		chunk.before = command.stripLinkDefs(chunk.before, defsToAdd);
		chunk.selection = command.stripLinkDefs(chunk.selection, defsToAdd);
		chunk.after = command.stripLinkDefs(chunk.after, defsToAdd);
		
		var defs = "";
		var regex = /(\[(?:\[[^\]]*\]|[^\[\]])*\][ ]?(?:\n[ ]*)?\[)(\d+)(\])/g;
		
		var addDefNumber = function(def){
			refNumber++;
			def = def.replace(/^[ ]{0,3}\[(\d+)\]:/, "  [" + refNumber + "]:");
			defs += "\n" + def;
		};
		
		var getLink = function(wholeMatch, link, id, end){
		
			if (defsToAdd[id]) {
				addDefNumber(defsToAdd[id]);
				return link + refNumber + end;
				
			}
			return wholeMatch;
		};
		
		chunk.before = chunk.before.replace(regex, getLink);
		
		if (linkDef) {
			addDefNumber(linkDef);
		}
		else {
			chunk.selection = chunk.selection.replace(regex, getLink);
		}
		
		var refOut = refNumber;
		
		chunk.after = chunk.after.replace(regex, getLink);
		
		if (chunk.after) {
			chunk.after = chunk.after.replace(/\n*$/, "");
		}
		if (!chunk.after) {
			chunk.selection = chunk.selection.replace(/\n*$/, "");
		}
		
		chunk.after += "\n\n" + defs;
		
		return refOut;
	};
	
	command.doLinkOrImage = function(chunk, postProcessing, isImage){
	
		chunk.trimWhitespace();
		chunk.findTags(/\s*!?\[/, /\][ ]?(?:\n[ ]*)?(\[.*?\])?/);
		
		if (chunk.endTag.length > 1) {
		
			chunk.startTag = chunk.startTag.replace(/!?\[/, "");
			chunk.endTag = "";
			command.addLinkDef(chunk, null);
			
		}
		else {
		
			if (/\n\n/.test(chunk.selection)) {
				command.addLinkDef(chunk, null);
				return;
			}
			
			// The function to be executed when you enter a link and press OK or Cancel.
			// Marks up the link and adds the ref.
			var makeLinkMarkdown = function(link){
			
				if (link !== null) {
				
					chunk.startTag = chunk.endTag = "";
					var linkDef = " [999]: " + link;
					
					var num = command.addLinkDef(chunk, linkDef);
					chunk.startTag = isImage ? "![" : "[";
					chunk.endTag = "][" + num + "]";
					
					if (!chunk.selection) {
						if (isImage) {
							chunk.selection = "alt text";
						}
						else {
							chunk.selection = "link text";
						}
					}
				}
				postProcessing();
			};
			
			if (isImage) {
				util.prompt(imageDialogText, imageDefaultText, makeLinkMarkdown);
			}
			else {
				util.prompt(linkDialogText, linkDefaultText, makeLinkMarkdown);
			}
			return true;
		}
	};
	
	util.makeAPI = function(){
		wmd.wmd = {};
		wmd.wmd.editor = wmd.editor;
		wmd.wmd.previewManager = wmd.previewManager;
	};
	
	util.startEditor = function(){
	
		if (wmd.wmd_env.autostart === false) {
			util.makeAPI();
			return;
		}

		var edit;		// The editor (buttons + input + outputs) - the main object.
		var previewMgr;	// The preview manager.
		
		// Fired after the page has fully loaded.
		var loadListener = function(){
		
			wmd.panels = new wmd.PanelCollection();
			
			previewMgr = new wmd.previewManager();
			var previewRefreshCallback = previewMgr.refresh;
						
			edit = new wmd.editor(previewRefreshCallback);
			
			previewMgr.refresh(true);
			
		};
		
		util.addEvent(top, "load", loadListener);
	};
	
	wmd.previewManager = function(){
		
		var managerObj = this;
		var converter;
		var poller;
		var timeout;
		var elapsedTime;
		var oldInputText;
		var htmlOut;
		var maxDelay = 3000;
		var startType = "delayed"; // The other legal value is "manual"
		
		// Adds event listeners to elements and creates the input poller.
		var setupEvents = function(inputElem, listener){
		
			util.addEvent(inputElem, "input", listener);
			inputElem.onpaste = listener;
			inputElem.ondrop = listener;
			
			util.addEvent(inputElem, "keypress", listener);
			util.addEvent(inputElem, "keydown", listener);
			// previewPollInterval is set at the top of this file.
			poller = new wmd.inputPoller(listener, previewPollInterval);
		};
		
		var getDocScrollTop = function(){
		
			var result = 0;
			
			if (top.innerHeight) {
				result = top.pageYOffset;
			}
			else 
				if (doc.documentElement && doc.documentElement.scrollTop) {
					result = doc.documentElement.scrollTop;
				}
				else 
					if (doc.body) {
						result = doc.body.scrollTop;
					}
			
			return result;
		};
		
		var makePreviewHtml = function(){
		
			// If there are no registered preview and output panels
			// there is nothing to do.
			if (!wmd.panels.preview && !wmd.panels.output) {
				return;
			}
			
			var text = wmd.panels.input.value;
			if (text && text == oldInputText) {
				return; // Input text hasn't changed.
			}
			else {
				oldInputText = text;
			}
			
			var prevTime = new Date().getTime();
			
			if (!converter && wmd.showdown) {
				converter = new wmd.showdown.converter();
			}
			
			if (converter) {
				text = converter.makeHtml(text);
			}
			
			// Calculate the processing time of the HTML creation.
			// It's used as the delay time in the event listener.
			var currTime = new Date().getTime();
			elapsedTime = currTime - prevTime;
			
			pushPreviewHtml(text);
			htmlOut = text;
		};
		
		// setTimeout is already used.  Used as an event listener.
		var applyTimeout = function(){
		
			if (timeout) {
				top.clearTimeout(timeout);
				timeout = undefined;
			}
			
			if (startType !== "manual") {
			
				var delay = 0;
				
				if (startType === "delayed") {
					delay = elapsedTime;
				}
				
				if (delay > maxDelay) {
					delay = maxDelay;
				}
				timeout = top.setTimeout(makePreviewHtml, delay);
			}
		};
		
		var getScaleFactor = function(panel){
			if (panel.scrollHeight <= panel.clientHeight) {
				return 1;
			}
			return panel.scrollTop / (panel.scrollHeight - panel.clientHeight);
		};
		
		var setPanelScrollTops = function(){
		
			if (wmd.panels.preview) {
				wmd.panels.preview.scrollTop = (wmd.panels.preview.scrollHeight - wmd.panels.preview.clientHeight) * getScaleFactor(wmd.panels.preview);
				;
			}
			
			if (wmd.panels.output) {
				wmd.panels.output.scrollTop = (wmd.panels.output.scrollHeight - wmd.panels.output.clientHeight) * getScaleFactor(wmd.panels.output);
				;
			}
		};
		
		this.refresh = function(requiresRefresh){
		
			if (requiresRefresh) {
				oldInputText = "";
				makePreviewHtml();
			}
			else {
				applyTimeout();
			}
		};
		
		this.processingTime = function(){
			return elapsedTime;
		};
		
		// The output HTML
		this.output = function(){
			return htmlOut;
		};
		
		// The mode can be "manual" or "delayed"
		this.setUpdateMode = function(mode){
			startType = mode;
			managerObj.refresh();
		};
		
		var isFirstTimeFilled = true;
		
		var pushPreviewHtml = function(text){
		
			var emptyTop = position.getTop(wmd.panels.input) - getDocScrollTop();
			
			// Send the encoded HTML to the output textarea/div.
			if (wmd.panels.output) {
				// The value property is only defined if the output is a textarea.
				if (wmd.panels.output.value !== undefined) {
					wmd.panels.output.value = text;
					wmd.panels.output.readOnly = true;
				}
				// Otherwise we are just replacing the text in a div.
				// Send the HTML wrapped in <pre><code>
				else {
					var newText = text.replace(/&/g, "&amp;");
					newText = newText.replace(/</g, "&lt;");
					wmd.panels.output.innerHTML = "<pre><code>" + newText + "</code></pre>";
				}
			}
			
			if (wmd.panels.preview) {
				wmd.panels.preview.innerHTML = text;
			}
			
			setPanelScrollTops();
			
			if (isFirstTimeFilled) {
				isFirstTimeFilled = false;
				return;
			}
			
			var fullTop = position.getTop(wmd.panels.input) - getDocScrollTop();
			
			if (global.isIE) {
				top.setTimeout(function(){
					top.scrollBy(0, fullTop - emptyTop);
				}, 0);
			}
			else {
				top.scrollBy(0, fullTop - emptyTop);
			}
		};
		
		var init = function(){
		
			setupEvents(wmd.panels.input, applyTimeout);
			makePreviewHtml();
			
			if (wmd.panels.preview) {
				wmd.panels.preview.scrollTop = 0;
			}
			if (wmd.panels.output) {
				wmd.panels.output.scrollTop = 0;
			}
		};
		
		this.destroy = function(){
			if (poller) {
				poller.destroy();
			}
		};
		
		init();
	};

	// Moves the cursor to the next line and continues lists, quotes and code.
	command.doAutoindent = function(chunk, postProcessing, useDefaultText){
		
		chunk.before = chunk.before.replace(/(\n|^)[ ]{0,3}([*+-]|\d+[.])[ \t]*\n$/, "\n\n");
		chunk.before = chunk.before.replace(/(\n|^)[ ]{0,3}>[ \t]*\n$/, "\n\n");
		chunk.before = chunk.before.replace(/(\n|^)[ \t]+\n$/, "\n\n");
		
		useDefaultText = false;
		
		if(/(\n|^)[ ]{0,3}([*+-])[ \t]+.*\n$/.test(chunk.before)){
			if(command.doList){
				command.doList(chunk, postProcessing, false, true);
			}
		}
		if(/(\n|^)[ ]{0,3}(\d+[.])[ \t]+.*\n$/.test(chunk.before)){
			if(command.doList){
				command.doList(chunk, postProcessing, true, true);
			}
		}
		if(/(\n|^)[ ]{0,3}>[ \t]+.*\n$/.test(chunk.before)){
			if(command.doBlockquote){
				command.doBlockquote(chunk, postProcessing, useDefaultText);
			}
		}
		if(/(\n|^)(\t|[ ]{4,}).*\n$/.test(chunk.before)){
			if(command.doCode){
				command.doCode(chunk, postProcessing, useDefaultText);
			}
		}
	};
	
	command.doBlockquote = function(chunk, postProcessing, useDefaultText){
		
		chunk.selection = chunk.selection.replace(/^(\n*)([^\r]+?)(\n*)$/,
			function(totalMatch, newlinesBefore, text, newlinesAfter){
				chunk.before += newlinesBefore;
				chunk.after = newlinesAfter + chunk.after;
				return text;
			});
			
		chunk.before = chunk.before.replace(/(>[ \t]*)$/,
			function(totalMatch, blankLine){
				chunk.selection = blankLine + chunk.selection;
				return "";
			});
		
		var defaultText = useDefaultText ? "Blockquote" : "";
		chunk.selection = chunk.selection.replace(/^(\s|>)+$/ ,"");
		chunk.selection = chunk.selection || defaultText;
		
		if(chunk.before){
			chunk.before = chunk.before.replace(/\n?$/,"\n");
		}
		if(chunk.after){
			chunk.after = chunk.after.replace(/^\n?/,"\n");
		}
		
		chunk.before = chunk.before.replace(/(((\n|^)(\n[ \t]*)*>(.+\n)*.*)+(\n[ \t]*)*$)/,
			function(totalMatch){
				chunk.startTag = totalMatch;
				return "";
			});
			
		chunk.after = chunk.after.replace(/^(((\n|^)(\n[ \t]*)*>(.+\n)*.*)+(\n[ \t]*)*)/,
			function(totalMatch){
				chunk.endTag = totalMatch;
				return "";
			});
		
		var replaceBlanksInTags = function(useBracket){
			
			var replacement = useBracket ? "> " : "";
			
			if(chunk.startTag){
				chunk.startTag = chunk.startTag.replace(/\n((>|\s)*)\n$/,
					function(totalMatch, markdown){
						return "\n" + markdown.replace(/^[ ]{0,3}>?[ \t]*$/gm, replacement) + "\n";
					});
			}
			if(chunk.endTag){
				chunk.endTag = chunk.endTag.replace(/^\n((>|\s)*)\n/,
					function(totalMatch, markdown){
						return "\n" + markdown.replace(/^[ ]{0,3}>?[ \t]*$/gm, replacement) + "\n";
					});
			}
		};
		
		if(/^(?![ ]{0,3}>)/m.test(chunk.selection)){
			command.wrap(chunk, wmd.wmd_env.lineLength - 2);
			chunk.selection = chunk.selection.replace(/^/gm, "> ");
			replaceBlanksInTags(true);
			chunk.addBlankLines();
		}
		else{
			chunk.selection = chunk.selection.replace(/^[ ]{0,3}> ?/gm, "");
			command.unwrap(chunk);
			replaceBlanksInTags(false);
			
			if(!/^(\n|^)[ ]{0,3}>/.test(chunk.selection) && chunk.startTag){
				chunk.startTag = chunk.startTag.replace(/\n{0,2}$/, "\n\n");
			}
			
			if(!/(\n|^)[ ]{0,3}>.*$/.test(chunk.selection) && chunk.endTag){
				chunk.endTag=chunk.endTag.replace(/^\n{0,2}/, "\n\n");
			}
		}
		
		if(!/\n/.test(chunk.selection)){
			chunk.selection = chunk.selection.replace(/^(> *)/,
			function(wholeMatch, blanks){
				chunk.startTag += blanks;
				return "";
			});
		}
	};

	command.doCode = function(chunk, postProcessing, useDefaultText){
		
		var hasTextBefore = /\S[ ]*$/.test(chunk.before);
		var hasTextAfter = /^[ ]*\S/.test(chunk.after);
		
		// Use 'four space' markdown if the selection is on its own
		// line or is multiline.
		if((!hasTextAfter && !hasTextBefore) || /\n/.test(chunk.selection)){
			
			chunk.before = chunk.before.replace(/[ ]{4}$/,
				function(totalMatch){
					chunk.selection = totalMatch + chunk.selection;
					return "";
				});
				
			var nLinesBefore = 1;
			var nLinesAfter = 1;
			
			
			if(/\n(\t|[ ]{4,}).*\n$/.test(chunk.before) || chunk.after === ""){
				nLinesBefore = 0; 
			}
			if(/^\n(\t|[ ]{4,})/.test(chunk.after)){
				nLinesAfter = 0; // This needs to happen on line 1
			}
			
			chunk.addBlankLines(nLinesBefore, nLinesAfter);
			
			if(!chunk.selection){
				chunk.startTag = "    ";
				chunk.selection = useDefaultText ? "enter code here" : "";
			}
			else {
				if(/^[ ]{0,3}\S/m.test(chunk.selection)){
					chunk.selection = chunk.selection.replace(/^/gm, "    ");
				}
				else{
					chunk.selection = chunk.selection.replace(/^[ ]{4}/gm, "");
				}
			}
		}
		else{
			// Use backticks (`) to delimit the code block.
			
			chunk.trimWhitespace();
			chunk.findTags(/`/, /`/);
			
			if(!chunk.startTag && !chunk.endTag){
				chunk.startTag = chunk.endTag="`";
				if(!chunk.selection){
					chunk.selection = useDefaultText ? "enter code here" : "";
				}
			}
			else if(chunk.endTag && !chunk.startTag){
				chunk.before += chunk.endTag;
				chunk.endTag = "";
			}
			else{
				chunk.startTag = chunk.endTag="";
			}
		}
	};
	
	command.doList = function(chunk, postProcessing, isNumberedList, useDefaultText){
				
		// These are identical except at the very beginning and end.
		// Should probably use the regex extension function to make this clearer.
		var previousItemsRegex = /(\n|^)(([ ]{0,3}([*+-]|\d+[.])[ \t]+.*)(\n.+|\n{2,}([*+-].*|\d+[.])[ \t]+.*|\n{2,}[ \t]+\S.*)*)\n*$/;
		var nextItemsRegex = /^\n*(([ ]{0,3}([*+-]|\d+[.])[ \t]+.*)(\n.+|\n{2,}([*+-].*|\d+[.])[ \t]+.*|\n{2,}[ \t]+\S.*)*)\n*/;
		
		// The default bullet is a dash but others are possible.
		// This has nothing to do with the particular HTML bullet,
		// it's just a markdown bullet.
		var bullet = "-";
		
		// The number in a numbered list.
		var num = 1;
		
		// Get the item prefix - e.g. " 1. " for a numbered list, " - " for a bulleted list.
		var getItemPrefix = function(){
			var prefix;
			if(isNumberedList){
				prefix = " " + num + ". ";
				num++;
			}
			else{
				prefix = " " + bullet + " ";
			}
			return prefix;
		};
		
		// Fixes the prefixes of the other list items.
		var getPrefixedItem = function(itemText){
		
			// The numbering flag is unset when called by autoindent.
			if(isNumberedList === undefined){
				isNumberedList = /^\s*\d/.test(itemText);
			}
			
			// Renumber/bullet the list element.
			itemText = itemText.replace(/^[ ]{0,3}([*+-]|\d+[.])\s/gm,
				function( _ ){
					return getItemPrefix();
				});
				
			return itemText;
		};
		
		chunk.findTags(/(\n|^)*[ ]{0,3}([*+-]|\d+[.])\s+/, null);
		
		if(chunk.before && !/\n$/.test(chunk.before) && !/^\n/.test(chunk.startTag)){
			chunk.before += chunk.startTag;
			chunk.startTag = "";
		}
		
		if(chunk.startTag){
			
			var hasDigits = /\d+[.]/.test(chunk.startTag);
			chunk.startTag = "";
			chunk.selection = chunk.selection.replace(/\n[ ]{4}/g, "\n");
			command.unwrap(chunk);
			chunk.addBlankLines();
			
			if(hasDigits){
				// Have to renumber the bullet points if this is a numbered list.
				chunk.after = chunk.after.replace(nextItemsRegex, getPrefixedItem);
			}
			if(isNumberedList == hasDigits){
				return;
			}
		}
		
		var nLinesBefore = 1;
		
		chunk.before = chunk.before.replace(previousItemsRegex,
			function(itemText){
				if(/^\s*([*+-])/.test(itemText)){
					bullet = re.$1;
				}
				nLinesBefore = /[^\n]\n\n[^\n]/.test(itemText) ? 1 : 0;
				return getPrefixedItem(itemText);
			});
			
		if(!chunk.selection){
			chunk.selection = useDefaultText ? "List item" : " ";
		}
		
		var prefix = getItemPrefix();
		
		var nLinesAfter = 1;
		
		chunk.after = chunk.after.replace(nextItemsRegex,
			function(itemText){
				nLinesAfter = /[^\n]\n\n[^\n]/.test(itemText) ? 1 : 0;
				return getPrefixedItem(itemText);
			});
			
		chunk.trimWhitespace(true);
		chunk.addBlankLines(nLinesBefore, nLinesAfter, true);
		chunk.startTag = prefix;
		var spaces = prefix.replace(/./g, " ");
		command.wrap(chunk, wmd.wmd_env.lineLength - spaces.length);
		chunk.selection = chunk.selection.replace(/\n/g, "\n" + spaces);
		
	};
	
	command.doHeading = function(chunk, postProcessing, useDefaultText){
		
		// Remove leading/trailing whitespace and reduce internal spaces to single spaces.
		chunk.selection = chunk.selection.replace(/\s+/g, " ");
		chunk.selection = chunk.selection.replace(/(^\s+|\s+$)/g, "");
		
		// If we clicked the button with no selected text, we just
		// make a level 2 hash header around some default text.
		if(!chunk.selection){
			chunk.startTag = "## ";
			chunk.selection = "Heading";
			chunk.endTag = " ##";
			return;
		}
		
		var headerLevel = 0;		// The existing header level of the selected text.
		
		// Remove any existing hash heading markdown and save the header level.
		chunk.findTags(/#+[ ]*/, /[ ]*#+/);
		if(/#+/.test(chunk.startTag)){
			headerLevel = re.lastMatch.length;
		}
		chunk.startTag = chunk.endTag = "";
		
		// Try to get the current header level by looking for - and = in the line
		// below the selection.
		chunk.findTags(null, /\s?(-+|=+)/);
		if(/=+/.test(chunk.endTag)){
			headerLevel = 1;
		}
		if(/-+/.test(chunk.endTag)){
			headerLevel = 2;
		}
		
		// Skip to the next line so we can create the header markdown.
		chunk.startTag = chunk.endTag = "";
		chunk.addBlankLines(1, 1);

		// We make a level 2 header if there is no current header.
		// If there is a header level, we substract one from the header level.
		// If it's already a level 1 header, it's removed.
		var headerLevelToCreate = headerLevel == 0 ? 2 : headerLevel - 1;
		
		if(headerLevelToCreate > 0){
			
			// The button only creates level 1 and 2 underline headers.
			// Why not have it iterate over hash header levels?  Wouldn't that be easier and cleaner?
			var headerChar = headerLevelToCreate >= 2 ? "-" : "=";
			var len = chunk.selection.length;
			if(len > wmd.wmd_env.lineLength){
				len = wmd.wmd_env.lineLength;
			}
			chunk.endTag = "\n";
			while(len--){
				chunk.endTag += headerChar;
			}
		}
	};	
	
	command.doHorizontalRule = function(chunk, postProcessing, useDefaultText){
		chunk.startTag = "----------\n";
		chunk.selection = "";
		chunk.addBlankLines(2, 1, true);
	}
};


Attacklab.wmd_env = {};
Attacklab.account_options = {};
Attacklab.wmd_defaults = {version:2.0, output_format:"markdown", lineLength:40, delayLoad:false};

if(!Attacklab.wmd)
{
	Attacklab.wmd = function()
	{
		Attacklab.loadEnv = function()
		{
			var mergeEnv = function(env)
			{
				if(!env)
				{
					return;
				}
			
				for(var key in env)
				{
					Attacklab.wmd_env[key] = env[key];
				}
			};
			
			mergeEnv(Attacklab.wmd_defaults);
			mergeEnv(Attacklab.account_options);
			mergeEnv(wmd_options);
			Attacklab.full = true;
			
			var defaultButtons = "bold italic link blockquote code image ol ul heading hr";
			Attacklab.wmd_env.buttons = Attacklab.wmd_env.buttons || defaultButtons;
		};
		Attacklab.loadEnv();

	};
	
	Attacklab.wmd();
	Attacklab.wmdBase();
	Attacklab.Util.startEditor();
};

}
//
// showdown.js -- A javascript port of Markdown.
//
// Copyright (c) 2007 John Fraser.
//
// Original Markdown Copyright (c) 2004-2005 John Gruber
//   <http://daringfireball.net/projects/markdown/>
//
// The full source distribution is at:
//
//				A A L
//				T C A
//				T K B
//
//   <http://www.attacklab.net/>
//

//
// Wherever possible, Showdown is a straight, line-by-line port
// of the Perl version of Markdown.
//
// This is not a normal parser design; it's basically just a
// series of string substitutions.  It's hard to read and
// maintain this way,  but keeping Showdown close to the original
// design makes it easier to port new features.
//
// More importantly, Showdown behaves like markdown.pl in most
// edge cases.  So web applications can do client-side preview
// in Javascript, and then build identical HTML on the server.
//
// This port needs the new RegExp functionality of ECMA 262,
// 3rd Edition (i.e. Javascript 1.5).  Most modern web browsers
// should do fine.  Even with the new regular expression features,
// We do a lot of work to emulate Perl's regex functionality.
// The tricky changes in this file mostly have the "attacklab:"
// label.  Major or self-explanatory changes don't.
//
// Smart diff tools like Araxis Merge will be able to match up
// this file with markdown.pl in a useful way.  A little tweaking
// helps: in a copy of markdown.pl, replace "#" with "//" and
// replace "$text" with "text".  Be sure to ignore whitespace
// and line endings.
//


//
// Showdown usage:
//
//   var text = "Markdown *rocks*.";
//
//   var converter = new Attacklab.showdown.converter();
//   var html = converter.makeHtml(text);
//
//   alert(html);
//
// Note: move the sample code to the bottom of this
// file before uncommenting it.
//


//
// Attacklab namespace
//
var Attacklab = Attacklab || {}

//
// Showdown namespace
//
Attacklab.showdown = Attacklab.showdown || {}

//
// converter
//
// Wraps all "globals" so that the only thing
// exposed is makeHtml().
//
Attacklab.showdown.converter = function() {

//
// Globals:
//

// Global hashes, used by various utility routines
var g_urls;
var g_titles;
var g_html_blocks;

// Used to track when we're inside an ordered or unordered list
// (see _ProcessListItems() for details):
var g_list_level = 0;


this.makeHtml = function(text) {
//
// Main function. The order in which other subs are called here is
// essential. Link and image substitutions need to happen before
// _EscapeSpecialCharsWithinTagAttributes(), so that any *'s or _'s in the <a>
// and <img> tags get encoded.
//

	// Clear the global hashes. If we don't clear these, you get conflicts
	// from other articles when generating a page which contains more than
	// one article (e.g. an index page that shows the N most recent
	// articles):
	g_urls = new Array();
	g_titles = new Array();
	g_html_blocks = new Array();

	// attacklab: Replace ~ with ~T
	// This lets us use tilde as an escape char to avoid md5 hashes
	// The choice of character is arbitray; anything that isn't
    // magic in Markdown will work.
	text = text.replace(/~/g,"~T");

	// attacklab: Replace $ with ~D
	// RegExp interprets $ as a special character
	// when it's in a replacement string
	text = text.replace(/\$/g,"~D");

	// Standardize line endings
	text = text.replace(/\r\n/g,"\n"); // DOS to Unix
	text = text.replace(/\r/g,"\n"); // Mac to Unix

	// Make sure text begins and ends with a couple of newlines:
	text = "\n\n" + text + "\n\n";

	// Convert all tabs to spaces.
	text = _Detab(text);

	// Strip any lines consisting only of spaces and tabs.
	// This makes subsequent regexen easier to write, because we can
	// match consecutive blank lines with /\n+/ instead of something
	// contorted like /[ \t]*\n+/ .
	text = text.replace(/^[ \t]+$/mg,"");

	// Turn block-level HTML blocks into hash entries
	text = _HashHTMLBlocks(text);

	// Strip link definitions, store in hashes.
	text = _StripLinkDefinitions(text);

	text = _RunBlockGamut(text);

	text = _UnescapeSpecialChars(text);

	// attacklab: Restore dollar signs
	text = text.replace(/~D/g,"$$");

	// attacklab: Restore tildes
	text = text.replace(/~T/g,"~");

        // ** GFM **  Auto-link URLs and emails
        text = text.replace(/https?\:\/\/[^"\s\<\>]*[^.,;'">\:\s\<\>\)\]\!]/g, function(wholeMatch){
            var left = RegExp.leftContext
            var right = RegExp.rightContext
            if (left.match(/<[^>]+$/) && right.match(/^[^>]*>/)) {return wholeMatch}
            return "<a href='" + wholeMatch + "'>" + wholeMatch + "</a>";
        });
        text = text.replace(/[a-z0-9_\-+=.]+@[a-z0-9\-]+(\.[a-z0-9-]+)+/ig, function(wholeMatch){
            return "<a href='mailto:" + wholeMatch + "'>" + wholeMatch + "</a>";
        });


	return text;
}

var _StripLinkDefinitions = function(text) {
//
// Strips link definitions from text, stores the URLs and titles in
// hash references.
//

	// Link defs are in the form: ^[id]: url "optional title"

	/*
		var text = text.replace(/
				^[ ]{0,3}\[(.+)\]:  // id = $1  attacklab: g_tab_width - 1
				  [ \t]*
				  \n?				// maybe *one* newline
				  [ \t]*
				<?(\S+?)>?			// url = $2
				  [ \t]*
				  \n?				// maybe one newline
				  [ \t]*
				(?:
				  (\n*)				// any lines skipped = $3 attacklab: lookbehind removed
				  ["(]
				  (.+?)				// title = $4
				  [")]
				  [ \t]*
				)?					// title is optional
				(?:\n+|$)
			  /gm,
			  function(){...});
	*/
	var text = text.replace(/^[ ]{0,3}\[(.+)\]:[ \t]*\n?[ \t]*<?(\S+?)>?[ \t]*\n?[ \t]*(?:(\n*)["(](.+?)[")][ \t]*)?(?:\n+)/gm,
		function (wholeMatch,m1,m2,m3,m4) {
			m1 = m1.toLowerCase();
			g_urls[m1] = _EncodeAmpsAndAngles(m2);  // Link IDs are case-insensitive
			if (m3) {
				// Oops, found blank lines, so it's not a title.
				// Put back the parenthetical statement we stole.
				return m3+m4;
			} else if (m4) {
				g_titles[m1] = m4.replace(/"/g,"&quot;");
			}
			
			// Completely remove the definition from the text
			return "";
		}
	);

	return text;
}

var _HashHTMLBlocks = function(text) {
	// attacklab: Double up blank lines to reduce lookaround
	text = text.replace(/\n/g,"\n\n");

	// Hashify HTML blocks:
	// We only want to do this for block-level HTML tags, such as headers,
	// lists, and tables. That's because we still want to wrap <p>s around
	// "paragraphs" that are wrapped in non-block-level tags, such as anchors,
	// phrase emphasis, and spans. The list of tags we're looking for is
	// hard-coded:
	var block_tags_a = "p|div|h[1-6]|blockquote|pre|table|dl|ol|ul|script|noscript|form|fieldset|iframe|math|ins|del"
	var block_tags_b = "p|div|h[1-6]|blockquote|pre|table|dl|ol|ul|script|noscript|form|fieldset|iframe|math"

	// First, look for nested blocks, e.g.:
	//   <div>
	//     <div>
	//     tags for inner block must be indented.
	//     </div>
	//   </div>
	//
	// The outermost tags must start at the left margin for this to match, and
	// the inner nested divs must be indented.
	// We need to do this before the next, more liberal match, because the next
	// match will start at the first `<div>` and stop at the first `</div>`.

	// attacklab: This regex can be expensive when it fails.
	/*
		var text = text.replace(/
		(						// save in $1
			^					// start of line  (with /m)
			<($block_tags_a)	// start tag = $2
			\b					// word break
								// attacklab: hack around khtml/pcre bug...
			[^\r]*?\n			// any number of lines, minimally matching
			</\2>				// the matching end tag
			[ \t]*				// trailing spaces/tabs
			(?=\n+)				// followed by a newline
		)						// attacklab: there are sentinel newlines at end of document
		/gm,function(){...}};
	*/
	text = text.replace(/^(<(p|div|h[1-6]|blockquote|pre|table|dl|ol|ul|script|noscript|form|fieldset|iframe|math|ins|del)\b[^\r]*?\n<\/\2>[ \t]*(?=\n+))/gm,hashElement);

	//
	// Now match more liberally, simply from `\n<tag>` to `</tag>\n`
	//

	/*
		var text = text.replace(/
		(						// save in $1
			^					// start of line  (with /m)
			<($block_tags_b)	// start tag = $2
			\b					// word break
								// attacklab: hack around khtml/pcre bug...
			[^\r]*?				// any number of lines, minimally matching
			.*</\2>				// the matching end tag
			[ \t]*				// trailing spaces/tabs
			(?=\n+)				// followed by a newline
		)						// attacklab: there are sentinel newlines at end of document
		/gm,function(){...}};
	*/
	text = text.replace(/^(<(p|div|h[1-6]|blockquote|pre|table|dl|ol|ul|script|noscript|form|fieldset|iframe|math)\b[^\r]*?.*<\/\2>[ \t]*(?=\n+)\n)/gm,hashElement);

	// Special case just for <hr />. It was easier to make a special case than
	// to make the other regex more complicated.  

	/*
		text = text.replace(/
		(						// save in $1
			\n\n				// Starting after a blank line
			[ ]{0,3}
			(<(hr)				// start tag = $2
			\b					// word break
			([^<>])*?			// 
			\/?>)				// the matching end tag
			[ \t]*
			(?=\n{2,})			// followed by a blank line
		)
		/g,hashElement);
	*/
	text = text.replace(/(\n[ ]{0,3}(<(hr)\b([^<>])*?\/?>)[ \t]*(?=\n{2,}))/g,hashElement);

	// Special case for standalone HTML comments:

	/*
		text = text.replace(/
		(						// save in $1
			\n\n				// Starting after a blank line
			[ ]{0,3}			// attacklab: g_tab_width - 1
			<!
			(--[^\r]*?--\s*)+
			>
			[ \t]*
			(?=\n{2,})			// followed by a blank line
		)
		/g,hashElement);
	*/
	text = text.replace(/(\n\n[ ]{0,3}<!(--[^\r]*?--\s*)+>[ \t]*(?=\n{2,}))/g,hashElement);

	// PHP and ASP-style processor instructions (<?...?> and <%...%>)

	/*
		text = text.replace(/
		(?:
			\n\n				// Starting after a blank line
		)
		(						// save in $1
			[ ]{0,3}			// attacklab: g_tab_width - 1
			(?:
				<([?%])			// $2
				[^\r]*?
				\2>
			)
			[ \t]*
			(?=\n{2,})			// followed by a blank line
		)
		/g,hashElement);
	*/
	text = text.replace(/(?:\n\n)([ ]{0,3}(?:<([?%])[^\r]*?\2>)[ \t]*(?=\n{2,}))/g,hashElement);

	// attacklab: Undo double lines (see comment at top of this function)
	text = text.replace(/\n\n/g,"\n");
	return text;
}

var hashElement = function(wholeMatch,m1) {
	var blockText = m1;

	// Undo double lines
	blockText = blockText.replace(/\n\n/g,"\n");
	blockText = blockText.replace(/^\n/,"");
	
	// strip trailing blank lines
	blockText = blockText.replace(/\n+$/g,"");
	
	// Replace the element text with a marker ("~KxK" where x is its key)
	blockText = "\n\n~K" + (g_html_blocks.push(blockText)-1) + "K\n\n";
	
	return blockText;
};

var _RunBlockGamut = function(text) {
//
// These are all the transformations that form block-level
// tags like paragraphs, headers, and list items.
//
	text = _DoHeaders(text);

	// Do Horizontal Rules:
	var key = hashBlock("<hr />");
	text = text.replace(/^[ ]{0,2}([ ]?\*[ ]?){3,}[ \t]*$/gm,key);
	text = text.replace(/^[ ]{0,2}([ ]?\-[ ]?){3,}[ \t]*$/gm,key);
	text = text.replace(/^[ ]{0,2}([ ]?\_[ ]?){3,}[ \t]*$/gm,key);

	text = _DoLists(text);
	text = _DoCodeBlocks(text);
	text = _DoBlockQuotes(text);

	// We already ran _HashHTMLBlocks() before, in Markdown(), but that
	// was to escape raw HTML in the original Markdown source. This time,
	// we're escaping the markup we've just created, so that we don't wrap
	// <p> tags around block-level tags.
	text = _HashHTMLBlocks(text);
	text = _FormParagraphs(text);

	return text;
}


var _RunSpanGamut = function(text) {
//
// These are all the transformations that occur *within* block-level
// tags like paragraphs, headers, and list items.
//

	text = _DoCodeSpans(text);
	text = _EscapeSpecialCharsWithinTagAttributes(text);
	text = _EncodeBackslashEscapes(text);

	// Process anchor and image tags. Images must come first,
	// because ![foo][f] looks like an anchor.
	text = _DoImages(text);
	text = _DoAnchors(text);

	// Make links out of things like `<http://example.com/>`
	// Must come after _DoAnchors(), because you can use < and >
	// delimiters in inline links like [this](<url>).
	text = _DoAutoLinks(text);
	text = _EncodeAmpsAndAngles(text);
	text = _DoItalicsAndBold(text);

	// Do hard breaks:
	text = text.replace(/  +\n/g," <br />\n");

	return text;
}

var _EscapeSpecialCharsWithinTagAttributes = function(text) {
//
// Within tags -- meaning between < and > -- encode [\ ` * _] so they
// don't conflict with their use in Markdown for code, italics and strong.
//

	// Build a regex to find HTML tags and comments.  See Friedl's 
	// "Mastering Regular Expressions", 2nd Ed., pp. 200-201.
	var regex = /(<[a-z\/!$]("[^"]*"|'[^']*'|[^'">])*>|<!(--.*?--\s*)+>)/gi;

	text = text.replace(regex, function(wholeMatch) {
		var tag = wholeMatch.replace(/(.)<\/?code>(?=.)/g,"$1`");
		tag = escapeCharacters(tag,"\\`*_");
		return tag;
	});

	return text;
}

var _DoAnchors = function(text) {
//
// Turn Markdown link shortcuts into XHTML <a> tags.
//
	//
	// First, handle reference-style links: [link text] [id]
	//

	/*
		text = text.replace(/
		(							// wrap whole match in $1
			\[
			(
				(?:
					\[[^\]]*\]		// allow brackets nested one level
					|
					[^\[]			// or anything else
				)*
			)
			\]

			[ ]?					// one optional space
			(?:\n[ ]*)?				// one optional newline followed by spaces

			\[
			(.*?)					// id = $3
			\]
		)()()()()					// pad remaining backreferences
		/g,_DoAnchors_callback);
	*/
	text = text.replace(/(\[((?:\[[^\]]*\]|[^\[\]])*)\][ ]?(?:\n[ ]*)?\[(.*?)\])()()()()/g,writeAnchorTag);

	//
	// Next, inline-style links: [link text](url "optional title")
	//

	/*
		text = text.replace(/
			(						// wrap whole match in $1
				\[
				(
					(?:
						\[[^\]]*\]	// allow brackets nested one level
					|
					[^\[\]]			// or anything else
				)
			)
			\]
			\(						// literal paren
			[ \t]*
			()						// no id, so leave $3 empty
			<?(.*?)>?				// href = $4
			[ \t]*
			(						// $5
				(['"])				// quote char = $6
				(.*?)				// Title = $7
				\6					// matching quote
				[ \t]*				// ignore any spaces/tabs between closing quote and )
			)?						// title is optional
			\)
		)
		/g,writeAnchorTag);
	*/
	text = text.replace(/(\[((?:\[[^\]]*\]|[^\[\]])*)\]\([ \t]*()<?(.*?)>?[ \t]*((['"])(.*?)\6[ \t]*)?\))/g,writeAnchorTag);

	//
	// Last, handle reference-style shortcuts: [link text]
	// These must come last in case you've also got [link test][1]
	// or [link test](/foo)
	//

	/*
		text = text.replace(/
		(		 					// wrap whole match in $1
			\[
			([^\[\]]+)				// link text = $2; can't contain '[' or ']'
			\]
		)()()()()()					// pad rest of backreferences
		/g, writeAnchorTag);
	*/
	text = text.replace(/(\[([^\[\]]+)\])()()()()()/g, writeAnchorTag);

	return text;
}

var writeAnchorTag = function(wholeMatch,m1,m2,m3,m4,m5,m6,m7) {
	if (m7 == undefined) m7 = "";
	var whole_match = m1;
	var link_text   = m2;
	var link_id	 = m3.toLowerCase();
	var url		= m4;
	var title	= m7;
	
	if (url == "") {
		if (link_id == "") {
			// lower-case and turn embedded newlines into spaces
			link_id = link_text.toLowerCase().replace(/ ?\n/g," ");
		}
		url = "#"+link_id;
		
		if (g_urls[link_id] != undefined) {
			url = g_urls[link_id];
			if (g_titles[link_id] != undefined) {
				title = g_titles[link_id];
			}
		}
		else {
			if (whole_match.search(/\(\s*\)$/m)>-1) {
				// Special case for explicit empty url
				url = "";
			} else {
				return whole_match;
			}
		}
	}	
	
	url = escapeCharacters(url,"*_");
	var result = "<a href=\"" + url + "\"";
	
	if (title != "") {
		title = title.replace(/"/g,"&quot;");
		title = escapeCharacters(title,"*_");
		result +=  " title=\"" + title + "\"";
	}
	
	result += ">" + link_text + "</a>";
	
	return result;
}


var _DoImages = function(text) {
//
// Turn Markdown image shortcuts into <img> tags.
//

	//
	// First, handle reference-style labeled images: ![alt text][id]
	//

	/*
		text = text.replace(/
		(						// wrap whole match in $1
			!\[
			(.*?)				// alt text = $2
			\]

			[ ]?				// one optional space
			(?:\n[ ]*)?			// one optional newline followed by spaces

			\[
			(.*?)				// id = $3
			\]
		)()()()()				// pad rest of backreferences
		/g,writeImageTag);
	*/
	text = text.replace(/(!\[(.*?)\][ ]?(?:\n[ ]*)?\[(.*?)\])()()()()/g,writeImageTag);

	//
	// Next, handle inline images:  ![alt text](url "optional title")
	// Don't forget: encode * and _

	/*
		text = text.replace(/
		(						// wrap whole match in $1
			!\[
			(.*?)				// alt text = $2
			\]
			\s?					// One optional whitespace character
			\(					// literal paren
			[ \t]*
			()					// no id, so leave $3 empty
			<?(\S+?)>?			// src url = $4
			[ \t]*
			(					// $5
				(['"])			// quote char = $6
				(.*?)			// title = $7
				\6				// matching quote
				[ \t]*
			)?					// title is optional
		\)
		)
		/g,writeImageTag);
	*/
	text = text.replace(/(!\[(.*?)\]\s?\([ \t]*()<?(\S+?)>?[ \t]*((['"])(.*?)\6[ \t]*)?\))/g,writeImageTag);

	return text;
}

var writeImageTag = function(wholeMatch,m1,m2,m3,m4,m5,m6,m7) {
	var whole_match = m1;
	var alt_text   = m2;
	var link_id	 = m3.toLowerCase();
	var url		= m4;
	var title	= m7;

	if (!title) title = "";
	
	if (url == "") {
		if (link_id == "") {
			// lower-case and turn embedded newlines into spaces
			link_id = alt_text.toLowerCase().replace(/ ?\n/g," ");
		}
		url = "#"+link_id;
		
		if (g_urls[link_id] != undefined) {
			url = g_urls[link_id];
			if (g_titles[link_id] != undefined) {
				title = g_titles[link_id];
			}
		}
		else {
			return whole_match;
		}
	}	
	
	alt_text = alt_text.replace(/"/g,"&quot;");
	url = escapeCharacters(url,"*_");
	var result = "<img src=\"" + url + "\" alt=\"" + alt_text + "\"";

	// attacklab: Markdown.pl adds empty title attributes to images.
	// Replicate this bug.

	//if (title != "") {
		title = title.replace(/"/g,"&quot;");
		title = escapeCharacters(title,"*_");
		result +=  " title=\"" + title + "\"";
	//}
	
	result += " />";
	
	return result;
}


var _DoHeaders = function(text) {

	// Setext-style headers:
	//	Header 1
	//	========
	//  
	//	Header 2
	//	--------
	//
	text = text.replace(/^(.+)[ \t]*\n=+[ \t]*\n+/gm,
		function(wholeMatch,m1){return hashBlock("<h1>" + _RunSpanGamut(m1) + "</h1>");});

	text = text.replace(/^(.+)[ \t]*\n-+[ \t]*\n+/gm,
		function(matchFound,m1){return hashBlock("<h2>" + _RunSpanGamut(m1) + "</h2>");});

	// atx-style headers:
	//  # Header 1
	//  ## Header 2
	//  ## Header 2 with closing hashes ##
	//  ...
	//  ###### Header 6
	//

	/*
		text = text.replace(/
			^(\#{1,6})				// $1 = string of #'s
			[ \t]*
			(.+?)					// $2 = Header text
			[ \t]*
			\#*						// optional closing #'s (not counted)
			\n+
		/gm, function() {...});
	*/

	text = text.replace(/^(\#{1,6})[ \t]*(.+?)[ \t]*\#*\n+/gm,
		function(wholeMatch,m1,m2) {
			var h_level = m1.length;
			return hashBlock("<h" + h_level + ">" + _RunSpanGamut(m2) + "</h" + h_level + ">");
		});

	return text;
}

// This declaration keeps Dojo compressor from outputting garbage:
var _ProcessListItems;

var _DoLists = function(text) {
//
// Form HTML ordered (numbered) and unordered (bulleted) lists.
//

	// attacklab: add sentinel to hack around khtml/safari bug:
	// http://bugs.webkit.org/show_bug.cgi?id=11231
	text += "~0";

	// Re-usable pattern to match any entirel ul or ol list:

	/*
		var whole_list = /
		(									// $1 = whole list
			(								// $2
				[ ]{0,3}					// attacklab: g_tab_width - 1
				([*+-]|\d+[.])				// $3 = first list item marker
				[ \t]+
			)
			[^\r]+?
			(								// $4
				~0							// sentinel for workaround; should be $
			|
				\n{2,}
				(?=\S)
				(?!							// Negative lookahead for another list item marker
					[ \t]*
					(?:[*+-]|\d+[.])[ \t]+
				)
			)
		)/g
	*/
	var whole_list = /^(([ ]{0,3}([*+-]|\d+[.])[ \t]+)[^\r]+?(~0|\n{2,}(?=\S)(?![ \t]*(?:[*+-]|\d+[.])[ \t]+)))/gm;

	if (g_list_level) {
		text = text.replace(whole_list,function(wholeMatch,m1,m2) {
			var list = m1;
			var list_type = (m2.search(/[*+-]/g)>-1) ? "ul" : "ol";

			// Turn double returns into triple returns, so that we can make a
			// paragraph for the last item in a list, if necessary:
			list = list.replace(/\n{2,}/g,"\n\n\n");;
			var result = _ProcessListItems(list);
	
			// Trim any trailing whitespace, to put the closing `</$list_type>`
			// up on the preceding line, to get it past the current stupid
			// HTML block parser. This is a hack to work around the terrible
			// hack that is the HTML block parser.
			result = result.replace(/\s+$/,"");
			result = "<"+list_type+">" + result + "</"+list_type+">\n";
			return result;
		});
	} else {
		whole_list = /(\n\n|^\n?)(([ ]{0,3}([*+-]|\d+[.])[ \t]+)[^\r]+?(~0|\n{2,}(?=\S)(?![ \t]*(?:[*+-]|\d+[.])[ \t]+)))/g;
		text = text.replace(whole_list,function(wholeMatch,m1,m2,m3) {
			var runup = m1;
			var list = m2;

			var list_type = (m3.search(/[*+-]/g)>-1) ? "ul" : "ol";
			// Turn double returns into triple returns, so that we can make a
			// paragraph for the last item in a list, if necessary:
			var list = list.replace(/\n{2,}/g,"\n\n\n");;
			var result = _ProcessListItems(list);
			result = runup + "<"+list_type+">\n" + result + "</"+list_type+">\n";	
			return result;
		});
	}

	// attacklab: strip sentinel
	text = text.replace(/~0/,"");

	return text;
}

_ProcessListItems = function(list_str) {
//
//  Process the contents of a single ordered or unordered list, splitting it
//  into individual list items.
//
	// The $g_list_level global keeps track of when we're inside a list.
	// Each time we enter a list, we increment it; when we leave a list,
	// we decrement. If it's zero, we're not in a list anymore.
	//
	// We do this because when we're not inside a list, we want to treat
	// something like this:
	//
	//    I recommend upgrading to version
	//    8. Oops, now this line is treated
	//    as a sub-list.
	//
	// As a single paragraph, despite the fact that the second line starts
	// with a digit-period-space sequence.
	//
	// Whereas when we're inside a list (or sub-list), that line will be
	// treated as the start of a sub-list. What a kludge, huh? This is
	// an aspect of Markdown's syntax that's hard to parse perfectly
	// without resorting to mind-reading. Perhaps the solution is to
	// change the syntax rules such that sub-lists must start with a
	// starting cardinal number; e.g. "1." or "a.".

	g_list_level++;

	// trim trailing blank lines:
	list_str = list_str.replace(/\n{2,}$/,"\n");

	// attacklab: add sentinel to emulate \z
	list_str += "~0";

	/*
		list_str = list_str.replace(/
			(\n)?							// leading line = $1
			(^[ \t]*)						// leading whitespace = $2
			([*+-]|\d+[.]) [ \t]+			// list marker = $3
			([^\r]+?						// list item text   = $4
			(\n{1,2}))
			(?= \n* (~0 | \2 ([*+-]|\d+[.]) [ \t]+))
		/gm, function(){...});
	*/
	list_str = list_str.replace(/(\n)?(^[ \t]*)([*+-]|\d+[.])[ \t]+([^\r]+?(\n{1,2}))(?=\n*(~0|\2([*+-]|\d+[.])[ \t]+))/gm,
		function(wholeMatch,m1,m2,m3,m4){
			var item = m4;
			var leading_line = m1;
			var leading_space = m2;

			if (leading_line || (item.search(/\n{2,}/)>-1)) {
				item = _RunBlockGamut(_Outdent(item));
			}
			else {
				// Recursion for sub-lists:
				item = _DoLists(_Outdent(item));
				item = item.replace(/\n$/,""); // chomp(item)
				item = _RunSpanGamut(item);
			}

			return  "<li>" + item + "</li>\n";
		}
	);

	// attacklab: strip sentinel
	list_str = list_str.replace(/~0/g,"");

	g_list_level--;
	return list_str;
}


var _DoCodeBlocks = function(text) {
//
//  Process Markdown `<pre><code>` blocks.
//  

	/*
		text = text.replace(text,
			/(?:\n\n|^)
			(								// $1 = the code block -- one or more lines, starting with a space/tab
				(?:
					(?:[ ]{4}|\t)			// Lines must start with a tab or a tab-width of spaces - attacklab: g_tab_width
					.*\n+
				)+
			)
			(\n*[ ]{0,3}[^ \t\n]|(?=~0))	// attacklab: g_tab_width
		/g,function(){...});
	*/

	// attacklab: sentinel workarounds for lack of \A and \Z, safari\khtml bug
	text += "~0";
	
	text = text.replace(/(?:\n\n|^)((?:(?:[ ]{4}|\t).*\n+)+)(\n*[ ]{0,3}[^ \t\n]|(?=~0))/g,
		function(wholeMatch,m1,m2) {
			var codeblock = m1;
			var nextChar = m2;
		
			codeblock = _EncodeCode( _Outdent(codeblock));
			codeblock = _Detab(codeblock);
			codeblock = codeblock.replace(/^\n+/g,""); // trim leading newlines
			codeblock = codeblock.replace(/\n+$/g,""); // trim trailing whitespace

			codeblock = "<pre><code>" + codeblock + "\n</code></pre>";

			return hashBlock(codeblock) + nextChar;
		}
	);

	// attacklab: strip sentinel
	text = text.replace(/~0/,"");

	return text;
}

var hashBlock = function(text) {
	text = text.replace(/(^\n+|\n+$)/g,"");
	return "\n\n~K" + (g_html_blocks.push(text)-1) + "K\n\n";
}


var _DoCodeSpans = function(text) {
//
//   *  Backtick quotes are used for <code></code> spans.
// 
//   *  You can use multiple backticks as the delimiters if you want to
//	 include literal backticks in the code span. So, this input:
//	 
//		 Just type ``foo `bar` baz`` at the prompt.
//	 
//	   Will translate to:
//	 
//		 <p>Just type <code>foo `bar` baz</code> at the prompt.</p>
//	 
//	There's no arbitrary limit to the number of backticks you
//	can use as delimters. If you need three consecutive backticks
//	in your code, use four for delimiters, etc.
//
//  *  You can use spaces to get literal backticks at the edges:
//	 
//		 ... type `` `bar` `` ...
//	 
//	   Turns to:
//	 
//		 ... type <code>`bar`</code> ...
//

	/*
		text = text.replace(/
			(^|[^\\])					// Character before opening ` can't be a backslash
			(`+)						// $2 = Opening run of `
			(							// $3 = The code block
				[^\r]*?
				[^`]					// attacklab: work around lack of lookbehind
			)
			\2							// Matching closer
			(?!`)
		/gm, function(){...});
	*/

	text = text.replace(/(^|[^\\])(`+)([^\r]*?[^`])\2(?!`)/gm,
		function(wholeMatch,m1,m2,m3,m4) {
			var c = m3;
			c = c.replace(/^([ \t]*)/g,"");	// leading whitespace
			c = c.replace(/[ \t]*$/g,"");	// trailing whitespace
			c = _EncodeCode(c);
			return m1+"<code>"+c+"</code>";
		});

	return text;
}


var _EncodeCode = function(text) {
//
// Encode/escape certain characters inside Markdown code runs.
// The point is that in code, these characters are literals,
// and lose their special Markdown meanings.
//
	// Encode all ampersands; HTML entities are not
	// entities within a Markdown code span.
	text = text.replace(/&/g,"&amp;");

	// Do the angle bracket song and dance:
	text = text.replace(/</g,"&lt;");
	text = text.replace(/>/g,"&gt;");

	// Now, escape characters that are magic in Markdown:
	text = escapeCharacters(text,"\*_{}[]\\",false);

// jj the line above breaks this:
//---

//* Item

//   1. Subitem

//            special char: *
//---

	return text;
}


var _DoItalicsAndBold = function(text) {

	// <strong> must go first:
	text = text.replace(/(\*\*|__)(?=\S)([^\r]*?\S[*_]*)\1/g,
		"<strong>$2</strong>");

        text = text.replace(/(\w)_(\w)/g, "$1~E95E$2") // ** GFM **  "~E95E" == escaped "_"

	text = text.replace(/(\*|_)(?=\S)([^\r]*?\S)\1/g,
		"<em>$2</em>");

	return text;
}


var _DoBlockQuotes = function(text) {

	/*
		text = text.replace(/
		(								// Wrap whole match in $1
			(
				^[ \t]*>[ \t]?			// '>' at the start of a line
				.+\n					// rest of the first line
				(.+\n)*					// subsequent consecutive lines
				\n*						// blanks
			)+
		)
		/gm, function(){...});
	*/

	text = text.replace(/((^[ \t]*>[ \t]?.+\n(.+\n)*\n*)+)/gm,
		function(wholeMatch,m1) {
			var bq = m1;

			// attacklab: hack around Konqueror 3.5.4 bug:
			// "----------bug".replace(/^-/g,"") == "bug"

			bq = bq.replace(/^[ \t]*>[ \t]?/gm,"~0");	// trim one level of quoting

			// attacklab: clean up hack
			bq = bq.replace(/~0/g,"");

			bq = bq.replace(/^[ \t]+$/gm,"");		// trim whitespace-only lines
			bq = _RunBlockGamut(bq);				// recurse
			
			bq = bq.replace(/(^|\n)/g,"$1  ");
			// These leading spaces screw with <pre> content, so we need to fix that:
			bq = bq.replace(
					/(\s*<pre>[^\r]+?<\/pre>)/gm,
				function(wholeMatch,m1) {
					var pre = m1;
					// attacklab: hack around Konqueror 3.5.4 bug:
					pre = pre.replace(/^  /mg,"~0");
					pre = pre.replace(/~0/g,"");
					return pre;
				});
			
			return hashBlock("<blockquote>\n" + bq + "\n</blockquote>");
		});
	return text;
}


var _FormParagraphs = function(text) {
//
//  Params:
//    $text - string to process with html <p> tags
//

	// Strip leading and trailing lines:
	text = text.replace(/^\n+/g,"");
	text = text.replace(/\n+$/g,"");

	var grafs = text.split(/\n{2,}/g);
	var grafsOut = new Array();

	//
	// Wrap <p> tags.
	//
	var end = grafs.length;
	for (var i=0; i<end; i++) {
		var str = grafs[i];

		// if this is an HTML marker, copy it
		if (str.search(/~K(\d+)K/g) >= 0) {
			grafsOut.push(str);
		}
		else if (str.search(/\S/) >= 0) {
			str = _RunSpanGamut(str);
                        str = str.replace(/\n/g,"<br />");  // ** GFM **
			str = str.replace(/^([ \t]*)/g,"<p>");
			str += "</p>"
			grafsOut.push(str);
		}

	}

	//
	// Unhashify HTML blocks
	//
	end = grafsOut.length;
	for (var i=0; i<end; i++) {
		// if this is a marker for an html block...
		while (grafsOut[i].search(/~K(\d+)K/) >= 0) {
			var blockText = g_html_blocks[RegExp.$1];
			blockText = blockText.replace(/\$/g,"$$$$"); // Escape any dollar signs
			grafsOut[i] = grafsOut[i].replace(/~K\d+K/,blockText);
		}
	}

	return grafsOut.join("\n\n");
}


var _EncodeAmpsAndAngles = function(text) {
// Smart processing for ampersands and angle brackets that need to be encoded.
	
	// Ampersand-encoding based entirely on Nat Irons's Amputator MT plugin:
	//   http://bumppo.net/projects/amputator/
	text = text.replace(/&(?!#?[xX]?(?:[0-9a-fA-F]+|\w+);)/g,"&amp;");
	
	// Encode naked <'s
	text = text.replace(/<(?![a-z\/?\$!])/gi,"&lt;");
	
	return text;
}


var _EncodeBackslashEscapes = function(text) {
//
//   Parameter:  String.
//   Returns:	The string, with after processing the following backslash
//			   escape sequences.
//

	// attacklab: The polite way to do this is with the new
	// escapeCharacters() function:
	//
	// 	text = escapeCharacters(text,"\\",true);
	// 	text = escapeCharacters(text,"`*_{}[]()>#+-.!",true);
	//
	// ...but we're sidestepping its use of the (slow) RegExp constructor
	// as an optimization for Firefox.  This function gets called a LOT.

	text = text.replace(/\\(\\)/g,escapeCharacters_callback);
	text = text.replace(/\\([`*_{}\[\]()>#+-.!])/g,escapeCharacters_callback);
	return text;
}


var _DoAutoLinks = function(text) {

	text = text.replace(/<((https?|ftp|dict):[^'">\s]+)>/gi,"<a href=\"$1\">$1</a>");

	// Email addresses: <address@domain.foo>

	/*
		text = text.replace(/
			<
			(?:mailto:)?
			(
				[-.\w]+
				\@
				[-a-z0-9]+(\.[-a-z0-9]+)*\.[a-z]+
			)
			>
		/gi, _DoAutoLinks_callback());
	*/
	text = text.replace(/<(?:mailto:)?([-.\w]+\@[-a-z0-9]+(\.[-a-z0-9]+)*\.[a-z]+)>/gi,
		function(wholeMatch,m1) {
			return _EncodeEmailAddress( _UnescapeSpecialChars(m1) );
		}
	);

	return text;
}


var _EncodeEmailAddress = function(addr) {
//
//  Input: an email address, e.g. "foo@example.com"
//
//  Output: the email address as a mailto link, with each character
//	of the address encoded as either a decimal or hex entity, in
//	the hopes of foiling most address harvesting spam bots. E.g.:
//
//	<a href="&#x6D;&#97;&#105;&#108;&#x74;&#111;:&#102;&#111;&#111;&#64;&#101;
//	   x&#x61;&#109;&#x70;&#108;&#x65;&#x2E;&#99;&#111;&#109;">&#102;&#111;&#111;
//	   &#64;&#101;x&#x61;&#109;&#x70;&#108;&#x65;&#x2E;&#99;&#111;&#109;</a>
//
//  Based on a filter by Matthew Wickline, posted to the BBEdit-Talk
//  mailing list: <http://tinyurl.com/yu7ue>
//

	// attacklab: why can't javascript speak hex?
	function char2hex(ch) {
		var hexDigits = '0123456789ABCDEF';
		var dec = ch.charCodeAt(0);
		return(hexDigits.charAt(dec>>4) + hexDigits.charAt(dec&15));
	}

	var encode = [
		function(ch){return "&#"+ch.charCodeAt(0)+";";},
		function(ch){return "&#x"+char2hex(ch)+";";},
		function(ch){return ch;}
	];

	addr = "mailto:" + addr;

	addr = addr.replace(/./g, function(ch) {
		if (ch == "@") {
		   	// this *must* be encoded. I insist.
			ch = encode[Math.floor(Math.random()*2)](ch);
		} else if (ch !=":") {
			// leave ':' alone (to spot mailto: later)
			var r = Math.random();
			// roughly 10% raw, 45% hex, 45% dec
			ch =  (
					r > .9  ?	encode[2](ch)   :
					r > .45 ?	encode[1](ch)   :
								encode[0](ch)
				);
		}
		return ch;
	});

	addr = "<a href=\"" + addr + "\">" + addr + "</a>";
	addr = addr.replace(/">.+:/g,"\">"); // strip the mailto: from the visible part

	return addr;
}


var _UnescapeSpecialChars = function(text) {
//
// Swap back in all the special characters we've hidden.
//
	text = text.replace(/~E(\d+)E/g,
		function(wholeMatch,m1) {
			var charCodeToReplace = parseInt(m1);
			return String.fromCharCode(charCodeToReplace);
		}
	);
	return text;
}


var _Outdent = function(text) {
//
// Remove one level of line-leading tabs or spaces
//

	// attacklab: hack around Konqueror 3.5.4 bug:
	// "----------bug".replace(/^-/g,"") == "bug"

	text = text.replace(/^(\t|[ ]{1,4})/gm,"~0"); // attacklab: g_tab_width

	// attacklab: clean up hack
	text = text.replace(/~0/g,"")

	return text;
}

var _Detab = function(text) {
// attacklab: Detab's completely rewritten for speed.
// In perl we could fix it by anchoring the regexp with \G.
// In javascript we're less fortunate.

	// expand first n-1 tabs
	text = text.replace(/\t(?=\t)/g,"    "); // attacklab: g_tab_width

	// replace the nth with two sentinels
	text = text.replace(/\t/g,"~A~B");

	// use the sentinel to anchor our regex so it doesn't explode
	text = text.replace(/~B(.+?)~A/g,
		function(wholeMatch,m1,m2) {
			var leadingText = m1;
			var numSpaces = 4 - leadingText.length % 4;  // attacklab: g_tab_width

			// there *must* be a better way to do this:
			for (var i=0; i<numSpaces; i++) leadingText+=" ";

			return leadingText;
		}
	);

	// clean up sentinels
	text = text.replace(/~A/g,"    ");  // attacklab: g_tab_width
	text = text.replace(/~B/g,"");

	return text;
}


//
//  attacklab: Utility functions
//


var escapeCharacters = function(text, charsToEscape, afterBackslash) {
	// First we have to escape the escape characters so that
	// we can build a character class out of them
	var regexString = "([" + charsToEscape.replace(/([\[\]\\])/g,"\\$1") + "])";

	if (afterBackslash) {
		regexString = "\\\\" + regexString;
	}

	var regex = new RegExp(regexString,"g");
	text = text.replace(regex,escapeCharacters_callback);

	return text;
}


var escapeCharacters_callback = function(wholeMatch,m1) {
	var charCodeToEscape = m1.charCodeAt(0);
	return "~E"+charCodeToEscape+"E";
}

} // end of Attacklab.showdown.converter


// Version 0.9 used the Showdown namespace instead of Attacklab.showdown
// The old namespace is deprecated, but we'll support it for now:
var Showdown = Attacklab.showdown;

// If anyone's interested, tell the world that this file's been loaded
if (Attacklab.fileLoaded) {
	Attacklab.fileLoaded("showdown.js");
}


/*	ColorBox v1.3.3 - a full featured, light-weight, customizable lightbox based on jQuery 1.3 */
(function(c){var s="colorbox",B="hover",o=true,g=false,e,E=!c.support.opacity,N=E&&!window.XMLHttpRequest,O="click.colorbox",fa="cbox_open",J="cbox_load",P="cbox_complete",Q="cbox_cleanup",aa="cbox_closed",R="resize.cbox_resize",u,j,x,p,S,T,U,V,h,r,n,K,L,ba,W,y,F,G,M,C,D,z,A,m,k,a,H,I,X,Y={transition:"elastic",speed:350,width:g,height:g,innerWidth:g,innerHeight:g,initialWidth:"400",initialHeight:"400",maxWidth:g,maxHeight:g,scalePhotos:o,scrolling:o,inline:g,html:g,iframe:g,photo:g,href:g,title:g, rel:g,opacity:0.9,preloading:o,current:"image {current} of {total}",previous:"previous",next:"next",close:"close",open:g,overlayClose:o,slideshow:g,slideshowAuto:o,slideshowSpeed:2500,slideshowStart:"start slideshow",slideshowStop:"stop slideshow",preloadIMG:o};function v(b,d){d=d==="x"?document.documentElement.clientWidth:document.documentElement.clientHeight;return typeof b==="string"?Math.round(b.match(/%/)?d/100*parseInt(b,10):parseInt(b,10)):b}function Z(b){return a.photo||b.match(/\.(gif|png|jpg|jpeg|bmp)(?:\?([^#]*))?(?:#(\.*))?$/i)} function ca(){for(var b in a)if(typeof a[b]==="function")a[b]=a[b].call(m)}e=c.fn.colorbox=function(b,d){this.length?this.each(function(){var i=c(this).data(s)?c.extend({},c(this).data(s),b):c.extend({},Y,b);c(this).data(s,i).addClass("cboxelement")}):c(this).data(s,c.extend({},Y,b));c(this).unbind(O).bind(O,function(i){m=this;a=c(m).data(s);ca();X=d||g;var l=a.rel||m.rel;if(l&&l!=="nofollow"){h=c(".cboxelement").filter(function(){var f=c(this).data(s).rel||this.rel;return f===l});k=h.index(m);if(k< 0){h=h.add(m);k=h.length-1}}else{h=c(m);k=0}if(!H){I=H=o;c().bind("keydown.cbox_close",function(f){if(f.keyCode===27){f.preventDefault();e.close()}}).bind("keydown.cbox_arrows",function(f){if(f.keyCode===37){f.preventDefault();G.click()}else if(f.keyCode===39){f.preventDefault();F.click()}});a.overlayClose&&u.css({cursor:"pointer"}).one("click",e.close);m.blur();c.event.trigger(fa);M.html(a.close);u.css({opacity:a.opacity}).show();a.w=v(a.initialWidth,"x");a.h=v(a.initialHeight,"y");e.position(0); N&&r.bind("resize.cboxie6 scroll.cboxie6",function(){u.css({width:r.width(),height:r.height(),top:r.scrollTop(),left:r.scrollLeft()})}).trigger("scroll.cboxie6")}e.slideshow();e.load();i.preventDefault()});b&&b.open&&c(this).triggerHandler(O);return this};e.init=function(){function b(d){return c('<div id="cbox'+d+'"/>')}r=c(window);j=c('<div id="colorbox"/>');u=b("Overlay").hide();x=b("Wrapper");p=b("Content").append(n=b("LoadedContent").css({width:0,height:0}),K=b("LoadingOverlay"),L=b("LoadingGraphic"), ba=b("Title"),W=b("Current"),y=b("Slideshow"),F=b("Next"),G=b("Previous"),M=b("Close"));x.append(c("<div/>").append(b("TopLeft"),S=b("TopCenter"),b("TopRight")),c("<div/>").append(T=b("MiddleLeft"),p,U=b("MiddleRight")),c("<div/>").append(b("BottomLeft"),V=b("BottomCenter"),b("BottomRight"))).children().children().css({"float":"left"});c("body").prepend(u,j.append(x));if(E){j.addClass("cboxIE");N&&u.css("position","absolute")}p.children().addClass(B).mouseover(function(){c(this).addClass(B)}).mouseout(function(){c(this).removeClass(B)}).hide(); C=S.height()+V.height()+p.outerHeight(o)-p.height();D=T.width()+U.width()+p.outerWidth(o)-p.width();z=n.outerHeight(o);A=n.outerWidth(o);j.css({"padding-bottom":C,"padding-right":D}).hide();F.click(e.next);G.click(e.prev);M.click(e.close);p.children().removeClass(B)};e.position=function(b,d){var i=document.documentElement.clientHeight;i=Math.max(i-a.h-z-C,0)/2+r.scrollTop();var l=Math.max(document.documentElement.clientWidth-a.w-A-D,0)/2+r.scrollLeft();b=j.width()===a.w+A&&j.height()===a.h+z?0:b; x[0].style.width=x[0].style.height="9999px";function f(q){S[0].style.width=V[0].style.width=p[0].style.width=q.style.width;L[0].style.height=K[0].style.height=p[0].style.height=T[0].style.height=U[0].style.height=q.style.height}j.dequeue().animate({width:a.w+A,height:a.h+z,top:i,left:l},{duration:b,complete:function(){f(this);I=g;x[0].style.width=a.w+A+D+"px";x[0].style.height=a.h+z+C+"px";d&&d()},step:function(){f(this)}})};e.resize=function(b){if(H){function d(w){e.position(w,function(){if(H){if(E){q&& n.fadeIn(100);j[0].style.removeAttribute("filter")}p.children().show();if(a.iframe)n.append("<iframe id='cboxIframe'"+(a.scrolling?" ":"scrolling='no'")+" name='iframe_"+(new Date).getTime()+"' frameborder=0 src='"+(a.href||m.href)+"' />");K.hide();L.hide();y.hide();if(h.length>1){W.html(a.current.replace(/\{current\}/,k+1).replace(/\{total\}/,h.length));F.html(a.next);G.html(a.previous);a.slideshow&&y.show()}else{W.hide();F.hide();G.hide()}ba.html(a.title||m.title);c.event.trigger(P);X&&X.call(m); a.transition==="fade"&&j.fadeTo(t,1,function(){E&&j[0].style.removeAttribute("filter")});r.bind(R,function(){e.position(0)})}})}function i(){a.h=a.h||n.height();return a.h}function l(){a.w=a.w||n.width();return a.w}var f,q,t=a.transition==="none"?0:a.speed;r.unbind(R);if(b){n.remove();n=c('<div id="cboxLoadedContent"/>').html(b);n.hide().appendTo(u).css({width:l(),overflow:a.scrolling?"auto":"hidden"}).css({height:i()}).prependTo(p);c("#cboxPhoto").css({cssFloat:"none"});N&&c("select:not(#colorbox select)").filter(function(){return this.style.visibility!== "hidden"}).css({visibility:"hidden"}).one(Q,function(){this.style.visibility="inherit"});a.transition==="fade"&&j.fadeTo(t,0,function(){d(0)})||d(t);if(a.preloading&&h.length>1){b=k>0?h[k-1]:h[h.length-1];f=k<h.length-1?h[k+1]:h[0];f=c(f).data(s).href||f.href;b=c(b).data(s).href||b.href;Z(f)&&c("<img />").attr("src",f);Z(b)&&c("<img />").attr("src",b)}}else b=setTimeout(function(){var w=n.wrapInner("<div style='overflow:auto'></div>").children();a.h=w.height();n.css({height:a.h});w.replaceWith(w.children()); e.position(t)},1)}};e.load=function(){var b,d,i,l=e.resize;I=o;function f(q){var t=c(q),w=t.find("img"),$=w.length;function da(){var ea=new Image;$-=1;if($>=0&&a.preloadIMG){ea.onload=da;ea.src=w[$].src}else l(t)}da()}m=h[k];a=c(m).data(s);ca();c.event.trigger(J);a.h=a.height?v(a.height,"y")-z-C:a.innerHeight?v(a.innerHeight,"y"):g;a.w=a.width?v(a.width,"x")-A-D:a.innerWidth?v(a.innerWidth,"x"):g;a.mw=a.w;a.mh=a.h;if(a.maxWidth){a.mw=v(a.maxWidth,"x")-A-D;a.mw=a.w&&a.w<a.mw?a.w:a.mw}if(a.maxHeight){a.mh= v(a.maxHeight,"y")-z-C;a.mh=a.h&&a.h<a.mh?a.h:a.mh}b=a.href||c(m).attr("href");K.show();L.show();M.show();if(a.inline){c('<div id="cboxInlineTemp" />').hide().insertBefore(c(b)[0]).bind(J+" "+Q,function(){c(this).replaceWith(n.children())});l(c(b))}else if(a.iframe)l(" ");else if(a.html)f(a.html);else if(Z(b)){d=new Image;d.onload=function(){var q;d.onload=null;d.id="cboxPhoto";c(d).css({margin:"auto",border:"none",display:"block",cssFloat:"left"});if(a.scalePhotos){i=function(){d.height-=d.height* q;d.width-=d.width*q};if(a.mw&&d.width>a.mw){q=(d.width-a.mw)/d.width;i()}if(a.mh&&d.height>a.mh){q=(d.height-a.mh)/d.height;i()}}if(a.h)d.style.marginTop=Math.max(a.h-d.height,0)/2+"px";l(d);h.length>1&&c(d).css({cursor:"pointer"}).click(e.next);if(E)d.style.msInterpolationMode="bicubic"};d.src=b}else c("<div />").load(b,function(q,t){t==="success"?f(this):l(c("<p>Request unsuccessful.</p>"))})};e.next=function(){if(!I){k=k<h.length-1?k+1:0;e.load()}};e.prev=function(){if(!I){k=k>0?k-1:h.length- 1;e.load()}};e.slideshow=function(){var b,d,i="cboxSlideshow_";y.bind(aa,function(){y.unbind();clearTimeout(d);j.removeClass(i+"off "+i+"on")});function l(){y.text(a.slideshowStop).bind(P,function(){d=setTimeout(e.next,a.slideshowSpeed)}).bind(J,function(){clearTimeout(d)}).one("click",function(){b();c(this).removeClass(B)});j.removeClass(i+"off").addClass(i+"on")}b=function(){clearTimeout(d);y.text(a.slideshowStart).unbind(P+" "+J).one("click",function(){l();d=setTimeout(e.next,a.slideshowSpeed); c(this).removeClass(B)});j.removeClass(i+"on").addClass(i+"off")};if(a.slideshow&&h.length>1)a.slideshowAuto?l():b()};e.close=function(){c.event.trigger(Q);H=g;c().unbind("keydown.cbox_close keydown.cbox_arrows");r.unbind(R+" resize.cboxie6 scroll.cboxie6");u.css({cursor:"auto"}).fadeOut("fast");j.stop(o,g).fadeOut("fast",function(){n.remove();j.css({opacity:1});p.children().hide();c.event.trigger(aa)})};e.element=function(){return c(m)};e.settings=Y;c(e.init)})(jQuery);


(function($){$.fn.jcarousel=function(o){return this.each(function(){new $jc(this,o);});};var defaults={vertical:false,start:1,offset:1,size:null,scroll:3,visible:null,animation:'normal',easing:'swing',auto:0,wrap:null,initCallback:null,reloadCallback:null,itemLoadCallback:null,itemFirstInCallback:null,itemFirstOutCallback:null,itemLastInCallback:null,itemLastOutCallback:null,itemVisibleInCallback:null,itemVisibleOutCallback:null,buttonNextHTML:'<div></div>',buttonPrevHTML:'<div></div>',buttonNextEvent:'click',buttonPrevEvent:'click',buttonNextCallback:null,buttonPrevCallback:null};$.jcarousel=function(e,o){this.options=$.extend({},defaults,o||{});this.locked=false;this.container=null;this.clip=null;this.list=null;this.buttonNext=null;this.buttonPrev=null;this.wh=!this.options.vertical?'width':'height';this.lt=!this.options.vertical?'left':'top';var skin='',split=e.className.split(' ');for(var i=0;i<split.length;i++){if(split[i].indexOf('jcarousel-skin')!=-1){$(e).removeClass(split[i]);var skin=split[i];break;}}
if(e.nodeName=='UL'||e.nodeName=='OL'){this.list=$(e);this.container=this.list.parent();if(this.container.hasClass('jcarousel-clip')){if(!this.container.parent().hasClass('jcarousel-container'))
this.container=this.container.wrap('<div></div>');this.container=this.container.parent();}else if(!this.container.hasClass('jcarousel-container'))
this.container=this.list.wrap('<div></div>').parent();}else{this.container=$(e);this.list=$(e).find('>ul,>ol,div>ul,div>ol');}
if(skin!=''&&this.container.parent()[0].className.indexOf('jcarousel-skin')==-1)
this.container.wrap('<div class=" '+skin+'"></div>');this.clip=this.list.parent();if(!this.clip.length||!this.clip.hasClass('jcarousel-clip'))
this.clip=this.list.wrap('<div></div>').parent();this.buttonPrev=$('.jcarousel-prev',this.container);if(this.buttonPrev.size()==0&&this.options.buttonPrevHTML!=null)
this.buttonPrev=this.clip.before(this.options.buttonPrevHTML).prev();this.buttonPrev.addClass(this.className('jcarousel-prev'));this.buttonNext=$('.jcarousel-next',this.container);if(this.buttonNext.size()==0&&this.options.buttonNextHTML!=null)
this.buttonNext=this.clip.before(this.options.buttonNextHTML).prev();this.buttonNext.addClass(this.className('jcarousel-next'));this.clip.addClass(this.className('jcarousel-clip'));this.list.addClass(this.className('jcarousel-list'));this.container.addClass(this.className('jcarousel-container'));var di=this.options.visible!=null?Math.ceil(this.clipping()/this.options.visible):null;var li=this.list.children('li');var self=this;if(li.size()>0){var wh=0,i=this.options.offset;li.each(function(){self.format(this,i++);wh+=self.dimension(this,di);});this.list.css(this.wh,wh+'px');if(!o||o.size===undefined)
this.options.size=li.size();}
this.container.css('display','block');this.buttonNext.css('display','block');this.buttonPrev.css('display','block');this.funcNext=function(){self.next();};this.funcPrev=function(){self.prev();};this.funcResize=function(){self.reload();};if(this.options.initCallback!=null)
this.options.initCallback(this,'init');if($.browser.safari){this.buttons(false,false);$(window).bind('load',function(){self.setup();});}else
this.setup();};var $jc=$.jcarousel;$jc.fn=$jc.prototype={jcarousel:'0.2.3'};$jc.fn.extend=$jc.extend=$.extend;$jc.fn.extend({setup:function(){this.first=null;this.last=null;this.prevFirst=null;this.prevLast=null;this.animating=false;this.timer=null;this.tail=null;this.inTail=false;if(this.locked)
return;this.list.css(this.lt,this.pos(this.options.offset)+'px');var p=this.pos(this.options.start);this.prevFirst=this.prevLast=null;this.animate(p,false);$(window).unbind('resize',this.funcResize).bind('resize',this.funcResize);},reset:function(){this.list.empty();this.list.css(this.lt,'0px');this.list.css(this.wh,'10px');if(this.options.initCallback!=null)
this.options.initCallback(this,'reset');this.setup();},reload:function(){if(this.tail!=null&&this.inTail)
this.list.css(this.lt,$jc.intval(this.list.css(this.lt))+this.tail);this.tail=null;this.inTail=false;if(this.options.reloadCallback!=null)
this.options.reloadCallback(this);if(this.options.visible!=null){var self=this;var di=Math.ceil(this.clipping()/this.options.visible),wh=0,lt=0;$('li',this.list).each(function(i){wh+=self.dimension(this,di);if(i+1<self.first)
lt=wh;});this.list.css(this.wh,wh+'px');this.list.css(this.lt,-lt+'px');}
this.scroll(this.first,false);},lock:function(){this.locked=true;this.buttons();},unlock:function(){this.locked=false;this.buttons();},size:function(s){if(s!=undefined){this.options.size=s;if(!this.locked)
this.buttons();}
return this.options.size;},has:function(i,i2){if(i2==undefined||!i2)
i2=i;if(this.options.size!==null&&i2>this.options.size)
i2=this.options.size;for(var j=i;j<=i2;j++){var e=this.get(j);if(!e.length||e.hasClass('jcarousel-item-placeholder'))
return false;}
return true;},get:function(i){return $('.jcarousel-item-'+i,this.list);},add:function(i,s){var e=this.get(i),old=0,add=0;if(e.length==0){var c,e=this.create(i),j=$jc.intval(i);while(c=this.get(--j)){if(j<=0||c.length){j<=0?this.list.prepend(e):c.after(e);break;}}}else
old=this.dimension(e);e.removeClass(this.className('jcarousel-item-placeholder'));typeof s=='string'?e.html(s):e.empty().append(s);var di=this.options.visible!=null?Math.ceil(this.clipping()/this.options.visible):null;var wh=this.dimension(e,di)-old;if(i>0&&i<this.first)
this.list.css(this.lt,$jc.intval(this.list.css(this.lt))-wh+'px');this.list.css(this.wh,$jc.intval(this.list.css(this.wh))+wh+'px');return e;},remove:function(i){var e=this.get(i);if(!e.length||(i>=this.first&&i<=this.last))
return;var d=this.dimension(e);if(i<this.first)
this.list.css(this.lt,$jc.intval(this.list.css(this.lt))+d+'px');e.remove();this.list.css(this.wh,$jc.intval(this.list.css(this.wh))-d+'px');},next:function(){this.stopAuto();if(this.tail!=null&&!this.inTail)
this.scrollTail(false);else
this.scroll(((this.options.wrap=='both'||this.options.wrap=='last')&&this.options.size!=null&&this.last==this.options.size)?1:this.first+this.options.scroll);},prev:function(){this.stopAuto();if(this.tail!=null&&this.inTail)
this.scrollTail(true);else
this.scroll(((this.options.wrap=='both'||this.options.wrap=='first')&&this.options.size!=null&&this.first==1)?this.options.size:this.first-this.options.scroll);},scrollTail:function(b){if(this.locked||this.animating||!this.tail)
return;var pos=$jc.intval(this.list.css(this.lt));!b?pos-=this.tail:pos+=this.tail;this.inTail=!b;this.prevFirst=this.first;this.prevLast=this.last;this.animate(pos);},scroll:function(i,a){if(this.locked||this.animating)
return;this.animate(this.pos(i),a);},pos:function(i){if(this.locked||this.animating)
return;i=$jc.intval(i);if(this.options.wrap!='circular')
i=i<1?1:(this.options.size&&i>this.options.size?this.options.size:i);var back=this.first>i;var pos=$jc.intval(this.list.css(this.lt));var f=this.options.wrap!='circular'&&this.first<=1?1:this.first;var c=back?this.get(f):this.get(this.last);var j=back?f:f-1;var e=null,l=0,p=false,d=0;while(back?--j>=i:++j<i){e=this.get(j);p=!e.length;if(e.length==0){e=this.create(j).addClass(this.className('jcarousel-item-placeholder'));c[back?'before':'after'](e);}
c=e;d=this.dimension(e);if(p)
l+=d;if(this.first!=null&&(this.options.wrap=='circular'||(j>=1&&(this.options.size==null||j<=this.options.size))))
pos=back?pos+d:pos-d;}
var clipping=this.clipping();var cache=[];var visible=0,j=i,v=0;var c=this.get(i-1);while(++visible){e=this.get(j);p=!e.length;if(e.length==0){e=this.create(j).addClass(this.className('jcarousel-item-placeholder'));c.length==0?this.list.prepend(e):c[back?'before':'after'](e);}
c=e;var d=this.dimension(e);if(d==0){alert('jCarousel: No width/height set for items. This will cause an infinite loop. Aborting...');return 0;}
if(this.options.wrap!='circular'&&this.options.size!==null&&j>this.options.size)
cache.push(e);else if(p)
l+=d;v+=d;if(v>=clipping)
break;j++;}
for(var x=0;x<cache.length;x++)
cache[x].remove();if(l>0){this.list.css(this.wh,this.dimension(this.list)+l+'px');if(back){pos-=l;this.list.css(this.lt,$jc.intval(this.list.css(this.lt))-l+'px');}}
var last=i+visible-1;if(this.options.wrap!='circular'&&this.options.size&&last>this.options.size)
last=this.options.size;if(j>last){visible=0,j=last,v=0;while(++visible){var e=this.get(j--);if(!e.length)
break;v+=this.dimension(e);if(v>=clipping)
break;}}
var first=last-visible+1;if(this.options.wrap!='circular'&&first<1)
first=1;if(this.inTail&&back){pos+=this.tail;this.inTail=false;}
this.tail=null;if(this.options.wrap!='circular'&&last==this.options.size&&(last-visible+1)>=1){var m=$jc.margin(this.get(last),!this.options.vertical?'marginRight':'marginBottom');if((v-m)>clipping)
this.tail=v-clipping-m;}
while(i-->first)
pos+=this.dimension(this.get(i));this.prevFirst=this.first;this.prevLast=this.last;this.first=first;this.last=last;return pos;},animate:function(p,a){if(this.locked||this.animating)
return;this.animating=true;var self=this;var scrolled=function(){self.animating=false;if(p==0)
self.list.css(self.lt,0);if(self.options.wrap=='both'||self.options.wrap=='last'||self.options.size==null||self.last<self.options.size)
self.startAuto();self.buttons();self.notify('onAfterAnimation');};this.notify('onBeforeAnimation');if(!this.options.animation||a==false){this.list.css(this.lt,p+'px');scrolled();}else{var o=!this.options.vertical?{'left':p}:{'top':p};this.list.animate(o,this.options.animation,this.options.easing,scrolled);}},startAuto:function(s){if(s!=undefined)
this.options.auto=s;if(this.options.auto==0)
return this.stopAuto();if(this.timer!=null)
return;var self=this;this.timer=setTimeout(function(){self.next();},this.options.auto*1000);},stopAuto:function(){if(this.timer==null)
return;clearTimeout(this.timer);this.timer=null;},buttons:function(n,p){if(n==undefined||n==null){var n=!this.locked&&this.options.size!==0&&((this.options.wrap&&this.options.wrap!='first')||this.options.size==null||this.last<this.options.size);if(!this.locked&&(!this.options.wrap||this.options.wrap=='first')&&this.options.size!=null&&this.last>=this.options.size)
n=this.tail!=null&&!this.inTail;}
if(p==undefined||p==null){var p=!this.locked&&this.options.size!==0&&((this.options.wrap&&this.options.wrap!='last')||this.first>1);if(!this.locked&&(!this.options.wrap||this.options.wrap=='last')&&this.options.size!=null&&this.first==1)
p=this.tail!=null&&this.inTail;}
var self=this;this.buttonNext[n?'bind':'unbind'](this.options.buttonNextEvent,this.funcNext)[n?'removeClass':'addClass'](this.className('jcarousel-next-disabled')).attr('disabled',n?false:true);this.buttonPrev[p?'bind':'unbind'](this.options.buttonPrevEvent,this.funcPrev)[p?'removeClass':'addClass'](this.className('jcarousel-prev-disabled')).attr('disabled',p?false:true);if(this.buttonNext.length>0&&(this.buttonNext[0].jcarouselstate==undefined||this.buttonNext[0].jcarouselstate!=n)&&this.options.buttonNextCallback!=null){this.buttonNext.each(function(){self.options.buttonNextCallback(self,this,n);});this.buttonNext[0].jcarouselstate=n;}
if(this.buttonPrev.length>0&&(this.buttonPrev[0].jcarouselstate==undefined||this.buttonPrev[0].jcarouselstate!=p)&&this.options.buttonPrevCallback!=null){this.buttonPrev.each(function(){self.options.buttonPrevCallback(self,this,p);});this.buttonPrev[0].jcarouselstate=p;}},notify:function(evt){var state=this.prevFirst==null?'init':(this.prevFirst<this.first?'next':'prev');this.callback('itemLoadCallback',evt,state);if(this.prevFirst!==this.first){this.callback('itemFirstInCallback',evt,state,this.first);this.callback('itemFirstOutCallback',evt,state,this.prevFirst);}
if(this.prevLast!==this.last){this.callback('itemLastInCallback',evt,state,this.last);this.callback('itemLastOutCallback',evt,state,this.prevLast);}
this.callback('itemVisibleInCallback',evt,state,this.first,this.last,this.prevFirst,this.prevLast);this.callback('itemVisibleOutCallback',evt,state,this.prevFirst,this.prevLast,this.first,this.last);},callback:function(cb,evt,state,i1,i2,i3,i4){if(this.options[cb]==undefined||(typeof this.options[cb]!='object'&&evt!='onAfterAnimation'))
return;var callback=typeof this.options[cb]=='object'?this.options[cb][evt]:this.options[cb];if(!$.isFunction(callback))
return;var self=this;if(i1===undefined)
callback(self,state,evt);else if(i2===undefined)
this.get(i1).each(function(){callback(self,this,i1,state,evt);});else{for(var i=i1;i<=i2;i++)
if(i!==null&&!(i>=i3&&i<=i4))
this.get(i).each(function(){callback(self,this,i,state,evt);});}},create:function(i){return this.format('<li></li>',i);},format:function(e,i){var $e=$(e).addClass(this.className('jcarousel-item')).addClass(this.className('jcarousel-item-'+i));$e.attr('jcarouselindex',i);return $e;},className:function(c){return c+' '+c+(!this.options.vertical?'-horizontal':'-vertical');},dimension:function(e,d){var el=e.jquery!=undefined?e[0]:e;var old=!this.options.vertical?el.offsetWidth+$jc.margin(el,'marginLeft')+$jc.margin(el,'marginRight'):el.offsetHeight+$jc.margin(el,'marginTop')+$jc.margin(el,'marginBottom');if(d==undefined||old==d)
return old;var w=!this.options.vertical?d-$jc.margin(el,'marginLeft')-$jc.margin(el,'marginRight'):d-$jc.margin(el,'marginTop')-$jc.margin(el,'marginBottom');$(el).css(this.wh,w+'px');return this.dimension(el);},clipping:function(){return!this.options.vertical?this.clip[0].offsetWidth-$jc.intval(this.clip.css('borderLeftWidth'))-$jc.intval(this.clip.css('borderRightWidth')):this.clip[0].offsetHeight-$jc.intval(this.clip.css('borderTopWidth'))-$jc.intval(this.clip.css('borderBottomWidth'));},index:function(i,s){if(s==undefined)
s=this.options.size;return Math.round((((i-1)/s)-Math.floor((i-1)/s))*s)+1;}});$jc.extend({defaults:function(d){return $.extend(defaults,d||{});},margin:function(e,p){if(!e)
return 0;var el=e.jquery!=undefined?e[0]:e;if(p=='marginRight'&&$.browser.safari){var old={'display':'block','float':'none','width':'auto'},oWidth,oWidth2;$.swap(el,old,function(){oWidth=el.offsetWidth;});old['marginRight']=0;$.swap(el,old,function(){oWidth2=el.offsetWidth;});return oWidth2-oWidth;}
return $jc.intval($.css(el,p));},intval:function(v){v=parseInt(v);return isNaN(v)?0:v;}});})(jQuery);/* jquery.sparkline 1.4.3 - http://omnipotent.net/jquery.sparkline/ */

(function($){$.fn.simpledraw=function(width,height,use_existing){if(use_existing&&this[0].vcanvas)return this[0].vcanvas;if(width==undefined)width=$(this).innerWidth();if(height==undefined)height=$(this).innerHeight();if($.browser.hasCanvas){return new vcanvas_canvas(width,height,this);}else if($.browser.msie){return new vcanvas_vml(width,height,this);}else{return false;}};var pending=[];$.fn.sparkline=function(uservalues,options){var options=$.extend({type:'line',lineColor:'#00f',fillColor:'#cdf',defaultPixelsPerValue:3,width:'auto',height:'auto',composite:false},options?options:{});return this.each(function(){var render=function(){var values=(uservalues=='html'||uservalues==undefined)?$(this).text().split(','):uservalues;var width=options.width=='auto'?values.length*options.defaultPixelsPerValue:options.width;if(options.height=='auto'){if(!options.composite||!this.vcanvas){var tmp=document.createElement('span');tmp.innerHTML='a';$(this).html(tmp);height=$(tmp).innerHeight();$(tmp).remove();}}else{height=options.height;}
$.fn.sparkline[options.type].call(this,values,options,width,height);}
if(($(this).html()&&$(this).is(':hidden'))||($.fn.jquery<"1.3.0"&&$(this).parents().is(':hidden'))){pending.push([this,render]);}else{render.call(this);}});};$.sparkline_display_visible=function(){for(var i=pending.length-1;i>=0;i--){var el=pending[i][0];if($(el).is(':visible')&&!$(el).parents().is(':hidden')){pending[i][1].call(el);pending.splice(i,1);}}};$.fn.sparkline.line=function(values,options,width,height){var options=$.extend({spotColor:'#f80',spotRadius:1.5,minSpotColor:'#f80',maxSpotColor:'#f80',lineWidth:1,normalRangeMin:undefined,normalRangeMax:undefined,normalRangeColor:'#ccc',chartRangeMin:undefined,chartRangeMax:undefined},options?options:{});var xvalues=[],yvalues=[],yminmax=[];for(i=0;i<values.length;i++){var v=values[i];var isstr=typeof(values[i])=='string';var isarray=typeof(values[i])=='object'&&values[i]instanceof Array;var sp=isstr&&values[i].split(':');if(isstr&&sp.length==2){xvalues.push(Number(sp[0]));yvalues.push(Number(sp[1]));yminmax.push(Number(sp[1]));}else if(isarray){xvalues.push(values[i][0]);yvalues.push(values[i][1]);yminmax.push(values[i][1]);}else{xvalues.push(i);if(values[i]===null||values[i]=='null'){yvalues.push(null);}else{yvalues.push(Number(values[i]));yminmax.push(Number(values[i]));}}}
if(options.xvalues){xvalues=options.xvalues;}
var maxy=Math.max.apply(Math,yminmax);var maxyval=maxy;var miny=Math.min.apply(Math,yminmax);var minyval=miny;var maxx=Math.max.apply(Math,xvalues);var maxxval=maxx;var minx=Math.min.apply(Math,xvalues);var minxval=minx;if(options.normalRangeMin!=undefined){if(options.normalRangeMin<miny)
miny=options.normalRangeMin;if(options.normalRangeMax>maxy)
maxy=options.normalRangeMax;}
if(options.chartRangeMin!=undefined&&options.chartRangeMin<miny){miny=options.chartRangeMin;}
if(options.chartRangeMax!=undefined&&options.chartRangeMax>maxy){maxy=options.chartRangeMax;}
var rangex=maxx-minx==0?1:maxx-minx;var rangey=maxy-miny==0?1:maxy-miny;var vl=yvalues.length-1;if(vl<1){this.innerHTML='';return;}
var target=$(this).simpledraw(width,height,options.composite);if(target){var canvas_width=target.pixel_width;var canvas_height=target.pixel_height;var canvas_top=0;var canvas_left=0;if(options.spotRadius&&(canvas_width<(options.spotRadius*4)||canvas_height<(options.spotRadius*4))){options.spotRadius=0;}
if(options.spotRadius){if(options.minSpotColor||(options.spotColor&&yvalues[vl]==miny))
canvas_height-=Math.ceil(options.spotRadius);if(options.maxSpotColor||(options.spotColor&&yvalues[vl]==maxy)){canvas_height-=Math.ceil(options.spotRadius);canvas_top+=Math.ceil(options.spotRadius);}
if(options.minSpotColor||options.maxSpotColor&&(yvalues[0]==miny||yvalues[0]==maxy)){canvas_left+=Math.ceil(options.spotRadius);canvas_width-=Math.ceil(options.spotRadius);}
if(options.spotColor||(options.minSpotColor||options.maxSpotColor&&(yvalues[vl]==miny||yvalues[vl]==maxy)))
canvas_width-=Math.ceil(options.spotRadius);}
canvas_height--;if(options.normalRangeMin!=undefined){var ytop=canvas_top+Math.round(canvas_height-(canvas_height*((options.normalRangeMax-miny)/rangey)));var height=Math.round((canvas_height*(options.normalRangeMax-options.normalRangeMin))/rangey);target.drawRect(canvas_left,ytop,canvas_width,height,undefined,options.normalRangeColor);}
var path=[];var paths=[path];for(var i=0;i<yvalues.length;i++){var x=xvalues[i],y=yvalues[i];if(y===null){if(i){if(yvalues[i-1]!==null){path=[];paths.push(path);}}}else{if(!path.length){path.push([canvas_left+Math.round((x-minx)*(canvas_width/rangex)),canvas_top+canvas_height]);}
path.push([canvas_left+Math.round((x-minx)*(canvas_width/rangex)),canvas_top+Math.round(canvas_height-(canvas_height*((y-miny)/rangey)))]);}}
for(var i=0;i<paths.length;i++){path=paths[i];if(!path.length)
continue;if(options.fillColor){path.push([path[path.length-1][0],canvas_top+canvas_height-1]);target.drawShape(path,undefined,options.fillColor);path.pop();}
if(path.length>2){path[0]=[path[0][0],path[1][1]];}
target.drawShape(path,options.lineColor,undefined,options.lineWidth);}
if(options.spotRadius&&options.spotColor){target.drawCircle(canvas_left+canvas_width,canvas_top+Math.round(canvas_height-(canvas_height*((yvalues[vl]-miny)/rangey))),options.spotRadius,undefined,options.spotColor);}
if(maxy!=minyval){if(options.spotRadius&&options.minSpotColor){var x=xvalues[yvalues.indexOf(minyval)];target.drawCircle(canvas_left+Math.round((x-minx)*(canvas_width/rangex)),canvas_top+Math.round(canvas_height-(canvas_height*((minyval-miny)/rangey))),options.spotRadius,undefined,options.minSpotColor);}
if(options.spotRadius&&options.maxSpotColor){var x=xvalues[yvalues.indexOf(maxyval)];target.drawCircle(canvas_left+Math.round((x-minx)*(canvas_width/rangex)),canvas_top+Math.round(canvas_height-(canvas_height*((maxyval-miny)/rangey))),options.spotRadius,undefined,options.maxSpotColor);}}}else{this.innerHTML='';}};$.fn.sparkline.bar=function(values,options,width,height){var options=$.extend({type:'bar',barColor:'#00f',negBarColor:'#f44',zeroColor:undefined,zeroAxis:undefined,barWidth:4,barSpacing:1,chartRangeMax:undefined,chartRangeMin:undefined,colorMap:{}},options?options:{});var width=(values.length*options.barWidth)+((values.length-1)*options.barSpacing);var num_values=[];for(var i=0;i<values.length;i++){if(values[i]=='null'||values[i]===null){values[i]=null;}else{values[i]=Number(values[i]);num_values.push(Number(values[i]));}}
var max=Math.max.apply(Math,num_values);var min=Math.min.apply(Math,num_values);if(options.chartRangeMin!=undefined&&options.chartRangeMin<min){min=options.chartRangeMin;}
if(options.chartRangeMax!=undefined&&options.chartRangeMax>max){max=options.chartRangeMax;}
if(options.zeroAxis==undefined)options.zeroAxis=min<0;var range=max-min==0?1:max-min;var target=$(this).simpledraw(width,height);if(target){var canvas_width=target.pixel_width;var canvas_height=target.pixel_height;var yzero=min<0&&options.zeroAxis?canvas_height-Math.round(canvas_height*(Math.abs(min)/range))-1:canvas_height-1;for(var i=0;i<values.length;i++){var x=i*(options.barWidth+options.barSpacing);var val=values[i];if(val===null){continue;}
var color=(val<0)?options.negBarColor:options.barColor;if(options.zeroAxis&&min<0){var height=Math.round(canvas_height*((Math.abs(val)/range)))+1;var y=(val<0)?yzero:yzero-height;}else{var height=Math.round(canvas_height*((val-min)/range))+1;var y=canvas_height-height;}
if(val==0&&options.zeroColor!=undefined){color=options.zeroColor;}
if(options.colorMap[val]){color=options.colorMap[val];}
target.drawRect(x,y,options.barWidth-1,height-1,color,color);}}else{this.innerHTML='';}};$.fn.sparkline.tristate=function(values,options,width,height){values=$.map(values,Number);var options=$.extend({barWidth:4,barSpacing:1,posBarColor:'#6f6',negBarColor:'#f44',zeroBarColor:'#999',colorMap:{}},options);var width=(values.length*options.barWidth)+((values.length-1)*options.barSpacing);var target=$(this).simpledraw(width,height);if(target){var canvas_width=target.pixel_width;var canvas_height=target.pixel_height;var half_height=Math.round(canvas_height/2);for(var i=0;i<values.length;i++){var x=i*(options.barWidth+options.barSpacing);if(values[i]<0){var y=half_height;var height=half_height-1;var color=options.negBarColor;}else if(values[i]>0){var y=0;var height=half_height-1;var color=options.posBarColor;}else{var y=half_height-1;var height=2;var color=options.zeroBarColor;}
if(options.colorMap[values[i]]){color=options.colorMap[values[i]];}
target.drawRect(x,y,options.barWidth-1,height-1,color,color);}}else{this.innerHTML='';}};$.fn.sparkline.discrete=function(values,options,width,height){values=$.map(values,Number);var options=$.extend({lineHeight:'auto',thresholdColor:undefined,thresholdValue:0,chartRangeMax:undefined,chartRangeMin:undefined},options);width=options.width=='auto'?values.length*2:width;var interval=Math.floor(width/values.length);var target=$(this).simpledraw(width,height);if(target){var canvas_width=target.pixel_width;var canvas_height=target.pixel_height;var line_height=options.lineHeight=='auto'?Math.round(canvas_height*0.3):options.lineHeight;var pheight=canvas_height-line_height;var min=Math.min.apply(Math,values);var max=Math.max.apply(Math,values);if(options.chartRangeMin!=undefined&&options.chartRangeMin<min){min=options.chartRangeMin;}
if(options.chartRangeMax!=undefined&&options.chartRangeMax>max){max=options.chartRangeMax;}
var range=max-min;for(var i=0;i<values.length;i++){var val=values[i];var x=(i*interval);var ytop=Math.round(pheight-pheight*((val-min)/range));target.drawLine(x,ytop,x,ytop+line_height,(options.thresholdColor&&val<options.thresholdValue)?options.thresholdColor:options.lineColor);}}else{this.innerHTML='';}};$.fn.sparkline.bullet=function(values,options,width,height){values=$.map(values,Number);var options=$.extend({targetColor:'red',targetWidth:3,performanceColor:'blue',rangeColors:['#D3DAFE','#A8B6FF','#7F94FF'],base:undefined},options);width=options.width=='auto'?'4.0em':width;var target=$(this).simpledraw(width,height);if(target&&values.length>1){var canvas_width=target.pixel_width-Math.ceil(options.targetWidth/2);var canvas_height=target.pixel_height;var min=Math.min.apply(Math,values);var max=Math.max.apply(Math,values);if(options.base==undefined){var min=min<0?min:0;}else{min=options.base;}
var range=max-min;for(i=2;i<values.length;i++){var rangeval=parseInt(values[i]);var rangewidth=Math.round(canvas_width*((rangeval-min)/range));target.drawRect(0,0,rangewidth-1,canvas_height-1,options.rangeColors[i-2],options.rangeColors[i-2]);}
var perfval=parseInt(values[1]);var perfwidth=Math.round(canvas_width*((perfval-min)/range));target.drawRect(0,Math.round(canvas_height*0.3),perfwidth-1,Math.round(canvas_height*0.4)-1,options.performanceColor,options.performanceColor);var targetval=parseInt(values[0]);var x=Math.round(canvas_width*((targetval-min)/range)-(options.targetWidth/2));var targettop=Math.round(canvas_height*0.10);var targetheight=canvas_height-(targettop*2);target.drawRect(x,targettop,options.targetWidth-1,targetheight-1,options.targetColor,options.targetColor);}else{this.innerHTML='';}};$.fn.sparkline.pie=function(values,options,width,height){values=$.map(values,Number);var options=$.extend({sliceColors:['#f00','#0f0','#00f']},options);width=options.width=='auto'?height:width;var target=$(this).simpledraw(width,height);if(target&&values.length>1){var canvas_width=target.pixel_width;var canvas_height=target.pixel_height;var radius=Math.floor(Math.min(canvas_width,canvas_height)/2);var total=0;for(var i=0;i<values.length;i++)
total+=values[i];var next=0;if(options.offset){next+=(2*Math.PI)*(options.offset/360);}
var circle=2*Math.PI;for(var i=0;i<values.length;i++){var start=next;var end=next;if(total>0){end=next+(circle*(values[i]/total));}
target.drawPieSlice(radius,radius,radius,start,end,undefined,options.sliceColors[i%options.sliceColors.length]);next=end;}}};function quartile(values,q){if(q==2){var vl2=Math.floor(values.length/2);return values.length%2?values[vl2]:(values[vl2]+values[vl2+1])/2;}else{var vl4=Math.floor(values.length/4);return values.length%2?(values[vl4*q]+values[vl4*q+1])/2:values[vl4*q];}};$.fn.sparkline.box=function(values,options,width,height){values=$.map(values,Number);var options=$.extend({raw:false,boxLineColor:'black',boxFillColor:'#cdf',whiskerColor:'black',outlierLineColor:'#333',outlierFillColor:'white',medianColor:'red',showOutliers:true,outlierIQR:1.5,spotRadius:1.5,target:undefined,targetColor:'#4a2',chartRangeMax:undefined,chartRangeMin:undefined},options);width=options.width=='auto'?'4.0em':width;minvalue=options.chartRangeMin==undefined?Math.min.apply(Math,values):options.chartRangeMin;maxvalue=options.chartRangeMax==undefined?Math.max.apply(Math,values):options.chartRangeMax;var target=$(this).simpledraw(width,height);if(target&&values.length>1){var canvas_width=target.pixel_width;var canvas_height=target.pixel_height;if(options.raw){if(options.showOutliers&&values.length>5){var loutlier=values[0],lwhisker=values[1],q1=values[2],q2=values[3],q3=values[4],rwhisker=values[5],routlier=values[6];}else{var lwhisker=values[0],q1=values[1],q2=values[2],q3=values[3],rwhisker=values[4];}}else{values.sort(function(a,b){return a-b;});var q1=quartile(values,1);var q2=quartile(values,2);var q3=quartile(values,3);var iqr=q3-q1;if(options.showOutliers){var lwhisker=undefined,rwhisker=undefined;for(var i=0;i<values.length;i++){if(lwhisker==undefined&&values[i]>q1-(iqr*options.outlierIQR))
lwhisker=values[i];if(values[i]<q3+(iqr*options.outlierIQR))
rwhisker=values[i];}
var loutlier=values[0];var routlier=values[values.length-1];}else{var lwhisker=values[0];var rwhisker=values[values.length-1];}}
var unitsize=canvas_width/(maxvalue-minvalue+1);var canvas_left=0;if(options.showOutliers){canvas_left=Math.ceil(options.spotRadius);canvas_width-=2*Math.ceil(options.spotRadius);var unitsize=canvas_width/(maxvalue-minvalue+1);if(loutlier<lwhisker)
target.drawCircle((loutlier-minvalue)*unitsize+canvas_left,canvas_height/2,options.spotRadius,options.outlierLineColor,options.outlierFillColor);if(routlier>rwhisker)
target.drawCircle((routlier-minvalue)*unitsize+canvas_left,canvas_height/2,options.spotRadius,options.outlierLineColor,options.outlierFillColor);}
target.drawRect(Math.round((q1-minvalue)*unitsize+canvas_left),Math.round(canvas_height*0.1),Math.round((q3-q1)*unitsize),Math.round(canvas_height*0.8),options.boxLineColor,options.boxFillColor);target.drawLine(Math.round((lwhisker-minvalue)*unitsize+canvas_left),Math.round(canvas_height/2),Math.round((q1-minvalue)*unitsize+canvas_left),Math.round(canvas_height/2),options.lineColor);target.drawLine(Math.round((lwhisker-minvalue)*unitsize+canvas_left),Math.round(canvas_height/4),Math.round((lwhisker-minvalue)*unitsize+canvas_left),Math.round(canvas_height-canvas_height/4),options.whiskerColor);target.drawLine(Math.round((rwhisker-minvalue)*unitsize+canvas_left),Math.round(canvas_height/2),Math.round((q3-minvalue)*unitsize+canvas_left),Math.round(canvas_height/2),options.lineColor);target.drawLine(Math.round((rwhisker-minvalue)*unitsize+canvas_left),Math.round(canvas_height/4),Math.round((rwhisker-minvalue)*unitsize+canvas_left),Math.round(canvas_height-canvas_height/4),options.whiskerColor);target.drawLine(Math.round((q2-minvalue)*unitsize+canvas_left),Math.round(canvas_height*0.1),Math.round((q2-minvalue)*unitsize+canvas_left),Math.round(canvas_height*0.9),options.medianColor);if(options.target){var size=Math.ceil(options.spotRadius);target.drawLine(Math.round((options.target-minvalue)*unitsize+canvas_left),Math.round((canvas_height/2)-size),Math.round((options.target-minvalue)*unitsize+canvas_left),Math.round((canvas_height/2)+size),options.targetColor);target.drawLine(Math.round((options.target-minvalue)*unitsize+canvas_left-size),Math.round(canvas_height/2),Math.round((options.target-minvalue)*unitsize+canvas_left+size),Math.round(canvas_height/2),options.targetColor);}}else{this.innerHTML='';}};if(!Array.prototype.indexOf){Array.prototype.indexOf=function(entry){for(var i=0;i<this.length;i++){if(this[i]==entry)
return i;}
return-1;}}
if($.browser.msie&&!document.namespaces['v']){document.namespaces.add('v','urn:schemas-microsoft-com:vml','#default#VML');}
if($.browser.hasCanvas==undefined){var t=document.createElement('canvas');$.browser.hasCanvas=t.getContext!=undefined;}
var vcanvas_base=function(width,height,target){};vcanvas_base.prototype={init:function(width,height,target){this.width=width;this.height=height;this.target=target;if(target[0])target=target[0];target.vcanvas=this;},drawShape:function(path,lineColor,fillColor,lineWidth){alert('drawShape not implemented');},drawLine:function(x1,y1,x2,y2,lineColor,lineWidth){return this.drawShape([[x1,y1],[x2,y2]],lineColor,lineWidth);},drawCircle:function(x,y,radius,lineColor,fillColor){alert('drawCircle not implemented');},drawPieSlice:function(x,y,radius,startAngle,endAngle,lineColor,fillColor){alert('drawPieSlice not implemented');},drawRect:function(x,y,width,height,lineColor,fillColor){alert('drawRect not implemented');},getElement:function(){return this.canvas;},_insert:function(el,target){$(target).html(el);}};var vcanvas_canvas=function(width,height,target){return this.init(width,height,target);};vcanvas_canvas.prototype=$.extend(new vcanvas_base,{_super:vcanvas_base.prototype,init:function(width,height,target){this._super.init(width,height,target);this.canvas=document.createElement('canvas');if(target[0])target=target[0];target.vcanvas=this;$(this.canvas).css({display:'inline-block',width:width,height:height,verticalAlign:'top'});this._insert(this.canvas,target);this.pixel_height=$(this.canvas).height();this.pixel_width=$(this.canvas).width();this.canvas.width=this.pixel_width;this.canvas.height=this.pixel_height;$(this.canvas).css({width:this.pixel_width,height:this.pixel_height});},_getContext:function(lineColor,fillColor,lineWidth){var context=this.canvas.getContext('2d');if(lineColor!=undefined)
context.strokeStyle=lineColor;context.lineWidth=lineWidth==undefined?1:lineWidth;if(fillColor!=undefined)
context.fillStyle=fillColor;return context;},drawShape:function(path,lineColor,fillColor,lineWidth){var context=this._getContext(lineColor,fillColor,lineWidth);context.beginPath();context.moveTo(path[0][0]+0.5,path[0][1]+0.5);for(var i=1;i<path.length;i++){context.lineTo(path[i][0]+0.5,path[i][1]+0.5);}
if(lineColor!=undefined){context.stroke();}
if(fillColor!=undefined){context.fill();}},drawCircle:function(x,y,radius,lineColor,fillColor){var context=this._getContext(lineColor,fillColor);context.beginPath();context.arc(x,y,radius,0,2*Math.PI,false);if(lineColor!=undefined){context.stroke();}
if(fillColor!=undefined){context.fill();}},drawPieSlice:function(x,y,radius,startAngle,endAngle,lineColor,fillColor){var context=this._getContext(lineColor,fillColor);context.beginPath();context.moveTo(x,y);context.arc(x,y,radius,startAngle,endAngle,false);context.lineTo(x,y);context.closePath();if(lineColor!=undefined){context.stroke();}
if(fillColor){context.fill();}},drawRect:function(x,y,width,height,lineColor,fillColor){return this.drawShape([[x,y],[x+width,y],[x+width,y+height],[x,y+height],[x,y]],lineColor,fillColor);}});var vcanvas_vml=function(width,height,target){return this.init(width,height,target);};vcanvas_vml.prototype=$.extend(new vcanvas_base,{_super:vcanvas_base.prototype,init:function(width,height,target){this._super.init(width,height,target);if(target[0])target=target[0];target.vcanvas=this;this.canvas=document.createElement('span');$(this.canvas).css({display:'inline-block',position:'relative',overflow:'hidden',width:width,height:height,margin:'0px',padding:'0px',verticalAlign:'top'});this._insert(this.canvas,target);this.pixel_height=$(this.canvas).height();this.pixel_width=$(this.canvas).width();this.canvas.width=this.pixel_width;this.canvas.height=this.pixel_height;;var groupel='<v:group coordorigin="0 0" coordsize="'+this.pixel_width+' '+this.pixel_height+'"'
+' style="position:absolute;top:0;left:0;width:'+this.pixel_width+'px;height='+this.pixel_height+'px;"></v:group>';this.canvas.insertAdjacentHTML('beforeEnd',groupel);this.group=$(this.canvas).children()[0];},drawShape:function(path,lineColor,fillColor,lineWidth){var vpath=[];for(var i=0;i<path.length;i++){vpath[i]=''+(path[i][0])+','+(path[i][1]);}
var initial=vpath.splice(0,1);lineWidth=lineWidth==undefined?1:lineWidth;var stroke=lineColor==undefined?' stroked="false" ':' strokeWeight="'+lineWidth+'" strokeColor="'+lineColor+'" ';var fill=fillColor==undefined?' filled="false"':' fillColor="'+fillColor+'" filled="true" ';var closed=vpath[0]==vpath[vpath.length-1]?'x ':'';var vel='<v:shape coordorigin="0 0" coordsize="'+this.pixel_width+' '+this.pixel_height+'" '
+stroke
+fill
+' style="position:absolute;left:0px;top:0px;height:'+this.pixel_height+'px;width:'+this.pixel_width+'px;padding:0px;margin:0px;" '
+' path="m '+initial+' l '+vpath.join(', ')+' '+closed+'e">'
+' </v:shape>';this.group.insertAdjacentHTML('beforeEnd',vel);},drawCircle:function(x,y,radius,lineColor,fillColor){x-=radius+1;y-=radius+1;var stroke=lineColor==undefined?' stroked="false" ':' strokeWeight="1" strokeColor="'+lineColor+'" ';var fill=fillColor==undefined?' filled="false"':' fillColor="'+fillColor+'" filled="true" ';var vel='<v:oval '
+stroke
+fill
+' style="position:absolute;top:'+y+'px; left:'+x+'px; width:'+(radius*2)+'px; height:'+(radius*2)+'px"></v:oval>';this.group.insertAdjacentHTML('beforeEnd',vel);},drawPieSlice:function(x,y,radius,startAngle,endAngle,lineColor,fillColor){if(startAngle==endAngle){return;}
if((endAngle-startAngle)==(2*Math.PI)){startAngle=0.0;endAngle=(2*Math.PI);}
var startx=x+Math.round(Math.cos(startAngle)*radius);var starty=y+Math.round(Math.sin(startAngle)*radius);var endx=x+Math.round(Math.cos(endAngle)*radius);var endy=y+Math.round(Math.sin(endAngle)*radius);var vpath=[x-radius,y-radius,x+radius,y+radius,startx,starty,endx,endy];var stroke=lineColor==undefined?' stroked="false" ':' strokeWeight="1" strokeColor="'+lineColor+'" ';var fill=fillColor==undefined?' filled="false"':' fillColor="'+fillColor+'" filled="true" ';var vel='<v:shape coordorigin="0 0" coordsize="'+this.pixel_width+' '+this.pixel_height+'" '
+stroke
+fill
+' style="position:absolute;left:0px;top:0px;height:'+this.pixel_height+'px;width:'+this.pixel_width+'px;padding:0px;margin:0px;" '
+' path="m '+x+','+y+' wa '+vpath.join(', ')+' x e">'
+' </v:shape>';this.group.insertAdjacentHTML('beforeEnd',vel);},drawRect:function(x,y,width,height,lineColor,fillColor){return this.drawShape([[x,y],[x,y+height],[x+width,y+height],[x+width,y],[x,y]],lineColor,fillColor);}});})(jQuery);

/* jQuery showPassword Plugin Version 1.0
 * @author Byron Rode
 * @website http://www.prothemer.com/blog/2009/07/02/new-jquery-plugin-targeting-usability-for-password-masking-on-forms
 * @requires jQuery v1.3.x
 * @license GPL/MIT
 */
;(function($){$.fn.showPassword=function(ph,options){var spinput=$(this);$.fn.showPassword.checker=function(cbid,inid){$('input[id="'+cbid+'"]').click(function(){if($(this).attr('checked')){$('input.'+inid).val(spinput.val()).attr('id',spinput.attr('id')).attr('name',spinput.attr('name'));$('input.'+inid).css('display','inline');spinput.css('display','none').removeAttr('id').removeAttr('name');}else{spinput.val($('input.'+inid).val()).attr('id',$('input.'+inid).attr('id')).attr('name',$('input.'+inid).attr('name'));spinput.css('display','inline');$('input.'+inid).css('display','none').removeAttr('id').removeAttr('name');}});}
return this.each(function(){var def={classname:'class',name:'password-input',text:'Show Password'};var spcbid='spcb_'+parseInt(Math.random()*1000);var spinid=spcbid.replace('spcb_','spin_');if(spinput.attr('class')!==''){var spclass=spinid+' '+spinput.attr('class');}else{var spclass=spinid;}if(typeof ph=='object'){$.extend(def,ph);}if(typeof options=='object'){$.extend(def,options);}var spname=def.name;if(def.classname==''){theclass='';}else{theclass=' class="'+def.clasname+'"';}$(this).before('<input type="text" value="" class="'+spclass+'" style="display: none;" />');var thecheckbox='<label><input'+theclass+' type="checkbox" id="'+spcbid+'" name="'+spname+'" value="sp" />'+def.text+'</label>';if(ph=='object'||typeof ph=='undefined'){$(this).after(thecheckbox);}else{$(ph).html(thecheckbox);}$.fn.showPassword.checker(spcbid,spinid);return this;});}})(jQuery);

;(function($){$.fn.ajaxSubmit=function(options){if(!this.length){log('ajaxSubmit: skipping submit process - no element selected');return this;}
if(typeof options=='function')
options={success:options};var url=$.trim(this.attr('action'));if(url){url=(url.match(/^([^#]+)/)||[])[1];}
url=url||window.location.href||'';options=$.extend({url:url,type:this.attr('method')||'GET',iframeSrc:/^https/i.test(window.location.href||'')?'javascript:false':'about:blank'},options||{});var veto={};this.trigger('form-pre-serialize',[this,options,veto]);if(veto.veto){log('ajaxSubmit: submit vetoed via form-pre-serialize trigger');return this;}
if(options.beforeSerialize&&options.beforeSerialize(this,options)===false){log('ajaxSubmit: submit aborted via beforeSerialize callback');return this;}
var a=this.formToArray(options.semantic);if(options.data){options.extraData=options.data;for(var n in options.data){if(options.data[n]instanceof Array){for(var k in options.data[n])
a.push({name:n,value:options.data[n][k]});}
else
a.push({name:n,value:options.data[n]});}}
if(options.beforeSubmit&&options.beforeSubmit(a,this,options)===false){log('ajaxSubmit: submit aborted via beforeSubmit callback');return this;}
this.trigger('form-submit-validate',[a,this,options,veto]);if(veto.veto){log('ajaxSubmit: submit vetoed via form-submit-validate trigger');return this;}
var q=$.param(a);if(options.type.toUpperCase()=='GET'){options.url+=(options.url.indexOf('?')>=0?'&':'?')+q;options.data=null;}
else
options.data=q;var $form=this,callbacks=[];if(options.resetForm)callbacks.push(function(){$form.resetForm();});if(options.clearForm)callbacks.push(function(){$form.clearForm();});if(!options.dataType&&options.target){var oldSuccess=options.success||function(){};callbacks.push(function(data){$(options.target).html(data).each(oldSuccess,arguments);});}
else if(options.success)
callbacks.push(options.success);options.success=function(data,status){for(var i=0,max=callbacks.length;i<max;i++)
callbacks[i].apply(options,[data,status,$form]);};var files=$('input:file',this).fieldValue();var found=false;for(var j=0;j<files.length;j++)
if(files[j])
found=true;var multipart=false;if((files.length&&options.iframe!==false)||options.iframe||found||multipart){if(options.closeKeepAlive)
$.get(options.closeKeepAlive,fileUpload);else
fileUpload();}
else
$.ajax(options);this.trigger('form-submit-notify',[this,options]);return this;function fileUpload(){var form=$form[0];if($(':input[name=submit]',form).length){alert('Error: Form elements must not be named "submit".');return;}
var opts=$.extend({},$.ajaxSettings,options);var s=$.extend(true,{},$.extend(true,{},$.ajaxSettings),opts);var id='jqFormIO'+(new Date().getTime());var $io=$('<iframe id="'+id+'" name="'+id+'" src="'+opts.iframeSrc+'" />');var io=$io[0];$io.css({position:'absolute',top:'-1000px',left:'-1000px'});var xhr={aborted:0,responseText:null,responseXML:null,status:0,statusText:'n/a',getAllResponseHeaders:function(){},getResponseHeader:function(){},setRequestHeader:function(){},abort:function(){this.aborted=1;$io.attr('src',opts.iframeSrc);}};var g=opts.global;if(g&&!$.active++)$.event.trigger("ajaxStart");if(g)$.event.trigger("ajaxSend",[xhr,opts]);if(s.beforeSend&&s.beforeSend(xhr,s)===false){s.global&&$.active--;return;}
if(xhr.aborted)
return;var cbInvoked=0;var timedOut=0;var sub=form.clk;if(sub){var n=sub.name;if(n&&!sub.disabled){options.extraData=options.extraData||{};options.extraData[n]=sub.value;if(sub.type=="image"){options.extraData[name+'.x']=form.clk_x;options.extraData[name+'.y']=form.clk_y;}}}
setTimeout(function(){var t=$form.attr('target'),a=$form.attr('action');form.setAttribute('target',id);if(form.getAttribute('method')!='POST')
form.setAttribute('method','POST');if(form.getAttribute('action')!=opts.url)
form.setAttribute('action',opts.url);if(!options.skipEncodingOverride){$form.attr({encoding:'multipart/form-data',enctype:'multipart/form-data'});}
if(opts.timeout)
setTimeout(function(){timedOut=true;cb();},opts.timeout);var extraInputs=[];try{if(options.extraData)
for(var n in options.extraData)
extraInputs.push($('<input type="hidden" name="'+n+'" value="'+options.extraData[n]+'" />').appendTo(form)[0]);$io.appendTo('body');io.attachEvent?io.attachEvent('onload',cb):io.addEventListener('load',cb,false);form.submit();}
finally{form.setAttribute('action',a);t?form.setAttribute('target',t):$form.removeAttr('target');$(extraInputs).remove();}},10);var domCheckCount=50;function cb(){if(cbInvoked++)return;io.detachEvent?io.detachEvent('onload',cb):io.removeEventListener('load',cb,false);var ok=true;try{if(timedOut)throw'timeout';var data,doc;doc=io.contentWindow?io.contentWindow.document:io.contentDocument?io.contentDocument:io.document;var isXml=opts.dataType=='xml'||doc.XMLDocument||$.isXMLDoc(doc);log('isXml='+isXml);if(!isXml&&(doc.body==null||doc.body.innerHTML=='')){if(--domCheckCount){cbInvoked=0;setTimeout(cb,100);return;}
log('Could not access iframe DOM after 50 tries.');return;}
xhr.responseText=doc.body?doc.body.innerHTML:null;xhr.responseXML=doc.XMLDocument?doc.XMLDocument:doc;xhr.getResponseHeader=function(header){var headers={'content-type':opts.dataType};return headers[header];};if(opts.dataType=='json'||opts.dataType=='script'){var ta=doc.getElementsByTagName('textarea')[0];if(ta)
xhr.responseText=ta.value;else{var pre=doc.getElementsByTagName('pre')[0];if(pre)
xhr.responseText=pre.innerHTML;}}
else if(opts.dataType=='xml'&&!xhr.responseXML&&xhr.responseText!=null){xhr.responseXML=toXml(xhr.responseText);}
data=$.httpData(xhr,opts.dataType);}
catch(e){ok=false;$.handleError(opts,xhr,'error',e);}
if(ok){opts.success(data,'success');if(g)$.event.trigger("ajaxSuccess",[xhr,opts]);}
if(g)$.event.trigger("ajaxComplete",[xhr,opts]);if(g&&!--$.active)$.event.trigger("ajaxStop");if(opts.complete)opts.complete(xhr,ok?'success':'error');setTimeout(function(){$io.remove();xhr.responseXML=null;},100);};function toXml(s,doc){if(window.ActiveXObject){doc=new ActiveXObject('Microsoft.XMLDOM');doc.async='false';doc.loadXML(s);}
else
doc=(new DOMParser()).parseFromString(s,'text/xml');return(doc&&doc.documentElement&&doc.documentElement.tagName!='parsererror')?doc:null;};};};$.fn.ajaxForm=function(options){return this.ajaxFormUnbind().bind('submit.form-plugin',function(){$(this).ajaxSubmit(options);return false;}).bind('click.form-plugin',function(e){var target=e.target;var $el=$(target);if(!($el.is(":submit,input:image"))){var t=$el.closest(':submit');if(t.length==0)
return;target=t[0];}
var form=this;form.clk=target;if(target.type=='image'){if(e.offsetX!=undefined){form.clk_x=e.offsetX;form.clk_y=e.offsetY;}else if(typeof $.fn.offset=='function'){var offset=$el.offset();form.clk_x=e.pageX-offset.left;form.clk_y=e.pageY-offset.top;}else{form.clk_x=e.pageX-target.offsetLeft;form.clk_y=e.pageY-target.offsetTop;}}
setTimeout(function(){form.clk=form.clk_x=form.clk_y=null;},100);});};$.fn.ajaxFormUnbind=function(){return this.unbind('submit.form-plugin click.form-plugin');};$.fn.formToArray=function(semantic){var a=[];if(this.length==0)return a;var form=this[0];var els=semantic?form.getElementsByTagName('*'):form.elements;if(!els)return a;for(var i=0,max=els.length;i<max;i++){var el=els[i];var n=el.name;if(!n)continue;if(semantic&&form.clk&&el.type=="image"){if(!el.disabled&&form.clk==el){a.push({name:n,value:$(el).val()});a.push({name:n+'.x',value:form.clk_x},{name:n+'.y',value:form.clk_y});}
continue;}
var v=$.fieldValue(el,true);if(v&&v.constructor==Array){for(var j=0,jmax=v.length;j<jmax;j++)
a.push({name:n,value:v[j]});}
else if(v!==null&&typeof v!='undefined')
a.push({name:n,value:v});}
if(!semantic&&form.clk){var $input=$(form.clk),input=$input[0],n=input.name;if(n&&!input.disabled&&input.type=='image'){a.push({name:n,value:$input.val()});a.push({name:n+'.x',value:form.clk_x},{name:n+'.y',value:form.clk_y});}}
return a;};$.fn.formSerialize=function(semantic){return $.param(this.formToArray(semantic));};$.fn.fieldSerialize=function(successful){var a=[];this.each(function(){var n=this.name;if(!n)return;var v=$.fieldValue(this,successful);if(v&&v.constructor==Array){for(var i=0,max=v.length;i<max;i++)
a.push({name:n,value:v[i]});}
else if(v!==null&&typeof v!='undefined')
a.push({name:this.name,value:v});});return $.param(a);};$.fn.fieldValue=function(successful){for(var val=[],i=0,max=this.length;i<max;i++){var el=this[i];var v=$.fieldValue(el,successful);if(v===null||typeof v=='undefined'||(v.constructor==Array&&!v.length))
continue;v.constructor==Array?$.merge(val,v):val.push(v);}
return val;};$.fieldValue=function(el,successful){var n=el.name,t=el.type,tag=el.tagName.toLowerCase();if(typeof successful=='undefined')successful=true;if(successful&&(!n||el.disabled||t=='reset'||t=='button'||(t=='checkbox'||t=='radio')&&!el.checked||(t=='submit'||t=='image')&&el.form&&el.form.clk!=el||tag=='select'&&el.selectedIndex==-1))
return null;if(tag=='select'){var index=el.selectedIndex;if(index<0)return null;var a=[],ops=el.options;var one=(t=='select-one');var max=(one?index+1:ops.length);for(var i=(one?index:0);i<max;i++){var op=ops[i];if(op.selected){var v=op.value;if(!v)
v=(op.attributes&&op.attributes['value']&&!(op.attributes['value'].specified))?op.text:op.value;if(one)return v;a.push(v);}}
return a;}
return el.value;};$.fn.clearForm=function(){return this.each(function(){$('input,select,textarea',this).clearFields();});};$.fn.clearFields=$.fn.clearInputs=function(){return this.each(function(){var t=this.type,tag=this.tagName.toLowerCase();if(t=='text'||t=='password'||tag=='textarea')
this.value='';else if(t=='checkbox'||t=='radio')
this.checked=false;else if(tag=='select')
this.selectedIndex=-1;});};$.fn.resetForm=function(){return this.each(function(){if(typeof this.reset=='function'||(typeof this.reset=='object'&&!this.reset.nodeType))
this.reset();});};$.fn.enable=function(b){if(b==undefined)b=true;return this.each(function(){this.disabled=!b;});};$.fn.selected=function(select){if(select==undefined)select=true;return this.each(function(){var t=this.type;if(t=='checkbox'||t=='radio')
this.checked=select;else if(this.tagName.toLowerCase()=='option'){var $sel=$(this).parent('select');if(select&&$sel[0]&&$sel[0].type=='select-one'){$sel.find('option').selected(false);}
this.selected=select;}});};function log(){if($.fn.ajaxSubmit.debug&&window.console&&window.console.log)
window.console.log('[jquery.form] '+Array.prototype.join.call(arguments,''));};})(jQuery);/*
 * jQuery validation plug-in 1.6
 *
 * http://bassistance.de/jquery-plugins/jquery-plugin-validation/
 * http://docs.jquery.com/Plugins/Validation
 *
 * Copyright (c) 2006 - 2008 Jörn Zaefferer
 *
 * $Id: jquery.validate.js 6403 2009-06-17 14:27:16Z joern.zaefferer $
 *
 * Dual licensed under the MIT and GPL licenses:
 *   http://www.opensource.org/licenses/mit-license.php
 *   http://www.gnu.org/licenses/gpl.html
 */
(function($){$.extend($.fn,{validate:function(options){if(!this.length){options&&options.debug&&window.console&&console.warn("nothing selected, can't validate, returning nothing");return;}var validator=$.data(this[0],'validator');if(validator){return validator;}validator=new $.validator(options,this[0]);$.data(this[0],'validator',validator);if(validator.settings.onsubmit){this.find("input, button").filter(".cancel").click(function(){validator.cancelSubmit=true;});if(validator.settings.submitHandler){this.find("input, button").filter(":submit").click(function(){validator.submitButton=this;});}this.submit(function(event){if(validator.settings.debug)event.preventDefault();function handle(){if(validator.settings.submitHandler){if(validator.submitButton){var hidden=$("<input type='hidden'/>").attr("name",validator.submitButton.name).val(validator.submitButton.value).appendTo(validator.currentForm);}validator.settings.submitHandler.call(validator,validator.currentForm);if(validator.submitButton){hidden.remove();}return false;}return true;}if(validator.cancelSubmit){validator.cancelSubmit=false;return handle();}if(validator.form()){if(validator.pendingRequest){validator.formSubmitted=true;return false;}return handle();}else{validator.focusInvalid();return false;}});}return validator;},valid:function(){if($(this[0]).is('form')){return this.validate().form();}else{var valid=true;var validator=$(this[0].form).validate();this.each(function(){valid&=validator.element(this);});return valid;}},removeAttrs:function(attributes){var result={},$element=this;$.each(attributes.split(/\s/),function(index,value){result[value]=$element.attr(value);$element.removeAttr(value);});return result;},rules:function(command,argument){var element=this[0];if(command){var settings=$.data(element.form,'validator').settings;var staticRules=settings.rules;var existingRules=$.validator.staticRules(element);switch(command){case"add":$.extend(existingRules,$.validator.normalizeRule(argument));staticRules[element.name]=existingRules;if(argument.messages)settings.messages[element.name]=$.extend(settings.messages[element.name],argument.messages);break;case"remove":if(!argument){delete staticRules[element.name];return existingRules;}var filtered={};$.each(argument.split(/\s/),function(index,method){filtered[method]=existingRules[method];delete existingRules[method];});return filtered;}}var data=$.validator.normalizeRules($.extend({},$.validator.metadataRules(element),$.validator.classRules(element),$.validator.attributeRules(element),$.validator.staticRules(element)),element);if(data.required){var param=data.required;delete data.required;data=$.extend({required:param},data);}return data;}});$.extend($.expr[":"],{blank:function(a){return!$.trim(""+a.value);},filled:function(a){return!!$.trim(""+a.value);},unchecked:function(a){return!a.checked;}});$.validator=function(options,form){this.settings=$.extend({},$.validator.defaults,options);this.currentForm=form;this.init();};$.validator.format=function(source,params){if(arguments.length==1)return function(){var args=$.makeArray(arguments);args.unshift(source);return $.validator.format.apply(this,args);};if(arguments.length>2&&params.constructor!=Array){params=$.makeArray(arguments).slice(1);}if(params.constructor!=Array){params=[params];}$.each(params,function(i,n){source=source.replace(new RegExp("\\{"+i+"\\}","g"),n);});return source;};$.extend($.validator,{defaults:{messages:{},groups:{},rules:{},errorClass:"error",validClass:"valid",errorElement:"label",focusInvalid:true,errorContainer:$([]),errorLabelContainer:$([]),onsubmit:true,ignore:[],ignoreTitle:false,onfocusin:function(element){this.lastActive=element;if(this.settings.focusCleanup&&!this.blockFocusCleanup){this.settings.unhighlight&&this.settings.unhighlight.call(this,element,this.settings.errorClass,this.settings.validClass);this.errorsFor(element).hide();}},onfocusout:function(element){if(!this.checkable(element)&&(element.name in this.submitted||!this.optional(element))){this.element(element);}},onkeyup:function(element){if(element.name in this.submitted||element==this.lastElement){this.element(element);}},onclick:function(element){if(element.name in this.submitted)this.element(element);else if(element.parentNode.name in this.submitted)this.element(element.parentNode)},highlight:function(element,errorClass,validClass){$(element).addClass(errorClass).removeClass(validClass);},unhighlight:function(element,errorClass,validClass){$(element).removeClass(errorClass).addClass(validClass);}},setDefaults:function(settings){$.extend($.validator.defaults,settings);},messages:{required:"This field is required.",remote:"Please fix this field.",email:"Please enter a valid email address.",url:"Please enter a valid URL.",date:"Please enter a valid date.",dateISO:"Please enter a valid date (ISO).",number:"Please enter a valid number.",digits:"Please enter only digits.",creditcard:"Please enter a valid credit card number.",equalTo:"Please enter the same value again.",accept:"Please enter a value with a valid extension.",maxlength:$.validator.format("Please enter no more than {0} characters."),minlength:$.validator.format("Please enter at least {0} characters."),rangelength:$.validator.format("Please enter a value between {0} and {1} characters long."),range:$.validator.format("Please enter a value between {0} and {1}."),max:$.validator.format("Please enter a value less than or equal to {0}."),min:$.validator.format("Please enter a value greater than or equal to {0}.")},autoCreateRanges:false,prototype:{init:function(){this.labelContainer=$(this.settings.errorLabelContainer);this.errorContext=this.labelContainer.length&&this.labelContainer||$(this.currentForm);this.containers=$(this.settings.errorContainer).add(this.settings.errorLabelContainer);this.submitted={};this.valueCache={};this.pendingRequest=0;this.pending={};this.invalid={};this.reset();var groups=(this.groups={});$.each(this.settings.groups,function(key,value){$.each(value.split(/\s/),function(index,name){groups[name]=key;});});var rules=this.settings.rules;$.each(rules,function(key,value){rules[key]=$.validator.normalizeRule(value);});function delegate(event){var validator=$.data(this[0].form,"validator");validator.settings["on"+event.type]&&validator.settings["on"+event.type].call(validator,this[0]);}$(this.currentForm).delegate("focusin focusout keyup",":text, :password, :file, select, textarea",delegate).delegate("click",":radio, :checkbox, select, option",delegate);if(this.settings.invalidHandler)$(this.currentForm).bind("invalid-form.validate",this.settings.invalidHandler);},form:function(){this.checkForm();$.extend(this.submitted,this.errorMap);this.invalid=$.extend({},this.errorMap);if(!this.valid())$(this.currentForm).triggerHandler("invalid-form",[this]);this.showErrors();return this.valid();},checkForm:function(){this.prepareForm();for(var i=0,elements=(this.currentElements=this.elements());elements[i];i++){this.check(elements[i]);}return this.valid();},element:function(element){element=this.clean(element);this.lastElement=element;this.prepareElement(element);this.currentElements=$(element);var result=this.check(element);if(result){delete this.invalid[element.name];}else{this.invalid[element.name]=true;}if(!this.numberOfInvalids()){this.toHide=this.toHide.add(this.containers);}this.showErrors();return result;},showErrors:function(errors){if(errors){$.extend(this.errorMap,errors);this.errorList=[];for(var name in errors){this.errorList.push({message:errors[name],element:this.findByName(name)[0]});}this.successList=$.grep(this.successList,function(element){return!(element.name in errors);});}this.settings.showErrors?this.settings.showErrors.call(this,this.errorMap,this.errorList):this.defaultShowErrors();},resetForm:function(){if($.fn.resetForm)$(this.currentForm).resetForm();this.submitted={};this.prepareForm();this.hideErrors();this.elements().removeClass(this.settings.errorClass);},numberOfInvalids:function(){return this.objectLength(this.invalid);},objectLength:function(obj){var count=0;for(var i in obj)count++;return count;},hideErrors:function(){this.addWrapper(this.toHide).hide();},valid:function(){return this.size()==0;},size:function(){return this.errorList.length;},focusInvalid:function(){if(this.settings.focusInvalid){try{$(this.findLastActive()||this.errorList.length&&this.errorList[0].element||[]).filter(":visible").focus();}catch(e){}}},findLastActive:function(){var lastActive=this.lastActive;return lastActive&&$.grep(this.errorList,function(n){return n.element.name==lastActive.name;}).length==1&&lastActive;},elements:function(){var validator=this,rulesCache={};return $([]).add(this.currentForm.elements).filter(":input").not(":submit, :reset, :image, [disabled]").not(this.settings.ignore).filter(function(){!this.name&&validator.settings.debug&&window.console&&console.error("%o has no name assigned",this);if(this.name in rulesCache||!validator.objectLength($(this).rules()))return false;rulesCache[this.name]=true;return true;});},clean:function(selector){return $(selector)[0];},errors:function(){return $(this.settings.errorElement+"."+this.settings.errorClass,this.errorContext);},reset:function(){this.successList=[];this.errorList=[];this.errorMap={};this.toShow=$([]);this.toHide=$([]);this.currentElements=$([]);},prepareForm:function(){this.reset();this.toHide=this.errors().add(this.containers);},prepareElement:function(element){this.reset();this.toHide=this.errorsFor(element);},check:function(element){element=this.clean(element);if(this.checkable(element)){element=this.findByName(element.name)[0];}var rules=$(element).rules();var dependencyMismatch=false;for(method in rules){var rule={method:method,parameters:rules[method]};try{var result=$.validator.methods[method].call(this,element.value.replace(/\r/g,""),element,rule.parameters);if(result=="dependency-mismatch"){dependencyMismatch=true;continue;}dependencyMismatch=false;if(result=="pending"){this.toHide=this.toHide.not(this.errorsFor(element));return;}if(!result){this.formatAndAdd(element,rule);return false;}}catch(e){this.settings.debug&&window.console&&console.log("exception occured when checking element "+element.id
+", check the '"+rule.method+"' method",e);throw e;}}if(dependencyMismatch)return;if(this.objectLength(rules))this.successList.push(element);return true;},customMetaMessage:function(element,method){if(!$.metadata)return;var meta=this.settings.meta?$(element).metadata()[this.settings.meta]:$(element).metadata();return meta&&meta.messages&&meta.messages[method];},customMessage:function(name,method){var m=this.settings.messages[name];return m&&(m.constructor==String?m:m[method]);},findDefined:function(){for(var i=0;i<arguments.length;i++){if(arguments[i]!==undefined)return arguments[i];}return undefined;},defaultMessage:function(element,method){return this.findDefined(this.customMessage(element.name,method),this.customMetaMessage(element,method),!this.settings.ignoreTitle&&element.title||undefined,$.validator.messages[method],"<strong>Warning: No message defined for "+element.name+"</strong>");},formatAndAdd:function(element,rule){var message=this.defaultMessage(element,rule.method),theregex=/\$?\{(\d+)\}/g;if(typeof message=="function"){message=message.call(this,rule.parameters,element);}else if(theregex.test(message)){message=jQuery.format(message.replace(theregex,'{$1}'),rule.parameters);}this.errorList.push({message:message,element:element});this.errorMap[element.name]=message;this.submitted[element.name]=message;},addWrapper:function(toToggle){if(this.settings.wrapper)toToggle=toToggle.add(toToggle.parent(this.settings.wrapper));return toToggle;},defaultShowErrors:function(){for(var i=0;this.errorList[i];i++){var error=this.errorList[i];this.settings.highlight&&this.settings.highlight.call(this,error.element,this.settings.errorClass,this.settings.validClass);this.showLabel(error.element,error.message);}if(this.errorList.length){this.toShow=this.toShow.add(this.containers);}if(this.settings.success){for(var i=0;this.successList[i];i++){this.showLabel(this.successList[i]);}}if(this.settings.unhighlight){for(var i=0,elements=this.validElements();elements[i];i++){this.settings.unhighlight.call(this,elements[i],this.settings.errorClass,this.settings.validClass);}}this.toHide=this.toHide.not(this.toShow);this.hideErrors();this.addWrapper(this.toShow).show();},validElements:function(){return this.currentElements.not(this.invalidElements());},invalidElements:function(){return $(this.errorList).map(function(){return this.element;});},showLabel:function(element,message){var label=this.errorsFor(element);if(label.length){label.removeClass().addClass(this.settings.errorClass);label.attr("generated")&&label.html(message);}else{label=$("<"+this.settings.errorElement+"/>").attr({"for":this.idOrName(element),generated:true}).addClass(this.settings.errorClass).html(message||"");if(this.settings.wrapper){label=label.hide().show().wrap("<"+this.settings.wrapper+"/>").parent();}if(!this.labelContainer.append(label).length)this.settings.errorPlacement?this.settings.errorPlacement(label,$(element)):label.insertAfter(element);}if(!message&&this.settings.success){label.text("");typeof this.settings.success=="string"?label.addClass(this.settings.success):this.settings.success(label);}this.toShow=this.toShow.add(label);},errorsFor:function(element){var name=this.idOrName(element);return this.errors().filter(function(){return $(this).attr('for')==name});},idOrName:function(element){return this.groups[element.name]||(this.checkable(element)?element.name:element.id||element.name);},checkable:function(element){return/radio|checkbox/i.test(element.type);},findByName:function(name){var form=this.currentForm;return $(document.getElementsByName(name)).map(function(index,element){return element.form==form&&element.name==name&&element||null;});},getLength:function(value,element){switch(element.nodeName.toLowerCase()){case'select':return $("option:selected",element).length;case'input':if(this.checkable(element))return this.findByName(element.name).filter(':checked').length;}return value.length;},depend:function(param,element){return this.dependTypes[typeof param]?this.dependTypes[typeof param](param,element):true;},dependTypes:{"boolean":function(param,element){return param;},"string":function(param,element){return!!$(param,element.form).length;},"function":function(param,element){return param(element);}},optional:function(element){return!$.validator.methods.required.call(this,$.trim(element.value),element)&&"dependency-mismatch";},startRequest:function(element){if(!this.pending[element.name]){this.pendingRequest++;this.pending[element.name]=true;}},stopRequest:function(element,valid){this.pendingRequest--;if(this.pendingRequest<0)this.pendingRequest=0;delete this.pending[element.name];if(valid&&this.pendingRequest==0&&this.formSubmitted&&this.form()){$(this.currentForm).submit();this.formSubmitted=false;}else if(!valid&&this.pendingRequest==0&&this.formSubmitted){$(this.currentForm).triggerHandler("invalid-form",[this]);this.formSubmitted=false;}},previousValue:function(element){return $.data(element,"previousValue")||$.data(element,"previousValue",{old:null,valid:true,message:this.defaultMessage(element,"remote")});}},classRuleSettings:{required:{required:true},email:{email:true},url:{url:true},date:{date:true},dateISO:{dateISO:true},dateDE:{dateDE:true},number:{number:true},numberDE:{numberDE:true},digits:{digits:true},creditcard:{creditcard:true}},addClassRules:function(className,rules){className.constructor==String?this.classRuleSettings[className]=rules:$.extend(this.classRuleSettings,className);},classRules:function(element){var rules={};var classes=$(element).attr('class');classes&&$.each(classes.split(' '),function(){if(this in $.validator.classRuleSettings){$.extend(rules,$.validator.classRuleSettings[this]);}});return rules;},attributeRules:function(element){var rules={};var $element=$(element);for(method in $.validator.methods){var value=$element.attr(method);if(value){rules[method]=value;}}if(rules.maxlength&&/-1|2147483647|524288/.test(rules.maxlength)){delete rules.maxlength;}return rules;},metadataRules:function(element){if(!$.metadata)return{};var meta=$.data(element.form,'validator').settings.meta;return meta?$(element).metadata()[meta]:$(element).metadata();},staticRules:function(element){var rules={};var validator=$.data(element.form,'validator');if(validator.settings.rules){rules=$.validator.normalizeRule(validator.settings.rules[element.name])||{};}return rules;},normalizeRules:function(rules,element){$.each(rules,function(prop,val){if(val===false){delete rules[prop];return;}if(val.param||val.depends){var keepRule=true;switch(typeof val.depends){case"string":keepRule=!!$(val.depends,element.form).length;break;case"function":keepRule=val.depends.call(element,element);break;}if(keepRule){rules[prop]=val.param!==undefined?val.param:true;}else{delete rules[prop];}}});$.each(rules,function(rule,parameter){rules[rule]=$.isFunction(parameter)?parameter(element):parameter;});$.each(['minlength','maxlength','min','max'],function(){if(rules[this]){rules[this]=Number(rules[this]);}});$.each(['rangelength','range'],function(){if(rules[this]){rules[this]=[Number(rules[this][0]),Number(rules[this][1])];}});if($.validator.autoCreateRanges){if(rules.min&&rules.max){rules.range=[rules.min,rules.max];delete rules.min;delete rules.max;}if(rules.minlength&&rules.maxlength){rules.rangelength=[rules.minlength,rules.maxlength];delete rules.minlength;delete rules.maxlength;}}if(rules.messages){delete rules.messages}return rules;},normalizeRule:function(data){if(typeof data=="string"){var transformed={};$.each(data.split(/\s/),function(){transformed[this]=true;});data=transformed;}return data;},addMethod:function(name,method,message){$.validator.methods[name]=method;$.validator.messages[name]=message!=undefined?message:$.validator.messages[name];if(method.length<3){$.validator.addClassRules(name,$.validator.normalizeRule(name));}},methods:{required:function(value,element,param){if(!this.depend(param,element))return"dependency-mismatch";switch(element.nodeName.toLowerCase()){case'select':var val=$(element).val();return val&&val.length>0;case'input':if(this.checkable(element))return this.getLength(value,element)>0;default:return $.trim(value).length>0;}},remote:function(value,element,param){if(this.optional(element))return"dependency-mismatch";var previous=this.previousValue(element);if(!this.settings.messages[element.name])this.settings.messages[element.name]={};previous.originalMessage=this.settings.messages[element.name].remote;this.settings.messages[element.name].remote=previous.message;param=typeof param=="string"&&{url:param}||param;if(previous.old!==value){previous.old=value;var validator=this;this.startRequest(element);var data={};data[element.name]=value;$.ajax($.extend(true,{url:param,mode:"abort",port:"validate"+element.name,dataType:"json",data:data,success:function(response){validator.settings.messages[element.name].remote=previous.originalMessage;var valid=response===true;if(valid){var submitted=validator.formSubmitted;validator.prepareElement(element);validator.formSubmitted=submitted;validator.successList.push(element);validator.showErrors();}else{var errors={};var message=(previous.message=response||validator.defaultMessage(element,"remote"));errors[element.name]=$.isFunction(message)?message(value):message;validator.showErrors(errors);}previous.valid=valid;validator.stopRequest(element,valid);}},param));return"pending";}else if(this.pending[element.name]){return"pending";}return previous.valid;},minlength:function(value,element,param){return this.optional(element)||this.getLength($.trim(value),element)>=param;},maxlength:function(value,element,param){return this.optional(element)||this.getLength($.trim(value),element)<=param;},rangelength:function(value,element,param){var length=this.getLength($.trim(value),element);return this.optional(element)||(length>=param[0]&&length<=param[1]);},min:function(value,element,param){return this.optional(element)||value>=param;},max:function(value,element,param){return this.optional(element)||value<=param;},range:function(value,element,param){return this.optional(element)||(value>=param[0]&&value<=param[1]);},email:function(value,element){return this.optional(element)||/^((([a-z]|\d|[!#\$%&'\*\+\-\/=\?\^_`{\|}~]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])+(\.([a-z]|\d|[!#\$%&'\*\+\-\/=\?\^_`{\|}~]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])+)*)|((\x22)((((\x20|\x09)*(\x0d\x0a))?(\x20|\x09)+)?(([\x01-\x08\x0b\x0c\x0e-\x1f\x7f]|\x21|[\x23-\x5b]|[\x5d-\x7e]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(\\([\x01-\x09\x0b\x0c\x0d-\x7f]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF]))))*(((\x20|\x09)*(\x0d\x0a))?(\x20|\x09)+)?(\x22)))@((([a-z]|\d|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(([a-z]|\d|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])*([a-z]|\d|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])))\.)+(([a-z]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(([a-z]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])*([a-z]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])))\.?$/i.test(value);},url:function(value,element){return this.optional(element)||/^(https?|ftp):\/\/(((([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(%[\da-f]{2})|[!\$&'\(\)\*\+,;=]|:)*@)?(((\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5])\.(\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5])\.(\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5])\.(\d|[1-9]\d|1\d\d|2[0-4]\d|25[0-5]))|((([a-z]|\d|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(([a-z]|\d|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])*([a-z]|\d|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])))\.)+(([a-z]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(([a-z]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])*([a-z]|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])))\.?)(:\d*)?)(\/((([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(%[\da-f]{2})|[!\$&'\(\)\*\+,;=]|:|@)+(\/(([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(%[\da-f]{2})|[!\$&'\(\)\*\+,;=]|:|@)*)*)?)?(\?((([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(%[\da-f]{2})|[!\$&'\(\)\*\+,;=]|:|@)|[\uE000-\uF8FF]|\/|\?)*)?(\#((([a-z]|\d|-|\.|_|~|[\u00A0-\uD7FF\uF900-\uFDCF\uFDF0-\uFFEF])|(%[\da-f]{2})|[!\$&'\(\)\*\+,;=]|:|@)|\/|\?)*)?$/i.test(value);},date:function(value,element){return this.optional(element)||!/Invalid|NaN/.test(new Date(value));},dateISO:function(value,element){return this.optional(element)||/^\d{4}[\/-]\d{1,2}[\/-]\d{1,2}$/.test(value);},number:function(value,element){return this.optional(element)||/^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(value);},digits:function(value,element){return this.optional(element)||/^\d+$/.test(value);},creditcard:function(value,element){if(this.optional(element))return"dependency-mismatch";if(/[^0-9-]+/.test(value))return false;var nCheck=0,nDigit=0,bEven=false;value=value.replace(/\D/g,"");for(var n=value.length-1;n>=0;n--){var cDigit=value.charAt(n);var nDigit=parseInt(cDigit,10);if(bEven){if((nDigit*=2)>9)nDigit-=9;}nCheck+=nDigit;bEven=!bEven;}return(nCheck%10)==0;},accept:function(value,element,param){param=typeof param=="string"?param.replace(/,/g,'|'):"png|jpe?g|gif";return this.optional(element)||value.match(new RegExp(".("+param+")$","i"));},equalTo:function(value,element,param){var target=$(param).unbind(".validate-equalTo").bind("blur.validate-equalTo",function(){$(element).valid();});return value==target.val();}}});$.format=$.validator.format;})(jQuery);;(function($){var ajax=$.ajax;var pendingRequests={};$.ajax=function(settings){settings=$.extend(settings,$.extend({},$.ajaxSettings,settings));var port=settings.port;if(settings.mode=="abort"){if(pendingRequests[port]){pendingRequests[port].abort();}return(pendingRequests[port]=ajax.apply(this,arguments));}return ajax.apply(this,arguments);};})(jQuery);;(function($){$.each({focus:'focusin',blur:'focusout'},function(original,fix){$.event.special[fix]={setup:function(){if($.browser.msie)return false;this.addEventListener(original,$.event.special[fix].handler,true);},teardown:function(){if($.browser.msie)return false;this.removeEventListener(original,$.event.special[fix].handler,true);},handler:function(e){arguments[0]=$.event.fix(e);arguments[0].type=fix;return $.event.handle.apply(this,arguments);}};});$.extend($.fn,{delegate:function(type,delegate,handler){return this.bind(type,function(event){var target=$(event.target);if(target.is(delegate)){return handler.apply(target,arguments);}});},triggerEvent:function(type,target){return this.triggerHandler(type,[$.event.fix({type:type,target:target})]);}})})(jQuery);

/*
 * jQuery Flickr - jQuery plug-in
 * Version 1.0, Released 2008.04.17
 *
 * Copyright (c) 2008 Daniel MacDonald (www.projectatomic.com)
 * Dual licensed GPL http://www.gnu.org/licenses/gpl.html 
 * and MIT http://www.opensource.org/licenses/mit-license.php
 */
(function($){$.fn.flickr=function(o){var s={api_key:null,type:null,photoset_id:null,text:null,user_id:null,group_id:null,tags:null,tag_mode:'any',sort:'date-posted-asc',thumb_size:'s',size:null,per_page:100,page:1,attr:'',api_url:null,params:'',api_callback:'?',callback:null};if(o)$.extend(s,o);return this.each(function(){var list=$('<ul>').appendTo(this);var url=$.flickr.format(s);$.getJSON(url,function(r){if(r.stat!="ok"){for(i in r){$('<li>').text(i+': '+r[i]).appendTo(list);};}else{if(s.type=='photoset')r.photos=r.photoset;list.append('<input type="hidden" value="'+r.photos.page+'" />');list.append('<input type="hidden" value="'+r.photos.pages+'" />');list.append('<input type="hidden" value="'+r.photos.perpage+'" />');list.append('<input type="hidden" value="'+r.photos.total+'" />');for(var i=0;i<r.photos.photo.length;i++){var photo=r.photos.photo[i];var t='http://farm'+photo['farm']+'.static.flickr.com/'+photo['server']+'/'+photo['id']+'_'+photo['secret']+'_'+s.thumb_size+'.jpg';var h='http://farm'+photo['farm']+'.static.flickr.com/'+photo['server']+'/'+photo['id']+'_';switch(s.size){case'm':h+=photo['secret']+'_m.jpg';break;case'b':h+=photo['secret']+'_b.jpg';break;case'o':if(photo['originalsecret']&&photo['originalformat']){h+=photo['originalsecret']+'_o.'+photo['originalformat'];break;};default:h+=photo['secret']+'.jpg';};list.append('<li><a href="'+h+'" '+s.attr+' title="'+photo['title']+'"><img src="'+t+'" alt="'+photo['title']+'" /></a></li>');};if(s.callback)s.callback(list);};});});};$.flickr={format:function(s){if(s.url)return s.url;var url='http://api.flickr.com/services/rest/?format=json&jsoncallback='+s.api_callback+'&api_key='+s.api_key;switch(s.type){case'photoset':url+='&method=flickr.photosets.getPhotos&photoset_id='+s.photoset_id;break;case'search':url+='&method=flickr.photos.search&sort='+s.sort;if(s.user_id)url+='&user_id='+s.user_id;if(s.group_id)url+='&group_id='+s.group_id;if(s.tags)url+='&tags='+s.tags;if(s.tag_mode)url+='&tag_mode='+s.tag_mode;if(s.text)url+='&text='+s.text;break;default:url+='&method=flickr.photos.getRecent';};if(s.size=='o')url+='&extras=original_format';url+='&per_page='+s.per_page+'&page='+s.page+s.params;return url;}};})(jQuery);


(function($){$.fn.tweet=function(o){var s={username:["seaofclouds"],avatar_size:null,count:3,intro_text:null,outro_text:null,join_text:null,auto_join_text_default:"i said,",auto_join_text_ed:"i",auto_join_text_ing:"i am",auto_join_text_reply:"i replied to",auto_join_text_url:"i was looking at",loading_text:null,query:null};$.fn.extend({linkUrl:function(){var returning=[];var regexp=/((ftp|http|https):\/\/(\w+:{0,1}\w*@)?(\S+)(:[0-9]+)?(\/|\/([\w#!:.?+=&%@!\-\/]))?)/gi;this.each(function(){returning.push(this.replace(regexp,"<a href=\"$1\">$1</a>"))});return $(returning);},linkUser:function(){var returning=[];var regexp=/[\@]+([A-Za-z0-9-_]+)/gi;this.each(function(){returning.push(this.replace(regexp,"<a href=\"http://twitter.com/$1\">@$1</a>"))});return $(returning);},linkHash:function(){var returning=[];var regexp=/ [\#]+([A-Za-z0-9-_]+)/gi;this.each(function(){returning.push(this.replace(regexp,' <a href="http://search.twitter.com/search?q=&tag=$1&lang=all&from='+s.username.join("%2BOR%2B")+'">#$1</a>'))});return $(returning);},capAwesome:function(){var returning=[];this.each(function(){returning.push(this.replace(/(a|A)wesome/gi,'AWESOME'))});return $(returning);},capEpic:function(){var returning=[];this.each(function(){returning.push(this.replace(/(e|E)pic/gi,'EPIC'))});return $(returning);},makeHeart:function(){var returning=[];this.each(function(){returning.push(this.replace(/[&lt;]+[3]/gi,"<tt class='heart'>&#x2665;</tt>"))});return $(returning);}});function relative_time(time_value){var parsed_date=Date.parse(time_value);var relative_to=(arguments.length>1)?arguments[1]:new Date();var delta=parseInt((relative_to.getTime()-parsed_date)/1000);if(delta<60){return'less than a minute ago';}else if(delta<120){return'about a minute ago';}else if(delta<(45*60)){return(parseInt(delta/60)).toString()+' minutes ago';}else if(delta<(90*60)){return'about an hour ago';}else if(delta<(24*60*60)){return'about '+(parseInt(delta/3600)).toString()+' hours ago';}else if(delta<(48*60*60)){return'1 day ago';}else{return(parseInt(delta/86400)).toString()+' days ago';}}
if(o)$.extend(s,o);return this.each(function(){var list=$('<ul class="tweet_list">').appendTo(this);var intro='<p class="tweet_intro">'+s.intro_text+'</p>'
var outro='<p class="tweet_outro">'+s.outro_text+'</p>'
var loading=$('<p class="loading">'+s.loading_text+'</p>');if(typeof(s.username)=="string"){s.username=[s.username];}
var query='';if(s.query){query+='q='+s.query;}
query+='&q=from:'+s.username.join('%20OR%20from:');var url='http://search.twitter.com/search.json?&'+query+'&rpp='+s.count+'&callback=?';if(s.loading_text)$(this).append(loading);$.getJSON(url,function(data){if(s.loading_text)loading.remove();if(s.intro_text)list.before(intro);$.each(data.results,function(i,item){if(s.join_text=="auto"){if(item.text.match(/^(@([A-Za-z0-9-_]+)) .*/i)){var join_text=s.auto_join_text_reply;}else if(item.text.match(/(^\w+:\/\/[A-Za-z0-9-_]+\.[A-Za-z0-9-_:%&\?\/.=]+) .*/i)){var join_text=s.auto_join_text_url;}else if(item.text.match(/^((\w+ed)|just) .*/im)){var join_text=s.auto_join_text_ed;}else if(item.text.match(/^(\w*ing) .*/i)){var join_text=s.auto_join_text_ing;}else{var join_text=s.auto_join_text_default;}}else{var join_text=s.join_text;};var join_template='<span class="tweet_join"> '+join_text+' </span>';var join=((s.join_text)?join_template:' ')
var avatar_template='<a class="tweet_avatar" href="http://twitter.com/'+item.from_user+'"><img src="'+item.profile_image_url+'" height="'+s.avatar_size+'" width="'+s.avatar_size+'" alt="'+item.from_user+'\'s avatar" border="0"/></a>';var avatar=(s.avatar_size?avatar_template:'')
var date='<a href="http://twitter.com/'+item.from_user+'/statuses/'+item.id+'" title="view tweet on twitter">'+relative_time(item.created_at)+'</a>';var text='<span class="tweet_text">'+$([item.text]).linkUrl().linkUser().linkHash().makeHeart().capAwesome().capEpic()[0]+'</span>';list.append('<li>'+avatar+date+join+text+'</li>');list.children('li:first').addClass('tweet_first');list.children('li:odd').addClass('tweet_even');list.children('li:even').addClass('tweet_odd');});if(s.outro_text)list.after(outro);});});};})(jQuery);/* Javascript plotting library for jQuery, v. 0.6.
 *
 * Released under the MIT license by IOLA, December 2007.
 *
 */

// first an inline dependency, jquery.colorhelpers.js, we inline it here
// for convenience

/* Plugin for jQuery for working with colors.
 * 
 * Version 1.0.
 * 
 * Inspiration from jQuery color animation plugin by John Resig.
 *
 * Released under the MIT license by Ole Laursen, October 2009.
 *
 * Examples:
 *
 *   $.color.parse("#fff").scale('rgb', 0.25).add('a', -0.5).toString()
 *   var c = $.color.extract($("#mydiv"), 'background-color');
 *   console.log(c.r, c.g, c.b, c.a);
 *   $.color.make(100, 50, 25, 0.4).toString() // returns "rgba(100,50,25,0.4)"
 *
 * Note that .scale() and .add() work in-place instead of returning
 * new objects.
 */ 
(function(){jQuery.color={};jQuery.color.make=function(E,D,B,C){var F={};F.r=E||0;F.g=D||0;F.b=B||0;F.a=C!=null?C:1;F.add=function(I,H){for(var G=0;G<I.length;++G){F[I.charAt(G)]+=H}return F.normalize()};F.scale=function(I,H){for(var G=0;G<I.length;++G){F[I.charAt(G)]*=H}return F.normalize()};F.toString=function(){if(F.a>=1){return"rgb("+[F.r,F.g,F.b].join(",")+")"}else{return"rgba("+[F.r,F.g,F.b,F.a].join(",")+")"}};F.normalize=function(){function G(I,J,H){return J<I?I:(J>H?H:J)}F.r=G(0,parseInt(F.r),255);F.g=G(0,parseInt(F.g),255);F.b=G(0,parseInt(F.b),255);F.a=G(0,F.a,1);return F};F.clone=function(){return jQuery.color.make(F.r,F.b,F.g,F.a)};return F.normalize()};jQuery.color.extract=function(C,B){var D;do{D=C.css(B).toLowerCase();if(D!=""&&D!="transparent"){break}C=C.parent()}while(!jQuery.nodeName(C.get(0),"body"));if(D=="rgba(0, 0, 0, 0)"){D="transparent"}return jQuery.color.parse(D)};jQuery.color.parse=function(E){var D,B=jQuery.color.make;if(D=/rgb\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*\)/.exec(E)){return B(parseInt(D[1],10),parseInt(D[2],10),parseInt(D[3],10))}if(D=/rgba\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\)/.exec(E)){return B(parseInt(D[1],10),parseInt(D[2],10),parseInt(D[3],10),parseFloat(D[4]))}if(D=/rgb\(\s*([0-9]+(?:\.[0-9]+)?)\%\s*,\s*([0-9]+(?:\.[0-9]+)?)\%\s*,\s*([0-9]+(?:\.[0-9]+)?)\%\s*\)/.exec(E)){return B(parseFloat(D[1])*2.55,parseFloat(D[2])*2.55,parseFloat(D[3])*2.55)}if(D=/rgba\(\s*([0-9]+(?:\.[0-9]+)?)\%\s*,\s*([0-9]+(?:\.[0-9]+)?)\%\s*,\s*([0-9]+(?:\.[0-9]+)?)\%\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\)/.exec(E)){return B(parseFloat(D[1])*2.55,parseFloat(D[2])*2.55,parseFloat(D[3])*2.55,parseFloat(D[4]))}if(D=/#([a-fA-F0-9]{2})([a-fA-F0-9]{2})([a-fA-F0-9]{2})/.exec(E)){return B(parseInt(D[1],16),parseInt(D[2],16),parseInt(D[3],16))}if(D=/#([a-fA-F0-9])([a-fA-F0-9])([a-fA-F0-9])/.exec(E)){return B(parseInt(D[1]+D[1],16),parseInt(D[2]+D[2],16),parseInt(D[3]+D[3],16))}var C=jQuery.trim(E).toLowerCase();if(C=="transparent"){return B(255,255,255,0)}else{D=A[C];return B(D[0],D[1],D[2])}};var A={aqua:[0,255,255],azure:[240,255,255],beige:[245,245,220],black:[0,0,0],blue:[0,0,255],brown:[165,42,42],cyan:[0,255,255],darkblue:[0,0,139],darkcyan:[0,139,139],darkgrey:[169,169,169],darkgreen:[0,100,0],darkkhaki:[189,183,107],darkmagenta:[139,0,139],darkolivegreen:[85,107,47],darkorange:[255,140,0],darkorchid:[153,50,204],darkred:[139,0,0],darksalmon:[233,150,122],darkviolet:[148,0,211],fuchsia:[255,0,255],gold:[255,215,0],green:[0,128,0],indigo:[75,0,130],khaki:[240,230,140],lightblue:[173,216,230],lightcyan:[224,255,255],lightgreen:[144,238,144],lightgrey:[211,211,211],lightpink:[255,182,193],lightyellow:[255,255,224],lime:[0,255,0],magenta:[255,0,255],maroon:[128,0,0],navy:[0,0,128],olive:[128,128,0],orange:[255,165,0],pink:[255,192,203],purple:[128,0,128],violet:[128,0,128],red:[255,0,0],silver:[192,192,192],white:[255,255,255],yellow:[255,255,0]}})();

// the actual Flot code
(function($) {
    function Plot(placeholder, data_, options_, plugins) {
        // data is on the form:
        //   [ series1, series2 ... ]
        // where series is either just the data as [ [x1, y1], [x2, y2], ... ]
        // or { data: [ [x1, y1], [x2, y2], ... ], label: "some label", ... }
        
        var series = [],
            options = {
                // the color theme used for graphs
                colors: ["#edc240", "#afd8f8", "#cb4b4b", "#4da74d", "#9440ed"],
                legend: {
                    show: true,
                    noColumns: 1, // number of colums in legend table
                    labelFormatter: null, // fn: string -> string
                    labelBoxBorderColor: "#ccc", // border color for the little label boxes
                    container: null, // container (as jQuery object) to put legend in, null means default on top of graph
                    position: "ne", // position of default legend container within plot
                    margin: 5, // distance from grid edge to default legend container within plot
                    backgroundColor: null, // null means auto-detect
                    backgroundOpacity: 0.85 // set to 0 to avoid background
                },
                xaxis: {
                    mode: null, // null or "time"
                    transform: null, // null or f: number -> number to transform axis
                    inverseTransform: null, // if transform is set, this should be the inverse function
                    min: null, // min. value to show, null means set automatically
                    max: null, // max. value to show, null means set automatically
                    autoscaleMargin: null, // margin in % to add if auto-setting min/max
                    ticks: null, // either [1, 3] or [[1, "a"], 3] or (fn: axis info -> ticks) or app. number of ticks for auto-ticks
                    tickFormatter: null, // fn: number -> string
                    labelWidth: null, // size of tick labels in pixels
                    labelHeight: null,
                    
                    // mode specific options
                    tickDecimals: null, // no. of decimals, null means auto
                    tickSize: null, // number or [number, "unit"]
                    minTickSize: null, // number or [number, "unit"]
                    monthNames: null, // list of names of months
                    timeformat: null, // format string to use
                    twelveHourClock: false // 12 or 24 time in time mode
                },
                yaxis: {
                    autoscaleMargin: 0.02
                },
                x2axis: {
                    autoscaleMargin: null
                },
                y2axis: {
                    autoscaleMargin: 0.02
                },
                series: {
                    points: {
                        show: false,
                        radius: 3,
                        lineWidth: 2, // in pixels
                        fill: true,
                        fillColor: "#ffffff"
                    },
                    lines: {
                        // we don't put in show: false so we can see
                        // whether lines were actively disabled 
                        lineWidth: 2, // in pixels
                        fill: false,
                        fillColor: null,
                        steps: false
                    },
                    bars: {
                        show: false,
                        lineWidth: 2, // in pixels
                        barWidth: 1, // in units of the x axis
                        fill: true,
                        fillColor: null,
                        align: "left", // or "center" 
                        horizontal: false // when horizontal, left is now top
                    },
                    shadowSize: 3
                },
                grid: {
                    show: true,
                    aboveData: false,
                    color: "#545454", // primary color used for outline and labels
                    backgroundColor: null, // null for transparent, else color
                    tickColor: "rgba(0,0,0,0.15)", // color used for the ticks
                    labelMargin: 5, // in pixels
                    borderWidth: 2, // in pixels
                    borderColor: null, // set if different from the grid color
                    markings: null, // array of ranges or fn: axes -> array of ranges
                    markingsColor: "#f4f4f4",
                    markingsLineWidth: 2,
                    // interactive stuff
                    clickable: false,
                    hoverable: false,
                    autoHighlight: true, // highlight in case mouse is near
                    mouseActiveRadius: 10 // how far the mouse can be away to activate an item
                },
                hooks: {}
            },
        canvas = null,      // the canvas for the plot itself
        overlay = null,     // canvas for interactive stuff on top of plot
        eventHolder = null, // jQuery object that events should be bound to
        ctx = null, octx = null,
        axes = { xaxis: {}, yaxis: {}, x2axis: {}, y2axis: {} },
        plotOffset = { left: 0, right: 0, top: 0, bottom: 0},
        canvasWidth = 0, canvasHeight = 0,
        plotWidth = 0, plotHeight = 0,
        hooks = {
            processOptions: [],
            processRawData: [],
            processDatapoints: [],
            draw: [],
            bindEvents: [],
            drawOverlay: []
        },
        plot = this;

        // public functions
        plot.setData = setData;
        plot.setupGrid = setupGrid;
        plot.draw = draw;
        plot.getPlaceholder = function() { return placeholder; };
        plot.getCanvas = function() { return canvas; };
        plot.getPlotOffset = function() { return plotOffset; };
        plot.width = function () { return plotWidth; };
        plot.height = function () { return plotHeight; };
        plot.offset = function () {
            var o = eventHolder.offset();
            o.left += plotOffset.left;
            o.top += plotOffset.top;
            return o;
        };
        plot.getData = function() { return series; };
        plot.getAxes = function() { return axes; };
        plot.getOptions = function() { return options; };
        plot.highlight = highlight;
        plot.unhighlight = unhighlight;
        plot.triggerRedrawOverlay = triggerRedrawOverlay;
        plot.pointOffset = function(point) {
            return { left: parseInt(axisSpecToRealAxis(point, "xaxis").p2c(+point.x) + plotOffset.left),
                     top: parseInt(axisSpecToRealAxis(point, "yaxis").p2c(+point.y) + plotOffset.top) };
        };
        

        // public attributes
        plot.hooks = hooks;
        
        // initialize
        initPlugins(plot);
        parseOptions(options_);
        constructCanvas();
        setData(data_);
        setupGrid();
        draw();
        bindEvents();


        function executeHooks(hook, args) {
            args = [plot].concat(args);
            for (var i = 0; i < hook.length; ++i)
                hook[i].apply(this, args);
        }

        function initPlugins() {
            for (var i = 0; i < plugins.length; ++i) {
                var p = plugins[i];
                p.init(plot);
                if (p.options)
                    $.extend(true, options, p.options);
            }
        }
        
        function parseOptions(opts) {
            $.extend(true, options, opts);
            if (options.grid.borderColor == null)
                options.grid.borderColor = options.grid.color;
            // backwards compatibility, to be removed in future
            if (options.xaxis.noTicks && options.xaxis.ticks == null)
                options.xaxis.ticks = options.xaxis.noTicks;
            if (options.yaxis.noTicks && options.yaxis.ticks == null)
                options.yaxis.ticks = options.yaxis.noTicks;
            if (options.grid.coloredAreas)
                options.grid.markings = options.grid.coloredAreas;
            if (options.grid.coloredAreasColor)
                options.grid.markingsColor = options.grid.coloredAreasColor;
            if (options.lines)
                $.extend(true, options.series.lines, options.lines);
            if (options.points)
                $.extend(true, options.series.points, options.points);
            if (options.bars)
                $.extend(true, options.series.bars, options.bars);
            if (options.shadowSize)
                options.series.shadowSize = options.shadowSize;

            for (var n in hooks)
                if (options.hooks[n] && options.hooks[n].length)
                    hooks[n] = hooks[n].concat(options.hooks[n]);

            executeHooks(hooks.processOptions, [options]);
        }

        function setData(d) {
            series = parseData(d);
            fillInSeriesOptions();
            processData();
        }
        
        function parseData(d) {
            var res = [];
            for (var i = 0; i < d.length; ++i) {
                var s = $.extend(true, {}, options.series);

                if (d[i].data) {
                    s.data = d[i].data; // move the data instead of deep-copy
                    delete d[i].data;

                    $.extend(true, s, d[i]);

                    d[i].data = s.data;
                }
                else
                    s.data = d[i];
                res.push(s);
            }

            return res;
        }
        
        function axisSpecToRealAxis(obj, attr) {
            var a = obj[attr];
            if (!a || a == 1)
                return axes[attr];
            if (typeof a == "number")
                return axes[attr.charAt(0) + a + attr.slice(1)];
            return a; // assume it's OK
        }
        
        function fillInSeriesOptions() {
            var i;
            
            // collect what we already got of colors
            var neededColors = series.length,
                usedColors = [],
                assignedColors = [];
            for (i = 0; i < series.length; ++i) {
                var sc = series[i].color;
                if (sc != null) {
                    --neededColors;
                    if (typeof sc == "number")
                        assignedColors.push(sc);
                    else
                        usedColors.push($.color.parse(series[i].color));
                }
            }
            
            // we might need to generate more colors if higher indices
            // are assigned
            for (i = 0; i < assignedColors.length; ++i) {
                neededColors = Math.max(neededColors, assignedColors[i] + 1);
            }

            // produce colors as needed
            var colors = [], variation = 0;
            i = 0;
            while (colors.length < neededColors) {
                var c;
                if (options.colors.length == i) // check degenerate case
                    c = $.color.make(100, 100, 100);
                else
                    c = $.color.parse(options.colors[i]);

                // vary color if needed
                var sign = variation % 2 == 1 ? -1 : 1;
                c.scale('rgb', 1 + sign * Math.ceil(variation / 2) * 0.2)

                // FIXME: if we're getting to close to something else,
                // we should probably skip this one
                colors.push(c);
                
                ++i;
                if (i >= options.colors.length) {
                    i = 0;
                    ++variation;
                }
            }

            // fill in the options
            var colori = 0, s;
            for (i = 0; i < series.length; ++i) {
                s = series[i];
                
                // assign colors
                if (s.color == null) {
                    s.color = colors[colori].toString();
                    ++colori;
                }
                else if (typeof s.color == "number")
                    s.color = colors[s.color].toString();

                // turn on lines automatically in case nothing is set
                if (s.lines.show == null) {
                    var v, show = true;
                    for (v in s)
                        if (s[v].show) {
                            show = false;
                            break;
                        }
                    if (show)
                        s.lines.show = true;
                }

                // setup axes
                s.xaxis = axisSpecToRealAxis(s, "xaxis");
                s.yaxis = axisSpecToRealAxis(s, "yaxis");
            }
        }
        
        function processData() {
            var topSentry = Number.POSITIVE_INFINITY,
                bottomSentry = Number.NEGATIVE_INFINITY,
                i, j, k, m, length,
                s, points, ps, x, y, axis, val, f, p;

            for (axis in axes) {
                axes[axis].datamin = topSentry;
                axes[axis].datamax = bottomSentry;
                axes[axis].used = false;
            }

            function updateAxis(axis, min, max) {
                if (min < axis.datamin)
                    axis.datamin = min;
                if (max > axis.datamax)
                    axis.datamax = max;
            }

            for (i = 0; i < series.length; ++i) {
                s = series[i];
                s.datapoints = { points: [] };
                
                executeHooks(hooks.processRawData, [ s, s.data, s.datapoints ]);
            }
            
            // first pass: clean and copy data
            for (i = 0; i < series.length; ++i) {
                s = series[i];

                var data = s.data, format = s.datapoints.format;

                if (!format) {
                    format = [];
                    // find out how to copy
                    format.push({ x: true, number: true, required: true });
                    format.push({ y: true, number: true, required: true });

                    if (s.bars.show)
                        format.push({ y: true, number: true, required: false, defaultValue: 0 });
                    
                    s.datapoints.format = format;
                }

                if (s.datapoints.pointsize != null)
                    continue; // already filled in

                if (s.datapoints.pointsize == null)
                    s.datapoints.pointsize = format.length;
                
                ps = s.datapoints.pointsize;
                points = s.datapoints.points;

                insertSteps = s.lines.show && s.lines.steps;
                s.xaxis.used = s.yaxis.used = true;
                
                for (j = k = 0; j < data.length; ++j, k += ps) {
                    p = data[j];

                    var nullify = p == null;
                    if (!nullify) {
                        for (m = 0; m < ps; ++m) {
                            val = p[m];
                            f = format[m];

                            if (f) {
                                if (f.number && val != null) {
                                    val = +val; // convert to number
                                    if (isNaN(val))
                                        val = null;
                                }

                                if (val == null) {
                                    if (f.required)
                                        nullify = true;
                                    
                                    if (f.defaultValue != null)
                                        val = f.defaultValue;
                                }
                            }
                            
                            points[k + m] = val;
                        }
                    }
                    
                    if (nullify) {
                        for (m = 0; m < ps; ++m) {
                            val = points[k + m];
                            if (val != null) {
                                f = format[m];
                                // extract min/max info
                                if (f.x)
                                    updateAxis(s.xaxis, val, val);
                                if (f.y)
                                    updateAxis(s.yaxis, val, val);
                            }
                            points[k + m] = null;
                        }
                    }
                    else {
                        // a little bit of line specific stuff that
                        // perhaps shouldn't be here, but lacking
                        // better means...
                        if (insertSteps && k > 0
                            && points[k - ps] != null
                            && points[k - ps] != points[k]
                            && points[k - ps + 1] != points[k + 1]) {
                            // copy the point to make room for a middle point
                            for (m = 0; m < ps; ++m)
                                points[k + ps + m] = points[k + m];

                            // middle point has same y
                            points[k + 1] = points[k - ps + 1];

                            // we've added a point, better reflect that
                            k += ps;
                        }
                    }
                }
            }

            // give the hooks a chance to run
            for (i = 0; i < series.length; ++i) {
                s = series[i];
                
                executeHooks(hooks.processDatapoints, [ s, s.datapoints]);
            }

            // second pass: find datamax/datamin for auto-scaling
            for (i = 0; i < series.length; ++i) {
                s = series[i];
                points = s.datapoints.points,
                ps = s.datapoints.pointsize;

                var xmin = topSentry, ymin = topSentry,
                    xmax = bottomSentry, ymax = bottomSentry;
                
                for (j = 0; j < points.length; j += ps) {
                    if (points[j] == null)
                        continue;

                    for (m = 0; m < ps; ++m) {
                        val = points[j + m];
                        f = format[m];
                        if (!f)
                            continue;
                        
                        if (f.x) {
                            if (val < xmin)
                                xmin = val;
                            if (val > xmax)
                                xmax = val;
                        }
                        if (f.y) {
                            if (val < ymin)
                                ymin = val;
                            if (val > ymax)
                                ymax = val;
                        }
                    }
                }
                
                if (s.bars.show) {
                    // make sure we got room for the bar on the dancing floor
                    var delta = s.bars.align == "left" ? 0 : -s.bars.barWidth/2;
                    if (s.bars.horizontal) {
                        ymin += delta;
                        ymax += delta + s.bars.barWidth;
                    }
                    else {
                        xmin += delta;
                        xmax += delta + s.bars.barWidth;
                    }
                }
                
                updateAxis(s.xaxis, xmin, xmax);
                updateAxis(s.yaxis, ymin, ymax);
            }

            for (axis in axes) {
                if (axes[axis].datamin == topSentry)
                    axes[axis].datamin = null;
                if (axes[axis].datamax == bottomSentry)
                    axes[axis].datamax = null;
            }
        }

        function constructCanvas() {
            function makeCanvas(width, height) {
                var c = document.createElement('canvas');
                c.width = width;
                c.height = height;
                if ($.browser.msie) // excanvas hack
                    c = window.G_vmlCanvasManager.initElement(c);
                return c;
            }
            
            canvasWidth = placeholder.width();
            canvasHeight = placeholder.height();
            placeholder.html(""); // clear placeholder
            if (placeholder.css("position") == 'static')
                placeholder.css("position", "relative"); // for positioning labels and overlay

            if (canvasWidth <= 0 || canvasHeight <= 0)
                throw "Invalid dimensions for plot, width = " + canvasWidth + ", height = " + canvasHeight;

            if ($.browser.msie) // excanvas hack
                window.G_vmlCanvasManager.init_(document); // make sure everything is setup
            
            // the canvas
            canvas = $(makeCanvas(canvasWidth, canvasHeight)).appendTo(placeholder).get(0);
            ctx = canvas.getContext("2d");

            // overlay canvas for interactive features
            overlay = $(makeCanvas(canvasWidth, canvasHeight)).css({ position: 'absolute', left: 0, top: 0 }).appendTo(placeholder).get(0);
            octx = overlay.getContext("2d");
            octx.stroke();
        }

        function bindEvents() {
            // we include the canvas in the event holder too, because IE 7
            // sometimes has trouble with the stacking order
            eventHolder = $([overlay, canvas]);

            // bind events
            if (options.grid.hoverable)
                eventHolder.mousemove(onMouseMove);

            if (options.grid.clickable)
                eventHolder.click(onClick);

            executeHooks(hooks.bindEvents, [eventHolder]);
        }

        function setupGrid() {
            function setTransformationHelpers(axis, o) {
                function identity(x) { return x; }
                
                var s, m, t = o.transform || identity,
                    it = o.inverseTransform;
                    
                // add transformation helpers
                if (axis == axes.xaxis || axis == axes.x2axis) {
                    // precompute how much the axis is scaling a point
                    // in canvas space
                    s = axis.scale = plotWidth / (t(axis.max) - t(axis.min));
                    m = t(axis.min);

                    // data point to canvas coordinate
                    if (t == identity) // slight optimization
                        axis.p2c = function (p) { return (p - m) * s; };
                    else
                        axis.p2c = function (p) { return (t(p) - m) * s; };
                    // canvas coordinate to data point
                    if (!it)
                        axis.c2p = function (c) { return m + c / s; };
                    else
                        axis.c2p = function (c) { return it(m + c / s); };
                }
                else {
                    s = axis.scale = plotHeight / (t(axis.max) - t(axis.min));
                    m = t(axis.max);
                    
                    if (t == identity)
                        axis.p2c = function (p) { return (m - p) * s; };
                    else
                        axis.p2c = function (p) { return (m - t(p)) * s; };
                    if (!it)
                        axis.c2p = function (c) { return m - c / s; };
                    else
                        axis.c2p = function (c) { return it(m - c / s); };
                }
            }

            function measureLabels(axis, axisOptions) {
                var i, labels = [], l;
                
                axis.labelWidth = axisOptions.labelWidth;
                axis.labelHeight = axisOptions.labelHeight;

                if (axis == axes.xaxis || axis == axes.x2axis) {
                    // to avoid measuring the widths of the labels, we
                    // construct fixed-size boxes and put the labels inside
                    // them, we don't need the exact figures and the
                    // fixed-size box content is easy to center
                    if (axis.labelWidth == null)
                        axis.labelWidth = canvasWidth / (axis.ticks.length > 0 ? axis.ticks.length : 1);

                    // measure x label heights
                    if (axis.labelHeight == null) {
                        labels = [];
                        for (i = 0; i < axis.ticks.length; ++i) {
                            l = axis.ticks[i].label;
                            if (l)
                                labels.push('<div class="tickLabel" style="float:left;width:' + axis.labelWidth + 'px">' + l + '</div>');
                        }
                        
                        if (labels.length > 0) {
                            var dummyDiv = $('<div style="position:absolute;top:-10000px;width:10000px;font-size:smaller">'
                                             + labels.join("") + '<div style="clear:left"></div></div>').appendTo(placeholder);
                            axis.labelHeight = dummyDiv.height();
                            dummyDiv.remove();
                        }
                    }
                }
                else if (axis.labelWidth == null || axis.labelHeight == null) {
                    // calculate y label dimensions
                    for (i = 0; i < axis.ticks.length; ++i) {
                        l = axis.ticks[i].label;
                        if (l)
                            labels.push('<div class="tickLabel">' + l + '</div>');
                    }
                    
                    if (labels.length > 0) {
                        var dummyDiv = $('<div style="position:absolute;top:-10000px;font-size:smaller">'
                                         + labels.join("") + '</div>').appendTo(placeholder);
                        if (axis.labelWidth == null)
                            axis.labelWidth = dummyDiv.width();
                        if (axis.labelHeight == null)
                            axis.labelHeight = dummyDiv.find("div").height();
                        dummyDiv.remove();
                    }
                    
                }

                if (axis.labelWidth == null)
                    axis.labelWidth = 0;
                if (axis.labelHeight == null)
                    axis.labelHeight = 0;
            }
            
            function setGridSpacing() {
                // get the most space needed around the grid for things
                // that may stick out
                var maxOutset = options.grid.borderWidth;
                for (i = 0; i < series.length; ++i)
                    maxOutset = Math.max(maxOutset, 2 * (series[i].points.radius + series[i].points.lineWidth/2));
                
                plotOffset.left = plotOffset.right = plotOffset.top = plotOffset.bottom = maxOutset;
                
                var margin = options.grid.labelMargin + options.grid.borderWidth;
                
                if (axes.xaxis.labelHeight > 0)
                    plotOffset.bottom = Math.max(maxOutset, axes.xaxis.labelHeight + margin);
                if (axes.yaxis.labelWidth > 0)
                    plotOffset.left = Math.max(maxOutset, axes.yaxis.labelWidth + margin);
                if (axes.x2axis.labelHeight > 0)
                    plotOffset.top = Math.max(maxOutset, axes.x2axis.labelHeight + margin);
                if (axes.y2axis.labelWidth > 0)
                    plotOffset.right = Math.max(maxOutset, axes.y2axis.labelWidth + margin);
            
                plotWidth = canvasWidth - plotOffset.left - plotOffset.right;
                plotHeight = canvasHeight - plotOffset.bottom - plotOffset.top;
            }
            
            var axis;
            for (axis in axes)
                setRange(axes[axis], options[axis]);
            
            if (options.grid.show) {
                for (axis in axes) {
                    prepareTickGeneration(axes[axis], options[axis]);
                    setTicks(axes[axis], options[axis]);
                    measureLabels(axes[axis], options[axis]);
                }

                setGridSpacing();
            }
            else {
                plotOffset.left = plotOffset.right = plotOffset.top = plotOffset.bottom = 0;
                plotWidth = canvasWidth;
                plotHeight = canvasHeight;
            }
            
            for (axis in axes)
                setTransformationHelpers(axes[axis], options[axis]);

            if (options.grid.show)
                insertLabels();
            
            insertLegend();
        }
        
        function setRange(axis, axisOptions) {
            var min = +(axisOptions.min != null ? axisOptions.min : axis.datamin),
                max = +(axisOptions.max != null ? axisOptions.max : axis.datamax),
                delta = max - min;

            if (delta == 0.0) {
                // degenerate case
                var widen = max == 0 ? 1 : 0.01;

                if (axisOptions.min == null)
                    min -= widen;
                // alway widen max if we couldn't widen min to ensure we
                // don't fall into min == max which doesn't work
                if (axisOptions.max == null || axisOptions.min != null)
                    max += widen;
            }
            else {
                // consider autoscaling
                var margin = axisOptions.autoscaleMargin;
                if (margin != null) {
                    if (axisOptions.min == null) {
                        min -= delta * margin;
                        // make sure we don't go below zero if all values
                        // are positive
                        if (min < 0 && axis.datamin != null && axis.datamin >= 0)
                            min = 0;
                    }
                    if (axisOptions.max == null) {
                        max += delta * margin;
                        if (max > 0 && axis.datamax != null && axis.datamax <= 0)
                            max = 0;
                    }
                }
            }
            axis.min = min;
            axis.max = max;
        }

        function prepareTickGeneration(axis, axisOptions) {
            // estimate number of ticks
            var noTicks;
            if (typeof axisOptions.ticks == "number" && axisOptions.ticks > 0)
                noTicks = axisOptions.ticks;
            else if (axis == axes.xaxis || axis == axes.x2axis)
                 // heuristic based on the model a*sqrt(x) fitted to
                 // some reasonable data points
                noTicks = 0.3 * Math.sqrt(canvasWidth);
            else
                noTicks = 0.3 * Math.sqrt(canvasHeight);
            
            var delta = (axis.max - axis.min) / noTicks,
                size, generator, unit, formatter, i, magn, norm;

            if (axisOptions.mode == "time") {
                // pretty handling of time
                
                // map of app. size of time units in milliseconds
                var timeUnitSize = {
                    "second": 1000,
                    "minute": 60 * 1000,
                    "hour": 60 * 60 * 1000,
                    "day": 24 * 60 * 60 * 1000,
                    "month": 30 * 24 * 60 * 60 * 1000,
                    "year": 365.2425 * 24 * 60 * 60 * 1000
                };


                // the allowed tick sizes, after 1 year we use
                // an integer algorithm
                var spec = [
                    [1, "second"], [2, "second"], [5, "second"], [10, "second"],
                    [30, "second"], 
                    [1, "minute"], [2, "minute"], [5, "minute"], [10, "minute"],
                    [30, "minute"], 
                    [1, "hour"], [2, "hour"], [4, "hour"],
                    [8, "hour"], [12, "hour"],
                    [1, "day"], [2, "day"], [3, "day"],
                    [0.25, "month"], [0.5, "month"], [1, "month"],
                    [2, "month"], [3, "month"], [6, "month"],
                    [1, "year"]
                ];

                var minSize = 0;
                if (axisOptions.minTickSize != null) {
                    if (typeof axisOptions.tickSize == "number")
                        minSize = axisOptions.tickSize;
                    else
                        minSize = axisOptions.minTickSize[0] * timeUnitSize[axisOptions.minTickSize[1]];
                }

                for (i = 0; i < spec.length - 1; ++i)
                    if (delta < (spec[i][0] * timeUnitSize[spec[i][1]]
                                 + spec[i + 1][0] * timeUnitSize[spec[i + 1][1]]) / 2
                       && spec[i][0] * timeUnitSize[spec[i][1]] >= minSize)
                        break;
                size = spec[i][0];
                unit = spec[i][1];
                
                // special-case the possibility of several years
                if (unit == "year") {
                    magn = Math.pow(10, Math.floor(Math.log(delta / timeUnitSize.year) / Math.LN10));
                    norm = (delta / timeUnitSize.year) / magn;
                    if (norm < 1.5)
                        size = 1;
                    else if (norm < 3)
                        size = 2;
                    else if (norm < 7.5)
                        size = 5;
                    else
                        size = 10;

                    size *= magn;
                }

                if (axisOptions.tickSize) {
                    size = axisOptions.tickSize[0];
                    unit = axisOptions.tickSize[1];
                }
                
                generator = function(axis) {
                    var ticks = [],
                        tickSize = axis.tickSize[0], unit = axis.tickSize[1],
                        d = new Date(axis.min);
                    
                    var step = tickSize * timeUnitSize[unit];

                    if (unit == "second")
                        d.setUTCSeconds(floorInBase(d.getUTCSeconds(), tickSize));
                    if (unit == "minute")
                        d.setUTCMinutes(floorInBase(d.getUTCMinutes(), tickSize));
                    if (unit == "hour")
                        d.setUTCHours(floorInBase(d.getUTCHours(), tickSize));
                    if (unit == "month")
                        d.setUTCMonth(floorInBase(d.getUTCMonth(), tickSize));
                    if (unit == "year")
                        d.setUTCFullYear(floorInBase(d.getUTCFullYear(), tickSize));
                    
                    // reset smaller components
                    d.setUTCMilliseconds(0);
                    if (step >= timeUnitSize.minute)
                        d.setUTCSeconds(0);
                    if (step >= timeUnitSize.hour)
                        d.setUTCMinutes(0);
                    if (step >= timeUnitSize.day)
                        d.setUTCHours(0);
                    if (step >= timeUnitSize.day * 4)
                        d.setUTCDate(1);
                    if (step >= timeUnitSize.year)
                        d.setUTCMonth(0);


                    var carry = 0, v = Number.NaN, prev;
                    do {
                        prev = v;
                        v = d.getTime();
                        ticks.push({ v: v, label: axis.tickFormatter(v, axis) });
                        if (unit == "month") {
                            if (tickSize < 1) {
                                // a bit complicated - we'll divide the month
                                // up but we need to take care of fractions
                                // so we don't end up in the middle of a day
                                d.setUTCDate(1);
                                var start = d.getTime();
                                d.setUTCMonth(d.getUTCMonth() + 1);
                                var end = d.getTime();
                                d.setTime(v + carry * timeUnitSize.hour + (end - start) * tickSize);
                                carry = d.getUTCHours();
                                d.setUTCHours(0);
                            }
                            else
                                d.setUTCMonth(d.getUTCMonth() + tickSize);
                        }
                        else if (unit == "year") {
                            d.setUTCFullYear(d.getUTCFullYear() + tickSize);
                        }
                        else
                            d.setTime(v + step);
                    } while (v < axis.max && v != prev);

                    return ticks;
                };

                formatter = function (v, axis) {
                    var d = new Date(v);

                    // first check global format
                    if (axisOptions.timeformat != null)
                        return $.plot.formatDate(d, axisOptions.timeformat, axisOptions.monthNames);
                    
                    var t = axis.tickSize[0] * timeUnitSize[axis.tickSize[1]];
                    var span = axis.max - axis.min;
                    var suffix = (axisOptions.twelveHourClock) ? " %p" : "";
                    
                    if (t < timeUnitSize.minute)
                        fmt = "%h:%M:%S" + suffix;
                    else if (t < timeUnitSize.day) {
                        if (span < 2 * timeUnitSize.day)
                            fmt = "%h:%M" + suffix;
                        else
                            fmt = "%b %d %h:%M" + suffix;
                    }
                    else if (t < timeUnitSize.month)
                        fmt = "%b %d";
                    else if (t < timeUnitSize.year) {
                        if (span < timeUnitSize.year)
                            fmt = "%b";
                        else
                            fmt = "%b %y";
                    }
                    else
                        fmt = "%y";
                    
                    return $.plot.formatDate(d, fmt, axisOptions.monthNames);
                };
            }
            else {
                // pretty rounding of base-10 numbers
                var maxDec = axisOptions.tickDecimals;
                var dec = -Math.floor(Math.log(delta) / Math.LN10);
                if (maxDec != null && dec > maxDec)
                    dec = maxDec;

                magn = Math.pow(10, -dec);
                norm = delta / magn; // norm is between 1.0 and 10.0
                
                if (norm < 1.5)
                    size = 1;
                else if (norm < 3) {
                    size = 2;
                    // special case for 2.5, requires an extra decimal
                    if (norm > 2.25 && (maxDec == null || dec + 1 <= maxDec)) {
                        size = 2.5;
                        ++dec;
                    }
                }
                else if (norm < 7.5)
                    size = 5;
                else
                    size = 10;

                size *= magn;
                
                if (axisOptions.minTickSize != null && size < axisOptions.minTickSize)
                    size = axisOptions.minTickSize;

                if (axisOptions.tickSize != null)
                    size = axisOptions.tickSize;

                axis.tickDecimals = Math.max(0, (maxDec != null) ? maxDec : dec);

                generator = function (axis) {
                    var ticks = [];

                    // spew out all possible ticks
                    var start = floorInBase(axis.min, axis.tickSize),
                        i = 0, v = Number.NaN, prev;
                    do {
                        prev = v;
                        v = start + i * axis.tickSize;
                        ticks.push({ v: v, label: axis.tickFormatter(v, axis) });
                        ++i;
                    } while (v < axis.max && v != prev);
                    return ticks;
                };

                formatter = function (v, axis) {
                    return v.toFixed(axis.tickDecimals);
                };
            }

            axis.tickSize = unit ? [size, unit] : size;
            axis.tickGenerator = generator;
            if ($.isFunction(axisOptions.tickFormatter))
                axis.tickFormatter = function (v, axis) { return "" + axisOptions.tickFormatter(v, axis); };
            else
                axis.tickFormatter = formatter;
        }
        
        function setTicks(axis, axisOptions) {
            axis.ticks = [];

            if (!axis.used)
                return;
            
            if (axisOptions.ticks == null)
                axis.ticks = axis.tickGenerator(axis);
            else if (typeof axisOptions.ticks == "number") {
                if (axisOptions.ticks > 0)
                    axis.ticks = axis.tickGenerator(axis);
            }
            else if (axisOptions.ticks) {
                var ticks = axisOptions.ticks;

                if ($.isFunction(ticks))
                    // generate the ticks
                    ticks = ticks({ min: axis.min, max: axis.max });
                
                // clean up the user-supplied ticks, copy them over
                var i, v;
                for (i = 0; i < ticks.length; ++i) {
                    var label = null;
                    var t = ticks[i];
                    if (typeof t == "object") {
                        v = t[0];
                        if (t.length > 1)
                            label = t[1];
                    }
                    else
                        v = t;
                    if (label == null)
                        label = axis.tickFormatter(v, axis);
                    axis.ticks[i] = { v: v, label: label };
                }
            }

            if (axisOptions.autoscaleMargin != null && axis.ticks.length > 0) {
                // snap to ticks
                if (axisOptions.min == null)
                    axis.min = Math.min(axis.min, axis.ticks[0].v);
                if (axisOptions.max == null && axis.ticks.length > 1)
                    axis.max = Math.max(axis.max, axis.ticks[axis.ticks.length - 1].v);
            }
        }
      
        function draw() {
            ctx.clearRect(0, 0, canvasWidth, canvasHeight);

            var grid = options.grid;
            
            if (grid.show && !grid.aboveData)
                drawGrid();

            for (var i = 0; i < series.length; ++i)
                drawSeries(series[i]);

            executeHooks(hooks.draw, [ctx]);
            
            if (grid.show && grid.aboveData)
                drawGrid();
        }

        function extractRange(ranges, coord) {
            var firstAxis = coord + "axis",
                secondaryAxis = coord + "2axis",
                axis, from, to, reverse;

            if (ranges[firstAxis]) {
                axis = axes[firstAxis];
                from = ranges[firstAxis].from;
                to = ranges[firstAxis].to;
            }
            else if (ranges[secondaryAxis]) {
                axis = axes[secondaryAxis];
                from = ranges[secondaryAxis].from;
                to = ranges[secondaryAxis].to;
            }
            else {
                // backwards-compat stuff - to be removed in future
                axis = axes[firstAxis];
                from = ranges[coord + "1"];
                to = ranges[coord + "2"];
            }

            // auto-reverse as an added bonus
            if (from != null && to != null && from > to)
                return { from: to, to: from, axis: axis };
            
            return { from: from, to: to, axis: axis };
        }
        
        function drawGrid() {
            var i;
            
            ctx.save();
            ctx.translate(plotOffset.left, plotOffset.top);

            // draw background, if any
            if (options.grid.backgroundColor) {
                ctx.fillStyle = getColorOrGradient(options.grid.backgroundColor, plotHeight, 0, "rgba(255, 255, 255, 0)");
                ctx.fillRect(0, 0, plotWidth, plotHeight);
            }

            // draw markings
            var markings = options.grid.markings;
            if (markings) {
                if ($.isFunction(markings))
                    // xmin etc. are backwards-compatible, to be removed in future
                    markings = markings({ xmin: axes.xaxis.min, xmax: axes.xaxis.max, ymin: axes.yaxis.min, ymax: axes.yaxis.max, xaxis: axes.xaxis, yaxis: axes.yaxis, x2axis: axes.x2axis, y2axis: axes.y2axis });

                for (i = 0; i < markings.length; ++i) {
                    var m = markings[i],
                        xrange = extractRange(m, "x"),
                        yrange = extractRange(m, "y");

                    // fill in missing
                    if (xrange.from == null)
                        xrange.from = xrange.axis.min;
                    if (xrange.to == null)
                        xrange.to = xrange.axis.max;
                    if (yrange.from == null)
                        yrange.from = yrange.axis.min;
                    if (yrange.to == null)
                        yrange.to = yrange.axis.max;

                    // clip
                    if (xrange.to < xrange.axis.min || xrange.from > xrange.axis.max ||
                        yrange.to < yrange.axis.min || yrange.from > yrange.axis.max)
                        continue;

                    xrange.from = Math.max(xrange.from, xrange.axis.min);
                    xrange.to = Math.min(xrange.to, xrange.axis.max);
                    yrange.from = Math.max(yrange.from, yrange.axis.min);
                    yrange.to = Math.min(yrange.to, yrange.axis.max);

                    if (xrange.from == xrange.to && yrange.from == yrange.to)
                        continue;

                    // then draw
                    xrange.from = xrange.axis.p2c(xrange.from);
                    xrange.to = xrange.axis.p2c(xrange.to);
                    yrange.from = yrange.axis.p2c(yrange.from);
                    yrange.to = yrange.axis.p2c(yrange.to);
                    
                    if (xrange.from == xrange.to || yrange.from == yrange.to) {
                        // draw line
                        ctx.beginPath();
                        ctx.strokeStyle = m.color || options.grid.markingsColor;
                        ctx.lineWidth = m.lineWidth || options.grid.markingsLineWidth;
                        //ctx.moveTo(Math.floor(xrange.from), yrange.from);
                        //ctx.lineTo(Math.floor(xrange.to), yrange.to);
                        ctx.moveTo(xrange.from, yrange.from);
                        ctx.lineTo(xrange.to, yrange.to);
                        ctx.stroke();
                    }
                    else {
                        // fill area
                        ctx.fillStyle = m.color || options.grid.markingsColor;
                        ctx.fillRect(xrange.from, yrange.to,
                                     xrange.to - xrange.from,
                                     yrange.from - yrange.to);
                    }
                }
            }
            
            // draw the inner grid
            ctx.lineWidth = 1;
            ctx.strokeStyle = options.grid.tickColor;
            ctx.beginPath();
            var v, axis = axes.xaxis;
            for (i = 0; i < axis.ticks.length; ++i) {
                v = axis.ticks[i].v;
                if (v <= axis.min || v >= axes.xaxis.max)
                    continue;   // skip those lying on the axes

                ctx.moveTo(Math.floor(axis.p2c(v)) + ctx.lineWidth/2, 0);
                ctx.lineTo(Math.floor(axis.p2c(v)) + ctx.lineWidth/2, plotHeight);
            }

            axis = axes.yaxis;
            for (i = 0; i < axis.ticks.length; ++i) {
                v = axis.ticks[i].v;
                if (v <= axis.min || v >= axis.max)
                    continue;

                ctx.moveTo(0, Math.floor(axis.p2c(v)) + ctx.lineWidth/2);
                ctx.lineTo(plotWidth, Math.floor(axis.p2c(v)) + ctx.lineWidth/2);
            }

            axis = axes.x2axis;
            for (i = 0; i < axis.ticks.length; ++i) {
                v = axis.ticks[i].v;
                if (v <= axis.min || v >= axis.max)
                    continue;
    
                ctx.moveTo(Math.floor(axis.p2c(v)) + ctx.lineWidth/2, -5);
                ctx.lineTo(Math.floor(axis.p2c(v)) + ctx.lineWidth/2, 5);
            }

            axis = axes.y2axis;
            for (i = 0; i < axis.ticks.length; ++i) {
                v = axis.ticks[i].v;
                if (v <= axis.min || v >= axis.max)
                    continue;

                ctx.moveTo(plotWidth-5, Math.floor(axis.p2c(v)) + ctx.lineWidth/2);
                ctx.lineTo(plotWidth+5, Math.floor(axis.p2c(v)) + ctx.lineWidth/2);
            }
            
            ctx.stroke();
            
            if (options.grid.borderWidth) {
                // draw border
                var bw = options.grid.borderWidth;
                ctx.lineWidth = bw;
                ctx.strokeStyle = options.grid.borderColor;
                ctx.strokeRect(-bw/2, -bw/2, plotWidth + bw, plotHeight + bw);
            }

            ctx.restore();
        }

        function insertLabels() {
            placeholder.find(".tickLabels").remove();
            
            var html = ['<div class="tickLabels" style="font-size:smaller;color:' + options.grid.color + '">'];

            function addLabels(axis, labelGenerator) {
                for (var i = 0; i < axis.ticks.length; ++i) {
                    var tick = axis.ticks[i];
                    if (!tick.label || tick.v < axis.min || tick.v > axis.max)
                        continue;
                    html.push(labelGenerator(tick, axis));
                }
            }

            var margin = options.grid.labelMargin + options.grid.borderWidth;
            
            addLabels(axes.xaxis, function (tick, axis) {
                return '<div style="position:absolute;top:' + (plotOffset.top + plotHeight + margin) + 'px;left:' + Math.round(plotOffset.left + axis.p2c(tick.v) - axis.labelWidth/2) + 'px;width:' + axis.labelWidth + 'px;text-align:center" class="tickLabel">' + tick.label + "</div>";
            });
            
            
            addLabels(axes.yaxis, function (tick, axis) {
                return '<div style="position:absolute;top:' + Math.round(plotOffset.top + axis.p2c(tick.v) - axis.labelHeight/2) + 'px;right:' + (plotOffset.right + plotWidth + margin) + 'px;width:' + axis.labelWidth + 'px;text-align:right" class="tickLabel">' + tick.label + "</div>";
            });
            
            addLabels(axes.x2axis, function (tick, axis) {
                return '<div style="position:absolute;bottom:' + (plotOffset.bottom + plotHeight + margin) + 'px;left:' + Math.round(plotOffset.left + axis.p2c(tick.v) - axis.labelWidth/2) + 'px;width:' + axis.labelWidth + 'px;text-align:center" class="tickLabel">' + tick.label + "</div>";
            });
            
            addLabels(axes.y2axis, function (tick, axis) {
                return '<div style="position:absolute;top:' + Math.round(plotOffset.top + axis.p2c(tick.v) - axis.labelHeight/2) + 'px;left:' + (plotOffset.left + plotWidth + margin) +'px;width:' + axis.labelWidth + 'px;text-align:left" class="tickLabel">' + tick.label + "</div>";
            });

            html.push('</div>');
            
            placeholder.append(html.join(""));
        }

        function drawSeries(series) {
            if (series.lines.show)
                drawSeriesLines(series);
            if (series.bars.show)
                drawSeriesBars(series);
            if (series.points.show)
                drawSeriesPoints(series);
        }
        
        function drawSeriesLines(series) {
            function plotLine(datapoints, xoffset, yoffset, axisx, axisy) {
                var points = datapoints.points,
                    ps = datapoints.pointsize,
                    prevx = null, prevy = null;
                
                ctx.beginPath();
                for (var i = ps; i < points.length; i += ps) {
                    var x1 = points[i - ps], y1 = points[i - ps + 1],
                        x2 = points[i], y2 = points[i + 1];
                    
                    if (x1 == null || x2 == null)
                        continue;

                    // clip with ymin
                    if (y1 <= y2 && y1 < axisy.min) {
                        if (y2 < axisy.min)
                            continue;   // line segment is outside
                        // compute new intersection point
                        x1 = (axisy.min - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y1 = axisy.min;
                    }
                    else if (y2 <= y1 && y2 < axisy.min) {
                        if (y1 < axisy.min)
                            continue;
                        x2 = (axisy.min - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y2 = axisy.min;
                    }

                    // clip with ymax
                    if (y1 >= y2 && y1 > axisy.max) {
                        if (y2 > axisy.max)
                            continue;
                        x1 = (axisy.max - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y1 = axisy.max;
                    }
                    else if (y2 >= y1 && y2 > axisy.max) {
                        if (y1 > axisy.max)
                            continue;
                        x2 = (axisy.max - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y2 = axisy.max;
                    }

                    // clip with xmin
                    if (x1 <= x2 && x1 < axisx.min) {
                        if (x2 < axisx.min)
                            continue;
                        y1 = (axisx.min - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x1 = axisx.min;
                    }
                    else if (x2 <= x1 && x2 < axisx.min) {
                        if (x1 < axisx.min)
                            continue;
                        y2 = (axisx.min - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x2 = axisx.min;
                    }

                    // clip with xmax
                    if (x1 >= x2 && x1 > axisx.max) {
                        if (x2 > axisx.max)
                            continue;
                        y1 = (axisx.max - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x1 = axisx.max;
                    }
                    else if (x2 >= x1 && x2 > axisx.max) {
                        if (x1 > axisx.max)
                            continue;
                        y2 = (axisx.max - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x2 = axisx.max;
                    }

                    if (x1 != prevx || y1 != prevy)
                        ctx.moveTo(axisx.p2c(x1) + xoffset, axisy.p2c(y1) + yoffset);
                    
                    prevx = x2;
                    prevy = y2;
                    ctx.lineTo(axisx.p2c(x2) + xoffset, axisy.p2c(y2) + yoffset);
                }
                ctx.stroke();
            }

            function plotLineArea(datapoints, axisx, axisy) {
                var points = datapoints.points,
                    ps = datapoints.pointsize,
                    bottom = Math.min(Math.max(0, axisy.min), axisy.max),
                    top, lastX = 0, areaOpen = false;
                
                for (var i = ps; i < points.length; i += ps) {
                    var x1 = points[i - ps], y1 = points[i - ps + 1],
                        x2 = points[i], y2 = points[i + 1];
                    
                    if (areaOpen && x1 != null && x2 == null) {
                        // close area
                        ctx.lineTo(axisx.p2c(lastX), axisy.p2c(bottom));
                        ctx.fill();
                        areaOpen = false;
                        continue;
                    }

                    if (x1 == null || x2 == null)
                        continue;

                    // clip x values
                    
                    // clip with xmin
                    if (x1 <= x2 && x1 < axisx.min) {
                        if (x2 < axisx.min)
                            continue;
                        y1 = (axisx.min - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x1 = axisx.min;
                    }
                    else if (x2 <= x1 && x2 < axisx.min) {
                        if (x1 < axisx.min)
                            continue;
                        y2 = (axisx.min - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x2 = axisx.min;
                    }

                    // clip with xmax
                    if (x1 >= x2 && x1 > axisx.max) {
                        if (x2 > axisx.max)
                            continue;
                        y1 = (axisx.max - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x1 = axisx.max;
                    }
                    else if (x2 >= x1 && x2 > axisx.max) {
                        if (x1 > axisx.max)
                            continue;
                        y2 = (axisx.max - x1) / (x2 - x1) * (y2 - y1) + y1;
                        x2 = axisx.max;
                    }

                    if (!areaOpen) {
                        // open area
                        ctx.beginPath();
                        ctx.moveTo(axisx.p2c(x1), axisy.p2c(bottom));
                        areaOpen = true;
                    }
                    
                    // now first check the case where both is outside
                    if (y1 >= axisy.max && y2 >= axisy.max) {
                        ctx.lineTo(axisx.p2c(x1), axisy.p2c(axisy.max));
                        ctx.lineTo(axisx.p2c(x2), axisy.p2c(axisy.max));
                        lastX = x2;
                        continue;
                    }
                    else if (y1 <= axisy.min && y2 <= axisy.min) {
                        ctx.lineTo(axisx.p2c(x1), axisy.p2c(axisy.min));
                        ctx.lineTo(axisx.p2c(x2), axisy.p2c(axisy.min));
                        lastX = x2;
                        continue;
                    }
                    
                    // else it's a bit more complicated, there might
                    // be two rectangles and two triangles we need to fill
                    // in; to find these keep track of the current x values
                    var x1old = x1, x2old = x2;

                    // and clip the y values, without shortcutting
                    
                    // clip with ymin
                    if (y1 <= y2 && y1 < axisy.min && y2 >= axisy.min) {
                        x1 = (axisy.min - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y1 = axisy.min;
                    }
                    else if (y2 <= y1 && y2 < axisy.min && y1 >= axisy.min) {
                        x2 = (axisy.min - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y2 = axisy.min;
                    }

                    // clip with ymax
                    if (y1 >= y2 && y1 > axisy.max && y2 <= axisy.max) {
                        x1 = (axisy.max - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y1 = axisy.max;
                    }
                    else if (y2 >= y1 && y2 > axisy.max && y1 <= axisy.max) {
                        x2 = (axisy.max - y1) / (y2 - y1) * (x2 - x1) + x1;
                        y2 = axisy.max;
                    }


                    // if the x value was changed we got a rectangle
                    // to fill
                    if (x1 != x1old) {
                        if (y1 <= axisy.min)
                            top = axisy.min;
                        else
                            top = axisy.max;
                        
                        ctx.lineTo(axisx.p2c(x1old), axisy.p2c(top));
                        ctx.lineTo(axisx.p2c(x1), axisy.p2c(top));
                    }
                    
                    // fill the triangles
                    ctx.lineTo(axisx.p2c(x1), axisy.p2c(y1));
                    ctx.lineTo(axisx.p2c(x2), axisy.p2c(y2));

                    // fill the other rectangle if it's there
                    if (x2 != x2old) {
                        if (y2 <= axisy.min)
                            top = axisy.min;
                        else
                            top = axisy.max;
                        
                        ctx.lineTo(axisx.p2c(x2), axisy.p2c(top));
                        ctx.lineTo(axisx.p2c(x2old), axisy.p2c(top));
                    }

                    lastX = Math.max(x2, x2old);
                }

                if (areaOpen) {
                    ctx.lineTo(axisx.p2c(lastX), axisy.p2c(bottom));
                    ctx.fill();
                }
            }
            
            ctx.save();
            ctx.translate(plotOffset.left, plotOffset.top);
            ctx.lineJoin = "round";

            var lw = series.lines.lineWidth,
                sw = series.shadowSize;
            // FIXME: consider another form of shadow when filling is turned on
            if (lw > 0 && sw > 0) {
                // draw shadow as a thick and thin line with transparency
                ctx.lineWidth = sw;
                ctx.strokeStyle = "rgba(0,0,0,0.1)";
                // position shadow at angle from the mid of line
                var angle = Math.PI/18;
                plotLine(series.datapoints, Math.sin(angle) * (lw/2 + sw/2), Math.cos(angle) * (lw/2 + sw/2), series.xaxis, series.yaxis);
                ctx.lineWidth = sw/2;
                plotLine(series.datapoints, Math.sin(angle) * (lw/2 + sw/4), Math.cos(angle) * (lw/2 + sw/4), series.xaxis, series.yaxis);
            }

            ctx.lineWidth = lw;
            ctx.strokeStyle = series.color;
            var fillStyle = getFillStyle(series.lines, series.color, 0, plotHeight);
            if (fillStyle) {
                ctx.fillStyle = fillStyle;
                plotLineArea(series.datapoints, series.xaxis, series.yaxis);
            }

            if (lw > 0)
                plotLine(series.datapoints, 0, 0, series.xaxis, series.yaxis);
            ctx.restore();
        }

        function drawSeriesPoints(series) {
            function plotPoints(datapoints, radius, fillStyle, offset, circumference, axisx, axisy) {
                var points = datapoints.points, ps = datapoints.pointsize;
                
                for (var i = 0; i < points.length; i += ps) {
                    var x = points[i], y = points[i + 1];
                    if (x == null || x < axisx.min || x > axisx.max || y < axisy.min || y > axisy.max)
                        continue;
                    
                    ctx.beginPath();
                    ctx.arc(axisx.p2c(x), axisy.p2c(y) + offset, radius, 0, circumference, false);
                    if (fillStyle) {
                        ctx.fillStyle = fillStyle;
                        ctx.fill();
                    }
                    ctx.stroke();
                }
            }
            
            ctx.save();
            ctx.translate(plotOffset.left, plotOffset.top);

            var lw = series.lines.lineWidth,
                sw = series.shadowSize,
                radius = series.points.radius;
            if (lw > 0 && sw > 0) {
                // draw shadow in two steps
                var w = sw / 2;
                ctx.lineWidth = w;
                ctx.strokeStyle = "rgba(0,0,0,0.1)";
                plotPoints(series.datapoints, radius, null, w + w/2, Math.PI,
                           series.xaxis, series.yaxis);

                ctx.strokeStyle = "rgba(0,0,0,0.2)";
                plotPoints(series.datapoints, radius, null, w/2, Math.PI,
                           series.xaxis, series.yaxis);
            }

            ctx.lineWidth = lw;
            ctx.strokeStyle = series.color;
            plotPoints(series.datapoints, radius,
                       getFillStyle(series.points, series.color), 0, 2 * Math.PI,
                       series.xaxis, series.yaxis);
            ctx.restore();
        }

        function drawBar(x, y, b, barLeft, barRight, offset, fillStyleCallback, axisx, axisy, c, horizontal) {
            var left, right, bottom, top,
                drawLeft, drawRight, drawTop, drawBottom,
                tmp;

            if (horizontal) {
                drawBottom = drawRight = drawTop = true;
                drawLeft = false;
                left = b;
                right = x;
                top = y + barLeft;
                bottom = y + barRight;

                // account for negative bars
                if (right < left) {
                    tmp = right;
                    right = left;
                    left = tmp;
                    drawLeft = true;
                    drawRight = false;
                }
            }
            else {
                drawLeft = drawRight = drawTop = true;
                drawBottom = false;
                left = x + barLeft;
                right = x + barRight;
                bottom = b;
                top = y;

                // account for negative bars
                if (top < bottom) {
                    tmp = top;
                    top = bottom;
                    bottom = tmp;
                    drawBottom = true;
                    drawTop = false;
                }
            }
           
            // clip
            if (right < axisx.min || left > axisx.max ||
                top < axisy.min || bottom > axisy.max)
                return;
            
            if (left < axisx.min) {
                left = axisx.min;
                drawLeft = false;
            }

            if (right > axisx.max) {
                right = axisx.max;
                drawRight = false;
            }

            if (bottom < axisy.min) {
                bottom = axisy.min;
                drawBottom = false;
            }
            
            if (top > axisy.max) {
                top = axisy.max;
                drawTop = false;
            }

            left = axisx.p2c(left);
            bottom = axisy.p2c(bottom);
            right = axisx.p2c(right);
            top = axisy.p2c(top);
            
            // fill the bar
            if (fillStyleCallback) {
                c.beginPath();
                c.moveTo(left, bottom);
                c.lineTo(left, top);
                c.lineTo(right, top);
                c.lineTo(right, bottom);
                c.fillStyle = fillStyleCallback(bottom, top);
                c.fill();
            }

            // draw outline
            if (drawLeft || drawRight || drawTop || drawBottom) {
                c.beginPath();

                // FIXME: inline moveTo is buggy with excanvas
                c.moveTo(left, bottom + offset);
                if (drawLeft)
                    c.lineTo(left, top + offset);
                else
                    c.moveTo(left, top + offset);
                if (drawTop)
                    c.lineTo(right, top + offset);
                else
                    c.moveTo(right, top + offset);
                if (drawRight)
                    c.lineTo(right, bottom + offset);
                else
                    c.moveTo(right, bottom + offset);
                if (drawBottom)
                    c.lineTo(left, bottom + offset);
                else
                    c.moveTo(left, bottom + offset);
                c.stroke();
            }
        }
        
        function drawSeriesBars(series) {
            function plotBars(datapoints, barLeft, barRight, offset, fillStyleCallback, axisx, axisy) {
                var points = datapoints.points, ps = datapoints.pointsize;
                
                for (var i = 0; i < points.length; i += ps) {
                    if (points[i] == null)
                        continue;
                    drawBar(points[i], points[i + 1], points[i + 2], barLeft, barRight, offset, fillStyleCallback, axisx, axisy, ctx, series.bars.horizontal);
                }
            }

            ctx.save();
            ctx.translate(plotOffset.left, plotOffset.top);

            // FIXME: figure out a way to add shadows (for instance along the right edge)
            ctx.lineWidth = series.bars.lineWidth;
            ctx.strokeStyle = series.color;
            var barLeft = series.bars.align == "left" ? 0 : -series.bars.barWidth/2;
            var fillStyleCallback = series.bars.fill ? function (bottom, top) { return getFillStyle(series.bars, series.color, bottom, top); } : null;
            plotBars(series.datapoints, barLeft, barLeft + series.bars.barWidth, 0, fillStyleCallback, series.xaxis, series.yaxis);
            ctx.restore();
        }

        function getFillStyle(filloptions, seriesColor, bottom, top) {
            var fill = filloptions.fill;
            if (!fill)
                return null;

            if (filloptions.fillColor)
                return getColorOrGradient(filloptions.fillColor, bottom, top, seriesColor);
            
            var c = $.color.parse(seriesColor);
            c.a = typeof fill == "number" ? fill : 0.4;
            c.normalize();
            return c.toString();
        }
        
        function insertLegend() {
            placeholder.find(".legend").remove();

            if (!options.legend.show)
                return;
            
            var fragments = [], rowStarted = false,
                lf = options.legend.labelFormatter, s, label;
            for (i = 0; i < series.length; ++i) {
                s = series[i];
                label = s.label;
                if (!label)
                    continue;
                
                if (i % options.legend.noColumns == 0) {
                    if (rowStarted)
                        fragments.push('</tr>');
                    fragments.push('<tr>');
                    rowStarted = true;
                }

                if (lf)
                    label = lf(label, s);
                
                fragments.push(
                    '<td class="legendColorBox"><div style="border:1px solid ' + options.legend.labelBoxBorderColor + ';padding:1px"><div style="width:4px;height:0;border:5px solid ' + s.color + ';overflow:hidden"></div></div></td>' +
                    '<td class="legendLabel">' + label + '</td>');
            }
            if (rowStarted)
                fragments.push('</tr>');
            
            if (fragments.length == 0)
                return;

            var table = '<table style="font-size:smaller;color:' + options.grid.color + '">' + fragments.join("") + '</table>';
            if (options.legend.container != null)
                $(options.legend.container).html(table);
            else {
                var pos = "",
                    p = options.legend.position,
                    m = options.legend.margin;
                if (m[0] == null)
                    m = [m, m];
                if (p.charAt(0) == "n")
                    pos += 'top:' + (m[1] + plotOffset.top) + 'px;';
                else if (p.charAt(0) == "s")
                    pos += 'bottom:' + (m[1] + plotOffset.bottom) + 'px;';
                if (p.charAt(1) == "e")
                    pos += 'right:' + (m[0] + plotOffset.right) + 'px;';
                else if (p.charAt(1) == "w")
                    pos += 'left:' + (m[0] + plotOffset.left) + 'px;';
                var legend = $('<div class="legend">' + table.replace('style="', 'style="position:absolute;' + pos +';') + '</div>').appendTo(placeholder);
                if (options.legend.backgroundOpacity != 0.0) {
                    // put in the transparent background
                    // separately to avoid blended labels and
                    // label boxes
                    var c = options.legend.backgroundColor;
                    if (c == null) {
                        c = options.grid.backgroundColor;
                        if (c && typeof c == "string")
                            c = $.color.parse(c);
                        else
                            c = $.color.extract(legend, 'background-color');
                        c.a = 1;
                        c = c.toString();
                    }
                    var div = legend.children();
                    $('<div style="position:absolute;width:' + div.width() + 'px;height:' + div.height() + 'px;' + pos +'background-color:' + c + ';"> </div>').prependTo(legend).css('opacity', options.legend.backgroundOpacity);
                }
            }
        }


        // interactive features
        
        var highlights = [],
            redrawTimeout = null;
        
        // returns the data item the mouse is over, or null if none is found
        function findNearbyItem(mouseX, mouseY, seriesFilter) {
            var maxDistance = options.grid.mouseActiveRadius,
                smallestDistance = maxDistance * maxDistance + 1,
                item = null, foundPoint = false, i, j;

            for (i = 0; i < series.length; ++i) {
                if (!seriesFilter(series[i]))
                    continue;
                
                var s = series[i],
                    axisx = s.xaxis,
                    axisy = s.yaxis,
                    points = s.datapoints.points,
                    ps = s.datapoints.pointsize,
                    mx = axisx.c2p(mouseX), // precompute some stuff to make the loop faster
                    my = axisy.c2p(mouseY),
                    maxx = maxDistance / axisx.scale,
                    maxy = maxDistance / axisy.scale;

                if (s.lines.show || s.points.show) {
                    for (j = 0; j < points.length; j += ps) {
                        var x = points[j], y = points[j + 1];
                        if (x == null)
                            continue;
                        
                        // For points and lines, the cursor must be within a
                        // certain distance to the data point
                        if (x - mx > maxx || x - mx < -maxx ||
                            y - my > maxy || y - my < -maxy)
                            continue;

                        // We have to calculate distances in pixels, not in
                        // data units, because the scales of the axes may be different
                        var dx = Math.abs(axisx.p2c(x) - mouseX),
                            dy = Math.abs(axisy.p2c(y) - mouseY),
                            dist = dx * dx + dy * dy; // we save the sqrt

                        // use <= to ensure last point takes precedence
                        // (last generally means on top of)
                        if (dist <= smallestDistance) {
                            smallestDistance = dist;
                            item = [i, j / ps];
                        }
                    }
                }
                    
                if (s.bars.show && !item) { // no other point can be nearby
                    var barLeft = s.bars.align == "left" ? 0 : -s.bars.barWidth/2,
                        barRight = barLeft + s.bars.barWidth;
                    
                    for (j = 0; j < points.length; j += ps) {
                        var x = points[j], y = points[j + 1], b = points[j + 2];
                        if (x == null)
                            continue;
  
                        // for a bar graph, the cursor must be inside the bar
                        if (series[i].bars.horizontal ? 
                            (mx <= Math.max(b, x) && mx >= Math.min(b, x) && 
                             my >= y + barLeft && my <= y + barRight) :
                            (mx >= x + barLeft && mx <= x + barRight &&
                             my >= Math.min(b, y) && my <= Math.max(b, y)))
                                item = [i, j / ps];
                    }
                }
            }

            if (item) {
                i = item[0];
                j = item[1];
                ps = series[i].datapoints.pointsize;
                
                return { datapoint: series[i].datapoints.points.slice(j * ps, (j + 1) * ps),
                         dataIndex: j,
                         series: series[i],
                         seriesIndex: i };
            }
            
            return null;
        }

        function onMouseMove(e) {
            if (options.grid.hoverable)
                triggerClickHoverEvent("plothover", e,
                                       function (s) { return s["hoverable"] != false; });
        }
        
        function onClick(e) {
            triggerClickHoverEvent("plotclick", e,
                                   function (s) { return s["clickable"] != false; });
        }

        // trigger click or hover event (they send the same parameters
        // so we share their code)
        function triggerClickHoverEvent(eventname, event, seriesFilter) {
            var offset = eventHolder.offset(),
                pos = { pageX: event.pageX, pageY: event.pageY },
                canvasX = event.pageX - offset.left - plotOffset.left,
                canvasY = event.pageY - offset.top - plotOffset.top;

            if (axes.xaxis.used)
                pos.x = axes.xaxis.c2p(canvasX);
            if (axes.yaxis.used)
                pos.y = axes.yaxis.c2p(canvasY);
            if (axes.x2axis.used)
                pos.x2 = axes.x2axis.c2p(canvasX);
            if (axes.y2axis.used)
                pos.y2 = axes.y2axis.c2p(canvasY);

            var item = findNearbyItem(canvasX, canvasY, seriesFilter);

            if (item) {
                // fill in mouse pos for any listeners out there
                item.pageX = parseInt(item.series.xaxis.p2c(item.datapoint[0]) + offset.left + plotOffset.left);
                item.pageY = parseInt(item.series.yaxis.p2c(item.datapoint[1]) + offset.top + plotOffset.top);
            }

            if (options.grid.autoHighlight) {
                // clear auto-highlights
                for (var i = 0; i < highlights.length; ++i) {
                    var h = highlights[i];
                    if (h.auto == eventname &&
                        !(item && h.series == item.series && h.point == item.datapoint))
                        unhighlight(h.series, h.point);
                }
                
                if (item)
                    highlight(item.series, item.datapoint, eventname);
            }
            
            placeholder.trigger(eventname, [ pos, item ]);
        }

        function triggerRedrawOverlay() {
            if (!redrawTimeout)
                redrawTimeout = setTimeout(drawOverlay, 30);
        }

        function drawOverlay() {
            redrawTimeout = null;

            // draw highlights
            octx.save();
            octx.clearRect(0, 0, canvasWidth, canvasHeight);
            octx.translate(plotOffset.left, plotOffset.top);
            
            var i, hi;
            for (i = 0; i < highlights.length; ++i) {
                hi = highlights[i];

                if (hi.series.bars.show)
                    drawBarHighlight(hi.series, hi.point);
                else
                    drawPointHighlight(hi.series, hi.point);
            }
            octx.restore();
            
            executeHooks(hooks.drawOverlay, [octx]);
        }
        
        function highlight(s, point, auto) {
            if (typeof s == "number")
                s = series[s];

            if (typeof point == "number")
                point = s.data[point];

            var i = indexOfHighlight(s, point);
            if (i == -1) {
                highlights.push({ series: s, point: point, auto: auto });

                triggerRedrawOverlay();
            }
            else if (!auto)
                highlights[i].auto = false;
        }
            
        function unhighlight(s, point) {
            if (s == null && point == null) {
                highlights = [];
                triggerRedrawOverlay();
            }
            
            if (typeof s == "number")
                s = series[s];

            if (typeof point == "number")
                point = s.data[point];

            var i = indexOfHighlight(s, point);
            if (i != -1) {
                highlights.splice(i, 1);

                triggerRedrawOverlay();
            }
        }
        
        function indexOfHighlight(s, p) {
            for (var i = 0; i < highlights.length; ++i) {
                var h = highlights[i];
                if (h.series == s && h.point[0] == p[0]
                    && h.point[1] == p[1])
                    return i;
            }
            return -1;
        }
        
        function drawPointHighlight(series, point) {
            var x = point[0], y = point[1],
                axisx = series.xaxis, axisy = series.yaxis;
            
            if (x < axisx.min || x > axisx.max || y < axisy.min || y > axisy.max)
                return;
            
            var pointRadius = series.points.radius + series.points.lineWidth / 2;
            octx.lineWidth = pointRadius;
            octx.strokeStyle = $.color.parse(series.color).scale('a', 0.5).toString();
            var radius = 1.5 * pointRadius;
            octx.beginPath();
            octx.arc(axisx.p2c(x), axisy.p2c(y), radius, 0, 2 * Math.PI, false);
            octx.stroke();
        }

        function drawBarHighlight(series, point) {
            octx.lineWidth = series.bars.lineWidth;
            octx.strokeStyle = $.color.parse(series.color).scale('a', 0.5).toString();
            var fillStyle = $.color.parse(series.color).scale('a', 0.5).toString();
            var barLeft = series.bars.align == "left" ? 0 : -series.bars.barWidth/2;
            drawBar(point[0], point[1], point[2] || 0, barLeft, barLeft + series.bars.barWidth,
                    0, function () { return fillStyle; }, series.xaxis, series.yaxis, octx, series.bars.horizontal);
        }

        function getColorOrGradient(spec, bottom, top, defaultColor) {
            if (typeof spec == "string")
                return spec;
            else {
                // assume this is a gradient spec; IE currently only
                // supports a simple vertical gradient properly, so that's
                // what we support too
                var gradient = ctx.createLinearGradient(0, top, 0, bottom);
                
                for (var i = 0, l = spec.colors.length; i < l; ++i) {
                    var c = spec.colors[i];
                    if (typeof c != "string") {
                        c = $.color.parse(defaultColor).scale('rgb', c.brightness);
                        c.a *= c.opacity;
                        c = c.toString();
                    }
                    gradient.addColorStop(i / (l - 1), c);
                }
                
                return gradient;
            }
        }
    }

    $.plot = function(placeholder, data, options) {
        var plot = new Plot($(placeholder), data, options, $.plot.plugins);
        /*var t0 = new Date();
        var t1 = new Date();
        var tstr = "time used (msecs): " + (t1.getTime() - t0.getTime())
        if (window.console)
            console.log(tstr);
        else
            alert(tstr);*/
        return plot;
    };

    $.plot.plugins = [];

    // returns a string with the date d formatted according to fmt
    $.plot.formatDate = function(d, fmt, monthNames) {
        var leftPad = function(n) {
            n = "" + n;
            return n.length == 1 ? "0" + n : n;
        };
        
        var r = [];
        var escape = false;
        var hours = d.getUTCHours();
        var isAM = hours < 12;
        if (monthNames == null)
            monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

        if (fmt.search(/%p|%P/) != -1) {
            if (hours > 12) {
                hours = hours - 12;
            } else if (hours == 0) {
                hours = 12;
            }
        }
        for (var i = 0; i < fmt.length; ++i) {
            var c = fmt.charAt(i);
            
            if (escape) {
                switch (c) {
                case 'h': c = "" + hours; break;
                case 'H': c = leftPad(hours); break;
                case 'M': c = leftPad(d.getUTCMinutes()); break;
                case 'S': c = leftPad(d.getUTCSeconds()); break;
                case 'd': c = "" + d.getUTCDate(); break;
                case 'm': c = "" + (d.getUTCMonth() + 1); break;
                case 'y': c = "" + d.getUTCFullYear(); break;
                case 'b': c = "" + monthNames[d.getUTCMonth()]; break;
                case 'p': c = (isAM) ? ("" + "am") : ("" + "pm"); break;
                case 'P': c = (isAM) ? ("" + "AM") : ("" + "PM"); break;
                }
                r.push(c);
                escape = false;
            }
            else {
                if (c == "%")
                    escape = true;
                else
                    r.push(c);
            }
        }
        return r.join("");
    };
    
    // round to nearby lower multiple of base
    function floorInBase(n, base) {
        return base * Math.floor(n / base);
    }
    
})(jQuery);


/*
Flot plugin for selecting regions.

The plugin defines the following options:

  selection: {
    mode: null or "x" or "y" or "xy",
    color: color
  }

You enable selection support by setting the mode to one of "x", "y" or
"xy". In "x" mode, the user will only be able to specify the x range,
similarly for "y" mode. For "xy", the selection becomes a rectangle
where both ranges can be specified. "color" is color of the selection.

When selection support is enabled, a "plotselected" event will be emitted
on the DOM element you passed into the plot function. The event
handler gets one extra parameter with the ranges selected on the axes,
like this:

  placeholder.bind("plotselected", function(event, ranges) {
    alert("You selected " + ranges.xaxis.from + " to " + ranges.xaxis.to)
    // similar for yaxis, secondary axes are in x2axis
    // and y2axis if present
  });

The "plotselected" event is only fired when the user has finished
making the selection. A "plotselecting" event is fired during the
process with the same parameters as the "plotselected" event, in case
you want to know what's happening while it's happening,

A "plotunselected" event with no arguments is emitted when the user
clicks the mouse to remove the selection.

The plugin allso adds the following methods to the plot object:

- setSelection(ranges, preventEvent)

  Set the selection rectangle. The passed in ranges is on the same
  form as returned in the "plotselected" event. If the selection
  mode is "x", you should put in either an xaxis (or x2axis) object,
  if the mode is "y" you need to put in an yaxis (or y2axis) object
  and both xaxis/x2axis and yaxis/y2axis if the selection mode is
  "xy", like this:

    setSelection({ xaxis: { from: 0, to: 10 }, yaxis: { from: 40, to: 60 } });

  setSelection will trigger the "plotselected" event when called. If
  you don't want that to happen, e.g. if you're inside a
  "plotselected" handler, pass true as the second parameter.
  
- clearSelection(preventEvent)

  Clear the selection rectangle. Pass in true to avoid getting a
  "plotunselected" event.

- getSelection()

  Returns the current selection in the same format as the
  "plotselected" event. If there's currently no selection, the
  function returns null.

*/

(function ($) {
    function init(plot) {
        var selection = {
                first: { x: -1, y: -1}, second: { x: -1, y: -1},
                show: false,
                active: false
            };

        // FIXME: The drag handling implemented here should be
        // abstracted out, there's some similar code from a library in
        // the navigation plugin, this should be massaged a bit to fit
        // the Flot cases here better and reused. Doing this would
        // make this plugin much slimmer.
        var savedhandlers = {};

        function onMouseMove(e) {
            if (selection.active) {
                plot.getPlaceholder().trigger("plotselecting", [ getSelection() ]);

                updateSelection(e);
            }
        }

        function onMouseDown(e) {
            if (e.which != 1)  // only accept left-click
                return;
            
            // cancel out any text selections
            document.body.focus();

            // prevent text selection and drag in old-school browsers
            if (document.onselectstart !== undefined && savedhandlers.onselectstart == null) {
                savedhandlers.onselectstart = document.onselectstart;
                document.onselectstart = function () { return false; };
            }
            if (document.ondrag !== undefined && savedhandlers.ondrag == null) {
                savedhandlers.ondrag = document.ondrag;
                document.ondrag = function () { return false; };
            }

            setSelectionPos(selection.first, e);

            selection.active = true;
            
            $(document).one("mouseup", onMouseUp);
        }

        function onMouseUp(e) {
            // revert drag stuff for old-school browsers
            if (document.onselectstart !== undefined)
                document.onselectstart = savedhandlers.onselectstart;
            if (document.ondrag !== undefined)
                document.ondrag = savedhandlers.ondrag;

            // no more draggy-dee-drag
            selection.active = false;
            updateSelection(e);

            if (selectionIsSane())
                triggerSelectedEvent();
            else {
                // this counts as a clear
                plot.getPlaceholder().trigger("plotunselected", [ ]);
                plot.getPlaceholder().trigger("plotselecting", [ null ]);
            }

            return false;
        }

        function getSelection() {
            if (!selectionIsSane())
                return null;

            var x1 = Math.min(selection.first.x, selection.second.x),
                x2 = Math.max(selection.first.x, selection.second.x),
                y1 = Math.max(selection.first.y, selection.second.y),
                y2 = Math.min(selection.first.y, selection.second.y);

            var r = {};
            var axes = plot.getAxes();
            if (axes.xaxis.used)
                r.xaxis = { from: axes.xaxis.c2p(x1), to: axes.xaxis.c2p(x2) };
            if (axes.x2axis.used)
                r.x2axis = { from: axes.x2axis.c2p(x1), to: axes.x2axis.c2p(x2) };
            if (axes.yaxis.used)
                r.yaxis = { from: axes.yaxis.c2p(y1), to: axes.yaxis.c2p(y2) };
            if (axes.y2axis.used)
                r.y2axis = { from: axes.y2axis.c2p(y1), to: axes.y2axis.c2p(y2) };
            return r;
        }

        function triggerSelectedEvent() {
            var r = getSelection();

            plot.getPlaceholder().trigger("plotselected", [ r ]);

            // backwards-compat stuff, to be removed in future
            var axes = plot.getAxes();
            if (axes.xaxis.used && axes.yaxis.used)
                plot.getPlaceholder().trigger("selected", [ { x1: r.xaxis.from, y1: r.yaxis.from, x2: r.xaxis.to, y2: r.yaxis.to } ]);
        }

        function clamp(min, value, max) {
            return value < min? min: (value > max? max: value);
        }

        function setSelectionPos(pos, e) {
            var o = plot.getOptions();
            var offset = plot.getPlaceholder().offset();
            var plotOffset = plot.getPlotOffset();
            pos.x = clamp(0, e.pageX - offset.left - plotOffset.left, plot.width());
            pos.y = clamp(0, e.pageY - offset.top - plotOffset.top, plot.height());

            if (o.selection.mode == "y")
                pos.x = pos == selection.first? 0: plot.width();

            if (o.selection.mode == "x")
                pos.y = pos == selection.first? 0: plot.height();
        }

        function updateSelection(pos) {
            if (pos.pageX == null)
                return;

            setSelectionPos(selection.second, pos);
            if (selectionIsSane()) {
                selection.show = true;
                plot.triggerRedrawOverlay();
            }
            else
                clearSelection(true);
        }

        function clearSelection(preventEvent) {
            if (selection.show) {
                selection.show = false;
                plot.triggerRedrawOverlay();
                if (!preventEvent)
                    plot.getPlaceholder().trigger("plotunselected", [ ]);
            }
        }

        function setSelection(ranges, preventEvent) {
            var axis, range, axes = plot.getAxes();
            var o = plot.getOptions();

            if (o.selection.mode == "y") {
                selection.first.x = 0;
                selection.second.x = plot.width();
            }
            else {
                axis = ranges["xaxis"]? axes["xaxis"]: (ranges["x2axis"]? axes["x2axis"]: axes["xaxis"]);
                range = ranges["xaxis"] || ranges["x2axis"] || { from:ranges["x1"], to:ranges["x2"] }
                selection.first.x = axis.p2c(Math.min(range.from, range.to));
                selection.second.x = axis.p2c(Math.max(range.from, range.to));
            }

            if (o.selection.mode == "x") {
                selection.first.y = 0;
                selection.second.y = plot.height();
            }
            else {
                axis = ranges["yaxis"]? axes["yaxis"]: (ranges["y2axis"]? axes["y2axis"]: axes["yaxis"]);
                range = ranges["yaxis"] || ranges["y2axis"] || { from:ranges["y1"], to:ranges["y2"] }
                selection.first.y = axis.p2c(Math.min(range.from, range.to));
                selection.second.y = axis.p2c(Math.max(range.from, range.to));
            }

            selection.show = true;
            plot.triggerRedrawOverlay();
            if (!preventEvent)
                triggerSelectedEvent();
        }

        function selectionIsSane() {
            var minSize = 5;
            return Math.abs(selection.second.x - selection.first.x) >= minSize &&
                Math.abs(selection.second.y - selection.first.y) >= minSize;
        }

        plot.clearSelection = clearSelection;
        plot.setSelection = setSelection;
        plot.getSelection = getSelection;

        plot.hooks.bindEvents.push(function(plot, eventHolder) {
            var o = plot.getOptions();
            if (o.selection.mode != null)
                eventHolder.mousemove(onMouseMove);

            if (o.selection.mode != null)
                eventHolder.mousedown(onMouseDown);
        });


        plot.hooks.drawOverlay.push(function (plot, ctx) {
            // draw selection
            if (selection.show && selectionIsSane()) {
                var plotOffset = plot.getPlotOffset();
                var o = plot.getOptions();

                ctx.save();
                ctx.translate(plotOffset.left, plotOffset.top);

                var c = $.color.parse(o.selection.color);

                ctx.strokeStyle = c.scale('a', 0.8).toString();
                ctx.lineWidth = 1;
                ctx.lineJoin = "round";
                ctx.fillStyle = c.scale('a', 0.4).toString();

                var x = Math.min(selection.first.x, selection.second.x),
                    y = Math.min(selection.first.y, selection.second.y),
                    w = Math.abs(selection.second.x - selection.first.x),
                    h = Math.abs(selection.second.y - selection.first.y);

                ctx.fillRect(x, y, w, h);
                ctx.strokeRect(x, y, w, h);

                ctx.restore();
            }
        });
    }

    $.plot.plugins.push({
        init: init,
        options: {
            selection: {
                mode: null, // one of null, "x", "y" or "xy"
                color: "#e8cfac"
            }
        },
        name: 'selection',
        version: '1.0'
    });
})(jQuery);


/*
Flot plugin for showing a crosshair, thin lines, when the mouse hovers
over the plot.

  crosshair: {
    mode: null or "x" or "y" or "xy"
    color: color
    lineWidth: number
  }

Set the mode to one of "x", "y" or "xy". The "x" mode enables a
vertical crosshair that lets you trace the values on the x axis, "y"
enables a horizontal crosshair and "xy" enables them both. "color" is
the color of the crosshair (default is "rgba(170, 0, 0, 0.80)"),
"lineWidth" is the width of the drawn lines (default is 1).

The plugin also adds four public methods:

  - setCrosshair(pos)

    Set the position of the crosshair. Note that this is cleared if
    the user moves the mouse. "pos" should be on the form { x: xpos,
    y: ypos } (or x2 and y2 if you're using the secondary axes), which
    is coincidentally the same format as what you get from a "plothover"
    event. If "pos" is null, the crosshair is cleared.

  - clearCrosshair()

    Clear the crosshair.

  - lockCrosshair(pos)

    Cause the crosshair to lock to the current location, no longer
    updating if the user moves the mouse. Optionally supply a position
    (passed on to setCrosshair()) to move it to.

    Example usage:
      var myFlot = $.plot( $("#graph"), ..., { crosshair: { mode: "x" } } };
      $("#graph").bind("plothover", function (evt, position, item) {
        if (item) {
          // Lock the crosshair to the data point being hovered
          myFlot.lockCrosshair({ x: item.datapoint[0], y: item.datapoint[1] });
        }
        else {
          // Return normal crosshair operation
          myFlot.unlockCrosshair();
        }
      });

  - unlockCrosshair()

    Free the crosshair to move again after locking it.
*/

(function ($) {
    var options = {
        crosshair: {
            mode: null, // one of null, "x", "y" or "xy",
            color: "rgba(170, 0, 0, 0.80)",
            lineWidth: 1
        }
    };
    
    function init(plot) {
        // position of crosshair in pixels
        var crosshair = { x: -1, y: -1, locked: false };

        plot.setCrosshair = function setCrosshair(pos) {
            if (!pos)
                crosshair.x = -1;
            else {
                var axes = plot.getAxes();
                
                crosshair.x = Math.max(0, Math.min(pos.x != null ? axes.xaxis.p2c(pos.x) : axes.x2axis.p2c(pos.x2), plot.width()));
                crosshair.y = Math.max(0, Math.min(pos.y != null ? axes.yaxis.p2c(pos.y) : axes.y2axis.p2c(pos.y2), plot.height()));
            }
            
            plot.triggerRedrawOverlay();
        };
        
        plot.clearCrosshair = plot.setCrosshair; // passes null for pos
        
        plot.lockCrosshair = function lockCrosshair(pos) {
            if (pos)
                plot.setCrosshair(pos);
            crosshair.locked = true;
        }

        plot.unlockCrosshair = function unlockCrosshair() {
            crosshair.locked = false;
        }

        plot.hooks.bindEvents.push(function (plot, eventHolder) {
            if (!plot.getOptions().crosshair.mode)
                return;

            eventHolder.mouseout(function () {
                if (crosshair.x != -1) {
                    crosshair.x = -1;
                    plot.triggerRedrawOverlay();
                }
            });
            
            eventHolder.mousemove(function (e) {
                if (plot.getSelection && plot.getSelection()) {
                    crosshair.x = -1; // hide the crosshair while selecting
                    return;
                }
                
                if (crosshair.locked)
                    return;
                
                var offset = plot.offset();
                crosshair.x = Math.max(0, Math.min(e.pageX - offset.left, plot.width()));
                crosshair.y = Math.max(0, Math.min(e.pageY - offset.top, plot.height()));
                plot.triggerRedrawOverlay();
            });
        });

        plot.hooks.drawOverlay.push(function (plot, ctx) {
            var c = plot.getOptions().crosshair;
            if (!c.mode)
                return;

            var plotOffset = plot.getPlotOffset();
            
            ctx.save();
            ctx.translate(plotOffset.left, plotOffset.top);

            if (crosshair.x != -1) {
                ctx.strokeStyle = c.color;
                ctx.lineWidth = c.lineWidth;
                ctx.lineJoin = "round";

                ctx.beginPath();
                if (c.mode.indexOf("x") != -1) {
                    ctx.moveTo(crosshair.x, 0);
                    ctx.lineTo(crosshair.x, plot.height());
                }
                if (c.mode.indexOf("y") != -1) {
                    ctx.moveTo(0, crosshair.y);
                    ctx.lineTo(plot.width(), crosshair.y);
                }
                ctx.stroke();
            }
            ctx.restore();
        });
    }
    
    $.plot.plugins.push({
        init: init,
        options: options,
        name: 'crosshair',
        version: '1.0'
    });
})(jQuery);


function DragDrop() {}
function Resizable() {}
function Selectable() {}
function Sortable() {}
function Accordtion() {}
function Dialog() {}
function Slider() {}
function Tabs() {}
function Datepicker() {}
function Progressbar() {}

function boxPop() {}
function carousels() {}
function bigCharts() {}
function smallCharts() {}
function passwordMask() {}
function passwordsMask() {}
function twitterFeed() {}
function flickrFeed(){}
function feedLoader() {}
function validateForms(){}


