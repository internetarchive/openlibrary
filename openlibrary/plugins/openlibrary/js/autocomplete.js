// Possible globals defined using jsdef inside openlibrary/templates/books/edit/edition.html
// In future we'll move these into JS but easier said than done!
const render_translated_from_language_field = window.render_translated_from_language_field,
    render_work_field = window.render_work_field,
    render_author = window.render_author,
    render_work_autocomplete_item = window.render_work_autocomplete_item,
    render_language_autocomplete_item = window.render_language_autocomplete_item,
    render_author_autocomplete_item = window.render_author_autocomplete_item,
    render_language_field = window.render_language_field;

/**
 * Some options specific to certain endpoint services.
 */
const ENDPOINT_OPTIONS_AUTHORS = {
    endpoint: '/authors/_autocomplete',
    // Don't render "Create new author" if searching by key
    addnew: function(query) { return !/^OL\d+A/i.test(query); },
};

const ENDPOINT_OPTIONS_LANGUAGES = {
    endpoint: '/languages/_autocomplete'
};

const ENDPOINT_OPTIONS_WORKS = {
    endpoint: '/works/_autocomplete'
};

/**
 * Some default options for autocompletes.
 */
const AUTOCOMPLETE_OPTIONS = {
    minChars: 2,
    max: 11,
    matchSubset: false,
    autoFill: false
};

/**
 * Some slightly different options for language autocompletes.
 */
const AUTOCOMPLETE_LANGUAGE_OPTIONS = {
    max: 6,
    formatItem: render_language_autocomplete_item
};

/**
 * Setup an autocomplete on
 * @param {jQuery.Object} $node to setup autocomplete for
 * @param {string|object} urlOrData to use for sourcing results.
 * @param {object} options
 * @return {jQuery.Object}
 */
function autocompleteWithUrl($node, urlOrData, options) {
    const isUrl = typeof urlOrData == 'string';
    const $autocomplete = $node.autocomplete(
        $.extend({}, options, {
            source: isUrl ? function(request, response) {
                const term = request.term;
                const query = {
                    q: term,
                    timestamp: +new Date(),
                    limit: options.max
                };
                $.ajax(`${urlOrData}?${$.param(query)}`).then(function (d) {
                    response(
                        d && d.length ? d.map((item) => {
                            return {
                                key: item.key,
                                value: item.name,
                                label: options.formatItem(item)
                            }
                        }) : [ {
                            key: '__new__',
                            value: term,
                            label: options.formatItem({ key: '__new__', name: term })
                        } ]
                    )
                })
            } : urlOrData
        })
    );

    // Allow HTML (based on https://github.com/scottgonzalez/jquery-ui-extensions/blob/master/src/autocomplete/jquery.ui.autocomplete.html.js)
    $autocomplete.data('ui-autocomplete')._renderItem = function(ul, item) {
        return $('<li></li>')
            .data('item.autocomplete', item)
            .append(item.label)
            .appendTo(ul);
    };
    return $autocomplete;
}
/**
 * Initialises autocomplete elements in the page.
 */
function initPageElements() {
    if (render_author_autocomplete_item) {
        $('#authors').setup_multi_input_autocomplete(
            'input.author-autocomplete',
            render_author, ENDPOINT_OPTIONS_AUTHORS,
            $.extend({}, AUTOCOMPLETE_OPTIONS, {
                formatItem: render_author_autocomplete_item
            })
        );
    }

    if (render_language_field) {
        $('#languages').setup_multi_input_autocomplete(
            'input.language-autocomplete',
            render_language_field,
            ENDPOINT_OPTIONS_LANGUAGES, AUTOCOMPLETE_LANGUAGE_OPTIONS);
    }

    if (render_translated_from_language_field) {
        $('#translated_from_languages').setup_multi_input_autocomplete(
            'input.language-autocomplete',
            render_translated_from_language_field, ENDPOINT_OPTIONS_LANGUAGES, AUTOCOMPLETE_LANGUAGE_OPTIONS);
    }

    if (render_work_field) {
        $('#works').setup_multi_input_autocomplete(
            'input.work-autocomplete',
            render_work_field, ENDPOINT_OPTIONS_WORKS,
            $.extend({}, AUTOCOMPLETE_OPTIONS, {
                formatItem: render_work_autocomplete_item
            })
        )
    }
}

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
            mustMatch: true
        };

        autocompleteWithUrl($(_this), ol_ac_opts.endpoint, $.extend(default_ac_opts, ac_opts))
            .on('autocompleteselect', function(event, data) {
                const item = data.item;
                const $this = $(this);

                $(`#${this.id}-key`).val(item.key);

                //adding class directly is not working when tab is pressed. setTimeout seems to be working!
                setTimeout(function() {
                    $this.addClass('accept');
                }, 0);
            })
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
    initPageElements();
}
