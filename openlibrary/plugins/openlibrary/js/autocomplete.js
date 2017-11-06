// jquery plugins to provide author and language autocompletes.

;(function($) {
    // author-autocomplete
    $.fn.author_autocomplete = function(options) {
        var local_options = {
            // Custom option; when returning true for the given query, this
            // will append a special "__new__" item so the user can enter a
            // custom value (i.e. new author in this case)
            addnew: function(query) {
                // Don't render "Create new author" if searching by key
                return !/^OL\d+A/i.test(query);
            },

            minChars: 2,
            max: 11,
            matchSubset: false,
            autoFill: false,
            formatItem: function(item) {
                if (item.key == "__new__") {
                    return '' +
                        '<div class="ac_author ac_addnew" title="Add a new author">' +
                            '<span class="action">' + _('Create a new record for') + '</span>' +
                            '<span class="name">' + item.name + '</span>' +
                        '</div>';
                }
                else {
                    var subjects_str = item.subjects ? item.subjects.join(', ') : '';
                    var main_work = item.works ? item.works[0] : '';
                    var author_lifespan = '';
                    if (item.birth_date || item.death_date) {
                        var birth = item.birth_date || ' ';
                        var death = item.death_date || ' ';
                        author_lifespan = ' (' + birth + '-' + death + ')';
                    }

                    var name_html = '<span class="name">' + item.name + author_lifespan + '</span>';
                    var olid_html = '<span class="olid">' + item.key.match(/OL\d+A/)[0] + '</span>';
                    var books_html = '<span class="books">' + item.work_count + ' books</span>';
                    var main_work_html =  '<span class="work">including <i>' + main_work + '</i></span><br/>';
                    var subjects_html = '<span class="subject">Subjects: ' + subjects_str + '</span>'

                    if (subjects_str == '')
                        subjects_html = '';

                    if (item.work_count == 0) {
                        books_html = '';
                        main_work_html = '<span class="work">No books associated with ' + item.name + '</span>';
                    }
                    else if (item.work_count == 1) {
                        books_html = '<span class="books">1 book</span>';
                        main_work_html = '<span class="work">titled <i>' + main_work + '</i></span><br/>';
                    }

                    return '<div class="ac_author" title="Select this author">' +
                                name_html +
                                olid_html + ' &bull; ' + books_html + ' ' + main_work_html +
                                subjects_html +
                            '</div>';
                }
            }
        };

        $(this).each(function() {
            setup_autocomplete(this, "/authors/_autocomplete", options, local_options);
        });
    }

    // language-autocomplete
    $.fn.language_autocomplete = function(options) {
        var local_options = {
            max: 6,
            formatItem: function(item) {
                return sprintf(
                    '<div class="ac_author" title="%s"><span class="name">%s</span></div>',
                    _("Select this language"),
                    item.name);
            }
        };

        $(this).each(function() {
            setup_autocomplete(this, "/languages/_autocomplete", options, local_options);
        });
    }

    function setup_autocomplete(_this, url, options, local_options) {
        options = $.extend(options, local_options);

        var default_options = {
            autoFill: true,
            mustMatch: true,
            parse: function(text) {
                var rows = JSON.parse(text);
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
                if (options.addnew && options.addnew(query)) {
                    parsed = parsed.slice(0, options.max - 1);
                    parsed.push({
                        data: {name: query, key: "__new__"},
                        value: query,
                        result: query
                    });
                }
                return parsed;
            },

            formatMatch: function(item) {
                return item.name;
            }
        };

        $(_this)
            .autocomplete(url, $.extend(default_options, options))
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
})(jQuery);
