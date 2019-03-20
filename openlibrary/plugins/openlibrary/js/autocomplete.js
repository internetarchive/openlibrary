// jquery plugins to provide author and language autocompletes.

export default function($) {
    /**
     * Some extra options for when creating an autocomplete input field
     * @typedef {Object} OpenLibraryAutocompleteOptions
     * @property{string} endpoint - url to hit for autocomplete results
     * @property{(boolean|Function)} [addnew] - when (or whether) to display a "Create new record"
     *     element in the autocomplete list. The function takes the query and should return a boolean.
     *     a boolean.
     */

    /**
     * @private
     * @param{HTMLInputElement} _this - input element that will become autocompleting.
     * @param{OpenLibraryAutocompleteOptions} ol_ac_opts
     * @param{Object} ac_opts - options passed to $.autocomplete; see that.
     */
    function setup_autocomplete(_this, ol_ac_opts, ac_opts) {
        var default_ac_opts = {
            autoFill: true,
            mustMatch: true,
            formatMatch: function(item) { return item.name; },
            parse: function(text) {
                // in v2, text IS the JSON
                var rows = typeof text === 'string' ? JSON.parse(text) : text;
                var parsed = [];
                for (var i=0; i < rows.length; i++) {
                    var row = rows[i];
                    parsed.push({
                        data: row,
                        value: row.name,
                        result: row.name
                    });
                }

                // XXX: this won't work when _this is multiple values (like $("input"))
                var query = $(_this).val();
                if (ol_ac_opts.addnew && ol_ac_opts.addnew(query)) {
                    parsed = parsed.slice(0, ac_opts.max - 1);
                    parsed.push({
                        data: {name: query, key: "__new__"},
                        value: query,
                        result: query
                    });
                }
                return parsed;
            },
        };

        $(_this)
            .autocomplete(ol_ac_opts.endpoint, $.extend(default_ac_opts, ac_opts))
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

    /**
     * @this HTMLElement - the element that contains the different inputs.
     * @param {string} autocomplete_selector - selector to find the input element use for autocomplete.
     * @param {Function} input_renderer - ((index, item) -> html_string) render the ith div.input.
     * @param {OpenLibraryAutocompleteOptions} ol_ac_opts
     * @param {Object} ac_opts - options given to override defaults of $.autocomplete; see that.
     */
    $.fn.setup_multi_input_autocomplete = function(autocomplete_selector, input_renderer, ol_ac_opts, ac_opts) {
        var container = $(this);

        // first let's init any pre-existing inputs
        container.find(autocomplete_selector).each(function() {
            setup_autocomplete(this, ol_ac_opts, ac_opts);
        });

        function update_visible() {
            if (container.find("div.input").length > 1) {
                container.find("a.remove").show();
            }
            else {
                container.find("a.remove").hide();
            }

            container.find("a.add:not(:last)").hide();
            container.find("a.add:last").show();
        }

        update_visible();

        container.on("click", "a.remove", function() {
            if (container.find("div.input").length > 1) {
                $(this).closest("div.input").remove();
                update_visible();
            }
        });

        container.on("click", "a.add", function(event) {
            event.preventDefault();

            var next_index = container.find("div.input").length;
            var new_input = $(input_renderer(next_index, {key:"", name: ""}));
            container.append(new_input);
            setup_autocomplete(
                new_input.find(autocomplete_selector)[0],
                ol_ac_opts,
                ac_opts);
            update_visible();
        });
    };
}
