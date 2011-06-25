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