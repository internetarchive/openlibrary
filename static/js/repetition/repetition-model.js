/*
 *  Web Forms 2.0 Repetition Model Cross-browser Implementation <http://code.google.com/p/repetitionmodel/>
 *  Version: 0.8.2.2 (2007-03-28)
 *  Copyright: 2007, Weston Ruter <http://weston.ruter.net/>
 *  License: http://creativecommons.org/licenses/LGPL/2.1/
 * 
 *  The comments contained in this code are largely quotations from the 
 *  WebForms 2.0 specification: <http://whatwg.org/specs/web-forms/current-work/#repeatingFormControls>
 *
 *  Usage: <script type="text/javascript" src="repetition-model.js"></script>
 */

if(!window.RepetitionElement || (
     document.implementation && document.implementation.hasFeature && 
     !document.implementation.hasFeature("WebForms", "2.0")
  )){
var RepetitionElement = {
	REPETITION_NONE:0,
	REPETITION_TEMPLATE:1,
	REPETITION_BLOCK:2,
	
	_initialized:false,
	_repetitionTemplates:[],

	_init_document : function(){ //called when the document is loaded
		if(RepetitionElement._initialized)
			return;
		RepetitionElement._initialized = true; //Safari needs this here for some reason

		//RepetitionElement interface must be implemented by all elements.
		if(window.Element && Element.prototype){
			Element.prototype.REPETITION_NONE     = RepetitionElement.REPETITION_NONE;
			Element.prototype.REPETITION_TEMPLATE = RepetitionElement.REPETITION_TEMPLATE;
			Element.prototype.REPETITION_BLOCK    = RepetitionElement.REPETITION_BLOCK;
			
			Element.prototype.repetitionType      = RepetitionElement.REPETITION_NONE;
			Element.prototype.repetitionIndex     = 0;
			Element.prototype.repetitionTemplate  = null; /*readonly*/
			Element.prototype.repetitionBlocks    = null; /*readonly*/

			Element.prototype.repeatStart = 1;
			Element.prototype.repeatMin   = 0;
			Element.prototype.repeatMax   = Infinity;
			
			Element.prototype.addRepetitionBlock        = RepetitionElement.addRepetitionBlock;
			Element.prototype.addRepetitionBlockByIndex = RepetitionElement.addRepetitionBlockByIndex;
			Element.prototype.moveRepetitionBlock       = RepetitionElement.moveRepetitionBlock;
			Element.prototype.removeRepetitionBlock     = RepetitionElement.removeRepetitionBlock;
		}
			
		RepetitionElement._init_repetitionBlocks(); //initialize any repetition block 
		
		RepetitionElement._init_repetitionTemplates();
		RepetitionElement._init_addButtons();
		RepetitionElement._init_removeButtons();
		RepetitionElement._init_moveUpButtons();
		RepetitionElement._init_moveDownButtons();
		
		RepetitionElement.__updateAddButtons();
		RepetitionElement.__updateMoveButtons();
	},

	/*##############################################################################################
	 # REPETITION TEMPLATE
	 ##############################################################################################*/
	_repetitionTemplate_constructor : function(){
		if(this._initialized)
			return;
		this._initialized = true; //SAFARI needs this to be here for some reason...
		
		this.style.display = 'none'; //This should preferrably be specified via a stylesheet
		this.repetitionType = RepetitionElement.REPETITION_TEMPLATE;
		this.repetitionIndex = 0;
		this.repetitionTemplate = null; //IMPLEMENT GETTER
		this.repetitionBlocks = []; //IMPLEMENT GETTER
		var _attr;
		this.repeatStart = /^\d+$/.test(_attr = this.getAttribute('repeat-start')) ? parseInt(_attr) : 1;
		this.repeatMin   = /^\d+$/.test(_attr = this.getAttribute('repeat-min'))   ? parseInt(_attr) : 0;
		this.repeatMax   = /^\d+$/.test(_attr = this.getAttribute('repeat-max'))   ? parseInt(_attr) : Infinity;
		
		if(!this.addRepetitionBlock) this.addRepetitionBlock = function(refNode, index){
			return RepetitionElement.addRepetitionBlock.apply(this, [refNode, index]); //wrapper to save memory
		};
		if(!this.addRepetitionBlockByIndex)
			this.addRepetitionBlockByIndex = this.addRepetitionBlock/*ByIndex*/; //one method implements both algorithms
		
		//On the HTMLFormElement, the templateElements attribute contains the list of form controls associated 
		//   with this form that form part of repetition templates. It is defined in more detail in the section 
		//   on the repetition model. (Image controls are part of this array, when appropriate.) The controls 
		//   in the elements and templateElements lists must be in document order. 
		var form = this;
		while(form = form.parentNode){
			if(form.nodeName.toLowerCase() == 'form')
				break;
		}
		var _templateElements;
		if(form && (_templateElements = RepetitionElement.__getElementsByTagNames.apply(this, ['button','input','select','textarea','isindex'])).length){
			//_templateElements = cssQuery("button,input,select,textarea,isindex", this); //IMAGE???, fieldset not included
			
			//INCORRECT IMPLEMENTATION: this should append the new elements onto the form.templateElements array and then sort them in document order?
			form.templateElements = _templateElements;

			//Controls in the templateElements attribute cannot be successful; controls inside repetition templates can never be submitted.
			//   Therefore disable all elements in the template; however, due to the issue below, the original disabled state must be stored in the field's class attribute as "disabled"
			//   this storing of the original disabled state will enable the elements in cloned blocks to be disabled as originally coded in the template
			//ISSUE: inputs retain disabled (but not defaultDisabled) attribue after returning to page from back button or reload
			//   see http://weblogs.mozillazine.org/gerv/archives/2006/10/firefox_reload_behaviour.html
			// As a workaround... this implementation requires that authors, in addition to supplying a DISABLED attribute (for Opera), to include a class name "disabled"
			for(var el, i = 0; el = form.templateElements[i]; i++)
				el.disabled = true;
			
			//sort elements by document order (code from PPK: http://www.quirksmode.org/dom/getElementsByTagNames.html)
			if (form.templateElements[0].sourceIndex){ //Internet Explorer
				form.templateElements.sort(function (a,b) {
						return a.sourceIndex - b.sourceIndex;
				});
			}
			else if (form.templateElements[0].compareDocumentPosition){ //Gecko/W3C
				form.templateElements.sort(function (a,b) {
						return 3 - (a.compareDocumentPosition(b) & 6);
				});
			}
			
			//IMPLEMENTATION DEFICIENCY: unable to remove form.templateElements from form.elements
		}
		
		//Repetition blocks without a repeat-template attribute are associated with their first following sibling 
		//   that is a repetition template, if there is one.
		var sibling = this;
		while(sibling = sibling.previousSibling){
			if(sibling.repetitionType == RepetitionElement.REPETITION_BLOCK && !sibling.getAttribute('repeat-template')){
				sibling.repetitionTemplate = this;
				sibling.setAttribute('repeat-template', this.id);
				this.repetitionBlocks.unshift(sibling);
			}
		}
	
		//the UA must invoke the template's replication behaviour as many times as the repeat-start attribute 
		//   on the same element specifies (just once, if the attribute is missing or has an invalid value). 
		//   Then, while the number of repetition blocks associated with the repetition template is less than 
		//   the template's repeat-min attribute, the template's replication behaviour must be further invoked. 
		//   (Invoking the template's replication behaviour means calling its addRepetitionBlock() method).
		for(var i = 0; i < Math.max(this.repeatStart, this.repeatMin); i++)
			this.addRepetitionBlock();
		
		RepetitionElement._repetitionTemplates.push(this);
		this._initialized = true;
	},
	
	_init_repetitionTemplates : function(parentNode){
		//UAs must iterate through every node in the document, depth first, looking for templates so that their 
		//   initial repetition blocks can be created. 
		//var repetitionTemplates = cssQuery("*[repeat=template]", parentNode);
		var repetitionTemplates = RepetitionElement.__getElementsByNameAndAttribute.apply((parentNode || document.body), ['*', 'repeat', 'template']);
		for(var i = 0, rt; i < repetitionTemplates.length; i++)
			RepetitionElement._repetitionTemplate_constructor.apply(repetitionTemplates[i]);
	},


	/*##############################################################################################
	 # REPETITION BLOCK
	 ##############################################################################################*/
	 
	_repetitionBlock_constructor : function(){
		if(this._initialized)
			return;
			
		this.style.display = ''; //This should preferrably be specified via a stylesheet
		this.repetitionType = RepetitionElement.REPETITION_BLOCK;
		var _attr;
		this.repetitionIndex = /^\d+$/.test(_attr = this.getAttribute('repeat')) ? parseInt(_attr) : 0;
		this.repetitionBlocks = null;
		
		//find this block's repetition template
		this.repetitionTemplate = null; //IMPLEMENT GETTER
		var node;
		
		if((node = document.getElementById(this.getAttribute('repeat-template'))) && 
		   node.repetitionType == RepetitionElement.REPETITION_TEMPLATE)
		{
			this.repetitionTemplate = node;
		}
		else {
			node = this;
			while(node = node.nextSibling){
				if(node.repetitionType == RepetitionElement.REPETITION_TEMPLATE){
					this.repetitionTemplate = node;
					break;
				}
			}
		}
		
		if(!this.removeRepetitionBlock) this.removeRepetitionBlock = function(){ 
			return RepetitionElement.removeRepetitionBlock.apply(this); //wrapper to save memory
		};
		if(!this.moveRepetitionBlock) this.moveRepetitionBlock = function(distance){ 
			return RepetitionElement.moveRepetitionBlock.apply(this, [distance]); //wrapper to save memory
		};
		this._initialized = true;
	},

	_init_repetitionBlocks : function(parentNode){
		//var repetitionBlocks = cssQuery('*[repeat]:not([repeat="template"])', parentNode); //:not([repeat="template"])
		var repetitionBlocks = RepetitionElement.__getElementsByNameAndAttribute.apply((parentNode || document.body), ['*', 'repeat', 'template', true]);
		for(var i = 0; i < repetitionBlocks.length; i++)
			RepetitionElement._repetitionBlock_constructor.apply(repetitionBlocks[i]);
	},

	/*##############################################################################################
	 # ADD BUTTON
	 ##############################################################################################*/
	_addButton_constructor : function(){
		if(this._initialized)
			return;

		this.htmlTemplate = RepetitionElement.__getHtmlTemplate(this); //IMPLEMENT GETTER
		
		//user agents must automatically disable add buttons (irrespective of the value of the disabled 
		//   DOM attribute [NOT IMPLEMENTED]) when the buttons are not in a repetition block that has an 
		//   associated template and their template attribute is either not specified or does not have 
		//   an ID that points to a repetition template...
		var rb;		
		this.disabled = !(  ((rb = RepetitionElement.__getRepetitionBlock(this)) && rb.repetitionTemplate)
		                    ||
		                    this.htmlTemplate
		                 );
		
		if(this.addEventListener)
			this.addEventListener('click', RepetitionElement._addButton_click, false);
		else if(this.attachEvent)
			this.attachEvent('onclick', RepetitionElement._addButton_click);
		else this.onclick = RepetitionElement._addButton_click;
		
		this._initialized = true;
	},
	
	_init_addButtons : function(parentNode){
		//var addButtons = cssQuery("button[type=add]", parentNode);
		var addButtons = RepetitionElement.__getElementsByNameAndAttribute.apply((parentNode || document.body), ['button', 'type', 'add']);
		for(var i = 0; i < addButtons.length; i++)
			RepetitionElement._addButton_constructor.apply(addButtons[i]);
	},
	
	_addButton_click : function(e){
		if(e && e.preventDefault)
			e.preventDefault(); //Firefox thinks default of custom repetition buttons is submit
		
		//If the event is canceled (btn.returnValue === false, set within onclick handler), then the default action will not occur.
		var btn;
		if(e && e.target)
			btn = e.target;
		else if(window.event)
			btn = window.event.srcElement;
		else if(String(this.nodeName).toLowerCase() == 'button')
			btn = this;

		//QUESTION: spec says that this event is not cancelable! Does Opera not follow the spec here?
		
		//Terminate if an onclick handler was called beforehand and returned a false value passed via the button's returnValue property
		if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){ 
			btn.returnValue = undefined;
			return false;
		}
		
		//Ensure that a user-supplied onclick handler is fired before the repetition behavior is executed
		//  and terminate if this onclick handler returns false
		if((btn.onclick || btn._onclick) && btn.hasAttribute && !btn.hasAttribute("onclick")){ //NOTE: MSIE fires this afterwards???
			if(btn.onclick)
				btn._onclick = btn.onclick;
			btn.returnValue = btn._onclick(e);
			btn.onclick = null; //prevent the onclick handler from firing afterwards (would fire after movement action)
			if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){
				btn.returnValue = undefined;
				return false;
			}
		}		
		//ISSUE: How do we ensure that the MSIE and DOM Level 2 Event handlers are executed beforehand, and how do we get their return values?		
		
		var rt;
		//If an add button with a template attribute is activated, and its template attribute gives the ID 
		//   of an element in the document that is a repetition template as defined above, then that 
		//   template's replication behaviour is invoked. (Specifically, in scripting-aware environments, 
		//   the template's addRepetitionBlock() method is called with a null argument.) In the case of 
		//   duplicate IDs, the behaviour should be the same as with getElementById().
		if(btn.htmlTemplate)
			rt = btn.htmlTemplate;
		else {
		//If an add button without a template attribute is activated, and it has an ancestor that is a 
		//   repetition block that is not an orphan repetition block, then the repetition template associated 
		//   with that repetition block has its template replication behaviour invoked with the respective 
		//   repetition block as its argument. (Specifically, in scripting-aware environments, the template's 
		//   addRepetitionBlock() method is called with a reference to the DOM Element node that represents 
		//   the repetition block.)
			var block = RepetitionElement.__getRepetitionBlock(btn);
			if(block && block.repetitionTemplate)
				rt = block.repetitionTemplate;
		}
		if(rt)
			rt.addRepetitionBlock();
		else
			btn.disabled = true; //NOTE: THIS IS NOT A VALID IMPLEMENTATION
		return true;
	},
	
	/*##############################################################################################
	 # REMOVE BUTTON
	 ##############################################################################################*/
	 
	_removeButton_constructor : function(){
		if(this._initialized)
			return;
		this.htmlTemplate = RepetitionElement.__getHtmlTemplate(this); //IMPLEMENT GETTER

		if(this.addEventListener)
			this.addEventListener('click', RepetitionElement._removeButton_click, false);
		else if(this.attachEvent)
			this.attachEvent('onclick', RepetitionElement._removeButton_click);
		else this.onclick = RepetitionElement._removeButton_click;
		
		this._initialized = true;
	},
	
	_init_removeButtons : function(parentNode){
		//var removeButtons = cssQuery("button[type=remove]", parentNode);
		var removeButtons = RepetitionElement.__getElementsByNameAndAttribute.apply((parentNode || document.body), ['button', 'type', 'remove']);
		for(var i = 0; i < removeButtons.length; i++)
			RepetitionElement._removeButton_constructor.apply(removeButtons[i]);
	},
	
	_removeButton_click : function(e){
		if(e && e.preventDefault)
			e.preventDefault(); //Firefox thinks default of custom repetition buttons is submit

		//user agents must automatically disable remove buttons when they are not in a repetition 
		//   block. [NOT IMPLEMENTED:] This automatic disabling does not affect the DOM disabled  attribute. It is an intrinsic property of these buttons.
		this.disabled = !RepetitionElement.__getRepetitionBlock(this);
		
		//If the event is canceled (btn.returnValue === false, set within onclick handler), then the default action will not occur.
		var btn;
		if(e && e.target)
			btn = e.target;
		else if(window.event)
			btn = window.event.srcElement;
		else if(String(this.nodeName).toLowerCase() == 'button')
			btn = this;
		
		//QUESTION: spec says that this event is not cancelable! Does Opera not follow the spec here?
		
		//Terminate if an onclick handler was called beforehand and returned a false value passed via the button's returnValue property
		if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){ 
			btn.returnValue = undefined;
			return false;
		}
		
		//Ensure that a user-supplied onclick handler is fired before the repetition behavior is executed
		//  and terminate if this onclick handler returns false
		if((btn.onclick || btn._onclick) && btn.hasAttribute && !btn.hasAttribute("onclick")){ //NOTE: MSIE fires this afterwards???
			if(btn.onclick)
				btn._onclick = btn.onclick;
			btn.returnValue = btn._onclick(e);
			btn.onclick = null; //prevent the onclick handler from firing afterwards (would fire after movement action)
			if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){
				btn.returnValue = undefined;
				return false;
			}
		}		
		//ISSUE: How do we ensure that the MSIE and DOM Level 2 Event handlers are executed beforehand, and how do we get their return values?
		
		var block = RepetitionElement.__getRepetitionBlock(btn);
		if(block)
			block.removeRepetitionBlock();
		return false;
	},
	
	/*##############################################################################################
	 # MOVE-UP BUTTON
	 ##############################################################################################*/
	_moveUpButton_constructor : function(){
		if(this._initialized)
			return;
		this.htmlTemplate = RepetitionElement.__getHtmlTemplate(this); //IMPLEMENT GETTER
		
		//user agents must automatically disable move-up buttons when they are not in a repetition 
		//   block. [NOT IMPLEMENTED:] This automatic disabling does not affect the DOM disabled  attribute. It is an intrinsic property of these buttons.
		this.disabled = !RepetitionElement.__getRepetitionBlock(this);

		if(this.addEventListener)
			this.addEventListener('click', RepetitionElement._moveUpButton_click, false);
		else if(this.attachEvent)
			this.attachEvent('onclick', RepetitionElement._moveUpButton_click);
		else this.onclick = RepetitionElement._moveUpButton_click;
		
		this._initialized = true;
	},

	_init_moveUpButtons : function(parentNode){
		//var moveUpButtons = cssQuery("button[type=move-up]", parentNode);
		var moveUpButtons = RepetitionElement.__getElementsByNameAndAttribute.apply((parentNode || document.body), ['button', 'type', 'move-up']);
		for(var i = 0; i < moveUpButtons.length; i++)
			RepetitionElement._moveUpButton_constructor.apply(moveUpButtons[i]);
	},

	_moveUpButton_click : function(e){
		if(e && e.preventDefault)
			e.preventDefault(); //Firefox thinks default of custom repetition buttons is submit
		
		//If the event is canceled (btn.returnValue === false, set within onclick handler), then the default action will not occur.
		var btn;
		if(e && e.target)
			btn = e.target;
		else if(window.event)
			btn = window.event.srcElement;
		else if(String(this.nodeName).toLowerCase() == 'button')
			btn = this;
		
		//QUESTION: spec says that this event is not cancelable! Does Opera not follow the spec here?
		
		//Terminate if an onclick handler was called beforehand and returned a false value passed via the button's returnValue property
		if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){ 
			btn.returnValue = undefined;
			return false;
		}
		
		//Ensure that a user-supplied onclick handler is fired before the repetition behavior is executed
		//  and terminate if this onclick handler returns false
		if((btn.onclick || btn._onclick) && btn.hasAttribute && !btn.hasAttribute("onclick")){ //NOTE: MSIE fires this afterwards???
			if(btn.onclick)
				btn._onclick = btn.onclick;
			btn.returnValue = btn._onclick(e);
			btn.onclick = null; //prevent the onclick handler from firing afterwards (would fire after movement action)
			if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){
				btn.returnValue = undefined;
				return false;
			}
		}		
		//ISSUE: How do we ensure that the MSIE and DOM Level 2 Event handlers are executed beforehand, and how do we get their return values?		
		
		var block = RepetitionElement.__getRepetitionBlock(btn);
		if(block){
			block._clickedMoveBtn = btn;
			block.moveRepetitionBlock(-1);
		}
		return false;
	},
	
	
	/*##############################################################################################
	 # MOVE-DOWN BUTTON
	 ##############################################################################################*/
	_moveDownButton_constructor : function(){
		if(this._initialized)
			return;
		this.htmlTemplate = RepetitionElement.__getHtmlTemplate(this); //IMPLEMENT GETTER
		
		//user agents must automatically disable move-down buttons when they are not in a repetition 
		//   block. [NOT IMPLEMENTED:] This automatic disabling does not affect the DOM disabled  attribute. It is an intrinsic property of these buttons.
		this.disabled = !RepetitionElement.__getRepetitionBlock(this);
		
		if(this.addEventListener)
			this.addEventListener('click', RepetitionElement._moveDownButton_click, false);
		else if(this.attachEvent)
			this.attachEvent('onclick', RepetitionElement._moveDownButton_click);
		else this.onclick = RepetitionElement._moveDownButton_click;
		
		this._initialized = true;
	},
	 
	_init_moveDownButtons : function(parentNode){
		//var moveDownButtons = cssQuery("button[type=move-down]", parentNode);
		var moveDownButtons = RepetitionElement.__getElementsByNameAndAttribute.apply((parentNode || document.body), ['button', 'type', 'move-down']);
		for(var i = 0; i < moveDownButtons.length; i++)
			RepetitionElement._moveDownButton_constructor.apply(moveDownButtons[i]);
	},
	 
	_moveDownButton_click : function(e){
		if(e && e.preventDefault)
			e.preventDefault(); //Firefox thinks default of custom repetition buttons is submit
		
		//If the event is canceled (btn.returnValue === false, set within onclick handler), then the default action will not occur.
		var btn;
		if(e && e.target)
			btn = e.target;
		else if(window.event)
			btn = window.event.srcElement;
		else if(String(this.nodeName).toLowerCase() == 'button')
			btn = this;

		//QUESTION: spec says that this event is not cancelable! Does Opera not follow the spec here?
		
		//Terminate if an onclick handler was called beforehand and returned a false value passed via the button's returnValue property
		if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){ 
			btn.returnValue = undefined;
			return false;
		}
		
		//Ensure that a user-supplied onclick handler is fired before the repetition behavior is executed
		//  and terminate if this onclick handler returns false
		if((btn.onclick || btn._onclick) && btn.hasAttribute && !btn.hasAttribute("onclick")){ //NOTE: MSIE fires this afterwards???
			if(btn.onclick)
				btn._onclick = btn.onclick;
			btn.returnValue = btn._onclick(e);
			btn.onclick = null; //prevent the onclick handler from firing afterwards (would fire after movement action)
			if(!btn.returnValue && typeof(btn.returnValue) != 'undefined'){
				btn.returnValue = undefined;
				return false;
			}
		}		
		//ISSUE: How do we ensure that the MSIE and DOM Level 2 Event handlers are executed beforehand, and how do we get their return values?		
		
		var block = RepetitionElement.__getRepetitionBlock(btn);
		if(block){
			block._clickedMoveBtn = btn;
			block.moveRepetitionBlock(1);
		}
		return false;
	},

	
	/*##############################################################################################
	 # AddRepetitionBlock algorithm
	 ##############################################################################################*/
	
	//Element addRepetitionBlock(in Node refNode);
	addRepetitionBlock : function(refNode, index){ //addRepetitionBlockByIndex functionalty enabled if @index defined
		if(refNode && !refNode.nodeType)
			throw Error("Exception: WRONG_ARGUMENTS_ERR");

		if(this.repetitionType != RepetitionElement.REPETITION_TEMPLATE)
			//throw DOMException("NOT_SUPPORTED_ERR");
			throw Error("DOMException: NOT_SUPPORTED_ERR");
	
		//1. If the template has no parent node or its parent node is not an element, then the method must abort 
		//   the steps and do nothing. 
		if(this.parentNode == null)
			return;
			
		//[furthermore, if this template is the child of another template (not the child of an instance, a block) return false]
		var node = this;
		while(node = node.parentNode){
			if(node.repetitionType == RepetitionElement.REPETITION_TEMPLATE)
				return false;
		}
		
		//2. The template examines its preceding siblings, up to the start of the parent element. For each sibling 
		//   that is a repetition block whose associated template is this template, if the repetition block's index 
		//   is greater than or equal to the template's index, then the template's index is increased to the repetition 
		//   block's index plus one. The total number of repetition blocks associated with this template that were 
		//   found is used in the next step.
		//QUESTION: Why not just use this.repetitionBlocks.length????????????
		var sibling = this.previousSibling;
		var currentBlockCount = 0;
		while(sibling != null){
			if(sibling.repetitionType == RepetitionElement.REPETITION_BLOCK && 
			   sibling.repetitionTemplate == this)
			{
				//Old Note: sibling.getAttribute('repeat') is used instead of sibling.repetitionIndex because appearantly
				//      the sibling is not yet bound to the document and so the getters are not available
				//this.repetitionIndex = Math.max(this.repetitionIndex, parseInt(sibling.getAttribute('repeat'))+1);
				this.repetitionIndex = Math.max(this.repetitionIndex, sibling.repetitionIndex+1);
				currentBlockCount++;
			}
			sibling = sibling.previousSibling;
		}
		
		//3. If the repetition template has a repeat-max attribute and that attribute's value is less than or equal 
		//   to the number of repetition blocks associated with this template that were found in the previous step, 
		//   the UA must stop at this step, returning a null value.
		if(this.repeatMax <= currentBlockCount)
			return null;
			
		//4. If this algorithm was invoked via the addRepetitionBlockByIndex()  method, and the value of the method's 
		//   index argument is greater than the template's index, then the template's index is set to the value of the 
		//   method's index argument.
		if(typeof index != 'undefined' && index > this.repetitionIndex)
			this.repetitionIndex = index;

		//(the following steps are out of order to facilitate a custom cloneNode to cope for MSIE and Gecko issues)
		
		//9. If the new repetition block has an ID attribute (that is, an attribute specifying an ID, regardless 
		//   of the attribute's namespace or name), then that attribute's value is used as the template name in 
		//   the following steps. Otherwise, the template has no name. (If there is more than one ID attribute, 
		//   the "first" one in terms of node order is used. [DOM3CORE]) 
		//   [Since this step was moved here, it uses 'this' and not 'block', which hasn't been created yet]
		//NOTE: hasAttribute throws error in IE
		//var IDAttr = block.getAttributeNode('id') ? block.getAttributeNode('id') : block.getAttributeNode('name'); //DETECT ID TYPE For others?
		var IDAttrName = this.getAttribute('id') ? 'id' : this.getAttribute('name') ? 'name' : ''; //NOTE: hasAttribute not implemented in MSIE
		var IDAttrValue = this.getAttribute(IDAttrName);
		
		//10. If the template has a name (see the previous step), and that name contains either an opening square 
		//    bracket (U+005B, "[") a modifier letter half triangular colon (U+02D1), a closing square bracket 
		//    (U+005D, "]") or a middle dot (U+00B7), then the template's name is ignored for the purposes of 
		//    the next step.
		var ignoreName = /\u005B|\u02D1|\u005D|\u00B7/.test(IDAttrValue); //VALID LOGIC?
		var boolProcessAttr = IDAttrValue && !ignoreName;

		//5. A clone of the template is made. The resulting element is the new repetition block element.
		//   [Note that the DOM cloneNode method is not invoked in this implementation due to MSIE 
		//   errors, such as not being able to modify the name attribute of an existing node and strange Gecko behavior
		//   regarding the inconsistant correspondence of an input node's value attribute and value property.
		//   Instead of invoking the native cloneNode method, each element is copied manually when it is iterated over.]
		//	 [Note: step 11 of the the specification's algorithm has been merged into step 5. See note at step 11 below]
		//(11). If the template has a name and it is not being ignored (see the previous two steps), then, for every 
		//      attribute on the new element, and for every attribute in every descendant of the new element: if the 
		//      attribute starts with a zero-width non-breaking space character (U+FEFF) then that character is 
		//      removed from the attribute; otherwise, any occurrences of a string consisting of an opening square 
		//      bracket (U+005B, "[") or a modifier letter half triangular colon (U+02D1), the template's name, 
		//      and a closing square bracket (U+005D, "]") or a middle dot (U+00B7), are replaced by the new 
		//      repetition block's index. This is performed regardless of the types, names, or namespaces of attributes, 
		//      and is done to all descendants, even those inside nested forms, nested repetition templates, and so forth.
		var block;
		
		//Function that processes an attribute value as defined in step 11
		var replaceValue = this.repetitionIndex;
		var reTemplateName = new RegExp("(\\[|\u02D1)" + IDAttrValue + "(\\]|\u00B7)", 'g'); //new RegExp('(\\u005B|\\u02D1)' + IDAttrValue + '(\\u005D|\\u00B7)', 'g');
		function _processAttr(attrVal){
			if(!attrVal) 
				return attrVal;
			attrVal = attrVal.toString();
			if(attrVal.indexOf("\uFEFF") === 0)
				return attrVal.replace(/^\uFEFF/, '');
			return attrVal.replace(reTemplateName, replaceValue);
		}
		
		
		var _customAttrs = { //FOR MSIE BUG: it cannot perceive the attributes that were actually specified
			'type':1,'template':1,'repeat':1,'repeat-template':1,'repeat-min':1,
			'repeat-max':1,'repeat-start':1,'value':1,'class':1,'required':1,
			'pattern':1,'form':1,'autocomplete':1,'autofocus':1,'inputmode':1
		};
		var _skippedAttrs = {
			'name':1,  //due to MSIE bug, set via RepetitionElement.__createElementWithName
			'class':1, //due to MSIE bug, set below (see http://www.alistapart.com/articles/jslogging)
			'for':1,   //due to preceived MSIE bug, set below
			'style':1,  //inline styles require special handling
			onadd:1,onremove:1,onmove:1, //don't copy Repetition old model event attributes not methods
			onmoved:1,onadded:1,onremoved:1, //deprecated
			
			//for MSIE, properties (or methods) == attributes
			addRepetitionBlock:1,addRepetitionBlockByIndex:1,moveRepetitionBlock:1,
			removeRepetitionBlock:1, repetitionBlocks:1, 
			_initialized:1
		};
		
		//BROWSER BUG: _cloneNode used with Gecko because Gecko starts to have irratic behavior with a cloned 
		//  input's value attribute and value property; furthermore, various MSIE bugs prevent its ise of cloneNode
		function _cloneNode(node){
			var clone, i, attr, el;
			if(node.nodeType == 1 /*Node.ELEMENT_NODE*/){
				//BROWSER BUG: MSIE does not allow the setting of the node.name, except when creating the new node
				clone = node.name ? 
				        RepetitionElement.__createElementWithName(node.nodeName, (boolProcessAttr ? _processAttr(node.name) : node.name)) 
				      : document.createElement(node.nodeName);
						
				for(i = 0; attr = node.attributes[i]; i++){
					//PROBLEM: some attributes that were specified are being skipped
					//VALUE IS REPEATED IN MSIE WHEN VALUE ATTRIBUTE SET?
					//if(attr.specified || node.getAttribute(attr.nodeName)) //_customAttrs[attr.nodeName] || 
					//	if(window.console && console.info) console.info(node.nodeName + "@" + attr.nodeName + " -- " + attr.specified + " <font color=red>" + node.getAttribute(attr.nodeName) + "</font>(" + typeof node.getAttribute(attr.nodeName) + ")<br>");

					if((attr.specified || _customAttrs[attr.name]) && !_skippedAttrs[attr.name]){
						//MSIE BUG: when button[type=add|remove|move-up|move-down], then (attr.nodeValue and attr.value == 'button') but node.getAttribute(attr.nodeName) == 'add|remove|move-up|move-down' (as desired)
						
						//clone and process an event handler property (attribute)
						if((attr.name.indexOf("on") === 0) && (typeof node[attr.name] == 'function')){
							var funcBody = _processAttr(node[attr.name].toString().match(/{((?:.|\n)+)}/)[1]);
							funcBody = _processAttr(funcBody);
							clone[attr.name] = new Function('event', funcBody);
						}
						//clone and process other attributes
						else {
							var attrValue = node.getAttribute(attr.name);
							attrValue = (boolProcessAttr ? _processAttr(attrValue) : attrValue);
							clone.setAttribute(attr.name, attrValue);
						}
					}
				}
				//MSIE BUG: setAttribute('class') creates duplicate value attribute in MSIE; 
				//QUESTION: will setting className on this clonedNode still cause this error later on for users? will addClassName croak? Should it be improved?
				//see: http://www.alistapart.com/articles/jslogging
				if(node.className){
					var _className = (boolProcessAttr ? _processAttr(node.className) : node.className);
					if(clone.getAttributeNode('class')){
						for(i = 0; i < clone.attributes.length; i++) {
							if(clone.attributes[i].name == 'class')
								clone.attributes[i].value = _className;
						}
					}
					else clone.setAttribute('class', _className);
				}

				//Restore the template's elements to the originally coded disabled state (indicated by 'disabled' class name)
				// All elements within the repetition template are disabled to prevent them from being successful.
				if(!/\bdisabled\b/.test(node.className))
					clone.disabled = false;
				
				//Process the inline style
				if(node.style){
					//console.warn("Unable to process style attribute.");
					//console.info("cssText = " + node.style.cssText);
					//console.info("style = " + node.getAttributeNode('style').textContent);
					//console.info(node.parentNode.innerHTML)
					//clone.setAttribute('style', _processAttr(node.style.cssText));
					clone.style.cssText = _processAttr(node.style.cssText);
				}
				
				//label's 'for' attribute, set here due to MSIE bug
				if(node.nodeName.toLowerCase() == 'label' && node.htmlFor)
					clone.htmlFor = (boolProcessAttr ? _processAttr(node.htmlFor) : node.htmlFor);
				
				for(i = 0; el = node.childNodes[i]; i++)
					clone.appendChild(_cloneNode(el));
			}
			else clone = node.cloneNode(true);
			return clone;
		}
		block = _cloneNode(this);
		block._initialized = false;
	
		
		//6. If this algorithm was invoked via the addRepetitionBlockByIndex()  method, the new repetition block 
		//   element's index is set to the method's index argument. Otherwise, the new repetition block element's 
		//   index is set to the template's index. [Note: if called by addRepetitionBlockByIndex() then the 
		//   template's repetitionIndex has already been set to the index argument. Redundant algorithm step.]
		//block.repetitionIndex = this.repetitionIndex; //this is set in the constructor for the repetitionBlock
		//7. If the new repetition block element is in the http://www.w3.org/1999/xhtml namespace, then the 
		//   repeat attribute in no namespace on the cloned element has its value changed to the new block's 
		//   index. Otherwise, the repeat attribute in the http://www.w3.org/1999/xhtml namespace has its value 
		//   changed to the new block's index.
		//if(block.namespaceURI == 'http://www.w3.org/1999/xhtml')
			block.setAttribute('repeat', this.repetitionIndex); //when inserted into DOM, constructor sets block.repetitionIndex
		//else
		//	block.setAttributeNS('http://www.w3.org/1999/xhtml', 'repeat', this.repetitionIndex);
		
		//8. If the new repetition block element is in the http://www.w3.org/1999/xhtml namespace, then any 
		//   repeat-min, repeat-max, or repeat-start attributes in no namespace are removed from the element. 
		//   Otherwise, any repeat-min, repeat-max, or repeat-start attributes in the http://www.w3.org/1999/xhtml 
		//   namespace are removed instead.

		//if(block.namespaceURI == 'http://www.w3.org/1999/xhtml'){
			block.removeAttribute('repeat-min');
			block.removeAttribute('repeat-max');
			block.removeAttribute('repeat-start');
		//}
		//else {
		//	block.removeAttributeNS('http://www.w3.org/1999/xhtml', 'repeat-min');
		//	block.removeAttributeNS('http://www.w3.org/1999/xhtml', 'repeat-max');
		//	block.removeAttributeNS('http://www.w3.org/1999/xhtml', 'repeat-start');
		//}
		
		//(steps 9 and 10 moved to before step 5 (operates on this repetition template, and not on cloned block))


		//11. (Note: the algorithm below which most closely follows the algorithm as described in the specification,
		//    this has been merged into the cloning of the template in step 5. This has been done because of MSIE 
		//    errors, such as not being able to modify the name attribute of an existing node and strange Gecko behavior
		//    regarding the inconsistant correspondence of an input node's value attribute and value property.)
		//if(IDAttrValue && !ignoreName){
		//	var reTemplateName = new RegExp('(?:\\u005B|\\u02D1)' + IDAttrValue + '(?:\\u005D|\\u00B7)', 'g');
		//	function processAttrs(node){
		//		var i,attr;
		//		for(i = 0; node.attributes && i < node.attributes.length; i++){
		//			if(!(attr = node.attributes[i]).nodeValue)
		//				continue;
		//			
		//			if(String(attr.nodeValue).indexOf("\uFEFF") === 0)
		//				attr.nodeValue = attr.nodeValue.replace(/^\uFEFF/, '');
		//				
		//			else if(reTemplateName.test(attr.nodeValue))
		//				attr.nodeValue = attr.nodeValue.replace(reTemplateName, block.getAttribute('repeat'));
		//		}
		//		for(i = 0; i < node.childNodes.length; i++)
		//			processAttrs(node.childNodes[i]);
		//	}
		//	processAttrs(block);
		//}

			
		//12. If the template has a name (see the earlier steps): If the new repetition block element is in the 
		//    http://www.w3.org/1999/xhtml namespace, then the repeat-template attribute in no namespace on the 
		//    cloned element has its value set to the template's name. Otherwise, the repeat-template attribute 
		//    in the http://www.w3.org/1999/xhtml namespace has its value set to the template's name. (This 
		//    happens even if the name was ignored for the purposes of the previous step.)
		if(IDAttrName){
			//if(block.namespaceURI == "http://www.w3.org/1999/xhtml")
				block.setAttribute('repeat-template', IDAttrValue); //block.setAttributeNS(null, 'repeat-template', IDAttr.nodeValue);
			//else 
			//	block.setAttributeNS('http://www.w3.org/1999/xhtml', 'repeat-template', IDAttr.nodeValue);
			
			
			//13. The attribute from which the template's name was derived, if any, and even if it was ignored, is 
			//    removed from the new repetition block element. (See the previous four steps.)
			block.removeAttribute(IDAttrName);
		}

		//14. If the first argument to the method was null, then the template once again crawls through its 
		//    previous siblings, this time stopping at the first node (possibly the template itself) whose 
		//    previous sibling is a repetition block (regardless of what that block's template is) or the first 
		//    node that has no previous sibling, whichever comes first. The new element is the inserted into the 
		//    parent of the template, immediately before that node. Mutation events are fired if appropriate.
		if(!refNode){
			var refNode = this;
			while(refNode.previousSibling && refNode.previousSibling.repetitionType != RepetitionElement.REPETITION_BLOCK)
				refNode = refNode.previousSibling;
			this.parentNode.insertBefore(block, refNode);
			this.repetitionBlocks.push(block);
		}
		//15. Otherwise, the new element is inserted into the parent of the node that was passed to the method 
		//    as the first argument, immediately after that node (before the node's following sibling, if any). 
		//    Mutation events are fired if appropriate.
		else {
			refNode.parentNode.insertBefore(block, refNode.nextSibling);
			this.repetitionBlocks.push(block);
		
			//sort elements by document order (code from PPK: http://www.quirksmode.org/dom/getElementsByTagNames.html)
			if (this.repetitionBlocks[0].sourceIndex){ //Internet Explorer
				this.repetitionBlocks.sort(function (a,b) {
						return a.sourceIndex - b.sourceIndex;
				});
			}
			else if (this.repetitionBlocks[0].compareDocumentPosition){ //Gecko/W3C
				this.repetitionBlocks.sort(function (a,b) {
						return 3 - (a.compareDocumentPosition(b) & 6);
				});
			}
		}
		
		//16. The template's index is increased by one. 
		this.repetitionIndex++;
		
		//[apply constructors to the new repetition block, and to the new remove buttons, add buttons, etc]
		RepetitionElement._repetitionBlock_constructor.apply(block);
		RepetitionElement._init_repetitionTemplates(block);
		RepetitionElement._init_addButtons(block);
		RepetitionElement._init_removeButtons(block);
		RepetitionElement._init_moveUpButtons(block);
		RepetitionElement._init_moveDownButtons(block);
		
		//In addition, user agents must automatically disable add buttons (irrespective of the value of the 
		//   disabled DOM attribute) when the buttons are not in a repetition block that has an associated 
		//   template and their template attribute is either not specified or does not have an ID that points 
		//   to a repetition template, and, when the repetition template's repeat-max attribute is less than 
		//   or equal to the number of repetition blocks that are associated with that template and that have 
		//   the same parent. This automatic disabling does not affect the DOM disabled attribute. It is an 
		//   intrinsic property of these buttons.
		if(RepetitionElement._initialized){ //if buttons not yet initialized, will initially be called by _init_document
			RepetitionElement.__updateAddButtons(this);
			RepetitionElement.__updateMoveButtons(this.parentNode);
		}
		
		//17. An added event with no namespace, which bubbles but is not cancelable and has no default action, 
		//    must be fired on the repetition template using the RepetitionEvent interface, with the repetition 
		//    block's DOM node as the context information in the element  attribute.
		var addEvt;
		try {
			if(document.createEvent)
				addEvt = document.createEvent("UIEvents"); //document.createEvent("RepetitionEvent")
			else if(document.createEventObject)
				addEvt = document.createEventObject();
			RepetitionEvent._upgradeEvent.apply(addEvt);
			addEvt.initRepetitionEvent("added", true /*canBubble*/, false /*cancelable*/, block);
			if(this.dispatchEvent)
				this.dispatchEvent(addEvt);
			else if(this.fireEvent){
				//console.warn("fireEvent('onadd') for MSIE is not yet working");
				//this.fireEvent('onadded', addEvt);
			}
		}
		catch(err){
			addEvt = new Object();
			RepetitionEvent._upgradeEvent.apply(addEvt);
			addEvt.initRepetitionEvent("added", true /*canBubble*/, false /*cancelable*/, block);
		}
		
		//Add support for event handler set with HTML attribute
		var onaddAttr = this.getAttribute('onadd') || /* deprecated */ this.getAttribute('onadded');
		if(onaddAttr && (!this.onadd || typeof this.onadd != 'function')) //in MSIE, attribute == property
			this.onadd = new Function('event', onaddAttr);
		
		//Dispatch events for the old event model (extension to spec)
		if(this.onadd)
			this.onadd(addEvt);
		else if(this.onadded) //deprecated
			this.onadded(addEvt);

		//18. The return value is the newly cloned element.
		return block;
	},
	//Element addRepetitionBlockByIndex(in Node refNode, in long index);
	addRepetitionBlockByIndex : function(refNode, index){
		RepetitionElement.addRepetitionBlock.apply(this, [refNode, index])
	},
	
	/*##############################################################################################
	 # RemoveRepetitionBlock algorithm
	 ##############################################################################################*/
	
	//void removeRepetitionBlock();
	removeRepetitionBlock : function(){
		if(this.repetitionType != RepetitionElement.REPETITION_BLOCK)
			//throw DOMException("NOT_SUPPORTED_ERR");
			throw Error("DOMException: NOT_SUPPORTED_ERR");

		//1. The node is removed from its parent, if it has one. Mutation events are fired if appropriate. 
		//   (This occurs even if the repetition block is an orphan repetition block.)
		var parentNode = this.parentNode; //save for __updateMoveButtons
		var block = parentNode.removeChild(this);
		RepetitionElement.__updateMoveButtons(parentNode);
		
		//The following loop used to appear within step #3 below; 
		//  this caused problems because the program state was incorrect when onremove was called (repetitionBlocks was not modified)
		if(this.repetitionTemplate != null){
			for(var i = 0; i < this.repetitionTemplate.repetitionBlocks.length; i++){
				if(this.repetitionTemplate.repetitionBlocks[i] == this){
					this.repetitionTemplate.repetitionBlocks.splice(i,1);
					break;
				}
			}
		}

		//2. If the repetition block is not an orphan, a removed event with no namespace, which bubbles but 
		//   is not cancelable and has no default action, must be fired on the element's repetition template, 
		//   using the RepetitionEvent interface, with the repetition block's DOM node as the context information 
		//   in the element attribute.
		if(this.repetitionTemplate != null){
			var removeEvt;
			try {
				if(document.createEvent)
					removeEvt = document.createEvent("UIEvents"); //document.createEvent("RepetitionEvent")
				else if(document.createEventObject)
					removeEvt = document.createEventObject();
				RepetitionEvent._upgradeEvent.apply(removeEvt);
				removeEvt.initRepetitionEvent("removed", true /*canBubble*/, false /*cancelable*/, this);
				if(this.repetitionTemplate.dispatchEvent)
					this.repetitionTemplate.dispatchEvent(removeEvt);
				else if(this.repetitionTemplate.fireEvent){
					//console.warn("fireEvent('onremove') for MSIE is not yet working");
					//this.repetitionTemplate.fireEvent('onremove', removeEvt);
				}
			}
			catch(err){
				removeEvt = new Object();
				RepetitionEvent._upgradeEvent.apply(removeEvt);
				removeEvt.initRepetitionEvent("removed", true /*canBubble*/, false /*cancelable*/, this);
			}
			
			//Add support for event handler set with HTML attribute
			var onremoveAttr = this.repetitionTemplate.getAttribute('onremove') 
			                   || /* deprecated */ this.repetitionTemplate.getAttribute('onremoved');
			if(onremoveAttr && (!this.repetitionTemplate.onremove || typeof this.repetitionTemplate.onremove != 'function')) //in MSIE, attribute == property
				this.repetitionTemplate.onremove = new Function('event', onremoveAttr);
			
			//Dispatch events for the old event model (extension to spec)
			if(this.repetitionTemplate.onremove)
				this.repetitionTemplate.onremove(removeEvt);
			else if(this.repetitionTemplate.onremoved) //deprecated
				this.repetitionTemplate.onremoved(removeEvt);
		}

		//3. If the repetition block is not an orphan, then while the remaining number of repetition blocks 
		//   associated with the original element's repetition template and with the same parent as the template 
		//   is less than the template's repeat-min attribute and less than its repeat-max attribute, the 
		//   template's replication behaviour is invoked (specifically, its addRepetitionBlock() method is called). 
		if(this.repetitionTemplate != null){
//			//BUG: The following needs to be moved before the call to onremove
//			var t = this.repetitionTemplate;
//			for(var i = 0; i < t.repetitionBlocks.length; i++){
//				if(t.repetitionBlocks[i] == this){
//					t.repetitionBlocks.splice(i,1);
//					break;
//				}
//			}
			if(this.repetitionTemplate.repetitionBlocks.length < this.repetitionTemplate.repeatMin 
			     && this.repetitionTemplate.repetitionBlocks.length < this.repetitionTemplate.repeatMax)
			{
				this.repetitionTemplate.addRepetitionBlock();
			}
			
			//enable add buttons
			if(this.repetitionTemplate.repetitionBlocks.length < this.repetitionTemplate.repeatMax){
				//var addBtns = cssQuery("button[type=add]");
				var addBtns = RepetitionElement.__getElementsByNameAndAttribute.apply(document.body, ['button', 'type', 'add']);
				for(i = 0; i < addBtns.length; i++){
					if(addBtns[i].htmlTemplate == this.repetitionTemplate)
						addBtns[i].disabled = false;
				}
			}
		}
	},

	/*##############################################################################################
	 # MoveRepetitionBlock algorithm
	 ##############################################################################################*/
	 
	//void moveRepetitionBlock(in long distance);
	moveRepetitionBlock : function(distance){
		if(this.repetitionType != RepetitionElement.REPETITION_BLOCK)
			//throw DOMException("NOT_SUPPORTED_ERR");
			throw Error("DOMException: NOT_SUPPORTED_ERR");
		
		//1. If distance is 0, or if the repetition block has no parent, nothing happens and the algorithm ends here.
		if(distance == 0 || this.parentNode == null)
			return;
		
		//2. Set target, a reference to a DOM Node, to the repetition block being moved.
		//   [Furthermore, move the reference to this block in the template's repetitionBlocks HTMLCollection to 
		//   reflect the new position that it is being moved to.]
		var target = this;
		if(this.repetitionTemplate){
			var pos = 0;
			var rp = this.repetitionTemplate.repetitionBlocks;
			while(pos < rp.length && rp[pos] != this)
				pos++;
			rp.splice(pos, 1);
			rp.splice(distance < 0 ? Math.max(pos+distance, 0) : Math.min(pos+distance, rp.length), 0, this);
		}
		
		//3. If distance is negative: while distance is not zero and target's previousSibling is defined and is 
		//   not a repetition template, set target to this previousSibling and, if it is a repetition block, 
		//   increase distance by one (make it less negative by one).
		if(distance < 0){
			while(distance != 0 && target.previousSibling && 
			      target.previousSibling.repetitionType != RepetitionElement.REPETITION_TEMPLATE)
			{
				target = target.previousSibling;
				if(target.repetitionType == RepetitionElement.REPETITION_BLOCK)
					distance++;
			}
		}
		//4. Otherwise, distance is positive: while distance  is not zero and target's nextSibling is defined 
		//   and is not a repetition template, set target to this nextSibling and, if it is a repetition block, 
		//   decrease distance by one. After the loop, set target to target's nextSibling (which may be null).
		else {
			while(distance != 0 && target.nextSibling && target.nextSibling.repetitionType != RepetitionElement.REPETITION_TEMPLATE){
				target = target.nextSibling;
				if(target.repetitionType == RepetitionElement.REPETITION_BLOCK)
					distance--;
			}
			target = target.nextSibling;
		}
		
		//5. Call the repetition block's parent node's insertBefore()  method with the newChild argument 
		//   being the repetition block and the refChild argument being target (which may be null by this 
		//   point). Mutation events are fired if appropriate. 
		this.parentNode.insertBefore(this, target);
		
		//Keep focus on the move button which was clicked
		if(this._clickedMoveBtn){
			this._clickedMoveBtn.focus();
			this._clickedMoveBtn = null;
		}
		
		//6. A moved event with no namespace, which bubbles but is not cancelable and has no default action, 
		//   must be fired on the element's repetition template (if it has one), using the RepetitionEvent 
		//   interface, with the repetition block's DOM node as the context information in the element  attribute.
		if(this.repetitionTemplate != null){
			var moveEvt;
			try {
				if(document.createEvent)
					moveEvt = document.createEvent("UIEvents"); //document.createEvent("RepetitionEvent")
				else if(document.createEventObject)
					moveEvt = document.createEventObject();
				RepetitionEvent._upgradeEvent.apply(moveEvt);
				moveEvt.initRepetitionEvent("moved", true /*canBubble*/, false /*cancelable*/, this);
				if(this.repetitionTemplate.dispatchEvent)
					this.repetitionTemplate.dispatchEvent(moveEvt);
				else if(this.repetitionTemplate.fireEvent){
					//console.warn("fireEvent('onmove') for MSIE is not yet working");
					//this.fireEvent('onmove', moveEvt);
				}
			}
			catch(err){
				moveEvt = new Object();
				RepetitionEvent._upgradeEvent.apply(moveEvt);
				moveEvt.initRepetitionEvent("moved", true /*canBubble*/, false /*cancelable*/, this);
			}
			
			//Add support for event handler set with HTML attribute---------------------
			var onmoveAttr = this.repetitionTemplate.getAttribute('onmove') 
			                   || /* deprecated */ this.repetitionTemplate.getAttribute('onmoved');
			
			//For MSIE, onmove is already an event, and attributes are equal to properties, so attribute value can be function.
			//  The 'event' argument must be added to the function argument list.
			var funcMatches;
			if(typeof onmoveAttr == 'function' && (funcMatches = onmoveAttr.toString().match(/^\s*function\s+anonymous\(\s*\)\s*\{((?:.|\n)+)\}\s*$/))){
				this.repetitionTemplate.onmove = new Function('event', funcMatches[1]);
			}
			
			//If the onmove attribute has been set but the property (method) has not
			if(onmoveAttr && !this.repetitionTemplate.onmove)
				this.repetitionTemplate.onmove = new Function('event', onmoveAttr);
			
			//This need not be done in MSIE since onmove is already an event, and attributes == properties
			//if(onmoveAttr && typeof onmoveAttr != 'function' /* for MSIE */ && 
			//      (!this.repetitionTemplate.onmove || typeof this.repetitionTemplate.onmove != 'function')
			//   ){
			//	this.repetitionTemplate.onmove = new Function('event', onmoveAttr);
			//}
			
			//Dispatch events for the old event model (extension to spec)
			if(this.repetitionTemplate.onmove)
				this.repetitionTemplate.onmove(moveEvt);
			else if(this.repetitionTemplate.onmoved) //deprecated
				this.repetitionTemplate.onmoved(moveEvt);
		}
		
		//In addition, user agents must automatically disable move-up buttons (irrespective of the 
		//   value of the disabled DOM attribute) when their repetition block could not be moved any 
		//   higher according to the algorithm above, and when the buttons are not in a repetition 
		//   block. Similarly, user agents must automatically disable move-down buttons when their 
		//   repetition block could not be moved any lower according to the algorithm above, and 
		//   when the buttons are not in a repetition block. This automatic disabling does not affect 
		//   the DOM disabled  attribute. It is an intrinsic property of these buttons.
		RepetitionElement.__updateMoveButtons(this.parentNode);
	},

	/*##############################################################################################
	 # other helper functions (not made into methods)
	 ##############################################################################################*/
	__getRepetitionBlock : function(node){
		while(node = node.parentNode){
			if(node.repetitionType == RepetitionElement.REPETITION_BLOCK){
				return node;
			}
		}
		return null;
	},
	
	__getHtmlTemplate : function(button){
		var attr = button.getAttribute('template');
		var node;
		if(attr && (node = document.getElementById(attr)) && node.repetitionType == RepetitionElement.REPETITION_TEMPLATE)
			return node;
		return null;
	},
	
	__updateAddButtons : function(rt){
		//In addition, user agents must automatically disable add buttons (irrespective of the value of the 
		//   disabled DOM attribute) when the buttons are not in a repetition block that has an associated 
		//   template and their template attribute is either not specified or does not have an ID that points 
		//   to a repetition template, and, when the repetition template's repeat-max attribute is less than 
		//   or equal to the number of repetition blocks that are associated with that template and that have 
		//   the same parent. This automatic disabling does not affect the DOM disabled attribute. It is an 
		//   intrinsic property of these buttons.
		
		var repetitionTemplates = rt ? [rt] : RepetitionElement._repetitionTemplates;
		
		//var btns = cssQuery("button[type=add]");
		var btns = RepetitionElement.__getElementsByNameAndAttribute.apply(document.body, ['button', 'type', 'add']);
		for(var i = 0; i < btns.length; i++){
			for(var t, j = 0; t = repetitionTemplates[j]; j++){
				if(btns[i].htmlTemplate == t && t.repetitionBlocks.length >= t.repeatMax){
					btns[i].disabled = true;
				}
			}
		}
	},
	
	__updateMoveButtons : function(parentNode){
		//In addition, user agents must automatically disable move-up buttons (irrespective of the value of 
		//   the disabled DOM attribute) when their repetition block could not be moved any higher according 
		//   to the algorithm above, and when the buttons are not in a repetition block. Similarly, user agents 
		//   must automatically disable move-down buttons when their repetition block could not be moved any 
		//   lower according to the algorithm above, and when the buttons are not in a repetition block. This 
		//   automatic disabling does not affect the DOM disabled  attribute. It is an intrinsic property of 
		//   these buttons.
		
		var i;
		var repetitionBlocks = [];
		
		//update all move buttons if a repetition block's parent was not given
		if(!parentNode){
			var visitedParents = [];
			//var repetitionBlocks = cssQuery('*[repeat]:not([repeat="template"])');
			var repetitionBlocks = RepetitionElement.__getElementsByProperty('repetitionType', RepetitionElement.REPETITION_BLOCK);
			for(i = 0; block = repetitionBlocks[i]; i++){
				if(!visitedParents.some(function(i){return i == block.parentNode})){
					RepetitionElement.__updateMoveButtons(block.parentNode);
					visitedParents.push(block.parentNode);
				}
			}
			return;
		}
		
		//get all of the repetition block siblings
		var j,btn,block;
		var child = parentNode.firstChild;
		while(child){
			if(child.repetitionType == RepetitionElement.REPETITION_BLOCK)
				repetitionBlocks.push(child);
			child = child.nextSibling;
		}
		
		//disable or enable movement buttons within each block
		for(i = 0; block = repetitionBlocks[i]; i++){
			//var moveUpBtns = cssQuery("button[type=move-up]", block);
			var moveUpBtns = RepetitionElement.__getElementsByNameAndAttribute.apply(block, ['button', 'type', 'move-up']);
			for(j = 0; btn = moveUpBtns[j]; j++){
				btn.disabled = 
					//if the button is not in a repetition block
					!(rb = RepetitionElement.__getRepetitionBlock(btn))
					 ||
					//when their repetition block could not be moved any lower
					(i == 0);
			}
			//var moveDownBtns = cssQuery("button[type=move-down]", block);
			var moveDownBtns = RepetitionElement.__getElementsByNameAndAttribute.apply(block, ['button', 'type', 'move-down']);
			for(j = 0; btn = moveDownBtns[j]; j++){
				btn.disabled = 
					//if the button is not in a repetition block
					!(rb = RepetitionElement.__getRepetitionBlock(btn))
					 ||
					//when their repetition block could not be moved any higher
					(i == repetitionBlocks.length-1);
			}
		}
	},
	
	/*##############################################################################################
	 # Generic DOM query functions
	 ##############################################################################################*/
	 
	__getElementsByProperty : function(propName, propValue){
		var els = [];
		var all = document.body.getElementsByTagName('*');
		for(i = 0; i < all.length; i++){
			if(all[i][propName] == propValue)
				els.push(all[i]);
		}
		return els;
	},
	
	__getElementsByTagNames : function(/* ... */){
		//IMPLEMENT XPATH
		var results = [];
		for(var i = 0; i < arguments.length; i++){
			var elements = this.getElementsByTagName(arguments[i]);
			for(var j = 0; j < elements.length; j++){
				results.push(elements[j]);
			}
		}
		return results;
		//sort with document order?
	},
	
	__getElementsByNameAndAttribute : function(elName, attrName, attrValue, isNotEqual){
		//IMPLEMENT XPATH
		var results = [];
		var all = this.getElementsByTagName(elName);
		for(var i = 0; i < all.length; i++){
			var thisAttrNode = all[i].getAttributeNode(attrName);
			var thisAttrValue = all[i].getAttribute(attrName); //MSIE needs getAttribute here for custom button types to be read
			if(thisAttrNode && (typeof attrValue == 'undefined' || (isNotEqual ? thisAttrValue != attrValue : thisAttrValue == attrValue) )){
				results.push(all[i]);
			}
		}
		return results;
	},

	//The following function enables MSIE to create elements with the name attribute set, per MSDN:
	//   The NAME attribute cannot be set at run time on elements dynamically created with the 
	//   createElement method. To create an element with a name attribute, include the attribute 
	//   and value when using the createElement method.
	__createElementWithName : function(type, name){
		throw Error("__createElementWithName not yet created. Browser-specific code defined immediately below.");
//		var element = document.createElement(type);
////		element.setAttribute('name', name);
////		if(element.getAttribute('name') != name){ //for MSIE
////			element = document.createElement('<' + type + ' name="' + name + '" />');
////		}
//		// First try the IE way; if this fails then use the standard way: http://www.easy-reader.net/archives/2005/09/02/death-to-bad-dom-implementations/
//		if (document.all)
//			element = document.createElement('<' + type + ' name="' + name + '" />');
//		else {
//			element = document.createElement(type);
//			element.setAttribute('name', name);
//		}
//		return element;
	}
};
//createElementWithName code by Anthony Lieuallen <http://www.easy-reader.net/archives/2005/09/02/death-to-bad-dom-implementations/#comment-444>
(function(){
	try {
		var el = document.createElement('<div name="foo">');
		if(el.tagName.toLowerCase() == 'div' || el.name != 'foo'){
			throw 'create element error';
		}
		RepetitionElement.__createElementWithName = function(tag, name){
			return document.createElement('<'+tag+' name="'+name+'"></'+tag+'>');
		};
	}
	catch(err){
		RepetitionElement.__createElementWithName = function(tag, name){
			var el = document.createElement(tag);
			el.setAttribute('name', name);
			//el.name = name;
			return el;
		};
	}
})();

//A repetition template should not be displayed. In CSS-aware user agents, this should be achieved by 
//including the following rules, or their equivalent, in the UA's user agent style sheet:
//   @namespace xh url(http://www.w3.org/1999/xhtml);
//   :not(xh|*)[xh|repeat="template"],
//   xh|*[|repeat="template"] { display: none; }
//if(document.styleSheets){
//	var style = document.createElement('style');
//	style.type = 'text/css';
//	//style.appendChild(document.createTextNode('@namespace xh url(http://www.w3.org/1999/xhtml);')); //XML
//	//style.appendChild(document.createTextNode(':not(xh|*)[xh|repeat="template"]')); //XML
//	//style.appendChild(document.createTextNode('xh|*[|repeat="template"] { display: none; }')); //XML
//	//style.appendChild(document.createTextNode("*[repeat='template'] { display:none; }")); //HTML
//	document.getElementsByTagName('head')[0].appendChild(style);
//	
//	var styleSheet = document.styleSheets[document.styleSheets.length-1];
//	var styleRules = [
//		//'@namespace xh url(http://www.w3.org/1999/xhtml);', //For XHTML
//		//':not(xh|*)[xh|repeat="template"]', //For XHTML
//		//'xh|*[|repeat="template"] { display: none; }', //For XHTML
//		//'*[repeat="template"] { display:none; }' //For HTML
//	];
//	if(styleSheet.insertRule) //Gecko/W3C
//		while(styleRules.length)
//			styleSheet.insertRule(styleRules.shift(), styleSheet.cssRules.length);
//	else if(styleSheet.addRule) //_MSIE
//		while(styleRules.length)
//			styleSheet.addRule(styleRules.shift());
//		
//}



/*##############################################################################################
 # RepetitionEvent
 ##############################################################################################*/

var RepetitionEvent = {};

//the following takes a UIEvent and adds the required properties for a RepetitionEvent
RepetitionEvent._upgradeEvent = function(){
	this.initRepetitionEvent = RepetitionEvent.initRepetitionEvent;
	this.initRepetitionEventNS = RepetitionEvent.initRepetitionEventNS;
};
RepetitionEvent.initRepetitionEvent = function(typeArg, canBubbleArg, cancelableArg, elementArg){
	if(this.initEvent)
		this.initEvent(typeArg, canBubbleArg, cancelableArg);
	else { //manually initialize event (i.e., for MSIE)
		this.type = typeArg;
//		switch(typeArg.toLowerCase()){
//			case 'added':
//				this.type = 'add';
//				break;
//			case 'removed':
//				this.type = 'remove';
//				break;
//			case 'moved':
//				this.type = 'move';
//				break;
//		}
		//this.srcElement = elementArg.repetitionTemplate;
		//this.cancelBubble = false;
		//this.cancelable = cancelableArg;
		//this.returnValue = false;
		
		if(!this.preventDefault)
		this.preventDefault = function(){
			this.returnValue = false;
		};
		if(!this.stopPropagation)
		this.stopPropagation = function(){
			this.cancelBubble = true;
		};
	}
	this.element = elementArg;
	this.relatedNode = elementArg; //for Opera (deprecated?)
};
RepetitionEvent.initRepetitionEventNS = function(namespaceURIArg, typeArg, canBubbleArg, cancelableArg, elementArg){
	throw Error("NOT IMPLEMENTED: RepetitionEvent.initRepetitionEventNS");
	//this.initEvent(namespaceURIArg, typeArg, canBubbleArg, cancelableArg);
	//this.element = elementArg;
	//this.relatedNode = elementArg; //for Opera (deprecated?)
};


/*##############################################################################################
 # Initializing the Repetition Model in the document
 ##############################################################################################*/
 
//Before load events are fired, but after the entire document has been parsed and after forms with data 
//   attributes are prefilled (if necessary), UAs must iterate through every node in the document, depth 
//   first, looking for templates so that their initial repetition blocks can be created. ... UAs should not 
//   specifically wait for images and style sheets to be loaded before creating initial repetition blocks 
//   as described above.
//   Some of the following code was borrowed from Dean Edwards, John Resig, et al <http://dean.edwards.name/weblog/2006/06/again/>

if(document.addEventListener){
	//onDOMload for Gecko and Opera
	document.addEventListener("DOMContentLoaded", function(){
		RepetitionElement._init_document();
	}, false);

	//for other browsers which do not support DOMContentLoaded use the following as a fallback to be called hopefully before all other onload handlers
	window.addEventListener("load", function(){
		RepetitionElement._init_document();
	}, false);
}
//old event model used as a last-resort fallback
else if(window.onload){ //if(window.onload != RepetitionElement._init_document)
	var oldonload = window.onload;
	window.onload = function(){
		RepetitionElement._init_document();
		oldonload();
	};
}
else window.onload = function(){
		RepetitionElement._init_document();
};

//onDOMload for Safari
if (/WebKit/i.test(navigator.userAgent)) { // sniff
	var _timer = setInterval(function() {
		if (/loaded|complete/.test(document.readyState)) {
			clearInterval(_timer);
			delete _timer;
			RepetitionElement._init_document(); // call the onload handler
		}
	}, 10);
}
//onDOMload for Internet Explorer (formerly using conditional comments)
else if(/MSIE/i.test(navigator.userAgent) && !document.addEventListener && window.attachEvent){
	//This following attached onload handler will attempt to be the first onload handler to be called and thus
	//  initiate the repetition model as early as possible if the DOMContentLoaded substitute fails.
	window.attachEvent("onload", function(){
		RepetitionElement._init_document();
	});
	
	//Dean Edward's first solution: http://dean.edwards.name/weblog/2005/09/busted/
	var match, dirname = ''; //get path to source directory
	var scripts = document.getElementsByTagName('head')[0].getElementsByTagName('script');
	for(var i = 0; i < scripts.length; i++){
		if(match = scripts[i].src.match(/^(.*)repetition-model[^\/]+$/))
			dirname = match[1];
	}
	//document.getElementsByTagName('*')[0].addBehavior(dirname + 'repetition-model.htc'); //use this if Behaviors are employed in 0.9
	document.write("<script defer src='" + dirname + "repetition-model-msie_init.js'><"+"/script>");

	//Dean Edward's revisited solution <http://dean.edwards.name/weblog/2005/09/busted/> (via Matthias Miller with insights from jQuery)
	//  Note that this solution will not result in its code firing before onload if there are no external images in the page; in this case, first solution above is used.
	document.write("<script id=__ie_onload defer src='//:'><\/script>"); //src value from jQuery
	var script = document.getElementById("__ie_onload");
	//var script = document.createElement('script');
	//script.setAttribute('defer', 'defer');
	//document.getElementsByTagName('head')[0].appendChild(script);
	script.onreadystatechange = function(){
		if(this.readyState == "complete"){
			RepetitionElement._init_document(); // call the onload handler
			this.parentNode.removeChild(this);
			
			//See issue #3 <http://code.google.com/p/repetitionmodel/issues/detail?id=3>
			//Sometimes cssQuery doesn't find all repetition templates from here within this DOMContentLoaded substitute
			if(RepetitionElement._repetitionTemplates.length == 0)
				RepetitionElement._initialized = false;
		}
	};
	script = null;
}

} //End If(!window.RepetitionElement...

//Extend the WebForms 2.0 Repetition Model to allow for the old event model
else if(document.addEventListener && 
        (typeof(RepetitionElement.oldEventModelEnabled) == 'undefined' || RepetitionElement.oldEventModelEnabled)
       ){
	RepetitionElement.oldEventModelEnabled = true;
	
	//added event----------------
	document.addEventListener("added", function(evt){
		if(!RepetitionElement.oldEventModelEnabled)
			return;
		if(!evt.element && evt.relatedNode) //Opera uses evt.relatedNode instead of evt.element as the specification dictates
			evt.element = evt.relatedNode;
		if(!evt.element || !evt.element.repetitionTemplate)
			return;
		
		var rt = evt.element.repetitionTemplate; 
		
		//Add support for event handler set with HTML attribute
		var onaddAttr = rt.getAttribute('onadd') || /* deprecated */ rt.getAttribute('onadded');
		if(onaddAttr && (!rt.onadd || typeof rt.onadd != 'function')) //in MSIE, attribute == property
			rt.onadd = new Function('event', onaddAttr);
		
		if(evt.element.repetitionTemplate.onadd)
			evt.element.repetitionTemplate.onadd(evt);
		else if(evt.element.repetitionTemplate.onadded) //deprecated
			evt.element.repetitionTemplate.onadded(evt);
	}, false);
	
	//removed event----------------
	document.addEventListener("removed", function(evt){
		if(!RepetitionElement.oldEventModelEnabled)
			return;
		if(!evt.element && evt.relatedNode) //Opera uses evt.relatedNode instead of evt.element as the specification dictates
			evt.element = evt.relatedNode;
		if(!evt.element || !evt.element.repetitionTemplate)
			return;
		
		var rt = evt.element.repetitionTemplate; 
		
		//Add support for event handler set with HTML attribute
		var onremoveAttr = rt.getAttribute('onremove') || /* deprecated */ rt.getAttribute('onremoved');
		if(onremoveAttr && (!rt.onremove || typeof rt.onremove != 'function')) //in MSIE, attribute == property
			rt.onremove = new Function('event', onremoveAttr);
		
		if(evt.element.repetitionTemplate.onremove)
			evt.element.repetitionTemplate.onremove(evt);
		else if(evt.element.repetitionTemplate.onremoved) //deprecated
			evt.element.repetitionTemplate.onremoved(evt);
	}, false);
	
	//moved event----------------
	document.addEventListener("moved", function(evt){
		if(!RepetitionElement.oldEventModelEnabled)
			return;
		if(!evt.element && evt.relatedNode) //Opera uses evt.relatedNode instead of evt.element as the specification dictates
			evt.element = evt.relatedNode;
		if(!evt.element || !evt.element.repetitionTemplate)
			return;
		
		var rt = evt.element.repetitionTemplate; 
		
		//Add support for event handler set with HTML attribute
		var onmoveAttr = rt.getAttribute('onmove') || /* deprecated */ rt.getAttribute('onmoved');
		if(onmoveAttr && (!rt.onmove || typeof rt.onmove != 'function')) //in MSIE, attribute == property
			rt.onmove = new Function('event', onmoveAttr);
		
		if(evt.element.repetitionTemplate.onmove)
			evt.element.repetitionTemplate.onmove(evt);
		else if(evt.element.repetitionTemplate.onmoved) //deprecated
			evt.element.repetitionTemplate.onmoved(evt);
	}, false);
}

//*** END REPETITION MODEL IMPLEMENTATION CODE ***************************************************************

if (!Array.prototype.some)
{	//http://www.dustindiaz.com/basement/sugar-arrays.html
	Array.prototype.some = function(fn, thisObj) {
		var scope = thisObj || window;
		for ( var i=0, j=this.length; i < j; ++i ) {
			if ( fn.call(scope, this[i], i, this) ) {
				return true;
			}
		}
		return false;
	};
}