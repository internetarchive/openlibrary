// jquery plugins to provide author and language autocompletes.

;(function($) {    
    // author-autocomplete
    $.fn.author_autocomplete = function(options) {
        var local_options = {
            minChars: 2,
            max: 11,
            addnew: true,  
            autoFill: false,
            formatItem: function(item) {
                var date = '';
                if (item.key != "__new__") {
                    if (item.birth_date || item.death_date) {
                        date = ' (';
                        if (item.birth_date) {
                            date += item.birth_date;
                        }
                        date += '-';
                        if (item.death_date) {
                            date += item.death_date;
                        }
                        date += ' )';
                    }
                }
                if (item.key == "__new__") {
                    return '' + 
                        '<div class="ac_author ac_addnew" title="Add a new author">' + 
                            '<span class="action">' + _('Create a new record for') + '</span>' +
                            '<span class="name">' + item.name + '</span>' +
                        '</div>'
                }
                else if (item.work_count == 0) {
                    return '<div class="ac_author" title="Select this author">' + 
                               '<span class="name">' + item['name'] + date + '</span>' +
                               '<span class="subject">No books associated with ' + item['name'] +'</span>' +  
                           '</div>';
                }
                else if (item.work_count == 1) {
                    return '<div class="ac_author" title="Select this author">' + 
                               '<span class="name">' + item['name'] + date + '</span>' +
                               '<span class="books">1 book</span> <span class="work">titled <i>' + (item.works[0]) + '</i></span><br/>' + 
                               '<span class="subject">Subjects: ' + (item.subjects && item.subjects.join(", ") || "") + '</span>' +  
                           '</div>';
                }
                else {
                    return '<div class="ac_author" title="Select this author">' + 
                               '<span class="name">' + item['name'] + date + '</span>' +
                               '<span class="books">' + (item.work_count) + ' books</span>' + 
                               ' <span class="work">including <i>' + (item.works && item.works[0] || "") + '</i></span><br/>' + 
                               '<span class="subject">Subjects: ' + (item.subjects && item.subjects.join(", ") || "") + '</span>' +  
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
                var rows = eval(text).slice(0, options.max-1);                
                var parsed = [];
                for (var i=0; i < rows.length; i++) {
                    var row = rows[i];
                    parsed[parsed.length] = {
                        data: row,
                        value: row.name,
                        result: row.name
                    };
                }
                if (options.addnew) {
                    // XXX: this won't work when _this is multiple values (like $("input"))
                    var name = $(_this).val();
                    parsed[parsed.length] = {
                        data: {name: name, key: "__new__"},
                        value: name,
                        result: name
                    }
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