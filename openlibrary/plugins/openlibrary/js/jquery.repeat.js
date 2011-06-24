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