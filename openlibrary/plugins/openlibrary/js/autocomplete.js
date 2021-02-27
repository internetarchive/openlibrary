// jquery plugins to provide author and language autocompletes.

export default function($) {
    /**
     * Some extra options for when creating an autocomplete input field
     * @typedef {Object} OpenLibraryAutocompleteOptions
     * @property {string} endpoint - url to hit for autocomplete results
     * @property{(boolean|Function)} [addnew] - when (or whether) to display a "Create new record"
     *     element in the autocomplete list. The function takes the query and should return a boolean.
     *     a boolean.
     * @property{string} [new_name] - name to display when __new__ selected. Defaults to the query
     */

    /**
     * @private
     * @param{HTMLInputElement} _this - input element that will become autocompleting.
     * @param{OpenLibraryAutocompleteOptions} ol_ac_opts
     * @param{Object} ac_opts - options passed to $.autocomplete; see that.
     * @param {Function} ac_opts.formatItem - optional item formatter. Returns a string of HTML for rendering as an item.
     */
    function setup_autocomplete(_this, ol_ac_opts, ac_opts) {
        var default_ac_opts = {
            autoFill: true,
            formatItem: function (item) {
                return item.name;
            },
            focus: function (event, ui) {
                event.preventDefault();
            },
            select: function (_event, ui) {
                var item = ui.item;
                var $this = $(this);
                $(`#${_this.id}-key`).val(item.key);
                setTimeout(function() {
                    $this.addClass('accept');
                }, 0);
            },
            mustMatch: true,
            formatMatch: function(item) { return item.name; }
        };

        /**
         * Port of code in vendor/js/jquery-autocomplete removed in e91119b
         * @param {string} value
         * @param {string} term to highlight in value
         * @return {string}
         */
        function highlight(value, term) {
            return value.replace(
                new RegExp(`(?![^&;]+;)(?!<[^<>]*)(${term.replace(/([\^$()[]\{\}\*\.\+\?\|\\])/gi, '$1')})(?![^<>]*>)(?![^&;]+;)`, 'gi'),
                '<strong>$1</strong>'
            );
        }

        $.widget('custom.autocompleteHTML', $.ui.autocomplete, {
            _renderMenu($ul, items) {
                $ul.addClass('ac_results');
                items.forEach((item, i) => {
                    $('<li>')
                        .addClass(i % 2 ? 'ac-even' : 'ac-odd')
                        .attr('data-value', item.value)
                        .data('ui-autocomplete-item', item)
                        .attr('aria-label', item.value)
                        .html(item.label)
                        .appendTo($ul);
                });
            }
        });

        const options = $.extend(default_ac_opts, ac_opts, {
            source: function (q, response) {
                const term = q.term;
                return $.ajax({
                    url: ol_ac_opts.endpoint,
                    data: {
                        q: term,
                        limit: options.max,
                        timestamp: new Date()
                    }
                }).then((results) => {
                    response(
                        results.map((r) => {
                            return {
                                key: r.key,
                                label: highlight(options.formatItem(r), term),
                                value: r.name
                            };
                        })
                    );

                    // When no results if callback is defined, append a create new entry
                    if (!results.length &&
                        (
                            ol_ac_opts.addnew === true ||
                            (ol_ac_opts.addnew && ol_ac_opts.addnew(term))
                        )
                    ) {
                        response([
                            {
                                label: options.formatItem({
                                    name: term,
                                    key: '__new__',
                                    result: term,
                                    value: term
                                }),
                                value: term
                            }
                        ]);
                    }
                });
            }
        });
        $(_this)
            .autocompleteHTML(options)
            .on('keypress', function() {
                $(this).removeClass('accept').removeClass('reject');
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
            if (container.find('div.input').length > 1) {
                container.find('a.remove').show();
            }
            else {
                container.find('a.remove').hide();
            }

            container.find('a.add:not(:last)').hide();
            container.find('a.add:last').show();
        }

        update_visible();

        container.on('click', 'a.remove', function() {
            if (container.find('div.input').length > 1) {
                $(this).closest('div.input').remove();
                update_visible();
            }
        });

        container.on('click', 'a.add', function(event) {
            var next_index, new_input;
            event.preventDefault();

            next_index = container.find('div.input').length;
            new_input = $(input_renderer(next_index, {key: '', name: ''}));
            container.append(new_input);
            setup_autocomplete(
                new_input.find(autocomplete_selector)[0],
                ol_ac_opts,
                ac_opts);
            update_visible();
        });
    };
}
