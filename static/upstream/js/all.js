function setup_account_create() {
    $("#signup").validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            if (errors) {
                var message = (errors == 1 ? "Hang on... you missed 1 field. It's highlighted below." : "Hang on...you missed some fields.They 're highlighted below.");
                $("div#contentMsg span").html(message);
                $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
            } else {
                $("div#contentMsg").hide();
            }
        },
        errorClass: "invalid",
        validClass: "success",
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find("label[for=" + element.id + "]")
            .addClass(errorClass);
        }
    });
    $("#email").rules("add", {
        required: true,
        email: true,
        messages: {
            required: "",
            email: "Are you sure that's an email address?"
        }
    });
    $("#username").rules("add", {
        required: true,
        minlength: 3,
        maxlength: 20,
        messages: {
            required: "",
            minlength: jQuery.format("This has to be at least {0} characters."),
            maxlength: jQuery.format("Sorry! This can't exceed {0} characters.")
        }
    });
    $("#password").rules("add", {
        required: true,
        messages: {
            required: ""
        }
    });
    
    // CHECK USERNAME AVAILABILITY
    $('#usernameLoading').hide();
    $('#emailLoading').hide();

};

/*
  function finishAjaxUsername(id, response) {
    $('#usernameLoading').hide();
    $('#'+id).html(unescape(response));
    $('#'+id).customFadeIn();
  } 
  //finishAjax

  // CHECK EMAIL ASSOCIATION
  function validateCheckEmail() {
    $('#emailLoading').hide();
    $('#email').blur(function(){
      $('#emailLoading').show();
      $.post("checkemail.php", {
        email: $('#email').val()
      }, function(response){
        $('#emailResult').customFadeOut();
        setTimeout("finishAjaxEmail('emailResult', '"+escape(response)+"')", 400);
      });
        return false;
    });
  });

  function finishAjaxEmail(id, response) {
    $('#emailLoading').hide();
    $('#'+id).html(unescape(response));
    $('#'+id).customFadeIn();
  } 
  //finishAjax 
  */

//RECAPTCHA
var RecaptchaOptions = {
    theme: 'custom',
    tabindex: 4,
    custom_theme_widget: 'recaptcha_widget'
};


function validateEmail() {
    $("form.email").validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            if (errors) {
                var message = errors == 1 ? 'Hang on... You forgot to provide an updated email address.' : 'Hang on... You forgot to provide an updated email address.';
                $("div#contentMsg span").html(message);
                $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
            } else {
                $("div#contentMsg").hide();
            }
        },
        errorClass: "invalid",
        validClass: "success",
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find("label[for=" + element.id + "]")
            .addClass(errorClass);
        }
    });
    $("#email").rules("add", {
        required: true,
        email: true,
        messages: {
            required: "",
            email: "Are you sure that's an email address?"
        }
    });
};

function validateDelete() {
    $("form.delete").validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            if (errors) {
                var message = (errors == 1 ? 'You need to click the box to delete your account.': 'You need to click the box to delete your account.');
                $("div#contentMsg span").html(message);
                $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
            } else {
                $("div#contentMsg").hide();
            }
        },
        errorClass: "invalid",
        validClass: "success",
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find("label[for=" + element.id + "]")
            .addClass(errorClass);
        }
    });
    $("#delete").rules("add", {
        required: true,
        messages: {
            required: ""
        }
    });
};

function validateLogin() {
    $(".login").validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            if (errors) {
                var message = (errors == 1? "Hang on... you missed 1 field. It's highlighted below.": "Hang on...you missed both fields.They 're highlighted below.");
                $("div#contentMsg span").html(message);
                $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
            } else {
                $("div#contentMsg").hide();
            }
        },
        errorClass: "invalid",
        validClass: "success",
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find("label[for=" + element.id + "]")
            .addClass(errorClass);
        }
    });
    $("#username").rules("add", {
        required: true,
        minlength: 3,
        maxlength: 20,
        messages: {
            required: "",
            minlength: jQuery.format("This has to be at least {0} characters."),
            maxlength: jQuery.format("Sorry! This can't exceed {0} characters.")
        }
    });
    $("#password").rules("add", {
        required: true,
        messages: {
            required: ""
        }
    });
};
function validatePassword() {
    $("form.password").validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            if (errors) {
                var message = (errors == 1? 'Hang on... you missed a field.': 'Hang on... to change your password, we need your current and your new one.');
                $("div#contentMsg span").html(message);
                $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
            } else {
                $("div#contentMsg").hide();
            }
        },
        errorClass: "invalid",
        validClass: "success",
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find("label[for=" + element.id + "]")
            .addClass(errorClass);
        }
    });
    $("#password").rules("add", {
        required: true,
        messages: {
            required: "."
        }
    });
    $("#new_password").rules("add", {
        required: true,
        messages: {
            required: ""
        }
    });
};

function validateReminder() {
    $("form.reminder").validate({
        invalidHandler: function(form, validator) {
            var errors = validator.numberOfInvalids();
            if (errors) {
                var message = (errors == 1 ? 'Hang on... to change your password, we need your email address.' : 'Hang on... to change your password, we need your email address.');
                $("div#contentMsg span").html(message);
                $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
            } else {
                $("div#contentMsg").hide();
            }
        },
        errorClass: "invalid",
        validClass: "success",
        highlight: function(element, errorClass) {
            $(element).addClass(errorClass);
            $(element.form).find("label[for=" + element.id + "]")
            .addClass(errorClass);
        }
    });
    $("#email").rules("add", {
        required: true,
        email: true,
        messages: {
            required: "",
            email: "Are you sure that's an email address?"
        }
    });
};

/**
 * jQuery plugin to add new field in edition edit form.
 * 
 * Usage:
 *     $("select#role").add_new_field({href: "#role-popup"});
 * 
 * Conventions:
 *     - value of option "select xxx" must be ""
 *     - value of option "add new xxx" must be "__add__"
 *     - the popup should have a form and the type of add button must be "submit".
 *     - On submit:
 *         - JSON of the form input is appended to a hidden field with name this.id + "_json"
 *         - new option is added to the select box with value=d.value || d.label and contents=d.label, where d is the form data.
 *     - On cancel/close:
 *         - value of the select is set to "" to select "select xxx"
 */
;(function($){
    $.fn.add_new_field = function(_options) {
        $(this).each(function() {
            var options = _options || {href: "#" + this.id + "-popup"};
            var $this = $(this);
            
            var $json = $('<input type="hidden">')
                        .attr("name", this.id + "-json")
                        .addClass("repeat-ignore") // tell repeat plugin to ignore this input
                        .val("[]")
                        .insertBefore($this);
            
            $this.change(function(){
                var value = $this.val();
                if (value == "__add__") {
                    if (options.onshow) {
                        options.onshow.apply($this, []);
                    }
                    $.fn.colorbox({
                       inline: true,
                       opacity: "0.5",
                       href: options.href,
                       open: true
                    });
                }
            });
        
            // handle cancel
            $(options.href).bind("cbox_closed", function() {
           
               if ($this.val() == "__add__") {
                   $this.val("");
                   $this.focus();
               }
               if (options.cancel) {
                   options.cancel();
               }
            });
        
            // handle submit
            $("form:first", $(options.href)).submit(function(event) {
                event.preventDefault();
                
                // extract data
                var array = $(this).serializeArray();
                var d = {};
                
                for (var i in array) {
                    d[array[i].name] = $.trim(array[i].value);
                }
                
                // validate
                if (options.validate && options.validate.apply($this, [d]) == false) {
                    return;
                }
                
                // close popup
                $.fn.colorbox.close();
                
                // add new option
                $("<option/>")
                    .html(d.label || d.value)
                    .attr("value", d.value)
                    .insertBefore($this.find("option:last").prev()) // insert before ---
                    .parent().val(d.value);
                    
                // add JSON to hidden field
                try {
                    var data = JSON.parse($json.val());
                } 
                catch (err) {
                    var data = [];
                }
                data.push(d);
                $json.val(JSON.stringify(data));
                
                // finally focus the next input field
                $this.focusNextInputField();
            });
            return this;
        });
    };
})(jQuery);

// jquery plugins to provide author and language autocompletes.

;(function($) {    
    // author-autocomplete
    $.fn.author_autocomplete = function(options) {
        var local_options = {
            minChars: 2,
            max: 11,
            addnew: true,  
            autoFill: false,
            formatItem: function(item) {
                if (item.key == "__new__") {
                    return '' + 
                        '<div class="ac_author ac_addnew" title="Add a new author">' + 
                            '<span class="action">' + _('Or, create a new author record for') + '</span>' +
                            '<span class="name">' + item.name + '</span>' +
                        '</div>'
                }
                else if (item.work_count == 0) {
                    return '<div class="ac_author" title="Select this author">' + 
                               '<span class="name">' + item['name'] + '</span>' +
                               '<span class="subject">Open Library has no books associated with ' + item['name'] +'</span>' +  
                           '</div>';
                }
                else if (item.work_count == 1) {
                    return '<div class="ac_author" title="Select this author">' + 
                               '<span class="name">' + item['name'] + '</span>' +
                               '<span class="books">1 book</span> <span class="work">titled <i>' + (item.works[0]) + '</i></span><br/>' + 
                               '<span class="subject">Subjects: ' + (item.subjects && item.subjects.join(", ") || "") + '</span>' +  
                           '</div>';
                }
                else {
                    return '<div class="ac_author" title="Select this author">' + 
                               '<span class="name">' + item['name'] + '</span>' +
                               '<span class="books">' + (item.work_count) + ' books</span>' + 
                               ' <span class="work">including <i>' + (item.works && item.works[0] || "") + '</i></span><br/>' + 
                               '<span class="subject">Subjects: ' + (item.subjects && item.subjects.join(", ") || "") + '</span>' +  
                           '</div>';
                }
            }
        };
        
        $(this).each(function() {
            setup_autocomplete(this, "/authors/_autocomplete", options, local_options);
        });
    }

    // language-autocomplete
    $.fn.language_autocomplete = function(options) {
        var local_options = {
            max: 6,
            formatItem: function(item) {
                return sprintf(
                    '<div class="ac_author" title="%s"><span class="name">%s</span></div>', 
                    _("Select this language"),
                    item.name);
            }
        };
        
        $(this).each(function() {
            setup_autocomplete(this, "/languages/_autocomplete", options, local_options);
        });
    }

    function setup_autocomplete(_this, url, options, local_options) {
        options = $.extend(options, local_options);
        
        var default_options = {
            autoFill: true,
            mustMatch: true,
            parse: function(text) {
                var rows = eval(text).slice(0, options.max-1);                
                var parsed = [];
                for (var i=0; i < rows.length; i++) {
                    var row = rows[i];
                    parsed[parsed.length] = {
                        data: row,
                        value: row.name,
                        result: row.name
                    };
                }
                if (options.addnew) {
                    // XXX: this won't work when _this is multiple values (like $("input"))
                    var name = $(_this).val();
                    parsed[parsed.length] = {
                        data: {name: name, key: "__new__"},
                        value: name,
                        result: name
                    }
                }
                return parsed;
            },
            formatMatch: function(item) {
                return item.name;
            }
        };
        
        $(_this)
            .autocomplete(url, $.extend(default_options, options))
            .result(function(event, item) {
                $("#" + this.id + "-key").val(item.key); 
                var $this = $(this);
            
                //adding class directly is not working when tab is pressed. setTimeout seems to be working!
                setTimeout(function() {
                    $this.addClass("accept");
                }, 0);
            })
            .nomatch(function(){
                $("#" + this.id + "-key").val(""); 
                $(this).addClass("reject");                                
            })
            .keypress(function() {
                $(this).removeClass("accept").removeClass("reject");
            });
    }
})(jQuery);

/**
 * Setup actions on document.ready for standard classNames.
 */

jQuery(function($) {
    // close-popup
    $("a.close-popup").click(function() {
        $.fn.colorbox.close();
    });

    // wmd editor
    $("textarea.markdown").wmd({
        helpLink: "/help/markdown",
        helpHoverTitle: "Formatting Help",
        helpTarget: "_new"
    });

    // tabs
    var options = {};
    if($.support.opacity){
        options.fx = {"opacity": "toggle"};
    }
    $(".tabs:not(.ui-tabs)").tabs(options)
    $(".tabs.autohash")
        .bind("tabsselect", function(event, ui) {
            document.location.hash = ui.panel.id;
        });

    // autocompletes
    $("input.author-autocomplete").author_autocomplete();
    $("input.language-autocomplete").language_autocomplete();

    // validate forms
    $("form.validate").ol_validate();

    // hide info flash messages
    $(".flash-messages .info").fadeTo(3000, 1).slideUp();
});

function sprintf(s) {
    var args = arguments;
    var i = 1;
    return s.replace(/%[%s]/g, function(match) {
        if (match == "%%")
            return "%";
        else
            return args[i++];
    });
}

// dummy i18n functions

function ugettext(s) {
    return s;
}
var _ = ugettext;

function ungettext(s1, s2, n) {
    return n == 1? s1 : s2;
}

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

/**
 * jquery repeat: jquery plugin to handle repetitive inputs in a form.
 *
 * Used in addbook process.
 */
(function($){    
    $.fn.repeat = function(options) {
        options = options || {};

        var id = "#" + this.attr("id");
        var elems = {
            '_this': this,
            'add': $(id + '-add'),
            'form': $(id + '-form'),
            'display': $(id + '-display'),
            'template': $(id + '-template')
        }
        
        function createTemplate(selector) {
            var code = $(selector).html()
                            .replace(/%7B%7B/gi, "<%=")
                            .replace(/%7D%7D/gi, "%>")
                            .replace(/{{/g, "<%=")
                            .replace(/}}/g, "%>");
            return Template(code);
        }
        
        var t = createTemplate(id + "-template");
        
        function formdata() {
            var data = {};
            $(":input", elems.form).each(function() {
                var e = $(this);
                data[e.attr("name")] = $.trim(e.val());
            });
            return data;
        }
        
        $(id + " .repeat-add").live("click", function(event) {
            event.preventDefault();
            
            var index = elems.display.children().length;
            var data = formdata();
            data.index = index;
            
            if (options.validate && options.validate(data) == false) {
                return;
            }
            
            $.extend(data, options.vars || {});
            
            var newid = elems._this.attr("id") + "--" + index;
            elems.template
                .clone()
                .attr("id", newid)
                .html(t(data))
                .css("display", null)
                .appendTo(elems.display);
                             
            $("[input[type!=button], textarea", elems.form).filter(":not(.repeat-ignore)").val("");
            elems._this.trigger("repeat-add");
        });
        
        $(id + " .repeat-remove").live("click", function(event) {
            event.preventDefault();
            $(this).parents(".repeat-item:eq(0)").remove();
            elems._this.trigger("repeat-remove");
        });
        
        $(id + " .repeat-moveup").live("click", function(event){
            // TODO:
        });
        $(id + " .repeat-movedown").live("click", function(event){
            // TODO:
        });
    }
})(jQuery);

/**
 * JavaScript companion for jsdef templetor extension.
 *
 * For more details, see:
 * http://github.com/anandology/notebook/tree/master/2010/03/jsdef/
 */

/**
 * Python range function.
 *
 *      > range(2,5)
 *      2,3,4
 *      > range(5)
 *      0,1,2,3,4
 *      > range(0, 10, 2)
 *      0,2,4,6,8
 */
function range(begin, end, step) {
    step = step || 1;
    if (end == undefined) {
        end = begin;
        begin = 0;
    }

    var r = [];
    for (var i=begin; i<end; i += step) {
        r[r.length] = i;
    }
    return r;
}

/**
 * Adds Python's str.join method to Javascript Strings.
 *
 *      > " - ".join(["a", "b", "c"])
 *      a - b - c
 */
String.prototype.join = function(items) {
    return items.join(this);
}

/**
 * Python's len function.
 */
function len(array) {
    return array.length;
}

function enumerate(a) {
    var b = new Array(a.length);
    for (var i in a) {
        b[i] = [i, a[i]];
    }
    return b;
}

function ForLoop(parent, seq) {
    this.parent = parent;
    this.seq = seq;
    
    this.length = seq.length;
    this.index0 = -1;
}

ForLoop.prototype.next = function() {
    var i = this.index0+1;
    
    this.index0 = i;
    this.index = i+1;
    
    this.first = (i == 0);
    this.last = (i == this.length-1);
    
    this.odd = (this.index % 2 == 1);
    this.even = (this.index % 2 == 0);
    this.parity = ['even', 'odd'][this.index % 2];
    
    this.revindex0 = this.length - i;
    this.revindex = this.length - i + 1;
}

function foreach(seq, parent_loop, callback) {
    var loop = new ForLoop(parent_loop, seq);
    
    for (var i=0; i<seq.length; i++) {
        loop.next();
        
        var args = [loop];
        
        // case of "for a, b in ..."
        if (callback.length > 2) {
            for (var j in seq[i]) {
                args.push(seq[i][j]);
            }
        }
        else {
            args[1] = seq[i];
        }
        callback.apply(this, args);
    }
}

function websafe(value) {
    if (value == null || value == undefined) {
        return "";
    }
    else {
        return htmlquote(value.toString());
    }
}

function htmlquote(text) {
    text = text.replace("&", "&amp;"); // Must be done first!
    text = text.replace("<", "&lt;");
    text = text.replace(">", "&gt;");
    text = text.replace("'", "&#39;");
    text = text.replace('"', "&quot;");
    return text;
}

// Add your third-party javascripts here

/**
 * jQuery.ScrollTo - Easy element scrolling using jQuery.
 * Copyright (c) 2007-2009 Ariel Flesler - aflesler(at)gmail(dot)com | http://flesler.blogspot.com
 * Dual licensed under MIT and GPL.
 * Date: 5/25/2009
 * @author Ariel Flesler
 * @version 1.4.2
 *
 * http://flesler.blogspot.com/2007/10/jqueryscrollto.html
 */
;(function(d){var k=d.scrollTo=function(a,i,e){d(window).scrollTo(a,i,e)};k.defaults={axis:'xy',duration:parseFloat(d.fn.jquery)>=1.3?0:1};k.window=function(a){return d(window)._scrollable()};d.fn._scrollable=function(){return this.map(function(){var a=this,i=!a.nodeName||d.inArray(a.nodeName.toLowerCase(),['iframe','#document','html','body'])!=-1;if(!i)return a;var e=(a.contentWindow||a).document||a.ownerDocument||a;return d.browser.safari||e.compatMode=='BackCompat'?e.body:e.documentElement})};d.fn.scrollTo=function(n,j,b){if(typeof j=='object'){b=j;j=0}if(typeof b=='function')b={onAfter:b};if(n=='max')n=9e9;b=d.extend({},k.defaults,b);j=j||b.speed||b.duration;b.queue=b.queue&&b.axis.length>1;if(b.queue)j/=2;b.offset=p(b.offset);b.over=p(b.over);return this._scrollable().each(function(){var q=this,r=d(q),f=n,s,g={},u=r.is('html,body');switch(typeof f){case'number':case'string':if(/^([+-]=)?\d+(\.\d+)?(px|%)?$/.test(f)){f=p(f);break}f=d(f,this);case'object':if(f.is||f.style)s=(f=d(f)).offset()}d.each(b.axis.split(''),function(a,i){var e=i=='x'?'Left':'Top',h=e.toLowerCase(),c='scroll'+e,l=q[c],m=k.max(q,i);if(s){g[c]=s[h]+(u?0:l-r.offset()[h]);if(b.margin){g[c]-=parseInt(f.css('margin'+e))||0;g[c]-=parseInt(f.css('border'+e+'Width'))||0}g[c]+=b.offset[h]||0;if(b.over[h])g[c]+=f[i=='x'?'width':'height']()*b.over[h]}else{var o=f[h];g[c]=o.slice&&o.slice(-1)=='%'?parseFloat(o)/100*m:o}if(/^\d+$/.test(g[c]))g[c]=g[c]<=0?0:Math.min(g[c],m);if(!a&&b.queue){if(l!=g[c])t(b.onAfterFirst);delete g[c]}});t(b.onAfter);function t(a){r.animate(g,j,b.easing,a&&function(){a.call(this,n,b)})}}).end()};k.max=function(a,i){var e=i=='x'?'Width':'Height',h='scroll'+e;if(!d(a).is('html,body'))return a[h]-d(a)[e.toLowerCase()]();var c='client'+e,l=a.ownerDocument.documentElement,m=a.ownerDocument.body;return Math.max(l[h],m[h])-Math.min(l[c],m[c])};function p(a){return typeof a=='object'?a:{top:a,left:a}}})(jQuery);


/**
* hoverIntent r5 // 2007.03.27 // jQuery 1.1.2+
* <http://cherne.net/brian/resources/jquery.hoverIntent.html>
* 
* @param  f  onMouseOver function || An object with configuration options
* @param  g  onMouseOut function  || Nothing (use configuration options object)
* @author    Brian Cherne <brian@cherne.net>
*/
(function($){$.fn.hoverIntent=function(f,g){var cfg={sensitivity:7,interval:100,timeout:0};cfg=$.extend(cfg,g?{over:f,out:g}:f);var cX,cY,pX,pY;var track=function(ev){cX=ev.pageX;cY=ev.pageY;};var compare=function(ev,ob){ob.hoverIntent_t=clearTimeout(ob.hoverIntent_t);if((Math.abs(pX-cX)+Math.abs(pY-cY))<cfg.sensitivity){$(ob).unbind("mousemove",track);ob.hoverIntent_s=1;return cfg.over.apply(ob,[ev]);}else{pX=cX;pY=cY;ob.hoverIntent_t=setTimeout(function(){compare(ev,ob);},cfg.interval);}};var delay=function(ev,ob){ob.hoverIntent_t=clearTimeout(ob.hoverIntent_t);ob.hoverIntent_s=0;return cfg.out.apply(ob,[ev]);};var handleHover=function(e){if($.fn.dataTableExt.oPagination.iPagingLoopStart==-1||$.fn.dataTableExt.oPagination.iPagingLoopStart==undefined){var p=(e.type=="mouseover"?e.fromElement:e.toElement)||e.relatedTarget;while(p&&p!=this){try{p=p.parentNode;}catch(e){p=this;}}if(p==this){return false;}var ev=jQuery.extend({},e);var ob=this;if(ob.hoverIntent_t){ob.hoverIntent_t=clearTimeout(ob.hoverIntent_t);}if(e.type=="mouseover"){pX=ev.pageX;pY=ev.pageY;$(ob).bind("mousemove",track);if(ob.hoverIntent_s!=1){ob.hoverIntent_t=setTimeout(function(){compare(ev,ob);},cfg.interval);}}else{$(ob).unbind("mousemove",track);if(ob.hoverIntent_s==1){ob.hoverIntent_t=setTimeout(function(){delay(ev,ob);},cfg.timeout);}}}else{return}};return this.mouseover(handleHover).mouseout(handleHover);};})(jQuery);

/*
 * File:        jquery.dataTables.min.js
 * Version:     1.6.2
 * Author:      Allan Jardine (www.sprymedia.co.uk)
 * Info:        www.datatables.net
 * 
 * Copyright 2008-2010 Allan Jardine, all rights reserved.
 *
 * This source file is free software, under either the GPL v2 license or a
 * BSD style license, as supplied with this software.
 * 
 * This source file is distributed in the hope that it will be useful, but 
 * WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY 
 * or FITNESS FOR A PARTICULAR PURPOSE. See the license files for details.
 */
(function($){$.fn.dataTableSettings=[];var _aoSettings=$.fn.dataTableSettings;$.fn.dataTableExt={};
var _oExt=$.fn.dataTableExt;_oExt.sVersion="1.6.2";_oExt.iApiIndex=0;_oExt.oApi={};
_oExt.afnFiltering=[];_oExt.aoFeatures=[];_oExt.ofnSearch={};_oExt.afnSortData=[];
_oExt.oStdClasses={sPagePrevEnabled:"paginate_enabled_previous",sPagePrevDisabled:"paginate_disabled_previous",sPageNextEnabled:"paginate_enabled_next",sPageNextDisabled:"paginate_disabled_next",sPageJUINext:"",sPageJUIPrev:"",sPageButton:"paginate_button",sPageButtonActive:"paginate_active",sPageButtonStaticDisabled:"paginate_button",sPageFirst:"first",sPagePrevious:"previous",sPageNext:"next",sPageLast:"last",sStripOdd:"odd",sStripEven:"even",sRowEmpty:"dataTables_empty",sWrapper:"dataTables_wrapper",sFilter:"dataTables_filter",sInfo:"dataTables_info",sPaging:"dataTables_paginate paging_",sLength:"dataTables_length",sProcessing:"dataTables_processing",sSortAsc:"sorting_asc",sSortDesc:"sorting_desc",sSortable:"sorting",sSortableAsc:"sorting_asc_disabled",sSortableDesc:"sorting_desc_disabled",sSortableNone:"sorting_disabled",sSortColumn:"sorting_",sSortJUIAsc:"",sSortJUIDesc:"",sSortJUI:"",sSortJUIAscAllowed:"",sSortJUIDescAllowed:""};
_oExt.oJUIClasses={sPagePrevEnabled:"fg-button ui-state-default ui-corner-left",sPagePrevDisabled:"fg-button ui-state-default ui-corner-left ui-state-disabled",sPageNextEnabled:"fg-button ui-state-default ui-corner-right",sPageNextDisabled:"fg-button ui-state-default ui-corner-right ui-state-disabled",sPageJUINext:"ui-icon ui-icon-circle-arrow-e",sPageJUIPrev:"ui-icon ui-icon-circle-arrow-w",sPageButton:"fg-button ui-state-default",sPageButtonActive:"fg-button ui-state-default ui-state-disabled",sPageButtonStaticDisabled:"fg-button ui-state-default ui-state-disabled",sPageFirst:"first ui-corner-tl ui-corner-bl",sPagePrevious:"previous",sPageNext:"next",sPageLast:"last ui-corner-tr ui-corner-br",sStripOdd:"odd",sStripEven:"even",sRowEmpty:"dataTables_empty",sWrapper:"dataTables_wrapper",sFilter:"dataTables_filter",sInfo:"dataTables_info",sPaging:"dataTables_paginate fg-buttonset fg-buttonset-multi paging_",sLength:"dataTables_length",sProcessing:"dataTables_processing",sSortAsc:"ui-state-default",sSortDesc:"ui-state-default",sSortable:"ui-state-default",sSortableAsc:"ui-state-default",sSortableDesc:"ui-state-default",sSortableNone:"ui-state-default",sSortColumn:"sorting_",sSortJUIAsc:"css_right ui-icon ui-icon-triangle-1-n",sSortJUIDesc:"css_right ui-icon ui-icon-triangle-1-s",sSortJUI:"css_right ui-icon ui-icon-carat-2-n-s",sSortJUIAscAllowed:"css_right ui-icon ui-icon-carat-1-n",sSortJUIDescAllowed:"css_right ui-icon ui-icon-carat-1-s"};
_oExt.oPagination={two_button:{fnInit:function(oSettings,nPaging,fnCallbackDraw){var nPrevious,nNext,nPreviousInner,nNextInner;
if(!oSettings.bJUI){nPrevious=document.createElement("div");nNext=document.createElement("div")
}else{nPrevious=document.createElement("a");nNext=document.createElement("a");nNextInner=document.createElement("span");
nNextInner.className=oSettings.oClasses.sPageJUINext;nNext.appendChild(nNextInner);
nPreviousInner=document.createElement("span");nPreviousInner.className=oSettings.oClasses.sPageJUIPrev;
nPrevious.appendChild(nPreviousInner)}nPrevious.className=oSettings.oClasses.sPagePrevDisabled;
nNext.className=oSettings.oClasses.sPageNextDisabled;nPrevious.title=oSettings.oLanguage.oPaginate.sPrevious;
nNext.title=oSettings.oLanguage.oPaginate.sNext;nPaging.appendChild(nPrevious);nPaging.appendChild(nNext);
$(nPrevious).click(function(){if(oSettings.oApi._fnPageChange(oSettings,"previous")){fnCallbackDraw(oSettings)
}});$(nNext).click(function(){if(oSettings.oApi._fnPageChange(oSettings,"next")){fnCallbackDraw(oSettings)
}});$(nPrevious).bind("selectstart",function(){return false});$(nNext).bind("selectstart",function(){return false
});if(oSettings.sTableId!==""&&typeof oSettings.aanFeatures.p=="undefined"){nPaging.setAttribute("id",oSettings.sTableId+"_paginate");
nPrevious.setAttribute("id",oSettings.sTableId+"_previous");nNext.setAttribute("id",oSettings.sTableId+"_next")
}},fnUpdate:function(oSettings,fnCallbackDraw){if(!oSettings.aanFeatures.p){return
}var an=oSettings.aanFeatures.p;for(var i=0,iLen=an.length;i<iLen;i++){if(an[i].childNodes.length!==0){an[i].childNodes[0].className=(oSettings._iDisplayStart===0)?oSettings.oClasses.sPagePrevDisabled:oSettings.oClasses.sPagePrevEnabled;
an[i].childNodes[1].className=(oSettings.fnDisplayEnd()==oSettings.fnRecordsDisplay())?oSettings.oClasses.sPageNextDisabled:oSettings.oClasses.sPageNextEnabled
}}}},iFullNumbersShowPages:5,full_numbers:{fnInit:function(oSettings,nPaging,fnCallbackDraw){var nFirst=document.createElement("span");
var nPrevious=document.createElement("span");var nList=document.createElement("span");
var nNext=document.createElement("span");var nLast=document.createElement("span");
nFirst.innerHTML=oSettings.oLanguage.oPaginate.sFirst;nPrevious.innerHTML=oSettings.oLanguage.oPaginate.sPrevious;
nNext.innerHTML=oSettings.oLanguage.oPaginate.sNext;nLast.innerHTML=oSettings.oLanguage.oPaginate.sLast;
var oClasses=oSettings.oClasses;nFirst.className=oClasses.sPageButton+" "+oClasses.sPageFirst;
nPrevious.className=oClasses.sPageButton+" "+oClasses.sPagePrevious;nNext.className=oClasses.sPageButton+" "+oClasses.sPageNext;
nLast.className=oClasses.sPageButton+" "+oClasses.sPageLast;nPaging.appendChild(nFirst);
nPaging.appendChild(nPrevious);nPaging.appendChild(nList);nPaging.appendChild(nNext);
nPaging.appendChild(nLast);$(nFirst).click(function(){if(oSettings.oApi._fnPageChange(oSettings,"first")){fnCallbackDraw(oSettings)
}});$(nPrevious).click(function(){if(oSettings.oApi._fnPageChange(oSettings,"previous")){fnCallbackDraw(oSettings)
}});$(nNext).click(function(){if(oSettings.oApi._fnPageChange(oSettings,"next")){fnCallbackDraw(oSettings)
}});$(nLast).click(function(){if(oSettings.oApi._fnPageChange(oSettings,"last")){fnCallbackDraw(oSettings)
}});$("span",nPaging).bind("mousedown",function(){return false}).bind("selectstart",function(){return false
});if(oSettings.sTableId!==""&&typeof oSettings.aanFeatures.p=="undefined"){nPaging.setAttribute("id",oSettings.sTableId+"_paginate");
nFirst.setAttribute("id",oSettings.sTableId+"_first");nPrevious.setAttribute("id",oSettings.sTableId+"_previous");
nNext.setAttribute("id",oSettings.sTableId+"_next");nLast.setAttribute("id",oSettings.sTableId+"_last")
}},fnUpdate:function(oSettings,fnCallbackDraw){if(!oSettings.aanFeatures.p){return
}var iPageCount=_oExt.oPagination.iFullNumbersShowPages;var iPageCountHalf=Math.floor(iPageCount/2);
var iPages=Math.ceil((oSettings.fnRecordsDisplay())/oSettings._iDisplayLength);var iCurrentPage=Math.ceil(oSettings._iDisplayStart/oSettings._iDisplayLength)+1;
var sList="";var iStartButton,iEndButton,i,iLen;var oClasses=oSettings.oClasses;if(iPages<iPageCount){iStartButton=1;
iEndButton=iPages}else{if(iCurrentPage<=iPageCountHalf){iStartButton=1;iEndButton=iPageCount
}else{if(iCurrentPage>=(iPages-iPageCountHalf)){iStartButton=iPages-iPageCount+1;
iEndButton=iPages}else{iStartButton=iCurrentPage-Math.ceil(iPageCount/2)+1;iEndButton=iStartButton+iPageCount-1
}}}for(i=iStartButton;i<=iEndButton;i++){if(iCurrentPage!=i){sList+='<span class="'+oClasses.sPageButton+'">'+i+"</span>"
}else{sList+='<span class="'+oClasses.sPageButtonActive+'">'+i+"</span>"}}var an=oSettings.aanFeatures.p;
var anButtons,anStatic,nPaginateList;var fnClick=function(){var iTarget=(this.innerHTML*1)-1;
oSettings._iDisplayStart=iTarget*oSettings._iDisplayLength;fnCallbackDraw(oSettings);
return false};var fnFalse=function(){return false};for(i=0,iLen=an.length;i<iLen;
i++){if(an[i].childNodes.length===0){continue}nPaginateList=an[i].childNodes[2];nPaginateList.innerHTML=sList;
$("span",nPaginateList).click(fnClick).bind("mousedown",fnFalse).bind("selectstart",fnFalse);
anButtons=an[i].getElementsByTagName("span");anStatic=[anButtons[0],anButtons[1],anButtons[anButtons.length-2],anButtons[anButtons.length-1]];
$(anStatic).removeClass(oClasses.sPageButton+" "+oClasses.sPageButtonActive+" "+oClasses.sPageButtonStaticDisabled);
if(iCurrentPage==1){anStatic[0].className+=" "+oClasses.sPageButtonStaticDisabled;
anStatic[1].className+=" "+oClasses.sPageButtonStaticDisabled}else{anStatic[0].className+=" "+oClasses.sPageButton;
anStatic[1].className+=" "+oClasses.sPageButton}if(iPages===0||iCurrentPage==iPages||oSettings._iDisplayLength==-1){anStatic[2].className+=" "+oClasses.sPageButtonStaticDisabled;
anStatic[3].className+=" "+oClasses.sPageButtonStaticDisabled}else{anStatic[2].className+=" "+oClasses.sPageButton;
anStatic[3].className+=" "+oClasses.sPageButton}}}}};_oExt.oSort={"string-asc":function(a,b){var x=a.toLowerCase();
var y=b.toLowerCase();return((x<y)?-1:((x>y)?1:0))},"string-desc":function(a,b){var x=a.toLowerCase();
var y=b.toLowerCase();return((x<y)?1:((x>y)?-1:0))},"html-asc":function(a,b){var x=a.replace(/<.*?>/g,"").toLowerCase();
var y=b.replace(/<.*?>/g,"").toLowerCase();return((x<y)?-1:((x>y)?1:0))},"html-desc":function(a,b){var x=a.replace(/<.*?>/g,"").toLowerCase();
var y=b.replace(/<.*?>/g,"").toLowerCase();return((x<y)?1:((x>y)?-1:0))},"date-asc":function(a,b){var x=Date.parse(a);
var y=Date.parse(b);if(isNaN(x)){x=Date.parse("01/01/1970 00:00:00")}if(isNaN(y)){y=Date.parse("01/01/1970 00:00:00")
}return x-y},"date-desc":function(a,b){var x=Date.parse(a);var y=Date.parse(b);if(isNaN(x)){x=Date.parse("01/01/1970 00:00:00")
}if(isNaN(y)){y=Date.parse("01/01/1970 00:00:00")}return y-x},"numeric-asc":function(a,b){var x=a=="-"?0:a;
var y=b=="-"?0:b;return x-y},"numeric-desc":function(a,b){var x=a=="-"?0:a;var y=b=="-"?0:b;
return y-x}};_oExt.aTypes=[function(sData){if(typeof sData=="number"){return"numeric"
}else{if(typeof sData.charAt!="function"){return null}}var sValidFirstChars="0123456789-";
var sValidChars="0123456789.";var Char;var bDecimal=false;Char=sData.charAt(0);if(sValidFirstChars.indexOf(Char)==-1){return null
}for(var i=1;i<sData.length;i++){Char=sData.charAt(i);if(sValidChars.indexOf(Char)==-1){return null
}if(Char=="."){if(bDecimal){return null}bDecimal=true}}return"numeric"},function(sData){var iParse=Date.parse(sData);
if(iParse!==null&&!isNaN(iParse)){return"date"}return null}];_oExt._oExternConfig={iNextUnique:0};
$.fn.dataTable=function(oInit){function classSettings(){this.fnRecordsTotal=function(){if(this.oFeatures.bServerSide){return this._iRecordsTotal
}else{return this.aiDisplayMaster.length}};this.fnRecordsDisplay=function(){if(this.oFeatures.bServerSide){return this._iRecordsDisplay
}else{return this.aiDisplay.length}};this.fnDisplayEnd=function(){if(this.oFeatures.bServerSide){return this._iDisplayStart+this.aiDisplay.length
}else{return this._iDisplayEnd}};this.sInstance=null;this.oFeatures={bPaginate:true,bLengthChange:true,bFilter:true,bSort:true,bInfo:true,bAutoWidth:true,bProcessing:false,bSortClasses:true,bStateSave:false,bServerSide:false};
this.aanFeatures=[];this.oLanguage={sProcessing:"Processing...",sLengthMenu:"Show _MENU_ entries",sZeroRecords:"No matching records found",sInfo:"Showing _START_ to _END_ of _TOTAL_ entries",sInfoEmpty:"Showing 0 to 0 of 0 entries",sInfoFiltered:"(filtered from _MAX_ total entries)",sInfoPostFix:"",sSearch:"Search:",sUrl:"",oPaginate:{sFirst:"First",sPrevious:"Previous",sNext:"Next",sLast:"Last"}};
this.aoData=[];this.aiDisplay=[];this.aiDisplayMaster=[];this.aoColumns=[];this.iNextId=0;
this.asDataSearch=[];this.oPreviousSearch={sSearch:"",bEscapeRegex:true};this.aoPreSearchCols=[];
this.aaSorting=[[0,"asc",0]];this.aaSortingFixed=null;this.asStripClasses=[];this.fnRowCallback=null;
this.fnHeaderCallback=null;this.fnFooterCallback=null;this.aoDrawCallback=[];this.fnInitComplete=null;
this.sTableId="";this.nTable=null;this.iDefaultSortIndex=0;this.bInitialised=false;
this.aoOpenRows=[];this.sDom="lfrtip";this.sPaginationType="two_button";this.iCookieDuration=60*60*2;
this.sAjaxSource=null;this.bAjaxDataGet=true;this.fnServerData=$.getJSON;this.iServerDraw=0;
this._iDisplayLength=10;this._iDisplayStart=0;this._iDisplayEnd=10;this._iRecordsTotal=0;
this._iRecordsDisplay=0;this.bJUI=false;this.oClasses=_oExt.oStdClasses;this.bFiltered=false;
this.bSorted=false}this.oApi={};this.fnDraw=function(bComplete){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
if(typeof bComplete!="undefined"&&bComplete===false){_fnCalculateEnd(oSettings);_fnDraw(oSettings)
}else{_fnReDraw(oSettings)}};this.fnFilter=function(sInput,iColumn,bEscapeRegex){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
if(typeof bEscapeRegex=="undefined"){bEscapeRegex=true}if(typeof iColumn=="undefined"||iColumn===null){_fnFilterComplete(oSettings,{sSearch:sInput,bEscapeRegex:bEscapeRegex},1)
}else{oSettings.aoPreSearchCols[iColumn].sSearch=sInput;oSettings.aoPreSearchCols[iColumn].bEscapeRegex=bEscapeRegex;
_fnFilterComplete(oSettings,oSettings.oPreviousSearch,1)}};this.fnSettings=function(nNode){return _fnSettingsFromNode(this[_oExt.iApiIndex])
};this.fnVersionCheck=function(sVersion){var fnZPad=function(Zpad,count){while(Zpad.length<count){Zpad+="0"
}return Zpad};var aThis=_oExt.sVersion.split(".");var aThat=sVersion.split(".");var sThis="",sThat="";
for(var i=0,iLen=aThat.length;i<iLen;i++){sThis+=fnZPad(aThis[i],3);sThat+=fnZPad(aThat[i],3)
}return parseInt(sThis,10)>=parseInt(sThat,10)};this.fnSort=function(aaSort){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
oSettings.aaSorting=aaSort;_fnSort(oSettings)};this.fnSortListener=function(nNode,iColumn,fnCallback){_fnSortAttachListener(_fnSettingsFromNode(this[_oExt.iApiIndex]),nNode,iColumn,fnCallback)
};this.fnAddData=function(mData,bRedraw){if(mData.length===0){return[]}var aiReturn=[];
var iTest;var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);if(typeof mData[0]=="object"){for(var i=0;
i<mData.length;i++){iTest=_fnAddData(oSettings,mData[i]);if(iTest==-1){return aiReturn
}aiReturn.push(iTest)}}else{iTest=_fnAddData(oSettings,mData);if(iTest==-1){return aiReturn
}aiReturn.push(iTest)}oSettings.aiDisplay=oSettings.aiDisplayMaster.slice();_fnBuildSearchArray(oSettings,1);
if(typeof bRedraw=="undefined"||bRedraw){_fnReDraw(oSettings)}return aiReturn};this.fnDeleteRow=function(mTarget,fnCallBack,bNullRow){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
var i,iAODataIndex;iAODataIndex=(typeof mTarget=="object")?_fnNodeToDataIndex(oSettings,mTarget):mTarget;
for(i=0;i<oSettings.aiDisplayMaster.length;i++){if(oSettings.aiDisplayMaster[i]==iAODataIndex){oSettings.aiDisplayMaster.splice(i,1);
break}}for(i=0;i<oSettings.aiDisplay.length;i++){if(oSettings.aiDisplay[i]==iAODataIndex){oSettings.aiDisplay.splice(i,1);
break}}_fnBuildSearchArray(oSettings,1);if(typeof fnCallBack=="function"){fnCallBack.call(this)
}if(oSettings._iDisplayStart>=oSettings.aiDisplay.length){oSettings._iDisplayStart-=oSettings._iDisplayLength;
if(oSettings._iDisplayStart<0){oSettings._iDisplayStart=0}}_fnCalculateEnd(oSettings);
_fnDraw(oSettings);var aData=oSettings.aoData[iAODataIndex]._aData.slice();if(typeof bNullRow!="undefined"&&bNullRow===true){oSettings.aoData[iAODataIndex]=null
}return aData};this.fnClearTable=function(bRedraw){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
_fnClearTable(oSettings);if(typeof bRedraw=="undefined"||bRedraw){_fnDraw(oSettings)
}};this.fnOpen=function(nTr,sHtml,sClass){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
this.fnClose(nTr);var nNewRow=document.createElement("tr");var nNewCell=document.createElement("td");
nNewRow.appendChild(nNewCell);nNewCell.className=sClass;nNewCell.colSpan=_fnVisbleColumns(oSettings);
nNewCell.innerHTML=sHtml;var nTrs=$("tbody tr",oSettings.nTable);if($.inArray(nTr,nTrs)!=-1){$(nNewRow).insertAfter(nTr)
}if(!oSettings.oFeatures.bServerSide){oSettings.aoOpenRows.push({nTr:nNewRow,nParent:nTr})
}return nNewRow};this.fnClose=function(nTr){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
for(var i=0;i<oSettings.aoOpenRows.length;i++){if(oSettings.aoOpenRows[i].nParent==nTr){var nTrParent=oSettings.aoOpenRows[i].nTr.parentNode;
if(nTrParent){nTrParent.removeChild(oSettings.aoOpenRows[i].nTr)}oSettings.aoOpenRows.splice(i,1);
return 0}}return 1};this.fnGetData=function(mRow){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
if(typeof mRow!="undefined"){var iRow=(typeof mRow=="object")?_fnNodeToDataIndex(oSettings,mRow):mRow;
return oSettings.aoData[iRow]._aData}return _fnGetDataMaster(oSettings)};this.fnGetNodes=function(iRow){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
if(typeof iRow!="undefined"){return oSettings.aoData[iRow].nTr}return _fnGetTrNodes(oSettings)
};this.fnGetPosition=function(nNode){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
var i;if(nNode.nodeName=="TR"){return _fnNodeToDataIndex(oSettings,nNode)}else{if(nNode.nodeName=="TD"){var iDataIndex=_fnNodeToDataIndex(oSettings,nNode.parentNode);
var iCorrector=0;for(var j=0;j<oSettings.aoColumns.length;j++){if(oSettings.aoColumns[j].bVisible){if(oSettings.aoData[iDataIndex].nTr.getElementsByTagName("td")[j-iCorrector]==nNode){return[iDataIndex,j-iCorrector,j]
}}else{iCorrector++}}}}return null};this.fnUpdate=function(mData,mRow,iColumn,bRedraw){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
var iVisibleColumn;var sDisplay;var iRow=(typeof mRow=="object")?_fnNodeToDataIndex(oSettings,mRow):mRow;
if(typeof mData!="object"){sDisplay=mData;oSettings.aoData[iRow]._aData[iColumn]=sDisplay;
if(oSettings.aoColumns[iColumn].fnRender!==null){sDisplay=oSettings.aoColumns[iColumn].fnRender({iDataRow:iRow,iDataColumn:iColumn,aData:oSettings.aoData[iRow]._aData,oSettings:oSettings});
if(oSettings.aoColumns[iColumn].bUseRendered){oSettings.aoData[iRow]._aData[iColumn]=sDisplay
}}iVisibleColumn=_fnColumnIndexToVisible(oSettings,iColumn);if(iVisibleColumn!==null){oSettings.aoData[iRow].nTr.getElementsByTagName("td")[iVisibleColumn].innerHTML=sDisplay
}}else{if(mData.length!=oSettings.aoColumns.length){alert("DataTables warning: An array passed to fnUpdate must have the same number of columns as the table in question - in this case "+oSettings.aoColumns.length);
return 1}for(var i=0;i<mData.length;i++){sDisplay=mData[i];oSettings.aoData[iRow]._aData[i]=sDisplay;
if(oSettings.aoColumns[i].fnRender!==null){sDisplay=oSettings.aoColumns[i].fnRender({iDataRow:iRow,iDataColumn:i,aData:oSettings.aoData[iRow]._aData,oSettings:oSettings});
if(oSettings.aoColumns[i].bUseRendered){oSettings.aoData[iRow]._aData[i]=sDisplay
}}iVisibleColumn=_fnColumnIndexToVisible(oSettings,i);if(iVisibleColumn!==null){oSettings.aoData[iRow].nTr.getElementsByTagName("td")[iVisibleColumn].innerHTML=sDisplay
}}}_fnBuildSearchArray(oSettings,1);if(typeof bRedraw!="undefined"&&bRedraw){_fnReDraw(oSettings)
}return 0};this.fnSetColumnVis=function(iCol,bShow){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
var i,iLen;var iColumns=oSettings.aoColumns.length;var nTd,anTds;if(oSettings.aoColumns[iCol].bVisible==bShow){return
}var nTrHead=$("thead:eq(0)>tr",oSettings.nTable)[0];var nTrFoot=$("tfoot:eq(0)>tr",oSettings.nTable)[0];
var anTheadTh=[];var anTfootTh=[];for(i=0;i<iColumns;i++){anTheadTh.push(oSettings.aoColumns[i].nTh);
anTfootTh.push(oSettings.aoColumns[i].nTf)}if(bShow){var iInsert=0;for(i=0;i<iCol;
i++){if(oSettings.aoColumns[i].bVisible){iInsert++}}if(iInsert>=_fnVisbleColumns(oSettings)){nTrHead.appendChild(anTheadTh[iCol]);
if(nTrFoot){nTrFoot.appendChild(anTfootTh[iCol])}for(i=0,iLen=oSettings.aoData.length;
i<iLen;i++){nTd=oSettings.aoData[i]._anHidden[iCol];oSettings.aoData[i].nTr.appendChild(nTd)
}}else{var iBefore;for(i=iCol;i<iColumns;i++){iBefore=_fnColumnIndexToVisible(oSettings,i);
if(iBefore!==null){break}}nTrHead.insertBefore(anTheadTh[iCol],nTrHead.getElementsByTagName("th")[iBefore]);
if(nTrFoot){nTrFoot.insertBefore(anTfootTh[iCol],nTrFoot.getElementsByTagName("th")[iBefore])
}anTds=_fnGetTdNodes(oSettings);for(i=0,iLen=oSettings.aoData.length;i<iLen;i++){nTd=oSettings.aoData[i]._anHidden[iCol];
oSettings.aoData[i].nTr.insertBefore(nTd,$(">td:eq("+iBefore+")",oSettings.aoData[i].nTr)[0])
}}oSettings.aoColumns[iCol].bVisible=true}else{nTrHead.removeChild(anTheadTh[iCol]);
if(nTrFoot){nTrFoot.removeChild(anTfootTh[iCol])}anTds=_fnGetTdNodes(oSettings);for(i=0,iLen=oSettings.aoData.length;
i<iLen;i++){nTd=anTds[(i*oSettings.aoColumns.length)+iCol];oSettings.aoData[i]._anHidden[iCol]=nTd;
nTd.parentNode.removeChild(nTd)}oSettings.aoColumns[iCol].bVisible=false}for(i=0,iLen=oSettings.aoOpenRows.length;
i<iLen;i++){oSettings.aoOpenRows[i].nTr.colSpan=_fnVisbleColumns(oSettings)}_fnSaveState(oSettings)
};this.fnPageChange=function(sAction,bRedraw){var oSettings=_fnSettingsFromNode(this[_oExt.iApiIndex]);
_fnPageChange(oSettings,sAction);_fnCalculateEnd(oSettings);if(typeof bRedraw=="undefined"||bRedraw){_fnDraw(oSettings)
}};function _fnExternApiFunc(sFunc){return function(){var aArgs=[_fnSettingsFromNode(this[_oExt.iApiIndex])].concat(Array.prototype.slice.call(arguments));
return _oExt.oApi[sFunc].apply(this,aArgs)}}for(var sFunc in _oExt.oApi){if(sFunc){this[sFunc]=_fnExternApiFunc(sFunc)
}}function _fnInitalise(oSettings){if(oSettings.bInitialised===false){setTimeout(function(){_fnInitalise(oSettings)
},200);return}_fnAddOptionsHtml(oSettings);_fnDrawHead(oSettings);if(oSettings.oFeatures.bSort){_fnSort(oSettings,false);
_fnSortingClasses(oSettings)}else{oSettings.aiDisplay=oSettings.aiDisplayMaster.slice();
_fnCalculateEnd(oSettings);_fnDraw(oSettings)}if(oSettings.sAjaxSource!==null&&!oSettings.oFeatures.bServerSide){_fnProcessingDisplay(oSettings,true);
oSettings.fnServerData(oSettings.sAjaxSource,null,function(json){for(var i=0;i<json.aaData.length;
i++){_fnAddData(oSettings,json.aaData[i])}oSettings.iInitDisplayStart=oSettings._iDisplayStart;
if(oSettings.oFeatures.bSort){_fnSort(oSettings)}else{oSettings.aiDisplay=oSettings.aiDisplayMaster.slice();
_fnCalculateEnd(oSettings);_fnDraw(oSettings)}_fnProcessingDisplay(oSettings,false);
if(typeof oSettings.fnInitComplete=="function"){oSettings.fnInitComplete(oSettings,json)
}});return}if(typeof oSettings.fnInitComplete=="function"){oSettings.fnInitComplete(oSettings)
}if(!oSettings.oFeatures.bServerSide){_fnProcessingDisplay(oSettings,false)}}function _fnLanguageProcess(oSettings,oLanguage,bInit){_fnMap(oSettings.oLanguage,oLanguage,"sProcessing");
_fnMap(oSettings.oLanguage,oLanguage,"sLengthMenu");_fnMap(oSettings.oLanguage,oLanguage,"sZeroRecords");
_fnMap(oSettings.oLanguage,oLanguage,"sInfo");_fnMap(oSettings.oLanguage,oLanguage,"sInfoEmpty");
_fnMap(oSettings.oLanguage,oLanguage,"sInfoFiltered");_fnMap(oSettings.oLanguage,oLanguage,"sInfoPostFix");
_fnMap(oSettings.oLanguage,oLanguage,"sSearch");if(typeof oLanguage.oPaginate!="undefined"){_fnMap(oSettings.oLanguage.oPaginate,oLanguage.oPaginate,"sFirst");
_fnMap(oSettings.oLanguage.oPaginate,oLanguage.oPaginate,"sPrevious");_fnMap(oSettings.oLanguage.oPaginate,oLanguage.oPaginate,"sNext");
_fnMap(oSettings.oLanguage.oPaginate,oLanguage.oPaginate,"sLast")}if(bInit){_fnInitalise(oSettings)
}}function _fnAddColumn(oSettings,oOptions,nTh){oSettings.aoColumns[oSettings.aoColumns.length++]={sType:null,_bAutoType:true,bVisible:true,bSearchable:true,bSortable:true,asSorting:["asc","desc"],sSortingClass:oSettings.oClasses.sSortable,sSortingClassJUI:oSettings.oClasses.sSortJUI,sTitle:nTh?nTh.innerHTML:"",sName:"",sWidth:null,sClass:null,fnRender:null,bUseRendered:true,iDataSort:oSettings.aoColumns.length-1,sSortDataType:"std",nTh:nTh?nTh:document.createElement("th"),nTf:null};
var iLength=oSettings.aoColumns.length-1;var oCol=oSettings.aoColumns[iLength];if(typeof oOptions!="undefined"&&oOptions!==null){if(typeof oOptions.sType!="undefined"){oCol.sType=oOptions.sType;
oCol._bAutoType=false}_fnMap(oCol,oOptions,"bVisible");_fnMap(oCol,oOptions,"bSearchable");
_fnMap(oCol,oOptions,"bSortable");_fnMap(oCol,oOptions,"sTitle");_fnMap(oCol,oOptions,"sName");
_fnMap(oCol,oOptions,"sWidth");_fnMap(oCol,oOptions,"sClass");_fnMap(oCol,oOptions,"fnRender");
_fnMap(oCol,oOptions,"bUseRendered");_fnMap(oCol,oOptions,"iDataSort");_fnMap(oCol,oOptions,"asSorting");
_fnMap(oCol,oOptions,"sSortDataType")}if(!oSettings.oFeatures.bSort){oCol.bSortable=false
}if(!oCol.bSortable||($.inArray("asc",oCol.asSorting)==-1&&$.inArray("desc",oCol.asSorting)==-1)){oCol.sSortingClass=oSettings.oClasses.sSortableNone;
oCol.sSortingClassJUI=""}else{if($.inArray("asc",oCol.asSorting)!=-1&&$.inArray("desc",oCol.asSorting)==-1){oCol.sSortingClass=oSettings.oClasses.sSortableAsc;
oCol.sSortingClassJUI=oSettings.oClasses.sSortJUIAscAllowed}else{if($.inArray("asc",oCol.asSorting)==-1&&$.inArray("desc",oCol.asSorting)!=-1){oCol.sSortingClass=oSettings.oClasses.sSortableDesc;
oCol.sSortingClassJUI=oSettings.oClasses.sSortJUIDescAllowed}}}if(typeof oSettings.aoPreSearchCols[iLength]=="undefined"||oSettings.aoPreSearchCols[iLength]===null){oSettings.aoPreSearchCols[iLength]={sSearch:"",bEscapeRegex:true}
}else{if(typeof oSettings.aoPreSearchCols[iLength].bEscapeRegex=="undefined"){oSettings.aoPreSearchCols[iLength].bEscapeRegex=true
}}}function _fnAddData(oSettings,aData){if(aData.length!=oSettings.aoColumns.length){alert("DataTables warning: Added data does not match known number of columns");
return -1}var iThisIndex=oSettings.aoData.length;oSettings.aoData.push({nTr:document.createElement("tr"),_iId:oSettings.iNextId++,_aData:aData.slice(),_anHidden:[],_sRowStripe:""});
var nTd,sThisType;for(var i=0;i<aData.length;i++){nTd=document.createElement("td");
if(typeof oSettings.aoColumns[i].fnRender=="function"){var sRendered=oSettings.aoColumns[i].fnRender({iDataRow:iThisIndex,iDataColumn:i,aData:aData,oSettings:oSettings});
nTd.innerHTML=sRendered;if(oSettings.aoColumns[i].bUseRendered){oSettings.aoData[iThisIndex]._aData[i]=sRendered
}}else{nTd.innerHTML=aData[i]}if(oSettings.aoColumns[i].sClass!==null){nTd.className=oSettings.aoColumns[i].sClass
}if(oSettings.aoColumns[i]._bAutoType&&oSettings.aoColumns[i].sType!="string"){sThisType=_fnDetectType(oSettings.aoData[iThisIndex]._aData[i]);
if(oSettings.aoColumns[i].sType===null){oSettings.aoColumns[i].sType=sThisType}else{if(oSettings.aoColumns[i].sType!=sThisType){oSettings.aoColumns[i].sType="string"
}}}if(oSettings.aoColumns[i].bVisible){oSettings.aoData[iThisIndex].nTr.appendChild(nTd)
}else{oSettings.aoData[iThisIndex]._anHidden[i]=nTd}}oSettings.aiDisplayMaster.push(iThisIndex);
return iThisIndex}function _fnGatherData(oSettings){var iLoop,i,iLen,j,jLen,jInner,nTds,nTrs,nTd,aLocalData,iThisIndex,iRow,iRows,iColumn,iColumns;
if(oSettings.sAjaxSource===null){nTrs=oSettings.nTable.getElementsByTagName("tbody")[0].childNodes;
for(i=0,iLen=nTrs.length;i<iLen;i++){if(nTrs[i].nodeName=="TR"){iThisIndex=oSettings.aoData.length;
oSettings.aoData.push({nTr:nTrs[i],_iId:oSettings.iNextId++,_aData:[],_anHidden:[],_sRowStripe:""});
oSettings.aiDisplayMaster.push(iThisIndex);aLocalData=oSettings.aoData[iThisIndex]._aData;
nTds=nTrs[i].childNodes;jInner=0;for(j=0,jLen=nTds.length;j<jLen;j++){if(nTds[j].nodeName=="TD"){aLocalData[jInner]=nTds[j].innerHTML;
jInner++}}}}}nTrs=_fnGetTrNodes(oSettings);nTds=[];for(i=0,iLen=nTrs.length;i<iLen;
i++){for(j=0,jLen=nTrs[i].childNodes.length;j<jLen;j++){nTd=nTrs[i].childNodes[j];
if(nTd.nodeName=="TD"){nTds.push(nTd)}}}if(nTds.length!=nTrs.length*oSettings.aoColumns.length){alert("DataTables warning: Unexpected number of TD elements. Expected "+(nTrs.length*oSettings.aoColumns.length)+" and got "+nTds.length+". DataTables does not support rowspan / colspan in the table body, and there must be one cell for each row/column combination.")
}for(iColumn=0,iColumns=oSettings.aoColumns.length;iColumn<iColumns;iColumn++){if(oSettings.aoColumns[iColumn].sTitle===null){oSettings.aoColumns[iColumn].sTitle=oSettings.aoColumns[iColumn].nTh.innerHTML
}var bAutoType=oSettings.aoColumns[iColumn]._bAutoType,bRender=typeof oSettings.aoColumns[iColumn].fnRender=="function",bClass=oSettings.aoColumns[iColumn].sClass!==null,bVisible=oSettings.aoColumns[iColumn].bVisible,nCell,sThisType,sRendered;
if(bAutoType||bRender||bClass||!bVisible){for(iRow=0,iRows=oSettings.aoData.length;
iRow<iRows;iRow++){nCell=nTds[(iRow*iColumns)+iColumn];if(bAutoType){if(oSettings.aoColumns[iColumn].sType!="string"){sThisType=_fnDetectType(oSettings.aoData[iRow]._aData[iColumn]);
if(oSettings.aoColumns[iColumn].sType===null){oSettings.aoColumns[iColumn].sType=sThisType
}else{if(oSettings.aoColumns[iColumn].sType!=sThisType){oSettings.aoColumns[iColumn].sType="string"
}}}}if(bRender){sRendered=oSettings.aoColumns[iColumn].fnRender({iDataRow:iRow,iDataColumn:iColumn,aData:oSettings.aoData[iRow]._aData,oSettings:oSettings});
nCell.innerHTML=sRendered;if(oSettings.aoColumns[iColumn].bUseRendered){oSettings.aoData[iRow]._aData[iColumn]=sRendered
}}if(bClass){nCell.className+=" "+oSettings.aoColumns[iColumn].sClass}if(!bVisible){oSettings.aoData[iRow]._anHidden[iColumn]=nCell;
nCell.parentNode.removeChild(nCell)}}}}}function _fnDrawHead(oSettings){var i,nTh,iLen;
var iThs=oSettings.nTable.getElementsByTagName("thead")[0].getElementsByTagName("th").length;
var iCorrector=0;if(iThs!==0){for(i=0,iLen=oSettings.aoColumns.length;i<iLen;i++){nTh=oSettings.aoColumns[i].nTh;
if(oSettings.aoColumns[i].bVisible){if(oSettings.aoColumns[i].sWidth!==null){nTh.style.width=oSettings.aoColumns[i].sWidth
}if(oSettings.aoColumns[i].sTitle!=nTh.innerHTML){nTh.innerHTML=oSettings.aoColumns[i].sTitle
}}else{nTh.parentNode.removeChild(nTh);iCorrector++}}}else{var nTr=document.createElement("tr");
for(i=0,iLen=oSettings.aoColumns.length;i<iLen;i++){nTh=oSettings.aoColumns[i].nTh;
nTh.innerHTML=oSettings.aoColumns[i].sTitle;if(oSettings.aoColumns[i].bVisible){if(oSettings.aoColumns[i].sClass!==null){nTh.className=oSettings.aoColumns[i].sClass
}if(oSettings.aoColumns[i].sWidth!==null){nTh.style.width=oSettings.aoColumns[i].sWidth
}nTr.appendChild(nTh)}}$("thead:eq(0)",oSettings.nTable).html("")[0].appendChild(nTr)
}if(oSettings.bJUI){for(i=0,iLen=oSettings.aoColumns.length;i<iLen;i++){oSettings.aoColumns[i].nTh.insertBefore(document.createElement("span"),oSettings.aoColumns[i].nTh.firstChild)
}}if(oSettings.oFeatures.bSort){for(i=0;i<oSettings.aoColumns.length;i++){if(oSettings.aoColumns[i].bSortable!==false){_fnSortAttachListener(oSettings,oSettings.aoColumns[i].nTh,i)
}else{$(oSettings.aoColumns[i].nTh).addClass(oSettings.oClasses.sSortableNone)}}$("thead:eq(0) th",oSettings.nTable).mousedown(function(e){if(e.shiftKey){this.onselectstart=function(){return false
};return false}})}var nTfoot=oSettings.nTable.getElementsByTagName("tfoot");if(nTfoot.length!==0){iCorrector=0;
var nTfs=nTfoot[0].getElementsByTagName("th");for(i=0,iLen=nTfs.length;i<iLen;i++){oSettings.aoColumns[i].nTf=nTfs[i-iCorrector];
if(!oSettings.aoColumns[i].bVisible){nTfs[i-iCorrector].parentNode.removeChild(nTfs[i-iCorrector]);
iCorrector++}}}}function _fnDraw(oSettings){var i,iLen;var anRows=[];var iRowCount=0;
var bRowError=false;var iStrips=oSettings.asStripClasses.length;var iOpenRows=oSettings.aoOpenRows.length;
if(oSettings.oFeatures.bServerSide&&!_fnAjaxUpdate(oSettings)){return}if(typeof oSettings.iInitDisplayStart!="undefined"&&oSettings.iInitDisplayStart!=-1){oSettings._iDisplayStart=(oSettings.iInitDisplayStart>=oSettings.fnRecordsDisplay())?0:oSettings.iInitDisplayStart;
oSettings.iInitDisplayStart=-1;_fnCalculateEnd(oSettings)}if(oSettings.aiDisplay.length!==0){var iStart=oSettings._iDisplayStart;
var iEnd=oSettings._iDisplayEnd;if(oSettings.oFeatures.bServerSide){iStart=0;iEnd=oSettings.aoData.length
}for(var j=iStart;j<iEnd;j++){var aoData=oSettings.aoData[oSettings.aiDisplay[j]];
var nRow=aoData.nTr;if(iStrips!==0){var sStrip=oSettings.asStripClasses[iRowCount%iStrips];
if(aoData._sRowStripe!=sStrip){$(nRow).removeClass(aoData._sRowStripe).addClass(sStrip);
aoData._sRowStripe=sStrip}}if(typeof oSettings.fnRowCallback=="function"){nRow=oSettings.fnRowCallback(nRow,oSettings.aoData[oSettings.aiDisplay[j]]._aData,iRowCount,j);
if(!nRow&&!bRowError){alert("DataTables warning: A node was not returned by fnRowCallback");
bRowError=true}}anRows.push(nRow);iRowCount++;if(iOpenRows!==0){for(var k=0;k<iOpenRows;
k++){if(nRow==oSettings.aoOpenRows[k].nParent){anRows.push(oSettings.aoOpenRows[k].nTr)
}}}}}else{anRows[0]=document.createElement("tr");if(typeof oSettings.asStripClasses[0]!="undefined"){anRows[0].className=oSettings.asStripClasses[0]
}var nTd=document.createElement("td");nTd.setAttribute("valign","top");nTd.colSpan=oSettings.aoColumns.length;
nTd.className=oSettings.oClasses.sRowEmpty;nTd.innerHTML=oSettings.oLanguage.sZeroRecords;
anRows[iRowCount].appendChild(nTd)}if(typeof oSettings.fnHeaderCallback=="function"){oSettings.fnHeaderCallback($("thead:eq(0)>tr",oSettings.nTable)[0],_fnGetDataMaster(oSettings),oSettings._iDisplayStart,oSettings.fnDisplayEnd(),oSettings.aiDisplay)
}if(typeof oSettings.fnFooterCallback=="function"){oSettings.fnFooterCallback($("tfoot:eq(0)>tr",oSettings.nTable)[0],_fnGetDataMaster(oSettings),oSettings._iDisplayStart,oSettings.fnDisplayEnd(),oSettings.aiDisplay)
}var nBody=oSettings.nTable.getElementsByTagName("tbody");if(nBody[0]){var nTrs=nBody[0].childNodes;
for(i=nTrs.length-1;i>=0;i--){nTrs[i].parentNode.removeChild(nTrs[i])}for(i=0,iLen=anRows.length;
i<iLen;i++){nBody[0].appendChild(anRows[i])}}for(i=0,iLen=oSettings.aoDrawCallback.length;
i<iLen;i++){oSettings.aoDrawCallback[i].fn(oSettings)}oSettings.bSorted=false;oSettings.bFiltered=false;
if(typeof oSettings._bInitComplete=="undefined"){oSettings._bInitComplete=true;if(oSettings.oFeatures.bAutoWidth&&oSettings.nTable.offsetWidth!==0){oSettings.nTable.style.width=oSettings.nTable.offsetWidth+"px"
}}}function _fnReDraw(oSettings){if(oSettings.oFeatures.bSort){_fnSort(oSettings,oSettings.oPreviousSearch)
}else{if(oSettings.oFeatures.bFilter){_fnFilterComplete(oSettings,oSettings.oPreviousSearch)
}else{_fnCalculateEnd(oSettings);_fnDraw(oSettings)}}}function _fnAjaxUpdate(oSettings){if(oSettings.bAjaxDataGet){_fnProcessingDisplay(oSettings,true);
var iColumns=oSettings.aoColumns.length;var aoData=[];var i;oSettings.iServerDraw++;
aoData.push({name:"sEcho",value:oSettings.iServerDraw});aoData.push({name:"iColumns",value:iColumns});
aoData.push({name:"sColumns",value:_fnColumnOrdering(oSettings)});aoData.push({name:"iDisplayStart",value:oSettings._iDisplayStart});
aoData.push({name:"iDisplayLength",value:oSettings.oFeatures.bPaginate!==false?oSettings._iDisplayLength:-1});
if(oSettings.oFeatures.bFilter!==false){aoData.push({name:"sSearch",value:oSettings.oPreviousSearch.sSearch});
aoData.push({name:"bEscapeRegex",value:oSettings.oPreviousSearch.bEscapeRegex});for(i=0;
i<iColumns;i++){aoData.push({name:"sSearch_"+i,value:oSettings.aoPreSearchCols[i].sSearch});
aoData.push({name:"bEscapeRegex_"+i,value:oSettings.aoPreSearchCols[i].bEscapeRegex});
aoData.push({name:"bSearchable_"+i,value:oSettings.aoColumns[i].bSearchable})}}if(oSettings.oFeatures.bSort!==false){var iFixed=oSettings.aaSortingFixed!==null?oSettings.aaSortingFixed.length:0;
var iUser=oSettings.aaSorting.length;aoData.push({name:"iSortingCols",value:iFixed+iUser});
for(i=0;i<iFixed;i++){aoData.push({name:"iSortCol_"+i,value:oSettings.aaSortingFixed[i][0]});
aoData.push({name:"sSortDir_"+i,value:oSettings.aaSortingFixed[i][1]})}for(i=0;i<iUser;
i++){aoData.push({name:"iSortCol_"+(i+iFixed),value:oSettings.aaSorting[i][0]});aoData.push({name:"sSortDir_"+(i+iFixed),value:oSettings.aaSorting[i][1]})
}for(i=0;i<iColumns;i++){aoData.push({name:"bSortable_"+i,value:oSettings.aoColumns[i].bSortable})
}}oSettings.fnServerData(oSettings.sAjaxSource,aoData,function(json){_fnAjaxUpdateDraw(oSettings,json)
});return false}else{return true}}function _fnAjaxUpdateDraw(oSettings,json){if(typeof json.sEcho!="undefined"){if(json.sEcho*1<oSettings.iServerDraw){return
}else{oSettings.iServerDraw=json.sEcho*1}}_fnClearTable(oSettings);oSettings._iRecordsTotal=json.iTotalRecords;
oSettings._iRecordsDisplay=json.iTotalDisplayRecords;var sOrdering=_fnColumnOrdering(oSettings);
var bReOrder=(typeof json.sColumns!="undefined"&&sOrdering!==""&&json.sColumns!=sOrdering);
if(bReOrder){var aiIndex=_fnReOrderIndex(oSettings,json.sColumns)}for(var i=0,iLen=json.aaData.length;
i<iLen;i++){if(bReOrder){var aData=[];for(var j=0,jLen=oSettings.aoColumns.length;
j<jLen;j++){aData.push(json.aaData[i][aiIndex[j]])}_fnAddData(oSettings,aData)}else{_fnAddData(oSettings,json.aaData[i])
}}oSettings.aiDisplay=oSettings.aiDisplayMaster.slice();oSettings.bAjaxDataGet=false;
_fnDraw(oSettings);oSettings.bAjaxDataGet=true;_fnProcessingDisplay(oSettings,false)
}function _fnAddOptionsHtml(oSettings){var nHolding=document.createElement("div");
oSettings.nTable.parentNode.insertBefore(nHolding,oSettings.nTable);var nWrapper=document.createElement("div");
nWrapper.className=oSettings.oClasses.sWrapper;if(oSettings.sTableId!==""){nWrapper.setAttribute("id",oSettings.sTableId+"_wrapper")
}var nInsertNode=nWrapper;var sDom=oSettings.sDom.replace("H","fg-toolbar ui-widget-header ui-corner-tl ui-corner-tr ui-helper-clearfix");
sDom=sDom.replace("F","fg-toolbar ui-widget-header ui-corner-bl ui-corner-br ui-helper-clearfix");
var aDom=sDom.split("");var nTmp,iPushFeature,cOption,nNewNode,cNext,sClass,j;for(var i=0;
i<aDom.length;i++){iPushFeature=0;cOption=aDom[i];if(cOption=="<"){nNewNode=document.createElement("div");
cNext=aDom[i+1];if(cNext=="'"||cNext=='"'){sClass="";j=2;while(aDom[i+j]!=cNext){sClass+=aDom[i+j];
j++}nNewNode.className=sClass;i+=j}nInsertNode.appendChild(nNewNode);nInsertNode=nNewNode
}else{if(cOption==">"){nInsertNode=nInsertNode.parentNode}else{if(cOption=="l"&&oSettings.oFeatures.bPaginate&&oSettings.oFeatures.bLengthChange){nTmp=_fnFeatureHtmlLength(oSettings);
iPushFeature=1}else{if(cOption=="f"&&oSettings.oFeatures.bFilter){nTmp=_fnFeatureHtmlFilter(oSettings);
iPushFeature=1}else{if(cOption=="r"&&oSettings.oFeatures.bProcessing){nTmp=_fnFeatureHtmlProcessing(oSettings);
iPushFeature=1}else{if(cOption=="t"){nTmp=oSettings.nTable;iPushFeature=1}else{if(cOption=="i"&&oSettings.oFeatures.bInfo){nTmp=_fnFeatureHtmlInfo(oSettings);
iPushFeature=1}else{if(cOption=="p"&&oSettings.oFeatures.bPaginate){nTmp=_fnFeatureHtmlPaginate(oSettings);
iPushFeature=1}else{if(_oExt.aoFeatures.length!==0){var aoFeatures=_oExt.aoFeatures;
for(var k=0,kLen=aoFeatures.length;k<kLen;k++){if(cOption==aoFeatures[k].cFeature){nTmp=aoFeatures[k].fnInit(oSettings);
if(nTmp){iPushFeature=1}break}}}}}}}}}}}if(iPushFeature==1){if(typeof oSettings.aanFeatures[cOption]!="object"){oSettings.aanFeatures[cOption]=[]
}oSettings.aanFeatures[cOption].push(nTmp);nInsertNode.appendChild(nTmp)}}nHolding.parentNode.replaceChild(nWrapper,nHolding)
}function _fnFeatureHtmlFilter(oSettings){var nFilter=document.createElement("div");
if(oSettings.sTableId!==""&&typeof oSettings.aanFeatures.f=="undefined"){nFilter.setAttribute("id",oSettings.sTableId+"_filter")
}nFilter.className=oSettings.oClasses.sFilter;var sSpace=oSettings.oLanguage.sSearch===""?"":" ";
nFilter.innerHTML=oSettings.oLanguage.sSearch+sSpace+'<input type="text" />';var jqFilter=$("input",nFilter);
jqFilter.val(oSettings.oPreviousSearch.sSearch.replace('"',"&quot;"));jqFilter.keyup(function(e){var n=oSettings.aanFeatures.f;
for(var i=0,iLen=n.length;i<iLen;i++){if(n[i]!=this.parentNode){$("input",n[i]).val(this.value)
}}_fnFilterComplete(oSettings,{sSearch:this.value,bEscapeRegex:oSettings.oPreviousSearch.bEscapeRegex})
});jqFilter.keypress(function(e){if(e.keyCode==13){return false}});return nFilter
}function _fnFilterComplete(oSettings,oInput,iForce){_fnFilter(oSettings,oInput.sSearch,iForce,oInput.bEscapeRegex);
for(var i=0;i<oSettings.aoPreSearchCols.length;i++){_fnFilterColumn(oSettings,oSettings.aoPreSearchCols[i].sSearch,i,oSettings.aoPreSearchCols[i].bEscapeRegex)
}if(_oExt.afnFiltering.length!==0){_fnFilterCustom(oSettings)}oSettings.bFiltered=true;
oSettings._iDisplayStart=0;_fnCalculateEnd(oSettings);_fnDraw(oSettings);_fnBuildSearchArray(oSettings,0)
}function _fnFilterCustom(oSettings){var afnFilters=_oExt.afnFiltering;for(var i=0,iLen=afnFilters.length;
i<iLen;i++){var iCorrector=0;for(var j=0,jLen=oSettings.aiDisplay.length;j<jLen;j++){var iDisIndex=oSettings.aiDisplay[j-iCorrector];
if(!afnFilters[i](oSettings,oSettings.aoData[iDisIndex]._aData,iDisIndex)){oSettings.aiDisplay.splice(j-iCorrector,1);
iCorrector++}}}}function _fnFilterColumn(oSettings,sInput,iColumn,bEscapeRegex){if(sInput===""){return
}var iIndexCorrector=0;var sRegexMatch=bEscapeRegex?_fnEscapeRegex(sInput):sInput;
var rpSearch=new RegExp(sRegexMatch,"i");for(var i=oSettings.aiDisplay.length-1;i>=0;
i--){var sData=_fnDataToSearch(oSettings.aoData[oSettings.aiDisplay[i]]._aData[iColumn],oSettings.aoColumns[iColumn].sType);
if(!rpSearch.test(sData)){oSettings.aiDisplay.splice(i,1);iIndexCorrector++}}}function _fnFilter(oSettings,sInput,iForce,bEscapeRegex){var i;
if(typeof iForce=="undefined"||iForce===null){iForce=0}if(_oExt.afnFiltering.length!==0){iForce=1
}var asSearch=bEscapeRegex?_fnEscapeRegex(sInput).split(" "):sInput.split(" ");var sRegExpString="^(?=.*?"+asSearch.join(")(?=.*?")+").*$";
var rpSearch=new RegExp(sRegExpString,"i");if(sInput.length<=0){oSettings.aiDisplay.splice(0,oSettings.aiDisplay.length);
oSettings.aiDisplay=oSettings.aiDisplayMaster.slice()}else{if(oSettings.aiDisplay.length==oSettings.aiDisplayMaster.length||oSettings.oPreviousSearch.sSearch.length>sInput.length||iForce==1||sInput.indexOf(oSettings.oPreviousSearch.sSearch)!==0){oSettings.aiDisplay.splice(0,oSettings.aiDisplay.length);
_fnBuildSearchArray(oSettings,1);for(i=0;i<oSettings.aiDisplayMaster.length;i++){if(rpSearch.test(oSettings.asDataSearch[i])){oSettings.aiDisplay.push(oSettings.aiDisplayMaster[i])
}}}else{var iIndexCorrector=0;for(i=0;i<oSettings.asDataSearch.length;i++){if(!rpSearch.test(oSettings.asDataSearch[i])){oSettings.aiDisplay.splice(i-iIndexCorrector,1);
iIndexCorrector++}}}}oSettings.oPreviousSearch.sSearch=sInput;oSettings.oPreviousSearch.bEscapeRegex=bEscapeRegex
}function _fnBuildSearchArray(oSettings,iMaster){oSettings.asDataSearch.splice(0,oSettings.asDataSearch.length);
var aArray=(typeof iMaster!="undefined"&&iMaster==1)?oSettings.aiDisplayMaster:oSettings.aiDisplay;
for(var i=0,iLen=aArray.length;i<iLen;i++){oSettings.asDataSearch[i]="";for(var j=0,jLen=oSettings.aoColumns.length;
j<jLen;j++){if(oSettings.aoColumns[j].bSearchable){var sData=oSettings.aoData[aArray[i]]._aData[j];
oSettings.asDataSearch[i]+=_fnDataToSearch(sData,oSettings.aoColumns[j].sType)+" "
}}}}function _fnDataToSearch(sData,sType){if(typeof _oExt.ofnSearch[sType]=="function"){return _oExt.ofnSearch[sType](sData)
}else{if(sType=="html"){return sData.replace(/\n/g," ").replace(/<.*?>/g,"")}else{if(typeof sData=="string"){return sData.replace(/\n/g," ")
}}}return sData}function _fnSort(oSettings,bApplyClasses){var aaSort=[];var oSort=_oExt.oSort;
var aoData=oSettings.aoData;var iDataSort;var iDataType;var i,j,jLen;if(!oSettings.oFeatures.bServerSide&&(oSettings.aaSorting.length!==0||oSettings.aaSortingFixed!==null)){if(oSettings.aaSortingFixed!==null){aaSort=oSettings.aaSortingFixed.concat(oSettings.aaSorting)
}else{aaSort=oSettings.aaSorting.slice()}for(i=0;i<aaSort.length;i++){var iColumn=aaSort[i][0];
var sDataType=oSettings.aoColumns[iColumn].sSortDataType;if(typeof _oExt.afnSortData[sDataType]!="undefined"){var iCorrector=0;
var aData=_oExt.afnSortData[sDataType](oSettings,iColumn);for(j=0,jLen=aoData.length;
j<jLen;j++){if(aoData[j]!==null){aoData[j]._aData[iColumn]=aData[iCorrector];iCorrector++
}}}}if(!window.runtime){var fnLocalSorting;var sDynamicSort="fnLocalSorting = function(a,b){var iTest;";
for(i=0;i<aaSort.length-1;i++){iDataSort=oSettings.aoColumns[aaSort[i][0]].iDataSort;
iDataType=oSettings.aoColumns[iDataSort].sType;sDynamicSort+="iTest = oSort['"+iDataType+"-"+aaSort[i][1]+"']( aoData[a]._aData["+iDataSort+"], aoData[b]._aData["+iDataSort+"] ); if ( iTest === 0 )"
}iDataSort=oSettings.aoColumns[aaSort[aaSort.length-1][0]].iDataSort;iDataType=oSettings.aoColumns[iDataSort].sType;
sDynamicSort+="iTest = oSort['"+iDataType+"-"+aaSort[aaSort.length-1][1]+"']( aoData[a]._aData["+iDataSort+"], aoData[b]._aData["+iDataSort+"] );if (iTest===0) return oSort['numeric-"+aaSort[aaSort.length-1][1]+"'](a, b); return iTest;}";
eval(sDynamicSort);oSettings.aiDisplayMaster.sort(fnLocalSorting)}else{var aAirSort=[];
var iLen=aaSort.length;for(i=0;i<iLen;i++){iDataSort=oSettings.aoColumns[aaSort[i][0]].iDataSort;
aAirSort.push([iDataSort,oSettings.aoColumns[iDataSort].sType+"-"+aaSort[i][1]])}oSettings.aiDisplayMaster.sort(function(a,b){var iTest;
for(var i=0;i<iLen;i++){iTest=oSort[aAirSort[i][1]](aoData[a]._aData[aAirSort[i][0]],aoData[b]._aData[aAirSort[i][0]]);
if(iTest!==0){return iTest}}return 0})}}if(typeof bApplyClasses=="undefined"||bApplyClasses){_fnSortingClasses(oSettings)
}oSettings.bSorted=true;if(oSettings.oFeatures.bFilter){_fnFilterComplete(oSettings,oSettings.oPreviousSearch,1)
}else{oSettings.aiDisplay=oSettings.aiDisplayMaster.slice();oSettings._iDisplayStart=0;
_fnCalculateEnd(oSettings);_fnDraw(oSettings)}}function _fnSortAttachListener(oSettings,nNode,iDataIndex,fnCallback){$(nNode).click(function(e){if(oSettings.aoColumns[iDataIndex].bSortable===false){return
}var fnInnerSorting=function(){var iColumn,iNextSort;if(e.shiftKey){var bFound=false;
for(var i=0;i<oSettings.aaSorting.length;i++){if(oSettings.aaSorting[i][0]==iDataIndex){bFound=true;
iColumn=oSettings.aaSorting[i][0];iNextSort=oSettings.aaSorting[i][2]+1;if(typeof oSettings.aoColumns[iColumn].asSorting[iNextSort]=="undefined"){oSettings.aaSorting.splice(i,1)
}else{oSettings.aaSorting[i][1]=oSettings.aoColumns[iColumn].asSorting[iNextSort];
oSettings.aaSorting[i][2]=iNextSort}break}}if(bFound===false){oSettings.aaSorting.push([iDataIndex,oSettings.aoColumns[iDataIndex].asSorting[0],0])
}}else{if(oSettings.aaSorting.length==1&&oSettings.aaSorting[0][0]==iDataIndex){iColumn=oSettings.aaSorting[0][0];
iNextSort=oSettings.aaSorting[0][2]+1;if(typeof oSettings.aoColumns[iColumn].asSorting[iNextSort]=="undefined"){iNextSort=0
}oSettings.aaSorting[0][1]=oSettings.aoColumns[iColumn].asSorting[iNextSort];oSettings.aaSorting[0][2]=iNextSort
}else{oSettings.aaSorting.splice(0,oSettings.aaSorting.length);oSettings.aaSorting.push([iDataIndex,oSettings.aoColumns[iDataIndex].asSorting[0],0])
}}_fnSort(oSettings)};if(!oSettings.oFeatures.bProcessing){fnInnerSorting()}else{_fnProcessingDisplay(oSettings,true);
setTimeout(function(){fnInnerSorting();if(!oSettings.oFeatures.bServerSide){_fnProcessingDisplay(oSettings,false)
}},0)}if(typeof fnCallback=="function"){fnCallback(oSettings)}})}function _fnSortingClasses(oSettings){var i,iLen,j,jLen,iFound;
var aaSort,sClass;var iColumns=oSettings.aoColumns.length;var oClasses=oSettings.oClasses;
for(i=0;i<iColumns;i++){if(oSettings.aoColumns[i].bSortable){$(oSettings.aoColumns[i].nTh).removeClass(oClasses.sSortAsc+" "+oClasses.sSortDesc+" "+oSettings.aoColumns[i].sSortingClass)
}}if(oSettings.aaSortingFixed!==null){aaSort=oSettings.aaSortingFixed.concat(oSettings.aaSorting)
}else{aaSort=oSettings.aaSorting.slice()}for(i=0;i<oSettings.aoColumns.length;i++){if(oSettings.aoColumns[i].bSortable){sClass=oSettings.aoColumns[i].sSortingClass;
iFound=-1;for(j=0;j<aaSort.length;j++){if(aaSort[j][0]==i){sClass=(aaSort[j][1]=="asc")?oClasses.sSortAsc:oClasses.sSortDesc;
iFound=j;break}}$(oSettings.aoColumns[i].nTh).addClass(sClass);if(oSettings.bJUI){var jqSpan=$("span",oSettings.aoColumns[i].nTh);
jqSpan.removeClass(oClasses.sSortJUIAsc+" "+oClasses.sSortJUIDesc+" "+oClasses.sSortJUI+" "+oClasses.sSortJUIAscAllowed+" "+oClasses.sSortJUIDescAllowed);
var sSpanClass;if(iFound==-1){sSpanClass=oSettings.aoColumns[i].sSortingClassJUI}else{if(aaSort[iFound][1]=="asc"){sSpanClass=oClasses.sSortJUIAsc
}else{sSpanClass=oClasses.sSortJUIDesc}}jqSpan.addClass(sSpanClass)}}else{$(oSettings.aoColumns[i].nTh).addClass(oSettings.aoColumns[i].sSortingClass)
}}sClass=oClasses.sSortColumn;if(oSettings.oFeatures.bSort&&oSettings.oFeatures.bSortClasses){var nTds=_fnGetTdNodes(oSettings);
if(nTds.length>=iColumns){for(i=0;i<iColumns;i++){if(nTds[i].className.indexOf(sClass+"1")!=-1){for(j=0,jLen=(nTds.length/iColumns);
j<jLen;j++){nTds[(iColumns*j)+i].className=nTds[(iColumns*j)+i].className.replace(" "+sClass+"1","")
}}else{if(nTds[i].className.indexOf(sClass+"2")!=-1){for(j=0,jLen=(nTds.length/iColumns);
j<jLen;j++){nTds[(iColumns*j)+i].className=nTds[(iColumns*j)+i].className.replace(" "+sClass+"2","")
}}else{if(nTds[i].className.indexOf(sClass+"3")!=-1){for(j=0,jLen=(nTds.length/iColumns);
j<jLen;j++){nTds[(iColumns*j)+i].className=nTds[(iColumns*j)+i].className.replace(" "+sClass+"3","")
}}}}}}var iClass=1,iTargetCol;for(i=0;i<aaSort.length;i++){iTargetCol=parseInt(aaSort[i][0],10);
for(j=0,jLen=(nTds.length/iColumns);j<jLen;j++){nTds[(iColumns*j)+iTargetCol].className+=" "+sClass+iClass
}if(iClass<3){iClass++}}}}function _fnFeatureHtmlPaginate(oSettings){var nPaginate=document.createElement("div");
nPaginate.className=oSettings.oClasses.sPaging+oSettings.sPaginationType;_oExt.oPagination[oSettings.sPaginationType].fnInit(oSettings,nPaginate,function(oSettings){_fnCalculateEnd(oSettings);
_fnDraw(oSettings)});if(typeof oSettings.aanFeatures.p=="undefined"){oSettings.aoDrawCallback.push({fn:function(oSettings){_oExt.oPagination[oSettings.sPaginationType].fnUpdate(oSettings,function(oSettings){_fnCalculateEnd(oSettings);
_fnDraw(oSettings)})},sName:"pagination"})}return nPaginate}function _fnPageChange(oSettings,sAction){var iOldStart=oSettings._iDisplayStart;
if(sAction=="first"){oSettings._iDisplayStart=0}else{if(sAction=="previous"){oSettings._iDisplayStart=oSettings._iDisplayLength>=0?oSettings._iDisplayStart-oSettings._iDisplayLength:0;
if(oSettings._iDisplayStart<0){oSettings._iDisplayStart=0}}else{if(sAction=="next"){if(oSettings._iDisplayLength>=0){if(oSettings._iDisplayStart+oSettings._iDisplayLength<oSettings.fnRecordsDisplay()){oSettings._iDisplayStart+=oSettings._iDisplayLength
}}else{oSettings._iDisplayStart=0}}else{if(sAction=="last"){if(oSettings._iDisplayLength>=0){var iPages=parseInt((oSettings.fnRecordsDisplay()-1)/oSettings._iDisplayLength,10)+1;
oSettings._iDisplayStart=(iPages-1)*oSettings._iDisplayLength}else{oSettings._iDisplayStart=0
}}else{alert("DataTables warning: unknown paging action: "+sAction)}}}}return iOldStart!=oSettings._iDisplayStart
}function _fnFeatureHtmlInfo(oSettings){var nInfo=document.createElement("div");nInfo.className=oSettings.oClasses.sInfo;
if(typeof oSettings.aanFeatures.i=="undefined"){oSettings.aoDrawCallback.push({fn:_fnUpdateInfo,sName:"information"});
if(oSettings.sTableId!==""){nInfo.setAttribute("id",oSettings.sTableId+"_info")}}return nInfo
}function _fnUpdateInfo(oSettings){if(!oSettings.oFeatures.bInfo||oSettings.aanFeatures.i.length===0){return
}var nFirst=oSettings.aanFeatures.i[0];if(oSettings.fnRecordsDisplay()===0&&oSettings.fnRecordsDisplay()==oSettings.fnRecordsTotal()){nFirst.innerHTML=oSettings.oLanguage.sInfoEmpty+oSettings.oLanguage.sInfoPostFix
}else{if(oSettings.fnRecordsDisplay()===0){nFirst.innerHTML=oSettings.oLanguage.sInfoEmpty+" "+oSettings.oLanguage.sInfoFiltered.replace("_MAX_",oSettings.fnRecordsTotal())+oSettings.oLanguage.sInfoPostFix
}else{if(oSettings.fnRecordsDisplay()==oSettings.fnRecordsTotal()){nFirst.innerHTML=oSettings.oLanguage.sInfo.replace("_START_",oSettings._iDisplayStart+1).replace("_END_",oSettings.fnDisplayEnd()).replace("_TOTAL_",oSettings.fnRecordsDisplay())+oSettings.oLanguage.sInfoPostFix
}else{nFirst.innerHTML=oSettings.oLanguage.sInfo.replace("_START_",oSettings._iDisplayStart+1).replace("_END_",oSettings.fnDisplayEnd()).replace("_TOTAL_",oSettings.fnRecordsDisplay())+" "+oSettings.oLanguage.sInfoFiltered.replace("_MAX_",oSettings.fnRecordsTotal())+oSettings.oLanguage.sInfoPostFix
}}}var n=oSettings.aanFeatures.i;if(n.length>1){var sInfo=nFirst.innerHTML;for(var i=1,iLen=n.length;
i<iLen;i++){n[i].innerHTML=sInfo}}}function _fnFeatureHtmlLength(oSettings){var sName=(oSettings.sTableId==="")?"":'name="'+oSettings.sTableId+'_length"';
var sStdMenu='<select size="1" '+sName+'><option value="10">10</option><option value="25">25</option><option value="50">50</option><option value="100">100</option></select>';
var nLength=document.createElement("div");if(oSettings.sTableId!==""&&typeof oSettings.aanFeatures.l=="undefined"){nLength.setAttribute("id",oSettings.sTableId+"_length")
}nLength.className=oSettings.oClasses.sLength;nLength.innerHTML=oSettings.oLanguage.sLengthMenu.replace("_MENU_",sStdMenu);
$('select option[value="'+oSettings._iDisplayLength+'"]',nLength).attr("selected",true);
$("select",nLength).change(function(e){var iVal=$(this).val();var n=oSettings.aanFeatures.l;
for(var i=0,iLen=n.length;i<iLen;i++){if(n[i]!=this.parentNode){$("select",n[i]).val(iVal)
}}oSettings._iDisplayLength=parseInt(iVal,10);_fnCalculateEnd(oSettings);if(oSettings._iDisplayEnd==oSettings.aiDisplay.length){oSettings._iDisplayStart=oSettings._iDisplayEnd-oSettings._iDisplayLength;
if(oSettings._iDisplayStart<0){oSettings._iDisplayStart=0}}if(oSettings._iDisplayLength==-1){oSettings._iDisplayStart=0
}_fnDraw(oSettings)});return nLength}function _fnFeatureHtmlProcessing(oSettings){var nProcessing=document.createElement("div");
if(oSettings.sTableId!==""&&typeof oSettings.aanFeatures.r=="undefined"){nProcessing.setAttribute("id",oSettings.sTableId+"_processing")
}nProcessing.innerHTML=oSettings.oLanguage.sProcessing;nProcessing.className=oSettings.oClasses.sProcessing;
oSettings.nTable.parentNode.insertBefore(nProcessing,oSettings.nTable);return nProcessing
}function _fnProcessingDisplay(oSettings,bShow){if(oSettings.oFeatures.bProcessing){var an=oSettings.aanFeatures.r;
for(var i=0,iLen=an.length;i<iLen;i++){an[i].style.visibility=bShow?"visible":"hidden"
}}}function _fnVisibleToColumnIndex(oSettings,iMatch){var iColumn=-1;for(var i=0;
i<oSettings.aoColumns.length;i++){if(oSettings.aoColumns[i].bVisible===true){iColumn++
}if(iColumn==iMatch){return i}}return null}function _fnColumnIndexToVisible(oSettings,iMatch){var iVisible=-1;
for(var i=0;i<oSettings.aoColumns.length;i++){if(oSettings.aoColumns[i].bVisible===true){iVisible++
}if(i==iMatch){return oSettings.aoColumns[i].bVisible===true?iVisible:null}}return null
}function _fnNodeToDataIndex(s,n){for(var i=0,iLen=s.aoData.length;i<iLen;i++){if(s.aoData[i]!==null&&s.aoData[i].nTr==n){return i
}}return null}function _fnVisbleColumns(oS){var iVis=0;for(var i=0;i<oS.aoColumns.length;
i++){if(oS.aoColumns[i].bVisible===true){iVis++}}return iVis}function _fnCalculateEnd(oSettings){if(oSettings.oFeatures.bPaginate===false){oSettings._iDisplayEnd=oSettings.aiDisplay.length
}else{if(oSettings._iDisplayStart+oSettings._iDisplayLength>oSettings.aiDisplay.length||oSettings._iDisplayLength==-1){oSettings._iDisplayEnd=oSettings.aiDisplay.length
}else{oSettings._iDisplayEnd=oSettings._iDisplayStart+oSettings._iDisplayLength}}}function _fnConvertToWidth(sWidth,nParent){if(!sWidth||sWidth===null||sWidth===""){return 0
}if(typeof nParent=="undefined"){nParent=document.getElementsByTagName("body")[0]
}var iWidth;var nTmp=document.createElement("div");nTmp.style.width=sWidth;nParent.appendChild(nTmp);
iWidth=nTmp.offsetWidth;nParent.removeChild(nTmp);return(iWidth)}function _fnCalculateColumnWidths(oSettings){var iTableWidth=oSettings.nTable.offsetWidth;
var iTotalUserIpSize=0;var iTmpWidth;var iVisibleColumns=0;var iColums=oSettings.aoColumns.length;
var i;var oHeaders=$("thead:eq(0)>th",oSettings.nTable);for(i=0;i<iColums;i++){if(oSettings.aoColumns[i].bVisible){iVisibleColumns++;
if(oSettings.aoColumns[i].sWidth!==null){iTmpWidth=_fnConvertToWidth(oSettings.aoColumns[i].sWidth,oSettings.nTable.parentNode);
iTotalUserIpSize+=iTmpWidth;oSettings.aoColumns[i].sWidth=iTmpWidth+"px"}}}if(iColums==oHeaders.length&&iTotalUserIpSize===0&&iVisibleColumns==iColums){for(i=0;
i<oSettings.aoColumns.length;i++){oSettings.aoColumns[i].sWidth=oHeaders[i].offsetWidth+"px"
}}else{var nCalcTmp=oSettings.nTable.cloneNode(false);nCalcTmp.setAttribute("id","");
var sTableTmp='<table class="'+nCalcTmp.className+'">';var sCalcHead="<tr>";var sCalcHtml="<tr>";
for(i=0;i<iColums;i++){if(oSettings.aoColumns[i].bVisible){sCalcHead+="<th>"+oSettings.aoColumns[i].sTitle+"</th>";
if(oSettings.aoColumns[i].sWidth!==null){var sWidth="";if(oSettings.aoColumns[i].sWidth!==null){sWidth=' style="width:'+oSettings.aoColumns[i].sWidth+';"'
}sCalcHtml+="<td"+sWidth+' tag_index="'+i+'">'+fnGetMaxLenString(oSettings,i)+"</td>"
}else{sCalcHtml+='<td tag_index="'+i+'">'+fnGetMaxLenString(oSettings,i)+"</td>"}}}sCalcHead+="</tr>";
sCalcHtml+="</tr>";nCalcTmp=$(sTableTmp+sCalcHead+sCalcHtml+"</table>")[0];nCalcTmp.style.width=iTableWidth+"px";
nCalcTmp.style.visibility="hidden";nCalcTmp.style.position="absolute";oSettings.nTable.parentNode.appendChild(nCalcTmp);
var oNodes=$("tr:eq(1)>td",nCalcTmp);var iIndex;for(i=0;i<oNodes.length;i++){iIndex=oNodes[i].getAttribute("tag_index");
var iContentWidth=$("td",nCalcTmp).eq(i).width();var iSetWidth=oSettings.aoColumns[i].sWidth?oSettings.aoColumns[i].sWidth.slice(0,-2):0;
oSettings.aoColumns[iIndex].sWidth=Math.max(iContentWidth,iSetWidth)+"px"}oSettings.nTable.parentNode.removeChild(nCalcTmp)
}}function fnGetMaxLenString(oSettings,iCol){var iMax=0;var iMaxIndex=-1;for(var i=0;
i<oSettings.aoData.length;i++){if(oSettings.aoData[i]._aData[iCol].length>iMax){iMax=oSettings.aoData[i]._aData[iCol].length;
iMaxIndex=i}}if(iMaxIndex>=0){return oSettings.aoData[iMaxIndex]._aData[iCol]}return""
}function _fnArrayCmp(aArray1,aArray2){if(aArray1.length!=aArray2.length){return 1
}for(var i=0;i<aArray1.length;i++){if(aArray1[i]!=aArray2[i]){return 2}}return 0}function _fnDetectType(sData){var aTypes=_oExt.aTypes;
var iLen=aTypes.length;for(var i=0;i<iLen;i++){var sType=aTypes[i](sData);if(sType!==null){return sType
}}return"string"}function _fnSettingsFromNode(nTable){for(var i=0;i<_aoSettings.length;
i++){if(_aoSettings[i].nTable==nTable){return _aoSettings[i]}}return null}function _fnGetDataMaster(oSettings){var aData=[];
var iLen=oSettings.aoData.length;for(var i=0;i<iLen;i++){if(oSettings.aoData[i]===null){aData.push(null)
}else{aData.push(oSettings.aoData[i]._aData)}}return aData}function _fnGetTrNodes(oSettings){var aNodes=[];
var iLen=oSettings.aoData.length;for(var i=0;i<iLen;i++){if(oSettings.aoData[i]===null){aNodes.push(null)
}else{aNodes.push(oSettings.aoData[i].nTr)}}return aNodes}function _fnGetTdNodes(oSettings){var nTrs=_fnGetTrNodes(oSettings);
var nTds=[],nTd;var anReturn=[];var iCorrector;var iRow,iRows,iColumn,iColumns;for(iRow=0,iRows=nTrs.length;
iRow<iRows;iRow++){nTds=[];for(iColumn=0,iColumns=nTrs[iRow].childNodes.length;iColumn<iColumns;
iColumn++){nTd=nTrs[iRow].childNodes[iColumn];if(nTd.nodeName=="TD"){nTds.push(nTd)
}}iCorrector=0;for(iColumn=0,iColumns=oSettings.aoColumns.length;iColumn<iColumns;
iColumn++){if(oSettings.aoColumns[iColumn].bVisible){anReturn.push(nTds[iColumn-iCorrector])
}else{anReturn.push(oSettings.aoData[iRow]._anHidden[iColumn]);iCorrector++}}}return anReturn
}function _fnEscapeRegex(sVal){var acEscape=["/",".","*","+","?","|","(",")","[","]","{","}","\\","$","^"];
var reReplace=new RegExp("(\\"+acEscape.join("|\\")+")","g");return sVal.replace(reReplace,"\\$1")
}function _fnReOrderIndex(oSettings,sColumns){var aColumns=sColumns.split(",");var aiReturn=[];
for(var i=0,iLen=oSettings.aoColumns.length;i<iLen;i++){for(var j=0;j<iLen;j++){if(oSettings.aoColumns[i].sName==aColumns[j]){aiReturn.push(j);
break}}}return aiReturn}function _fnColumnOrdering(oSettings){var sNames="";for(var i=0,iLen=oSettings.aoColumns.length;
i<iLen;i++){sNames+=oSettings.aoColumns[i].sName+","}if(sNames.length==iLen){return""
}return sNames.slice(0,-1)}function _fnClearTable(oSettings){oSettings.aoData.length=0;
oSettings.aiDisplayMaster.length=0;oSettings.aiDisplay.length=0;_fnCalculateEnd(oSettings)
}function _fnSaveState(oSettings){if(!oSettings.oFeatures.bStateSave){return}var i;
var sValue="{";sValue+='"iStart": '+oSettings._iDisplayStart+",";sValue+='"iEnd": '+oSettings._iDisplayEnd+",";
sValue+='"iLength": '+oSettings._iDisplayLength+",";sValue+='"sFilter": "'+oSettings.oPreviousSearch.sSearch.replace('"','\\"')+'",';
sValue+='"sFilterEsc": '+oSettings.oPreviousSearch.bEscapeRegex+",";sValue+='"aaSorting": [ ';
for(i=0;i<oSettings.aaSorting.length;i++){sValue+="["+oSettings.aaSorting[i][0]+",'"+oSettings.aaSorting[i][1]+"'],"
}sValue=sValue.substring(0,sValue.length-1);sValue+="],";sValue+='"aaSearchCols": [ ';
for(i=0;i<oSettings.aoPreSearchCols.length;i++){sValue+="['"+oSettings.aoPreSearchCols[i].sSearch.replace("'","'")+"',"+oSettings.aoPreSearchCols[i].bEscapeRegex+"],"
}sValue=sValue.substring(0,sValue.length-1);sValue+="],";sValue+='"abVisCols": [ ';
for(i=0;i<oSettings.aoColumns.length;i++){sValue+=oSettings.aoColumns[i].bVisible+","
}sValue=sValue.substring(0,sValue.length-1);sValue+="]";sValue+="}";_fnCreateCookie("SpryMedia_DataTables_"+oSettings.sInstance,sValue,oSettings.iCookieDuration)
}function _fnLoadState(oSettings,oInit){if(!oSettings.oFeatures.bStateSave){return
}var oData;var sData=_fnReadCookie("SpryMedia_DataTables_"+oSettings.sInstance);if(sData!==null&&sData!==""){try{if(typeof JSON=="object"&&typeof JSON.parse=="function"){oData=JSON.parse(sData.replace(/'/g,'"'))
}else{oData=eval("("+sData+")")}}catch(e){return}oSettings._iDisplayStart=oData.iStart;
oSettings.iInitDisplayStart=oData.iStart;oSettings._iDisplayEnd=oData.iEnd;oSettings._iDisplayLength=oData.iLength;
oSettings.oPreviousSearch.sSearch=oData.sFilter;oSettings.aaSorting=oData.aaSorting.slice();
oSettings.saved_aaSorting=oData.aaSorting.slice();if(typeof oData.sFilterEsc!="undefined"){oSettings.oPreviousSearch.bEscapeRegex=oData.sFilterEsc
}if(typeof oData.aaSearchCols!="undefined"){for(var i=0;i<oData.aaSearchCols.length;
i++){oSettings.aoPreSearchCols[i]={sSearch:oData.aaSearchCols[i][0],bEscapeRegex:oData.aaSearchCols[i][1]}
}}if(typeof oData.abVisCols!="undefined"){oInit.saved_aoColumns=[];for(i=0;i<oData.abVisCols.length;
i++){oInit.saved_aoColumns[i]={};oInit.saved_aoColumns[i].bVisible=oData.abVisCols[i]
}}}}function _fnCreateCookie(sName,sValue,iSecs){var date=new Date();date.setTime(date.getTime()+(iSecs*1000));
sName+="_"+window.location.pathname.replace(/[\/:]/g,"").toLowerCase();document.cookie=sName+"="+encodeURIComponent(sValue)+"; expires="+date.toGMTString()+"; path=/"
}function _fnReadCookie(sName){var sNameEQ=sName+"_"+window.location.pathname.replace(/[\/:]/g,"").toLowerCase()+"=";
var sCookieContents=document.cookie.split(";");for(var i=0;i<sCookieContents.length;
i++){var c=sCookieContents[i];while(c.charAt(0)==" "){c=c.substring(1,c.length)}if(c.indexOf(sNameEQ)===0){return decodeURIComponent(c.substring(sNameEQ.length,c.length))
}}return null}function _fnGetUniqueThs(nThead){var nTrs=nThead.getElementsByTagName("tr");
if(nTrs.length==1){return nTrs[0].getElementsByTagName("th")}var aLayout=[],aReturn=[];
var ROWSPAN=2,COLSPAN=3,TDELEM=4;var i,j,k,iLen,jLen,iColumnShifted;var fnShiftCol=function(a,i,j){while(typeof a[i][j]!="undefined"){j++
}return j};var fnAddRow=function(i){if(typeof aLayout[i]=="undefined"){aLayout[i]=[]
}};for(i=0,iLen=nTrs.length;i<iLen;i++){fnAddRow(i);var iColumn=0;var nTds=[];for(j=0,jLen=nTrs[i].childNodes.length;
j<jLen;j++){if(nTrs[i].childNodes[j].nodeName=="TD"||nTrs[i].childNodes[j].nodeName=="TH"){nTds.push(nTrs[i].childNodes[j])
}}for(j=0,jLen=nTds.length;j<jLen;j++){var iColspan=nTds[j].getAttribute("colspan")*1;
var iRowspan=nTds[j].getAttribute("rowspan")*1;if(!iColspan||iColspan===0||iColspan===1){iColumnShifted=fnShiftCol(aLayout,i,iColumn);
aLayout[i][iColumnShifted]=(nTds[j].nodeName=="TD")?TDELEM:nTds[j];if(iRowspan||iRowspan===0||iRowspan===1){for(k=1;
k<iRowspan;k++){fnAddRow(i+k);aLayout[i+k][iColumnShifted]=ROWSPAN}}iColumn++}else{iColumnShifted=fnShiftCol(aLayout,i,iColumn);
for(k=0;k<iColspan;k++){aLayout[i][iColumnShifted+k]=COLSPAN}iColumn+=iColspan}}}for(i=0,iLen=aLayout[0].length;
i<iLen;i++){for(j=0,jLen=aLayout.length;j<jLen;j++){if(typeof aLayout[j][i]=="object"){aReturn.push(aLayout[j][i])
}}}return aReturn}function _fnMap(oRet,oSrc,sName,sMappedName){if(typeof sMappedName=="undefined"){sMappedName=sName
}if(typeof oSrc[sName]!="undefined"){oRet[sMappedName]=oSrc[sName]}}this.oApi._fnInitalise=_fnInitalise;
this.oApi._fnLanguageProcess=_fnLanguageProcess;this.oApi._fnAddColumn=_fnAddColumn;
this.oApi._fnAddData=_fnAddData;this.oApi._fnGatherData=_fnGatherData;this.oApi._fnDrawHead=_fnDrawHead;
this.oApi._fnDraw=_fnDraw;this.oApi._fnAjaxUpdate=_fnAjaxUpdate;this.oApi._fnAddOptionsHtml=_fnAddOptionsHtml;
this.oApi._fnFeatureHtmlFilter=_fnFeatureHtmlFilter;this.oApi._fnFeatureHtmlInfo=_fnFeatureHtmlInfo;
this.oApi._fnFeatureHtmlPaginate=_fnFeatureHtmlPaginate;this.oApi._fnPageChange=_fnPageChange;
this.oApi._fnFeatureHtmlLength=_fnFeatureHtmlLength;this.oApi._fnFeatureHtmlProcessing=_fnFeatureHtmlProcessing;
this.oApi._fnProcessingDisplay=_fnProcessingDisplay;this.oApi._fnFilterComplete=_fnFilterComplete;
this.oApi._fnFilterColumn=_fnFilterColumn;this.oApi._fnFilter=_fnFilter;this.oApi._fnSortingClasses=_fnSortingClasses;
this.oApi._fnVisibleToColumnIndex=_fnVisibleToColumnIndex;this.oApi._fnColumnIndexToVisible=_fnColumnIndexToVisible;
this.oApi._fnNodeToDataIndex=_fnNodeToDataIndex;this.oApi._fnVisbleColumns=_fnVisbleColumns;
this.oApi._fnBuildSearchArray=_fnBuildSearchArray;this.oApi._fnDataToSearch=_fnDataToSearch;
this.oApi._fnCalculateEnd=_fnCalculateEnd;this.oApi._fnConvertToWidth=_fnConvertToWidth;
this.oApi._fnCalculateColumnWidths=_fnCalculateColumnWidths;this.oApi._fnArrayCmp=_fnArrayCmp;
this.oApi._fnDetectType=_fnDetectType;this.oApi._fnGetDataMaster=_fnGetDataMaster;
this.oApi._fnGetTrNodes=_fnGetTrNodes;this.oApi._fnGetTdNodes=_fnGetTdNodes;this.oApi._fnEscapeRegex=_fnEscapeRegex;
this.oApi._fnReOrderIndex=_fnReOrderIndex;this.oApi._fnColumnOrdering=_fnColumnOrdering;
this.oApi._fnClearTable=_fnClearTable;this.oApi._fnSaveState=_fnSaveState;this.oApi._fnLoadState=_fnLoadState;
this.oApi._fnCreateCookie=_fnCreateCookie;this.oApi._fnReadCookie=_fnReadCookie;this.oApi._fnGetUniqueThs=_fnGetUniqueThs;
this.oApi._fnReDraw=_fnReDraw;var _that=this;return this.each(function(){var i=0,iLen,j,jLen;
for(i=0,iLen=_aoSettings.length;i<iLen;i++){if(_aoSettings[i].nTable==this){alert("DataTables warning: Unable to re-initialise DataTable. Please use the API to make any configuration changes required.");
return _aoSettings[i]}}var oSettings=new classSettings();_aoSettings.push(oSettings);
var bInitHandedOff=false;var bUsePassedData=false;var sId=this.getAttribute("id");
if(sId!==null){oSettings.sTableId=sId;oSettings.sInstance=sId}else{oSettings.sInstance=_oExt._oExternConfig.iNextUnique++
}oSettings.nTable=this;oSettings.oApi=_that.oApi;if(typeof oInit!="undefined"&&oInit!==null){_fnMap(oSettings.oFeatures,oInit,"bPaginate");
_fnMap(oSettings.oFeatures,oInit,"bLengthChange");_fnMap(oSettings.oFeatures,oInit,"bFilter");
_fnMap(oSettings.oFeatures,oInit,"bSort");_fnMap(oSettings.oFeatures,oInit,"bInfo");
_fnMap(oSettings.oFeatures,oInit,"bProcessing");_fnMap(oSettings.oFeatures,oInit,"bAutoWidth");
_fnMap(oSettings.oFeatures,oInit,"bSortClasses");_fnMap(oSettings.oFeatures,oInit,"bServerSide");
_fnMap(oSettings,oInit,"asStripClasses");_fnMap(oSettings,oInit,"fnRowCallback");
_fnMap(oSettings,oInit,"fnHeaderCallback");_fnMap(oSettings,oInit,"fnFooterCallback");
_fnMap(oSettings,oInit,"fnInitComplete");_fnMap(oSettings,oInit,"fnServerData");_fnMap(oSettings,oInit,"aaSorting");
_fnMap(oSettings,oInit,"aaSortingFixed");_fnMap(oSettings,oInit,"sPaginationType");
_fnMap(oSettings,oInit,"sAjaxSource");_fnMap(oSettings,oInit,"iCookieDuration");_fnMap(oSettings,oInit,"sDom");
_fnMap(oSettings,oInit,"oSearch","oPreviousSearch");_fnMap(oSettings,oInit,"aoSearchCols","aoPreSearchCols");
_fnMap(oSettings,oInit,"iDisplayLength","_iDisplayLength");_fnMap(oSettings,oInit,"bJQueryUI","bJUI");
if(typeof oInit.fnDrawCallback=="function"){oSettings.aoDrawCallback.push({fn:oInit.fnDrawCallback,sName:"user"})
}if(oSettings.oFeatures.bServerSide&&oSettings.oFeatures.bSort&&oSettings.oFeatures.bSortClasses){oSettings.aoDrawCallback.push({fn:_fnSortingClasses,sName:"server_side_sort_classes"})
}if(typeof oInit.bJQueryUI!="undefined"&&oInit.bJQueryUI){oSettings.oClasses=_oExt.oJUIClasses;
if(typeof oInit.sDom=="undefined"){oSettings.sDom='<"H"lfr>t<"F"ip>'}}if(typeof oInit.iDisplayStart!="undefined"&&typeof oSettings.iInitDisplayStart=="undefined"){oSettings.iInitDisplayStart=oInit.iDisplayStart;
oSettings._iDisplayStart=oInit.iDisplayStart}if(typeof oInit.bStateSave!="undefined"){oSettings.oFeatures.bStateSave=oInit.bStateSave;
_fnLoadState(oSettings,oInit);oSettings.aoDrawCallback.push({fn:_fnSaveState,sName:"state_save"})
}if(typeof oInit.aaData!="undefined"){bUsePassedData=true}if(typeof oInit!="undefined"&&typeof oInit.aoData!="undefined"){oInit.aoColumns=oInit.aoData
}if(typeof oInit.oLanguage!="undefined"){if(typeof oInit.oLanguage.sUrl!="undefined"&&oInit.oLanguage.sUrl!==""){oSettings.oLanguage.sUrl=oInit.oLanguage.sUrl;
$.getJSON(oSettings.oLanguage.sUrl,null,function(json){_fnLanguageProcess(oSettings,json,true)
});bInitHandedOff=true}else{_fnLanguageProcess(oSettings,oInit.oLanguage,false)}}}else{oInit={}
}if(typeof oInit.asStripClasses=="undefined"){oSettings.asStripClasses.push(oSettings.oClasses.sStripOdd);
oSettings.asStripClasses.push(oSettings.oClasses.sStripEven)}var nThead=this.getElementsByTagName("thead");
var nThs=nThead.length===0?null:_fnGetUniqueThs(nThead[0]);var bUseCols=typeof oInit.aoColumns!="undefined";
for(i=0,iLen=bUseCols?oInit.aoColumns.length:nThs.length;i<iLen;i++){var oCol=bUseCols?oInit.aoColumns[i]:null;
var nTh=nThs?nThs[i]:null;if(typeof oInit.saved_aoColumns!="undefined"&&oInit.saved_aoColumns.length==iLen){if(oCol===null){oCol={}
}oCol.bVisible=oInit.saved_aoColumns[i].bVisible}_fnAddColumn(oSettings,oCol,nTh)
}for(i=0,iLen=oSettings.aaSorting.length;i<iLen;i++){var oColumn=oSettings.aoColumns[oSettings.aaSorting[i][0]];
if(typeof oSettings.aaSorting[i][2]=="undefined"){oSettings.aaSorting[i][2]=0}if(typeof oInit.aaSorting=="undefined"&&typeof oSettings.saved_aaSorting=="undefined"){oSettings.aaSorting[i][1]=oColumn.asSorting[0]
}for(j=0,jLen=oColumn.asSorting.length;j<jLen;j++){if(oSettings.aaSorting[i][1]==oColumn.asSorting[j]){oSettings.aaSorting[i][2]=j;
break}}}if(this.getElementsByTagName("thead").length===0){this.appendChild(document.createElement("thead"))
}if(this.getElementsByTagName("tbody").length===0){this.appendChild(document.createElement("tbody"))
}if(bUsePassedData){for(i=0;i<oInit.aaData.length;i++){_fnAddData(oSettings,oInit.aaData[i])
}}else{_fnGatherData(oSettings)}oSettings.aiDisplay=oSettings.aiDisplayMaster.slice();
if(oSettings.oFeatures.bAutoWidth){_fnCalculateColumnWidths(oSettings)}oSettings.bInitialised=true;
if(bInitHandedOff===false){_fnInitalise(oSettings)}})}})(jQuery);

/*
* Function: fnLengthChangeRelative
* Purpose:  Change the number of records on display relative to what is currently is showing
* Returns:  array:
* Inputs:   object:oSettings - DataTables settings object
*           int:iDisplay - Display length change
*/
$.fn.dataTableExt.oApi. fnLengthChangeRelative = function ( oSettings, iDisplay )
{
	oSettings._iDisplayLength += iDisplay;
	oSettings.oApi._fnCalculateEnd( oSettings );
	
	/* Always show at least 10 records */
	if ( oSettings._iDisplayLength < 10 )
	{
		oSettings._iDisplayLength = 10;
	}
	
	/* If we have space to show extra rows (backing up from the end point - then do so */
	if ( oSettings._iDisplayEnd == oSettings.aiDisplay.length )
	{
		oSettings._iDisplayStart = oSettings._iDisplayEnd - oSettings._iDisplayLength;
		if ( oSettings._iDisplayStart < 0 )
		{
			oSettings._iDisplayStart = 0;
		}
	}
	
	if ( oSettings._iDisplayLength == -1 )
	{
		oSettings._iDisplayStart = 0;
	}
	
	oSettings.oApi._fnDraw( oSettings );
	
	$('select', oSettings.oFeatures.l).val( iDisplay );
}

/* Pagination scrolling */
/* Time between each scrolling frame */

$.fn.dataTableExt.oPagination.iTweenTime = 50;

$.fn.dataTableExt.oPagination.fnRunAnimation = function ( oSettings, fnCallbackDraw )
{
	var iTween = $.fn.dataTableExt.oPagination.iTweenTime;
	var innerLoop = function () {
		if ( oSettings.iPagingLoopStart > oSettings.iPagingEnd )
		{
			oSettings.iPagingLoopStart--;
			oSettings._iDisplayStart = oSettings.iPagingLoopStart;
			fnCallbackDraw( oSettings );
			setTimeout( function() { innerLoop(); }, iTween );
		}
		else if ( oSettings.iPagingLoopStart < oSettings.iPagingEnd )
		{
			oSettings.iPagingLoopStart++;
			oSettings._iDisplayStart = oSettings.iPagingLoopStart;
			fnCallbackDraw( oSettings );
			setTimeout( function() { innerLoop(); }, iTween );
		}
		else
		{
			oSettings.iPagingLoopStart = -1;
		}
	};
	innerLoop();
}

$.fn.dataTableExt.oPagination.full_numbers = {
	"fnInit": function ( oSettings, nPaging, fnCallbackDraw )
	{
		var nFirst = document.createElement( 'span' );
		var nPrevious = document.createElement( 'span' );
		var nList = document.createElement( 'span' );
		var nNext = document.createElement( 'span' );
		var nLast = document.createElement( 'span' );
		
		nFirst.innerHTML = oSettings.oLanguage.oPaginate.sFirst;
		nPrevious.innerHTML = oSettings.oLanguage.oPaginate.sPrevious;
		nNext.innerHTML = oSettings.oLanguage.oPaginate.sNext;
		nLast.innerHTML = oSettings.oLanguage.oPaginate.sLast;
		
		var oClasses = oSettings.oClasses;
		nFirst.className = oClasses.sPageButton+" "+oClasses.sPageFirst;
		nPrevious.className = oClasses.sPageButton+" "+oClasses.sPagePrevious;
		nNext.className= oClasses.sPageButton+" "+oClasses.sPageNext;
		nLast.className = oClasses.sPageButton+" "+oClasses.sPageLast;
		
		nPaging.appendChild( nFirst );
		nPaging.appendChild( nPrevious );
		nPaging.appendChild( nList );
		nPaging.appendChild( nNext );
		nPaging.appendChild( nLast );
		
		$(nFirst).click( function() {
			/* Disallow paging event during a current paging event */
			if ( typeof oSettings.iPagingLoopStart != 'undefined' && oSettings.iPagingLoopStart != -1 )
			{
				return;
			}
			
			oSettings.iPagingLoopStart = oSettings._iDisplayStart;
			oSettings.iPagingEnd = 0;
			
			$.fn.dataTableExt.oPagination.fnRunAnimation( oSettings, fnCallbackDraw );
		} );
		
		$(nPrevious).click( function() {
			/* Disallow paging event during a current paging event */
			if ( typeof oSettings.iPagingLoopStart != 'undefined' && oSettings.iPagingLoopStart != -1 )
			{
				return;
			}
			
			oSettings.iPagingLoopStart = oSettings._iDisplayStart;
			oSettings.iPagingEnd = oSettings._iDisplayStart - oSettings._iDisplayLength;
			
			/* Correct for underrun */
			if ( oSettings.iPagingEnd < 0 )
			{
			  oSettings.iPagingEnd = 0;
			}
			
			$.fn.dataTableExt.oPagination.fnRunAnimation( oSettings, fnCallbackDraw );
		} );
		
		$(nNext).click( function() {
			/* Disallow paging event during a current paging event */
			if ( typeof oSettings.iPagingLoopStart != 'undefined' && oSettings.iPagingLoopStart != -1 )
			{
				return;
			}
			
			/* Make sure we are not over running the display array */
			if ( oSettings._iDisplayStart + oSettings._iDisplayLength < oSettings.fnRecordsDisplay() )
			{
				oSettings.iPagingEnd = oSettings._iDisplayStart + oSettings._iDisplayLength;
			}
			
			oSettings.iPagingLoopStart = oSettings._iDisplayStart;
			$.fn.dataTableExt.oPagination.fnRunAnimation( oSettings, fnCallbackDraw );
		} );
		
		$(nLast).click( function() {
			/* Disallow paging event during a current paging event */
			if ( typeof oSettings.iPagingLoopStart != 'undefined' && oSettings.iPagingLoopStart != -1 )
			{
				return;
			}
		
			if ( oSettings._iDisplayLength >= 0 )
			{
				var iPages = parseInt( (oSettings.fnRecordsDisplay()-1) / oSettings._iDisplayLength, 10 ) + 1;
				oSettings.iPagingEnd = (iPages-1) * oSettings._iDisplayLength;
			}
			else
			{
				oSettings.iPagingEnd = 0;
			}
			
			oSettings.iPagingLoopStart = oSettings._iDisplayStart;
			$.fn.dataTableExt.oPagination.fnRunAnimation( oSettings, fnCallbackDraw );
		} );
		
		/* Take the brutal approach to cancelling text selection */
		$('span', nPaging)
			.bind( 'mousedown', function () { return false; } )
			.bind( 'selectstart', function () { return false; } );
	},
	
	
	
	"fnUpdate": function ( oSettings, fnCallbackDraw )
	{
		if ( !oSettings.aanFeatures.p )
		{
			return;
		}
		
		var iPageCount = $.fn.dataTableExt.oPagination.iFullNumbersShowPages;
		var iPageCountHalf = Math.floor(iPageCount / 2);
		var iPages = Math.ceil((oSettings.fnRecordsDisplay()) / oSettings._iDisplayLength);
		var iCurrentPage = Math.ceil(oSettings._iDisplayStart / oSettings._iDisplayLength) + 1;
		var sList = "";
		var iStartButton, iEndButton, i, iLen;
		var oClasses = oSettings.oClasses;
		
		/* Pages calculation */
		if (iPages < iPageCount)
		{
			iStartButton = 1;
			iEndButton = iPages;
		}
		else
		{
			if (iCurrentPage <= iPageCountHalf)
			{
				iStartButton = 1;
				iEndButton = iPageCount;
			}
			else
			{
				if (iCurrentPage >= (iPages - iPageCountHalf))
				{
					iStartButton = iPages - iPageCount + 1;
					iEndButton = iPages;
				}
				else
				{
					iStartButton = iCurrentPage - Math.ceil(iPageCount / 2) + 1;
					iEndButton = iStartButton + iPageCount - 1;
				}
			}
		}
		
		/* Build the dynamic list */
		for ( i=iStartButton ; i<=iEndButton ; i++ )
		{
			if ( iCurrentPage != i )
			{
				sList += '<span class="'+oClasses.sPageButton+'">'+i+'</span>';
			}
			else
			{
				sList += '<span class="'+oClasses.sPageButtonActive+'">'+i+'</span>';
			}
		}
		
		/* Loop over each instance of the pager */
		var an = oSettings.aanFeatures.p;
		var anButtons, anStatic, nPaginateList;
		var fnClick = function() {
			/* Use the information in the element to jump to the required page */
			var iTarget = (this.innerHTML * 1) - 1;
			oSettings.iPagingLoopStart = oSettings._iDisplayStart;
			oSettings.iPagingEnd = iTarget * oSettings._iDisplayLength;
			
			/* Correct for underrun */
			if ( oSettings.iPagingEnd < 0 )
			{
			  oSettings.iPagingEnd = 0;
			}
			
			$.fn.dataTableExt.oPagination.fnRunAnimation( oSettings, fnCallbackDraw );
			return false;
		};
		var fnFalse = function () { return false; };
		
		for ( i=0, iLen=an.length ; i<iLen ; i++ )
		{
			if ( an[i].childNodes.length === 0 )
			{
				continue;
			}
			
			/* Build up the dynamic list forst - html and listeners */
			nPaginateList = an[i].childNodes[2];
			nPaginateList.innerHTML = sList;
			
			$('span', nPaginateList).click( fnClick ).bind( 'mousedown', fnFalse )
				.bind( 'selectstart', fnFalse );
			
			/* Update the 'premanent botton's classes */
			anButtons = an[i].getElementsByTagName('span');
			anStatic = [
				anButtons[0], anButtons[1], 
				anButtons[anButtons.length-2], anButtons[anButtons.length-1]
			];
			$(anStatic).removeClass( oClasses.sPageButton+" "+oClasses.sPageButtonActive+" "+oClasses.sPageButtonStaticDisabled );
			if ( iCurrentPage == 1 )
			{
				anStatic[0].className += " "+oClasses.sPageButtonStaticDisabled;
				anStatic[1].className += " "+oClasses.sPageButtonStaticDisabled;
			}
			else
			{
				anStatic[0].className += " "+oClasses.sPageButton;
				anStatic[1].className += " "+oClasses.sPageButton;
			}
			
			if ( iPages === 0 || iCurrentPage == iPages || oSettings._iDisplayLength == -1 )
			{
				anStatic[2].className += " "+oClasses.sPageButtonStaticDisabled;
				anStatic[3].className += " "+oClasses.sPageButtonStaticDisabled;
			}
			else
			{
				anStatic[2].className += " "+oClasses.sPageButton;
				anStatic[3].className += " "+oClasses.sPageButton;
			}
		}
	}
}

jQuery.fn.highlight = function(pat) {
    function innerHighlight(node, pat) {
        var skip = 0;
        if (node.nodeType == 3) {
            var pos = node.data.toUpperCase().indexOf(pat);
            if (pos >= 0) {
                var spannode = document.createElement('span');
                spannode.className = 'highlight';
                var middlebit = node.splitText(pos);
                var endbit = middlebit.splitText(pat.length);
                var middleclone = middlebit.cloneNode(true);
                spannode.appendChild(middleclone);
                middlebit.parentNode.replaceChild(spannode, middlebit);
                skip = 1;
            }
        }
        else if (node.nodeType == 1 && node.childNodes && !/(script|style)/i.test(node.tagName)) {
            for (var i = 0; i < node.childNodes.length; ++i) {
                i += innerHighlight(node.childNodes[i], pat);
            }
        }
    return skip;
    }
    return this.each(function() {
        innerHighlight(this, pat.toUpperCase());
    });
};

jQuery.fn.removeHighlight = function() {
    return this.find("span.highlight").each(function() {
        this.parentNode.firstChild.nodeName;
        with (this.parentNode) {
            replaceChild(this.firstChild, this);
            normalize();
        }
     }).end();
};

function linkbuttons() {
    $(".linkButton").click(function(){
        window.location = $(this).attr("name");
    });
};
function twitterOn() {
    if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
    $("input[type=radio]").click(function(){
        if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
    });
};
function isScrolledIntoView(elem) {
    var docViewTop = $(window).scrollTop();
    var docViewBottom = docViewTop + $(window).height();
    var elemTop = $(elem).offset().top;
    var elemBottom = elemTop + $(elem).height();
    return ((docViewTop < elemTop) && (docViewBottom > elemBottom));
}
$(window).scroll(function(){
  var scroller = $("#formScroll");
  if(isScrolledIntoView(scroller)){$("#scrollBtm").show();}else{$("#scrollBtm").hide();};
})
function setupSearch() {
  $(".optionsNoScript").hide();
  $(".optionsScript").show();

    var A = $("#topOptions");
    var B = A.parent().parent();
    var C = B.find("a");
    var t1 = C.text();
    var t2 = "Hide options";
    C.click(function(){
        var D = $(this);
        $('#footerSearch').toggle();
        A.toggle();
        B.toggleClass("darker");
        D.toggleClass("attn");
        D.toggleText(t1, t2);
        B.mouseup(function(){
            return false
        });
        $(document).mouseup(function(D){
            if($(D.target).parent("a").length==0){
                hideSearch()
            };
        });
        function hideSearch(){
            A.hide();
            B.removeClass("darker");
            C.removeClass("attn");
            C.text(t1);
        };
    });
    var E = $("#bottomOptions");
    var F = E.parent().parent();
    var G = F.find("a");
    var t3 = G.text();
    var t4 = "Hide options";
    G.click(function(){
        var H = $(this);
        E.toggle();
        if($("#bottomOptions").is(":visible")){if($("#scrollBtm").is(":hidden")){$.scrollTo($("#formScroll"),800);};};
        F.toggleClass("darker");
        H.toggleClass("attn");
        H.toggleText(t3, t4);
        $("#btmSrchLabel").toggle();
        F.mouseup(function(){
            return false
        });
        $(document).mouseup(function(H){
            if($(H.target).parent("a").length==0){
                hideSearch()
            };
        });
        function hideSearch(){
            E.hide();
            F.removeClass("darker");
            G.removeClass("attn");
            G.text(t3);
        };    
    });

};

function flickrBuild(){$(".flickrs").flickr({callback:colorboxCallback});};
function colorboxCallback(){$('a.flickrpic').colorbox({photo:true,preloading:true,opacity:'0.70'});};

function aboutFeeds() {
    jQuery.getFeed({
        url: 'http://www.archive.org/services/collection-rss.php?mediatype=texts',
        success: function(feed) {
        
            jQuery('#resultScanned').append('<h4>New Scanned Books</h4>');
            var html = '';
            for(var i = 0; i < feed.items.length && i < 4; i++) {
                var item = feed.items[i];
                html += '<div class="item"><div class="cover">'+item.description+'</div><div class="title"><a href="'+item.link+'"><strong>'+item.title+'</strong></a></div><div class="updated">'+item.updated+'</div></div>';
            }
            jQuery('#resultScanned').append(html);
            jQuery('#resultScanned').append('<div class="title"><a href="'+feed.link+'">See all</a></div>');
        }    
    });
    jQuery.getFeed({
        url: 'http://blog.openlibrary.org/feed/',
        success: function(feed) {
        
            jQuery('#resultBlog').append('<h4>From The Blog</h4>');
            var html = '';
            for(var i = 0; i < feed.items.length && i < 2; i++) {
                var item = feed.items[i];
                html += '<div class="item"><div class="title"><a href="'+item.link+'">'+item.title+'</a></div><div class="byline">By '+item.author+', '+item.updated+'</div><div class="content">'+item.description+'</div></div>';
            }
            jQuery('#resultBlog').append(html);
            jQuery('#resultBlog').append('<div class="content"><a href="'+feed.link+'">Visit the blog...</a></div>');
        }    
    });
};


// BUILD CAROUSEL 
function carouselSetup(loadCovers, loadLists) {
  $('#coversCarousel').jcarousel({
    visible: 1,
    scroll: 1,
    itemLoadCallback: loadCovers
  });
// SET-UP COVERS LIST
  $('#listCarousel').jcarousel({
    vertical: true,
    visible: 6,
    scroll: 6,
    itemLoadCallback: loadLists
  });
// SWITCH RESULTS VIEW
  $("#resultsList").hide()
  $("a#booksList").click(function(){
    //page.listCarousel.scroll(1+page.pos);
    
    $('span.tools a').toggleClass('on');
    $('#resultsList').customFadeIn();
    $('#resultsCovers').hide();
  });
  $("a#booksCovers").click(function(){
    //page.coverCarousel.scroll(1+page.pos/12);
    
    $('span.tools a').toggleClass('on');
    $('#resultsList').hide();
    $('#resultsCovers').customFadeIn();
  });
// SWITCH EDITIONS VIEW
  $("#editionsList").hide()
  $("a#edsList").click(function(){
    $('span.tools a').toggleClass('on');
    $('#editionsList').customFadeIn();
    $('#editionsCovers').hide();
  });
  $("a#edsCovers").click(function(){
    $('span.tools a').toggleClass('on');
    $('#editionsList').hide();
    $('#editionsCovers').customFadeIn();
  });
};
// BOOK COVERS
function bookCovers(){
    $("img.cover").error(function(){
        $(this).closest(".SRPCover").hide();
        $(this).closest(".coverMagic").find(".SRPCoverBlank").show();
    });
};
// CLOSE POP-UP FROM IFRAME 
function closePop(){
    $("#popClose").click(function(){
        parent.$.fn.colorbox.close();
    });
};
function get_subject_covers(key, pagenumber) {
    // will implement it later.
    var covers = [];
    for (var i=0; i<20; i++)
        covers[i] = pagenumber * 20 + i;
    return covers;
}

function get_work_covers(key, pagenumber) {
    // will implement it later.
    var covers = [];
    for (var i=0; i<20; i++)
        covers[i] = pagenumber * 20 + i;
    return covers;
}

function Place(key) {
    this.key = key;
    this.covers = {};
    this.bookCount = 0;
}

/**
 * Gets the covers using AJAX call and calls the callback with covers as argument. 
 * AJAX call is avoided if the cover data is already present. 
 */
Place.prototype.getCovers = function(pagenum, callback) {
    var offset = pagenum * 12;
    var limit = 12;
    
    if (offset > this.bookCount)
        return [];
    
    if (this.covers[pagenum]) {
        callback(this.covers[pagenum]);
    }
    else {
        var page = this;
        $.getJSON(this.key + "/covers.json?limit=12&offset=" + offset, function(data) {
            page.covers[pagenum] = data;
            callback(data);
        });
    }
};
/*
function deleteVerify() {
    $('#dialog').dialog({
        autoOpen: false,
        width: 400,
        modal: true,
        resizable: false,
        buttons: {
            "Yes, I'm sure": function() {
                $("#_delete").click();
            },
            "No, cancel": function() {
                $(this).dialog("close");
            }
        }
    });
    $('#delete').click(function(){
        $('#dialog').dialog('open');
        return false;
    });
};
*/
function passwordHide(){
;(function($){
    $.fn.revealPassword=function(ph,options){
        var spinput=$(this);
        $.fn.revealPassword.checker=function(cbid,inid){
            $('input[id="'+cbid+'"]').click(function(){
                if($(this).attr('checked')){
                    $('input.'+inid).val(spinput.val()).attr('id',spinput.attr('id')).attr('name',spinput.attr('name'));
                    $('input.'+inid).css('display','inline');
                    spinput.css('display','none').removeAttr('id').removeAttr('name');
                } else {
                    spinput.val($('input.'+inid).val()).attr('id',$('input.'+inid).attr('id')).attr('name',$('input.'+inid).attr('name'));
                    spinput.css('display','inline');
                    $('input.'+inid).css('display','none').removeAttr('id').removeAttr('name');
                }
            });
        }
        return this.each(function(){
            var def={classname:'class',name:'password-input',text:'Unmask password?'};
            var spcbid='spcb';
            var spinid=spcbid.replace('spcb','spin');
            var spclass=spinid;
            if(typeof ph=='object'){
                $.extend(def,ph);
            }
            if(typeof options=='object'){
                $.extend(def,options);
            }
            var spname=def.name;
            if(def.classname==''){
                theclass='';
            } else {
                theclass=' class="'+def.clasname+'"';
            }
            $(this).before('<input type="text" value="" class="'+spclass+'" style="display: none;" />');
            var thecheckbox='<input type="checkbox" id="'+spcbid+'" name="'+spname+'" value="sp" /> <label for="'+spcbid+'">'+def.text+'</label>';
            if(ph=='object'||typeof ph=='undefined'){
                $(this).after(thecheckbox);
            } else {
                $(ph).html(thecheckbox);
            }
            $.fn.revealPassword.checker(spcbid,spinid);
            return this;
        });
    }
})(jQuery);
};
$().ready(function(){
    $('textarea.markdown').focus(function(){
        $('.wmd-preview').show();
        if ($("#prevHead").length == 0) {
            $('.wmd-preview').before('<h3 id="prevHead" style="margin:15px 0 10px;padding:0;">Preview</h3>');
        }
    });
    $('.dropclick').click(function(){
        $(this).next('.dropdown').slideToggle();
        $(this).parent().find('.arrow').toggleClass("up");
    });
});
jQuery.fn.exists = function(){return jQuery(this).length>0;}

function commify(n) {
    var text = n.toString();
    var re = /(\d+)(\d{3})/;

    while (re.test(text)) {
        text = text.replace(re, "$1,$2");
    }

    return text;
}

// Subject class
//
// Usage:
//      var subject = Subject({
//              "key": "/subjects/Love", 
//              "name": "Love", 
//              "work_count": 1234, 
//              "works": [...]
//          }, 
//          {
//              "pagsize": 12
//          });
//

;(function() {

function Subject(data, options) {
    var defaults = {
        pagesize: 12
    }
    this.settings = $.extend(defaults, options);

    this.filter = {};
    this.has_fulltext = "false";
    
    this.init(data);
    this._data = data;
}

window.Subject = Subject;

// Implementation of Python urllib.urlencode in Javascript.
function urlencode(query) {
    var parts = [];
    for (var k in query) {
        parts.push(k + "=" + query[k]);
    }
    return parts.join("&");
}

function slice(array, begin, end) {
    var a = [];
    for (var i=begin; i < Math.min(array.length, end); i++) {
        a.push(array[i]);
    }
    return a;
}

$.extend(Subject.prototype, {
    
    init: function(data) {
        $.log(["init", this, arguments]);
        
        $.extend(this, data);    
        this.page_count = Math.ceil(this.work_count / this.settings.pagesize);
        this.epage_count = Math.ceil(this.ebook_count / this.settings.pagesize);
        
        // cache already visited pages
        //@@ Can't this be handled by HTTP caching?
        this._pages = {};
        if (this.has_fulltext != "true")
            this._pages[0] = {"works": slice(data.works, 0, this.settings.pagesize)};
    
        // TODO: initialize additional pages when there are more works.
    },

    bind: function(name, callback) {
        $(this).bind(name, callback);
    },

    getPageCount: function() {
        return this.has_fulltext == "true"? this.epage_count : this.page_count;
    },

    loadPage: function(pagenum, callback) {
        var offset = pagenum * this.settings.pagesize;
        var limit = this.settings.pagesize;
    
        if (offset > this.bookCount) {
            callback && callback([]);
        }
    
        if (this._pages[pagenum]) {
            callback(this._pages[pagenum]);
        }
        else {
            var page = this;
            
            var params = {"limit": limit, "offset": offset, "has_fulltext": this.has_fulltext}
            $.extend(params, this.filter);
            
            var url = this.key + ".json?" + urlencode(params);
            var t = this;
                
            $.getJSON(url, function(data) {
                t._pages[pagenum] = data;
                callback(data);
            });
        }
    },
    
    _ajax: function(params, callback) {
        params = $.extend({"limit": this.settings.pagesize, "offset": 0}, this.filter, params);
        var url = this.key + ".json?" + urlencode(params);
        $.getJSON(url, callback);
    },

    setFilter: function(filter, callback) {
        for (var k in filter) {
            if (filter[k] == null) {
                delete filter[k];
            }
        }
        this.filter = filter;
                
        var _this = this;
        this._ajax({"details": "true"}, function(data) {
            _this.init(data);
            callback && callback();
        });
    },
    
    setFulltext: function(has_fulltext) {
        if (this.has_fulltext == has_fulltext) {
            return;
        }
        this.has_fulltext = has_fulltext;
        this._pages = {}
    },
    
    addFilter: function(filter, callback) {
        this.setFilter($.extend({}, this.filter, filter), callback);
    },
        
    reset: function(callback) {
        this.filter = {};
        this.init(this._data);
		callback && callback();
    }
});

})();

// Simple Javascript Templating 
//
// Inspired by http://ejohn.org/blog/javascript-micro-templating/
function Template(tmpl_text) {
    var s = [];
    var js = ["var _p=[];", "with(env) {"];

    function addCode(text) {
        js.push(text);
    }
    function addExpr(text) {
        js.push("_p.push(htmlquote(" + text + "));");
    }
    function addText(text) {
        js.push("_p.push(__s[" + s.length + "]);"); 
        s.push(text);
    }

    var tokens = tmpl_text.split("<%");

    addText(tokens[0]);
    for (var i=1; i < tokens.length; i++) {
        var t = tokens[i].split('%>');
        
        if (t[0][0] == "=") {
            addExpr(t[0].substr(1));
        }
        else {
            addCode(t[0]);
        }
        addText(t[1]);
    }
    js.push("}", "return _p.join('');");

    var f = new Function(["__s", "env"], js.join("\n"));
    var g = function(env) {
        return f(s, env);
    };
    g.toString = function() { return tmpl_text; };
    g.toCode = function() { return f.toString(); };
    return g;
}

function htmlquote(text) {
    text = String(text);
    text = text.replace(/&/g, "&amp;"); // Must be done first!
    text = text.replace(/</g, "&lt;");
    text = text.replace(/>/g, "&gt;");
    text = text.replace(/'/g, "&#39;");
    text = text.replace(/"/g, "&quot;");
    return text;
}

;(function($) {
    
// source: http://snipplr.com/view/8916/jquery-toggletext/
$.fn.toggleText = function(a, b) {
    return this.each(function() {
        $(this).text($(this).text() == a ? b : a);
    });
};

// http://jqueryminute.com/set-focus-to-the-next-input-field-with-jquery/
$.fn.focusNextInputField = function() {
    return this.each(function() {
        var fields = $(this).parents('form:eq(0),body').find(':input:visible');
        var index = fields.index( this );
        if ( index > -1 && ( index + 1 ) < fields.length ) {
            fields.eq( index + 1 ).focus();
        }
        return false;
    });
};

// Tap into jquery chain
$.fn.tap = function(callback) {
    callback(this);
    return this;
}

// debug log
$.log = function() {
    if (window.console) {
        console.log.apply(console, arguments);
    }
};

})(jQuery);

// closes active popup
function closePopup() {
    parent.jQuery.fn.colorbox.close();
};

function truncate(text, limit) {
   if (text.length > limit)
       return text.substr(0, limit) + "...";
   else
       return text;
}

function cond(predicate, true_value, false_value) {
    if (predicate) {
        return true_value;
    } 
    else {
        return false_value;
    }
}

// showPasswords implemented by Lance
(function($) {
    $.fn.extend({
        showPasswords: function(f) {
            return this.each(function() {
                var c = function(a) {
                    var a = $(a);
                    var b = $("<input type='text' />");
                    b.insertAfter(a).attr({
                        'class': a.attr('class'),
                        'style': a.attr('style')
                    });
                    return b
                };
                var d = function($this, $that) {
                    $that.val($this.val())
                };
                var e = function() {
                    if ($checkbox.is(':checked')) {
                        d($this, $clone);
                        $clone.show();
                        $this.hide()
                    } else {
                        d($clone, $this);
                        $clone.hide();
                        $this.show()
                    }
                };
                var $clone = c(this),
                $this = $(this),
                $checkbox = $(f);
                $checkbox.click(function() {
                    e()
                });
                $this.keyup(function() {
                    d($this, $clone)
                });
                $clone.keyup(function() {
                    d($clone, $this)
                });
                e()
            })
        }
    })
})(jQuery);

/**
 * jQuery plugin to add form validations. 
 *
 * To enable, add class="validate" to the form and add required validations in class to the input elements.
 * Available validations are: required, email, and publish-date.
 *
 * Example:
 *      <form name="create" class="validate">
 *          Username: <input type="text" class="required" name="username" value=""/> <br/>
 *          E-mail: <input type="text" class="required email" name="username" value=""/> <br/>
 *          Password: <input type="text" class="required" name="username" value=""/> <br/>
 *          <input type="submit" name="submit" value="Register"/>
 *      </form>
 */
(function($) {
    

    // validate publish-date to make sure the date is not in future
    jQuery.validator.addMethod("publish-date", function(value, element) { 
            // if it doesn't have even three digits then it can't be a future date      
            var tokens = /(\d{3,})/.exec(value);

            var year = new Date().getFullYear();
            return tokens && tokens[1] && parseInt(tokens[1]) <= year;
        }, 
        "Are you sure that's the published date?"
    );

    $.validator.messages.required = "";
    $.validator.messages.email = _("Are you sure that's an email address?");
    

    $.fn.ol_validate = function() {
        $(this).validate({
            errorClass: "invalid",
            validClass: "success",
            errorElement: "span",
            invalidHandler: function(form, validator) {
                var errors = validator.numberOfInvalids();
                if (errors) {
                    var message = ungettext(
                        "Hang on... you missed a bit. It's highlighted below.",
                        "Hang on...you missed some fields. They're highlighted below.",
                        errors);

                    $("div#contentMsg span").html(message);
                    $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
                    $("span.remind").css("font-weight", "700").css("text-decoration", "underline");
                } else {
                    $("div#contentMsg").hide();
                }
            },
            highlight: function(element, errorClass) {
                $(element).addClass(errorClass);
                $(element.form)
                    .find("label[for=" + element.id + "]")
                    .addClass(errorClass);
            },
            unhighlight: function(element, errorClass) {
                $(element).removeClass(errorClass);
                $(element.form)
                    .find("label[for=" + element.id + "]")
                    .removeClass(errorClass);
            },
            submitHandler: function(form){
                var validator = this;
                var valid = true;

                /* validate author-autocompletes on submit
                $(form).find("input.author-autocomplete").each(function() {
                    if ($(this).val() && !$(this).hasClass("accept")) {
                        validator.showLabel(this, _("Please select an author from the dropdown."));
                        validator.toShow.show();
                        $(this).focus();
                        valid = false;
                    }
                });
                */
                
                if (valid) {
                    form.submit();
                }
            }
        });
    };

})(jQuery);