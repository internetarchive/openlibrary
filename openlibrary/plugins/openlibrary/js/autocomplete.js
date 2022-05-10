// jquery plugins to provide author and language autocompletes.
/**
 * Port of code in vendor/js/jquery-autocomplete removed in e91119b
 * @param {string} value
 * @param {string} term to highlight in value, its assumed these are plain text or safe HTML.
 * @return {string}
 */
export function highlight(value, term) {
    return value.replace(
        new RegExp(`(?![^&;]+;)(?!<[^<>]*)(${term.replace(/([\^$()[]\{\}\*\.\+\?\|\\])/gi, '$1')})(?![^<>]*>)(?![^&;]+;)`, 'gi'),
        '<strong>$1</strong>'
    );
}

/**
 * Map an OpenLibrary API response to a jquery autocomplete data structure.
 *
 * @param {array} results
 * @param {function} labelFormatter
 * @param {string} [addNewFieldTerm] when passed a new item at the end of the list for
 *  creating a new entry will be added
 * @return {array} of modified results that are compatible with the jquery autocomplete search suggestions
 */
export const mapApiResultsToAutocompleteSuggestions = (results, labelFormatter, addNewFieldTerm) => {
    const mapAPIResultToSuggestedItem = (r) => ({
        key: r.key,
        label: labelFormatter(r),
        value: r.name
    });

    // When no results if callback is defined, append a create new entry
    if (addNewFieldTerm) {
        results.push(
            {
                name: addNewFieldTerm,
                key: '__new__',
                value: addNewFieldTerm
            }
        );
    }
    return results.map(mapAPIResultToSuggestedItem);
};

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
            formatItem: item => item.name,
            /**
             * Adds the ac_over class to the selected autocomplete item
             *
             * @param {Event} _event (unused)
             * @param {Object} ui containing item key
             */
            focus: function (_event, ui) {
                const $list = $(_this).data('list');
                if ($list) {
                    $list.find('li')
                        .removeClass('ac_over')
                        .filter((_, el) => $(el).data('ui-autocomplete-item').key === ui.item.key)
                        .addClass('ac_over');
                }
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

        $.widget('custom.autocompleteHTML', $.ui.autocomplete, {
            _renderMenu($ul, items) {
                $ul.addClass('ac_results').attr('id', this.ulRef);
                items.forEach((item) => {
                    $('<li>')
                        .data('ui-autocomplete-item', item)
                        .attr('aria-label', item.value)
                        .html(item.label)
                        .appendTo($ul);
                });
                // store list so we can add ac_over hover effect in `focus` event
                $(_this).data('list', $ul);
            }
        });

        const options = $.extend(default_ac_opts, ac_opts, {
            source: function (q, response) {
                const term = q.term;
                const params = {
                    q: term,
                    limit: options.max,
                    timestamp: new Date()
                };
                if (location.search.indexOf('lang=') !== -1) {
                    params.lang = new URLSearchParams(location.search).get('lang');
                }
                return $.ajax({
                    url: ol_ac_opts.endpoint,
                    data: params
                }).then((results) => {
                    response(
                        mapApiResultsToAutocompleteSuggestions(
                            results,
                            (r) => highlight(options.formatItem(r), term),
                            ol_ac_opts.addnew === true ||
                                (ol_ac_opts.addnew && ol_ac_opts.addnew(term)) ? (ol_ac_opts.new_name || term) : null
                        )
                    );
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
