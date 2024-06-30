import Template from './template'
import { isbnOverride } from '../../openlibrary/js/isbnOverride'

/**
 * jquery repeat: jquery plugin to handle repetitive inputs in a form.
 *
 * Used in addbook process.
 */
export function init() {
    // used in books/edit/exercpt, books/edit/web and books/edit/edition
    $.fn.repeat = function(options) {
        var addSelector, removeSelector, id, elems, t, code,
            nextRowId;
        options = options || {};

        id = `#${this.attr('id')}`;
        elems = {
            _this: this,
            add: $(`${id}-add`),
            form: $(`${id}-form`),
            display: $(`${id}-display`),
            template: $(`${id}-template`)
        }

        function createTemplate(selector) {
            code = $(selector).html()
                .replace(/%7B%7B/gi, '<%=')
                .replace(/%7D%7D/gi, '%>')
                .replace(/{{/g, '<%=')
                .replace(/}}/g, '%>');
            return Template(code);
        }

        t = createTemplate(`${id}-template`);

        /**
         * Search elems.form for input fields and create an
         * object representing.
         * @return {object} data mapping names to values
         */
        function formdata() {
            var data = {};
            $(':input', elems.form).each(function() {
                var $e = $(this),
                    name = $e.attr('name'),
                    type = $e.attr('type'),
                    _id = $e.attr('id');

                data[name] = $e.val().trim();

                if (type === 'text' && _id === 'id-value') {
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
            var data, newid;
            const isbnOverrideData = isbnOverride.get();
            event.preventDefault();

            // if no index, set it to the number of children
            if (!nextRowId) {
                nextRowId = elems.display.children().length;
            }

            // If a user confirms adding an ISBN with a failed checksum in
            // js/edit.js, the {data} object is filled from the
            // isbnOverrideData object rather than the input form.
            if (isbnOverrideData) {
                data = isbnOverrideData;
                isbnOverride.clear();
            } else {
                data = formdata();
                data.index = nextRowId;

                if (options.validate && options.validate(data) === false) {
                    return;
                }
            }

            $.extend(data, options.vars || {});

            newid = `${elems._this.attr('id')}--${nextRowId}`;
            // increment the index to avoid situations where more than one element have same
            nextRowId++;
            // Create the HTML of a hidden input
            elems.template
                .clone()
                .attr('id', newid)
                .html(t(data))
                .show()
                .appendTo(elems.display);

            elems._this.trigger('repeat-add');
        }
        function onRemove(event) {
            event.preventDefault();
            $(this).parents('.repeat-item').eq(0).remove();
            elems._this.trigger('repeat-remove');
        }
        addSelector = `${id} .repeat-add`;
        removeSelector = `${id} .repeat-remove`;
        // Click handlers should apply to newly created add/remove selectors
        $(document).on('click', addSelector, onAdd);
        $(document).on('click', removeSelector, onRemove);
    }
}
