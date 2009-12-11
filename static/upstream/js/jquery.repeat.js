/**
 * jquery repeat: jquery plugin to handle repeatative inputs in a form.
 *
 * Version: 0.1
 */
(function($){    
    $.fn.repeat = function(options) {
        var id = "#" + this.attr("id");
        var elems = {
            'this': this,
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
            $("input, textarea, select", elems.form).each(function() {
                var e = $(this);
                data[e.attr("name")] = e.val();
            });
            return data;
        }
        
        $(id + "-add").click(function() {
            var index = elems.display.children().length;
            var data = formdata();
            data.index = index;
            
            $.extend(data, options.vars || {});
            
            var newid = elems.this.attr("id") + "--" + index;
            elems.template
                .clone()
                .attr("id", newid)
                .html(t(data))
                .css("display", null)
                .appendTo(elems.display);
                
            $("input", elems.form).each(function() {
                var e = $(this);
                if (e.attr("type") != "button")
                    e.val("");
            });
            $("textarea", elems.form).val("");
        });
    }
})(jQuery);
