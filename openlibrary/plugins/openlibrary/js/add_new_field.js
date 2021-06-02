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
export default function($){
    $.fn.add_new_field = function(_options) {
        $(this).each(function() {
            var options = _options || {href: `#${this.id}-popup`};
            var $this = $(this);

            var $json = $('<input type="hidden">')
                .attr('name', `${this.id}-json`)
                .addClass('repeat-ignore') // tell repeat plugin to ignore this input
                .val('[]')
                .insertBefore($this);

            $this.on('change', function(){
                var value = $this.val();
                if (value == '__add__') {
                    if (options.onshow) {
                        options.onshow.apply($this, []);
                    }
                    $.fn.colorbox({
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

                if ($this.val() == '__add__') {
                    $this.val('');
                    $this.trigger('focus');
                }
                if (options.cancel) {
                    options.cancel();
                }
            });

            // handle submit
            $('form').first().add($href).on('submit', function(event) {
                var array, d, i, data;
                event.preventDefault();

                // extract data
                array = $(this).serializeArray();
                d = {};

                for (i in array) {
                    d[array[i].name] = array[i].value.trim();
                }

                // validate
                if (options.validate && options.validate.apply($this, [d]) == false) {
                    return;
                }

                // close popup
                $.fn.colorbox.close();

                // add new option
                $('<option/>')
                    .html(d.label || d.value)
                    .attr('value', d.value)
                    .insertBefore($this.find('option').last().prev()) // insert before ---
                    .parent().val(d.value);

                // add JSON to hidden field
                data = null;
                try {
                    data = JSON.parse($json.val());
                }
                catch (err) {
                    data = [];
                }
                data.push(d);
                $json.val(JSON.stringify(data));

                // finally focus the next input field
                $this.focusNextInputField();
            });
            return this;
        });
    };
}
