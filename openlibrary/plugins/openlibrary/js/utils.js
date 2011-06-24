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

// Confirm dialog with OL styles.
$.fn.ol_confirm_dialog = function(callback, options) {
    var _this = this;
    var defaults = {
        autoOpen: false,
        width: 400,
        modal: true,
        resizable: false,
        buttons: {
            "Yes, I'm sure": function() {
                callback.apply(_this);
            },
            "No, cancel": function() {
                $(_this).dialog("close");
            }
        }
    };
    options = $.extend(defaults, options);
    this.dialog(options);
}

// Tap into jquery chain
$.fn.tap = function(callback) {
    callback(this);
    return this;
}

// debug log
$.log = function() {
    if (window.console) {
        //console.log.apply(console, arguments);
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