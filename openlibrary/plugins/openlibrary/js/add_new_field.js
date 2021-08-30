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
 *
 * Backend code that handles the save is in openlibrary/plugins/upstream/addbook.py (search for select-role-json)
 */
export default function($) {
    function add_new_field(selectSelector, options) {
        const $selectEl = $(selectSelector);
        if (!$selectEl.length) return;

        const $json = $('<input type="hidden">')
            .attr('name', `${$selectEl[0].id}-json`)
            .addClass('repeat-ignore') // tell repeat plugin to ignore this input
            .val('[]')
            .insertBefore($selectEl);

        $selectEl.on('change', function(){
            var value = $selectEl.val();
            if (value == '__add__') {
                if (options.onshow) {
                    options.onshow.apply($selectEl, []);
                }
                $.colorbox({
                    inline: true,
                    opacity: '0.5',
                    href: options.href,
                    open: true
                });
            }
        });

        const $href = $(options.href);
        // handle cancel
        $href.on('cbox_closed', function() {

            if ($selectEl.val() == '__add__') {
                $selectEl.val('');
                $selectEl.trigger('focus');
            }
            if (options.cancel) {
                options.cancel();
            }
        });

        // handle submit
        $('form').first().add($href).on('submit', function(event) {
            event.preventDefault();

            // extract data
            const array = $(event.target).serializeArray();
            const d = {};

            for (let i in array) {
                d[array[i].name] = array[i].value.trim();
            }

            // validate
            if (options.validate && !options.validate.call($selectEl, d)) {
                return;
            }

            // close popup
            $.colorbox.close();

            // add new option
            $('<option/>')
                .html(d.label || d.value)
                .attr('value', d.value)
                .insertBefore($selectEl.find('option').last().prev()) // insert before ---
                .parent().val(d.value);

            // add JSON to hidden field
            const data = JSON.parse($json.val());
            data.push(d);
            $json.val(JSON.stringify(data));

            // finally focus the next input field
            $selectEl.focusNextInputField();
        });
    }

    function error(error_div, input, message) {
        $(error_div).show().html(message);
        $.colorbox.resize();
        setTimeout(function(){
            $(input).trigger('focus');
        }, 0);
        return false;
    }

    add_new_field('#select-role', {
        href: '#select-role-popup',
        validate: function(data) {
            if (data.value == '') {
                return error('#select-role-popup-errors', '#select-role-popup-value', 'Please enter a new role.');
            }
            $('#select-role-popup-errors').hide();
            return true;
        },
        onshow: function() {
            $('#select-role-popup-errors').hide();
            $('#select-role-popup input[type=text]').val('');
        }
    });

    add_new_field('#select-id', {
        href: '#select-id-popup',
        validate: function(data) {
            if (data.label == '') {
                return error('#select-id-popup-errors', '#select-id-popup-label', 'Please enter name of the new identifier type.');
            }
            data.value = data.label.toLowerCase().replace(/ /g, '_');
            return true;
        },
        onshow: function() {
            $('#select-id-popup-errors').hide();
            $('#select-id-popup input[type=text]').val('');
        }
    });

    add_new_field('#select-classification', {
        href: '#select-classification-popup',
        validate: function(data) {
            if (data.label == '') {
                return error('#select-classification-popup-errors', '#select-classification-popup-label', 'Please enter name of the new classification type.');
            }
            data.value = data.label.toLowerCase().replace(/ /g, '_');
            return true;
        },
        onshow: function() {
            $('#select-classification-popup-errors').hide();
            $('#select-classification-popup input[type=text]').val('');
        }
    });
}
