// http://jqueryminute.com/set-focus-to-the-next-input-field-with-jquery/
$.fn.focusNextInputField = function() {
    return this.each(function() {
        var fields = $(this).parents('form:eq(0),body').find(':input:visible');
        var index = fields.index(this);
        if (index > -1 && (index + 1) < fields.length) {
            fields.eq(index + 1).focus();
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
            'Yes, I\'m sure': function() {
                callback.apply(_this);
            },
            'No, cancel': function() {
                $(_this).dialog('close');
            }
        }
    };
    options = $.extend(defaults, options);
    this.dialog(options);
}

// closes active popup
// used in templates/covers/saved.html
export function closePopup() {
    parent.jQuery.fn.colorbox.close();
}

// used in templates/admin/imports.html
export function truncate(text, limit) {
    if (text.length > limit) {
        return `${text.substr(0, limit)}...`;
    } else {
        return text;
    }
}

// used in templates/admin/ip/view.html
export function cond(predicate, true_value, false_value) {
    if (predicate) {
        return true_value;
    }
    else {
        return false_value;
    }
}
