/**
 * jquery repeat: jquery plugin to handle repetitive inputs in a form.
 *
 * Used in addbook process.
 */
(function($){
    // For v2 and v1 page support. Can be removed when no v1 support needed
    var isOldJQuery = $('body').on === undefined;
    $.fn.repeat = function(options) {
        var addSelector, removeSelector;
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
            // Template is defined in openlibrary\plugins\openlibrary\js\template.js
            // eslint-disable-next-line no-undef
            return Template(code);
        }

        var t = createTemplate(id + "-template");

        /**
         * Search elems.form for input fields and create an
         * object representing.
         * This function has side effects and will reset any
         * input[type=text] fields it has found in the process
         * @return {object} data mapping names to values
         */
        function formdata() {
            var data = {};
            $(":input", elems.form).each(function() {
                var $e = $(this),
                    type = $e.attr('type'),
                    name = $e.attr("name");

                data[name] = $e.val().trim();
                // reset the values we are copying across
                if (type === 'text') {
                    $e.val('');
                }
            });
            return data;
        }
        /**
         * triggered when "add link" button is clicked on author edit field.
         * Creates a removable `repeat-item`.
         * @param {jQuery.Event} event
         */
        function onAdd(event) {
            event.preventDefault();

            var index = elems.display.children().length;
            var data = formdata();
            data.index = index;

            if (options.validate && options.validate(data) == false) {
                return;
            }

            $.extend(data, options.vars || {});

            var newid = elems._this.attr("id") + "--" + index;
            // Create the HTML of a hidden input
            elems.template
                .clone()
                .attr("id", newid)
                .html(t(data))
                .show()
                .appendTo(elems.display);

            elems._this.trigger("repeat-add");
        }
        function onRemove(event) {
            event.preventDefault();
            $(this).parents(".repeat-item:eq(0)").remove();
            elems._this.trigger("repeat-remove");
        }
        addSelector = id + " .repeat-add";
        removeSelector = id + " .repeat-remove";
        // Click handlers should apply to newly created add/remove selectors
        if (isOldJQuery) {
            $(document).on('click', addSelector, onAdd);
            $(document).on('click', removeSelector, onRemove);
        } else {
            $(document).on("click", addSelector, onAdd);
            $(document).on("click", removeSelector, onRemove);
        }
    }
})(jQuery);
