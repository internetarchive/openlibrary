/******************************************************************************
 * All source and examples in this project are subject to the
 * following copyright, unless specifically stated otherwise
 * in the file itself:
 *
 * Copyright (c) 2007, Metaweb Technologies, Inc.
 * All rights reserved.
 * 
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *     * Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above
 *       copyright notice, this list of conditions and the following
 *       disclaimer in the documentation and/or other materials provided
 *       with the distribution.
 * 
 * THIS SOFTWARE IS PROVIDED BY METAWEB TECHNOLOGIES ``AS IS'' AND ANY
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL METAWEB TECHNOLOGIES BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
 * BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
 * OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
 * IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *****************************************************************************/
 
  
// Use existing freebase namespace
// if it exists
if (!window.freebase)
    window.freebase = {};

if (!window.freebase.controls)
    window.freebase.controls = {};

(function($, fb) {

/**
 * !!! NOTICE: This requires jQuery rev 3578 or higher !!!
 * 
 * Version 0.3
 */


/**
 * Apply the specified input control behavior to an input with the specified options
 * 
 * @param control:InputControl - @see InputControl 
 * @param options:Object - dictionary of options that overwrite control.default_options
 */
$.fn._freebaseInput = function(control, options) {
    if (!options) options = {};
    return this
        .attr("autocomplete", "off")
        .each(function() {
            control.release(this);
            $(this).unbind("focus", control.delegate("focus")).focus(control.delegate("focus")); 
            // we might be just resetting the options
            if (typeof this['fb_id'] == 'undefined')
                this.fb_id = control.counter++;
            // flush cache
            control.cache[this.fb_id] = null;
            // store options in hash
            var o = {};
            $.extend(o, control.default_options, options);
            control.option_hash[this.fb_id] = o;            
        });
};

/**
 * use firebug's console if it exists
 */
fb.log = fb.error = fb.debug = function() {};
if (typeof console != "undefined" && console.log && console.error) {
    fb.log = console.log;
    fb.error = console.error;
    fb.debug = console.debug;
};


/**
 * a function wrapper to be invoked within a context object (thisArg) with
 * additional parameters (argArray).
 * 
 * @param fn:Function - Function to run.
 * @param thisArg:Object - Context in which to run the function (thisArg)
 * @param argArray:Array - extra arguments to be appended to func's own arguments.
 *          So if a callback invokes func with an eventObject, func will be called
 *          with: func(arg1, arg2,..., argN, eventObject)
 */
fb.delegate = function(fn, thisArg, argArray)  {
    if (typeof argArray == "undefined") 
        argArray = [];
    var dg = function(){
        // 'arguments' isn't technically an array, so we can't just use concat
        var f_args = [];
        for(var i=0, len=arguments.length; i<len; i++)
          	f_args.push(arguments[i]);
        if (arguments.callee && arguments.callee.fn)
          return (arguments.callee.fn.apply(arguments.callee.thisArg, arguments.callee.argArray.concat(f_args)));
        return undefined;
    };

    dg.thisArg = thisArg;
    dg.fn = fn;
    dg.argArray = argArray;

    // clean up delegate on window.unload
    fb.autoclean(dg, fb.clean_delegate);

    return (dg);
};

/**
 * clean up a delegate
 */
fb.clean_delegate = function(f) {
    if (f) 
        f.thisArg = f.fn = f.argArray = null;      
};

/**
 * clean up an image object
 */
fb.clean_image = function(i) {
    if (i)
        i.onload = i.onerror = null;
};

/**
 * clean up fb expando variables on an object
 */
fb.clean_expando = function(obj) {
    if (obj) 
        delete obj.fb_data;        
};

// ---------------------------------------------------- autoclean
fb.AUTOCLEAN_HEAP = {};
fb.AUTOCLEAN_SERIAL_NO = 0;

fb.autoclean = function(obj, finalizer) {
    obj._autoclean_serial_no = fb.AUTOCLEAN_SERIAL_NO++;
    if (finalizer)
        obj._autoclean_finalizer = finalizer;
    fb.AUTOCLEAN_HEAP[obj._autoclean_serial_no] = obj;
};

fb.autoclean_gc = function() {
    for (var k in fb.AUTOCLEAN_HEAP) {
        var obj = fb.AUTOCLEAN_HEAP[k];
        if ('_autoclean_finalizer' in obj)
            obj._autoclean_finalizer(obj)
    }
    fb.AUTOCLEAN_HEAP = {};
}

fb.finalize = function(obj) {
    if (!obj || !('_autoclean_serial_no' in obj))
        return;
    var serial_no = obj._autoclean_serial_no;
    delete fb.AUTOCLEAN_HEAP[serial_no];
    if ('_autoclean_finalizer' in obj)
        obj._autoclean_finalizer(obj);
}

/**
 * call autoclean on window.unload
 */
$(window).unload(fb.autoclean_gc);

/**
 * simple state object
 */
fb.state = function() {};
fb.state.prototype = {
    enter: function(data) {},
    exit: function(data) {},
    handle: function(data) {}
};

/**
 * simple state machine
 */
fb.state_machine = function(states) {
    // states: [["STATE_NAME_1", state_1],...,["STATE_NAME_n", state_n]]
    this.current_state = null;
    this.states = {};
    var owner = this;
    $.each(states, function(i,n) {
        n[1].sm = owner;
        owner.states[n[0]] = n[1];
        if (i==0) 
            owner.current_state = n[0];
    });
    if (!this.current_state) 
        throw "StateMachine must be initialized with at least one state";
    this.states[this.current_state].enter();     
};
fb.state_machine.prototype = {    
    transition: function(to_state, exit_data, enter_data, data) { //fb.log("state_machine.transition current_state: ", this.current_state, "to_state: ", to_state);
        // to_state: the target destination state
        // exit_data: the exit data for current state
        // enter_data: the enter data for to_state
        // data: the data for to_state.handle        
        var target = this.states[to_state];
        if (!target) 
            throw("Unrecongized state:" + to_state);
    
        var source = this.states[this.current_state];

        // exit current state
        source.exit(exit_data);
    
        // enter target state
        target.enter(enter_data);

        this.current_state = to_state;        
        
        // handle data
        this.handle(data);
    },    
    handle: function(data) {
        if (data) 
            this.states[this.current_state].handle(data);
    }
};


/**
 * InputControl class
 */
fb.InputControl = function() {
    this.default_options = {};
    this.counter = 0;
    this.cache = {};
    this.option_hash = {};
    this.sm = null;
    this.delegates = {};
    this.manage_delay = 200;
    this.release_delay = 100;
};

fb.InputControl.prototype = {
    /**
     * facility to reuse delegate functions with different arguments
     */
    delegate: function(fname, argArray) {
        if (!this.delegates[fname])
            this.delegates[fname] = fb.delegate(this[fname], this);
        this.delegates[fname].argArray = argArray ? argArray : [];
        return this.delegates[fname];
    },

    options: function(input) {//fb.log("this.options", input);
        var o = this.option_hash[input.fb_id];
        if (!o) 
            throw "Unknown input";
        return o;
    },
    
    transition: function(state) {
        if (this.sm)
            this.sm.transition(state);
    },
    
    handle: function(data) {
        if (this.sm)
            this.sm.handle(data);  
    },
    
    /**
     * get input value, if null, return empty string ("")
     */
    val: function(input) {
        var v = $(input).val();
        if (v == null) 
            return "";
        return $.trim(v);
    },

    /**
     * get "name" or "text" field of an object. if none return "unknown"
     */
    name: function(obj) {
        // backwards compatibility with data.text and data.name  
        if (obj.text != null)
            return obj.text;
        if (obj.name != null)
            return obj.name;
        return "unknown";
    },

    /**
     * text change delay variable to length of string
     */
    delay: function(l) {
        var t = .3;
        if (l > 0)
            t = 1/(6 * (l-0.7)) + .3;
        return t * 1000;
    },   

    manage: function(input) {
        this.release(input);
        var owner = this;
        $.each(["blur", "keydown", "keypress", "keyup", "input", "paste"], function(i,n) {
           $(input).bind(n, owner.delegate(n));
        });
        this.transition("start");
        //this.handle({id:"TEXTCHANGE", input:input});        
        this.manage_hook(input);    
    },
    
    // over-ride to handle manage
    manage_hook: function(input) {},
    
    release: function(input) {//fb.log("release", input); 
        var owner = this;    
        $.each(["blur", "keydown", "keypress", "keyup", "input", "paste"], function(i,n) {
           $(input).unbind(n, owner.delegate(n)); 
        });
        this.transition("start");
        this.release_hook(input); 
    },
    
    // over-ride to handle release
    release_hook: function(input) {},

    focus: function(e) {//fb.log("on_focus", e);
        window.clearTimeout(this.manage_timeout);
        var input = e.target;    
        try {
            this.options(input);              
        }
        catch(e) {
            return;   
        }
        this.manage_timeout = window.setTimeout(this.delegate("manage", [input]), this.manage_delay);     
    },

    blur: function(e) {//fb.log("on_blur", e.target, this, this.dont_release, this._input); 
        window.clearTimeout(this.release_timeout);
        var input = $(e.target)[0];
        if (this.dont_release) {
            // the current input we are losing focus on
            // because we've clicked on the list/listitem
            this._input = input;
            return;
        }
        this.release_timeout = window.setTimeout(this.delegate("release", [input]), this.release_delay);
    },

    keydown: function(e) {//fb.log("on_keydown", e.keyCode);
        switch(e.keyCode) {
        	case 38: // up
        	case 40: // down
        	   // prevents cursor/caret from moving (in Safari)
        	   e.preventDefault();
        	   break;    
        	default:
        	   break;
        }
    },

    keypress: function(e) {//fb.log("on_keypress", e.keyCode);
        switch(e.keyCode) {
        	case 38: // up
        	case 40: // down
        	   // prevents cursor/caret from moving
        	   if (!e.shiftKey)
            	   e.preventDefault();
        	   break;
        	case 13: // return
                this.enterkey(e);
        		break ;
            case 27: // escape
                this.escapekey(e);
                break;    	   	   
        	default:
        	   break;
        } 
    },

    keyup: function(e) {//fb.log("on_keyup", e.keyCode);
        switch(e.keyCode) {
        	case 38: // up
        		e.preventDefault();
        		this.uparrow(e);
        		break;
        	case 40: // down
        		e.preventDefault();
        		this.downarrow(e);
        		break;
            case  9: // tab    		
            case 13: // enter
            case 16: // ctrl
            case 17: // shift
            case 18: // option/alt
            case 27: // escape
            case 37: // left
            case 39: // right
            case 224:// apple/command
                break;
        	default:
        	   this.textchange(e);
        	   break;
        } 
    },

    // Mozilla only, to detech paste
    input: function(e) {//fb.log("on_input", e);
        this.textchange(e);
    },
    
    // IE only, to detect paste
    paste: function(e) {//fb.log("on_paste", e);
        this.textchange(e);
    },

    uparrow: function(e) {
        this.handle({id:"UPARROW", input:e.target});    
    },

    downarrow: function(e) {
        this.handle({id:"DOWNARROW", input:e.target});
    },

    enterkey: function(e) {
        this.handle({id:"ENTERKEY", input:e.target, domEvent:e});
    },

    escapekey: function(e) {
        this.handle({id:"ESCAPEKEY", input:e.target});
    },

    textchange: function(e) {//fb.log("on_textchange", e.target); 
        window.clearTimeout(this.textchange_timeout);
        var txt = this.val(e.target);
        var delay = this.delay(txt.length);
        this.textchange_timeout = window.setTimeout(this.delegate("textchange_delay", [e.target]), delay);
    },
    
    textchange_delay: function(input){//fb.log("on_textchange_delay", input);    
        this.handle({id:"TEXTCHANGE", input:input});
    }   
};

/**
 * InputSelectControl class
 * superClass: InputControl
 */
fb.InputSelectControl = function() {
    fb.InputControl.call(this);
    this.min_len = 1;
    this.fudge = 8;
    this.loadmsg_delay = 500;
    
    /**
     * initialize the select state machine
     * 
     * states:
     *      start: 
     *      getting:
     *      selecting:
     */
    this.sm = new fb.state_machine([
        ["start", new state_start(this)],
        ["getting", new state_getting(this)],
        ["selecting", new state_selecting(this)]
    ]);
};
// inheritance: prototype/constructor chaining
fb.InputSelectControl.prototype = new fb.InputControl();
fb.InputSelectControl.prototype.constructor = fb.InputSelectControl;

// shorthand for fb.InputSelectControl.prototype
var p = fb.InputSelectControl.prototype;

p.release_hook = function(input) {
    this.list_hide();
};

p.click_listitem = function(li) {//fb.log("click_listitem", li, this._input);
    this.handle({id:"LISTITEM_CLICK", item:li, input:this._input});
};

p.mousedown_list = function(e) {//fb.log("mousedown_list", e, this);
    // hack in IE/safari to keep suggestion list from disappearing when click/scrolling
    this.dont_release = true;    
};

p.mouseup_list = function(e) {//fb.log("mouseup_list", e, this, this._input);
    // hack in IE/safari to keep suggestion list from disappearing when click/scrolling
    if (this._input) {
        $(this._input).unbind("focus", this.delegate("focus")); 
        $(this._input).focus();
        window.setTimeout(this.delegate("reset_focus", [this._input]), 0);
        //$(this._input).focus(this.delegate("focus"));
    }
    this.dont_release = false;
};

p.reset_focus = function(input) {
    $(input).focus(this.delegate("focus"));
};

p.list_load = function(input) {//fb.log("list_load", input);
    throw "You must override InputSelectControl.prototype.list_load";
};

p.list_receive = function(input, txt, o) {//fb.log("list_receive", input, query, o);
    // handle errors
    if (o.status !== '200 OK') {
        fb.error("list_receive", o.code, o.messages, o);
        return;
    }

    // currently, list_receive recognizes results of the forms:
    // 1. { list: { listItems: [...] } }
    // 2. { results: [...] }
    // 3. { result: [...] }
    // 4. { query: { result: [...] } }
    var result = [];
    if ("list" in o && "listItems" in o.list)
        result = o.list.listItems;
    else if ("result" in o)
        result = o.result;
    else if ("results" in o)
        result = o.results;
    else if ("query" in o && "result" in o.query) 
        result = o.query.result;
    else {
        fb.error("list_receive", o.code, "Unrecognized list result", o);
        return;
    }

    // hook to update cache
    this.list_receive_hook(input, txt, result);
    
    // handle result    
    this.handle({id:"LIST_RESULT", input:input, result:result});
};

p.list_receive_hook = function(input, txt, result) { 
    // overwrite to process search result
    // like updating the cache
};

p.list_show = function(input, result) {//fb.log("list_show", input, result);
    if (!input) 
        return;
    if (!result) 
        result = [];
    var options = this.options(input);  
    var txt = this.val(input);
    var list = null;
    if (!$("#fbs_list").length) {
        $(document.body)
            .append(
                '<div style="display:none;position:absolute" id="fbs_list" class="fbs-topshadow">' +
                    '<div class="fbs-bottomshadow">'+
                        '<ul class="fbs-ul"></ul>' +
                    '</div>' +
                '</div>');

        list = $("> .fbs-ul")[0];
    }
    if (!list) 
        list = $("#fbs_list > .fbs-bottomshadow > .fbs-ul")[0];

    $("#fbs_list > .fbs-bottomshadow")
        .unbind()
        .mousedown(this.delegate("mousedown_list"))
        .mouseup(this.delegate("mouseup_list"))
        .scroll(this.delegate("mousedown_list"));

    
    // unbind all li events and empty list
    $("li", list)
        .each(function(i,n) {
            $(n).unbind();
        });
    $(list).empty();
        
    var filter = this.filter;
    if (typeof options.filter == "function")
        filter = options.filter;
    
    if (!result.length)
        $(list).append(this.create_list_item({id:"NO_MATCHES", text:"no matches"}, null, options).addClass("fbs-li-nomatch"));

    
    var filtered = [];
    $.each(result, function(i, n) {
        if (filter.apply(null, [n, txt]))
            filtered.push(n);
    });
    filtered = this.filter_hook(filtered, result);
    var owner = this;    
    $.each(filtered, function(i, n) {
        $(list).append(owner.create_list_item(n, txt, options));
    });
    
    // hook to add additional html elemments and handlers
    // like "Create New" item under the list
    this.list_show_hook(list, input, options);

    var pos = $(input).offset({border: true, padding: true});
    var top = pos.top + input.clientHeight + this.fudge;
    $("#fbs_list")
        .css({top:top, left:pos.left, width:options.width})
        .show();
};

p.list_show_hook = function(list, input, options) { };

p.filter_hook = function(filtered, result) {
    return filtered;  
};

p.list_hide = function() {//fb.log("list_hide");
    $("#fbs_list").hide();
    this.list_hide_hook();
};

p.list_hide_hook = function() {};

p.create_list_item = function(data, txt, options) {
    var li = $("<li class='fbs-li'></li>")[0];
    
    var trans = this.transform;
    if (typeof options.transform == "function")
        trans = options.transform;

    var html = trans.apply(this, [data, txt]); 
   
    $(li).append(html);

    // sometimes data contains text and/or name
    if ("text" in data)
        data.name = data.text;
    
    li.fb_data = data;
    fb.autoclean(li, fb.clean_expando);
    
    var owner = this;
    return $(li)
        .mouseover(function(e) { 
            owner.list_select(null, this, options); 
        })
        .click(function(e) { 
            owner.click_listitem(this); 
        });
};

/**
 * The default filter
 * 
 * @param data - The individual item from the ac_path service.
 * @return TRUE to include in list or FALSE to exclude from list.
 */
p.filter = function(data, txt) {
    return true;  
};

/**
 * The default transform
 * 
 * @param data - The individual item from the ac_path service
 * @param txt - The input string
 * @param options - Options used for the input
 * @return a DOM element or html that will be appended to an <li/>
 */
p.transform = function(data, txt) {
    return data;
};

/**
 * show loading message
 */
p.loading_show = function(input) {
    this.list_hide();
    if (!$("#fbs_loading").length) {
        $(document.body)        
            .append(
                '<div style="display:none;position:absolute" id="fbs_loading" class="fbs-topshadow">' +
                    '<div class="fbs-bottomshadow">'+
                        '<ul class="fbs-ul">' +
                            '<li class="fbs-li">'+ 
                                '<div class="fbs-li-name">loading...</div>' +
                            '</li>' +
                        '</ul>' +
                    '</div>' +
                '</div>');        
    }
    var options = this.options(input);
    var pos = $(input).offset({border: true, padding: true});
    
    var top = pos.top + input.clientHeight + this.fudge;
    $("#fbs_loading")
        .css({top:top, left:pos.left, width:options.width})
        .show();
};

/**
 * hide loading message
 */
p.loading_hide = function() {
    $("#fbs_loading").hide();     
};

p.list_select = function(index, li, options) {
    var sli = null;
    $("#fbs_list > .fbs-bottomshadow > .fbs-ul > li").each(function(i,n) {
        if (i == index || li == n) {
            $(n).addClass("fbs-li-selected");
            sli = n;
        }
        else 
            $(n).removeClass("fbs-li-selected");
    });
    this.list_select_hook(sli, options);
    return sli;
};

/**
 * list select hook
 * @param sli - list item (li) html element
 */
p.list_select_hook = function(sli, options) { };

p.list_length = function() {
    return $("#fbs_list > .fbs-bottomshadow > .fbs-ul > li").length;
};

p.list_selection = function(returnObj) {
    if (!returnObj) 
        returnObj = {};
    returnObj.index = -1;
    returnObj.item = null;
    $("#fbs_list > .fbs-bottomshadow > .fbs-ul > li").each(function(i,n){
        if (n.className.indexOf("fbs-li-selected") != -1) {
            returnObj.index = i;
            returnObj.item = n;
            return false;
        }
    });
    return returnObj;
}

p.list_select_next = function(options) {
    var len = this.list_length();
    var obj = this.list_selection();
    var index = obj.index+1;
    if (index >=0 && index < len)
        return this.list_select(index, null, options);
    else if (options.soft)
        return this.list_select(null, null, options);
    else if (len > 0)
        return this.list_select(0, null, options);
    return null;
};

p.list_select_prev = function(options) {
    var len = this.list_length();
    var obj = this.list_selection();
    var index = obj.index-1;
    if (index >=0 && index < len)
        return this.list_select(index, null, options);
    else if (options.soft) {
        if (index < -1 && len > 0) 
            return this.list_select(len - 1, null, options);
        else 
            return this.list_select(null, null, options);
    }
    else if (len > 0)
        return this.list_select(len - 1, null, options);
    return null;
};

p.scroll_into_view = function(elt, p) {
    if (elt) 
        elt.scrollIntoView(false);
};

/**
 * emphasize part of the html text with <em/>
 */
p.em_text = function(text, em_str) {
    var em = text;
    var index = text.toLowerCase().indexOf(em_str.toLowerCase());
    if (index >= 0) {    
        em = text.substring(0, index) + 
        '<em class="fbs-em">' +
        text.substring(index, index+em_str.length) +
        '</em>' +
        text.substring(index + em_str.length);
    }  
    return em;
};

p.caret_last = function(input) {
    var l = this.val(input).length;
    if (input.createTextRange) {
        // IE
        var range = input.createTextRange();;
        range.collapse(true);
        range.moveEnd("character", l);
        range.moveStart("character", l);
        range.select();
    }
    else if (input.setSelectionRange) {
        // mozilla
        input.setSelectionRange(l, l);
    }    
};

/**
 * base class for all select states
 * @param c:InputSelectControl
 */
function select_state(c) {
    fb.state.call(this);
    this.c = c;
};
// inheritance: prototype/constructor chaining
select_state.prototype = new fb.state();
select_state.prototype.constructor = select_state;

/**
 * state: start
 */
function state_start(c) {
    select_state.call(this, c);
};
// inheritance: prototype/constructor chaining
state_start.prototype = new select_state();
state_start.prototype.constructor = state_start;

state_start.prototype.handle = function(data) {//fb.log("state_start.handle", data);
    if (!data || !data.input) 
        return;
    var options = this.c.options(data.input);
    switch (data.id) {
        case "TEXTCHANGE":
        case "DOWNARROW":
            var txt = this.c.val(data.input);
            if (txt.length >= this.c.min_len)
                this.sm.transition("getting", null, data);
            else 
                this.c.list_hide();
            break;
        case "ENTERKEY":
            $(data.input).trigger("fb-submit", [{name:this.c.val(data.input)}]);
            break;
        default:
            break;
    };
};

/**
 * state: getting
 */
function state_getting(c) {
    select_state.call(this, c);
};
// inheritance: prototype/constructor chaining
state_getting.prototype = new select_state();
state_getting.prototype.constructor = state_getting;

state_getting.prototype.enter = function(data) {//fb.log("state_getting.enter", data); 
    window.clearTimeout(this.loadmsg_timeout);
    if (!data || !data.input) 
        return;
    // show loading msg
    this.loadmsg_timeout = window.setTimeout(this.c.delegate("loading_show", [data.input]), this.c.loadmsg_delay);    
    // request autocomplete url
    this.c.list_load(data.input);
};
state_getting.prototype.exit = function(data) {//fb.log("state_getting.exit", data); 
    // hide loading msg
    window.clearTimeout(this.loadmsg_timeout);
    this.c.loading_hide();
};
state_getting.prototype.handle = function(data) {//fb.log("state_getting.handle", data);
    if (!data || !data.input) 
        return;
    var options = this.c.options(data.input);    
    switch (data.id) {
        case "TEXTCHANGE":
            this.sm.transition("start", null, null, data);
            break;
        case "LIST_RESULT":
            this.sm.transition("selecting", null, data);
            break;
        case "ENTERKEY":      
            $(data.input).trigger("fb-submit", [{name:this.c.val(data.input)}]);            
            break;
        case "ESCAPEKEY":
            this.c.list_hide();
            this.sm.transition("start");
            break;            
        default:
            break;
    };
};

/**
 * state: selecting
 */
function state_selecting(c) {
    select_state.call(this, c);
};
// inheritance: prototype/constructor chaining
state_selecting.prototype = new select_state();
state_selecting.prototype.constructor = state_selecting;

state_selecting.prototype.enter = function(data) {//fb.log("state_selecting.enter", data);    
    if (!data || !data.input || !data.result) 
        return;
    this.c.list_show(data.input, data.result);
    var options = this.c.options(data.input);
    if (!options.soft)
        this.c.list_select(0, null, options);
};
state_selecting.prototype.exit = function(data) {//fb.log("state_selecting.exit", data);    
    this.c.list_select(null);
};
state_selecting.prototype.handle = function(data) {//fb.log("state_selecting.handle", data);
    if (!data || !data.input) 
        return;    
    var options = this.c.options(data.input);
    switch (data.id) {
        case "TEXTCHANGE":
            this.sm.transition("start", null, null, data);
            break;
        case "DOWNARROW":
            $("#fbs_list").show();
            var li = this.c.list_select_next(options);
            this.c.scroll_into_view(li);
            break;
        case "UPARROW":
            $("#fbs_list").show();        
            var li = this.c.list_select_prev(options);
            this.c.scroll_into_view(li);
            break;
        case "ENTERKEY":
            var s = this.c.list_selection();
            if (s.index == -1 || !s.item) {
                this.sm.transition("start", null, null, data);
                return;
            }
            if ($("#fbs_list").css("display") != "none")
                data.domEvent.preventDefault();
            else {              
                $(data.input).trigger("fb-submit", [s.item.fb_data]);
                return;   
            }
            data.id = "LISTITEM_CLICK";
            data.item = s.item;
            // let it fall directly into
            // 'case "LISTITEM_CLICK":'
        case "LISTITEM_CLICK":
            if (!data.item) 
                return;
            switch(data.item.fb_data.id) {
                case "NO_MATCHES":
                    break;
                default:
                    var txt = $(".fbs-li-name", data.item).text();
                    $(data.input).val(txt);
                    this.c.caret_last(data.input);
                    $(data.input).trigger("fb-select", [data.item.fb_data])
                        .trigger("suggest", [data.item.fb_data]); // legacy - for compatibility
                    this.c.list_hide();
                    break;
            }            
            break;
        case "ESCAPEKEY":
            this.c.list_hide();        
            this.sm.transition("start");
            break;            
        default:
            break;
    };
};


function use_jsonp(options) {
    // if we're on the same host, then we don't need to use jsonp. This
    // greatly increases our cachability
    if (!options.service_url)
        return false;             // no host == same host == no jsonp
    var pathname_len = window.location.pathname.length;
    var hostname = window.location.href;
    var hostname = hostname.substr(0, hostname.length - pathname_len);
    //console.log("Hostname = ", hostname);
    if (hostname == options.service_url)
        return false;

    return true;
}  
/**
 * freebaseSelect() allows one to select from an enumeration of freebase topics
 * of a certain freebase type under an input box.
 * 
 * freebaseSelect accepts a single argument which is an options Object with
 * the following attributes:
 *
 * width:       This is the width of the suggestion list and the flyout in
 *              pixels. Default is 275.
 * 
 * service_url: This the base url to all the api services like autocomplete,
 *              blurbs and thumbnails. Default is "http://www.freebase.com".
 * 
 * mqlread_path: The path to the mql service. Default is "/api/service/mqlread".
 * 
 * type:        The freebase type id to enumerate on. Default is "/location/us_state".
 * 
 * limit:       The max number of instances to show.
 * 
 * In addition, freebaseSelect will trigger the following events on behalf of
 * the input it's attached to. They include:
 * 
 * fb-select:       Triggered when something is selected from the selection
 *                  list. The data object will contain id and name fields:
 *                  { id: aString, name: aString }.
 *
 * @example
 * $('#myInput')
 *      .freebaseSelect({type:"/location/us_state", limit: 50}) * 
 *      .bind('fb-select', function(e, data) { console.log('select: ', data.id); })
 * 
 * @desc Choose from an enumeration of all the 50 States.
 *
 * @name   freebaseSelect
 * @param  options  object literal containing options
 * @return jQuery
 * @cat    Plugins/Freebase
 * @type   jQuery
 */
$.fn.freebaseSelect = function(options) {
    return $(this)._freebaseInput(fb.select.getInstance(), options);
};

function SelectControl() { 
    fb.InputSelectControl.call(this);
    this.default_options = {
        width: 275,   // width of list and flyout
        service_url: "http://www.freebase.com",
        mqlread_path: "/api/service/mqlread",
        type: "/location/us_state",
        limit: 100,
        filter: null,
        transform: null
    };
    this.min_len = 0;    
};
// inheritance: prototype/constructor chaining
SelectControl.prototype = new fb.InputSelectControl();
SelectControl.prototype.constructor = SelectControl;

SelectControl.instance = null;
SelectControl.getInstance = function() {
    if (!SelectControl.instance)
        SelectControl.instance = new SelectControl();
    return SelectControl.instance;
};

// shorthand for SelectControl.prototype
var p = SelectControl.prototype;

p.list_load = function(input) {//fb.log("list_load", input);
    if (!input) 
        return;
    if (!"fb_id" in input) 
        return;
    var txt = this.val(input);
    if (this.cache[input.fb_id]) {
        //fb.log("load from cache: ", this.cache[input.fb_id]);
        window.clearTimeout(this.handle_timeout);
        this.handle_timeout = window.setTimeout(this.delegate("handle", [{id:"LIST_RESULT", input:input, result:this.cache[input.fb_id]}]), 0);
        return;
    }
    var options = this.options(input);    
    // mql read
    var q = '{' +
        '"query":{' +
            '"query":[{' +
                '"name":null,' +
                '"id":null,' +   
                '"sort":"name",' +                               
                '"type":"'+options.type+'",'+
                '"limit":'+options.limit +
            '}]' +
        '}' +
    '}';
    var param = {queries: q};
    $.ajax({
        type: "GET",
		url: options.service_url + options.mqlread_path,
		data: param,
		success: this.delegate("list_receive", [input, txt]),
		dataType: use_jsonp(options) ? "jsonp" : "json",
		cache: true
	});
};

p.list_receive_hook = function(input, txt, result) {
    // update cache
    this.cache[input.fb_id] = result;
};

p.list_show_hook = function(list, input, options) {    
    $(list).next(".fbs-selectnew").hide();
};

p.transform = function(data, txt) {
    var div = document.createElement("div");
    $(div).append('<div class="fbs-li-name"></div>');
    var text = $(".fbs-li-name", div).append(document.createTextNode(data.name)).text();
    return div.innerHTML;    
};

p.filter = function(data, txt) {
    if (txt == "")
        return true;
    return data.name && data.name.toLowerCase().indexOf(txt.toLowerCase()) == 0;
};

p.filter_hook = function(filtered, result) {
    if (!filtered.length)
        return result;
    return filtered;
};

p.delay = function(l) {
    return 0;
};

fb.select = SelectControl;





})(jQuery, window.freebase.controls);
