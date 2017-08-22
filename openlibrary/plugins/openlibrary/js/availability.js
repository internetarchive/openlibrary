/*
  Solr is stale on the backend and we needed a performant way to check
  the actual availability of books (works, editions) in bulk.

  The getAvailability function hits OL's Availability API with a list
  of ocaids (archive.org item ids). It [OL] then in turn sends a http
  request to a service on Archive.org which looks up each ocaid in the
  Archive.org List API database (i.e. how lending data is currently
  stored on Archive.org for Open Library).

  Note: The plan is to move away from the List API for lending data
  (the List API is supposed to be for allowing users to create Lists
  of items, so using this data structure to support our lending is a
  bit of a hack). Instead of the List API, users lending data will be
  stored as metadata within their Archive.org user account.
*/

var getAvailability, getAvailabilityV2, getEditions, updateBookAvailability, updateWorkAvailability;

$(function(){

    /**
     * params:
     *
     *     olids - a csv of open library editions ids
     *
     *     callback - a method to which to return results
     *
     *     decoration - decoration allows us to return an html
     *                  component partial instead of raw json.
     *                  value of `carousel_item` is a decoration type
     *                  which allows the api to return results as a
     *                  list of html partials instead of dicts.
     *
     *     pixel - an option of decoration which enables analytics
     *             tracking to be set. E.g. a 'CarouselPopular' is
     *             sent to the decorate partial so we can add pixel
     *             tracking to it
     */
    getEditions = function(olids, callback, decoration, pixel) {
        var url = '/api/editions?olids=' + olids.join(',');
        if (decoration) {
            url += '&decoration=' + decoration;
        }
        if (pixel) {
            url += '&pixel=' + pixel;
        }
        $.ajax({
            url: url,
            type: "GET",
            dataType: "json",
            contentType: "application/json",
            beforeSend: function(xhr) {
                xhr.setRequestHeader("Content-Type", "application/json");
                xhr.setRequestHeader("Accept", "application/json");
            },
            success: function(result) {
                return callback(result);
            }
        });
    }

    getAvailability = function(ocaids, callback) {
        var url = '/availability?acs=0&restricted=1';
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify({
                "ocaids": ocaids
            }),
            dataType: "json",
            contentType: "application/json",
            beforeSend: function(xhr) {
                xhr.setRequestHeader("Content-Type", "application/json");
                xhr.setRequestHeader("Accept", "application/json");
            },
            success: function(result) {
                return callback(result);
            }
        });
    };

    getAvailabilityV2 = function(_type, _ids, callback) {
        if (!_ids.length) {
            return callback({});
        }
        var url = '/availability/v2?' + _type + '_ids=' + _ids.join(',');
        $.ajax({
            url: url,
            type: "GET",
            dataType: "json",
            contentType: "application/json",
            beforeSend: function(xhr) {
                xhr.setRequestHeader("Content-Type", "application/json");
                xhr.setRequestHeader("Accept", "application/json");
            },
            success: function(result) {
                return callback(result);
            }
        });
    };

    /*
     * Finds DOM elements for borrowable books (i.e. they have a
     * data-ocaid field and a data-key field) within the specified
     * scope of `selector` and updates the displayed borrow status
     * and ebook links to reflect correct statuses and available
     * copies.
     */
    updateBookAvailability = function(selector) {
        selector = (selector || '') + '[data-ocaid]';
        var books = {};  // lets us keep track of which ocaids came from
        // which book (i.e. edition or work). As we learn
        // ocaids are available, we'll need a way to
        // determine which edition or work this ocaid
        // comes from.
        var ocaids = [];  // a full set of ocaids spanning all books
        // which can be checked in a single request
        // to the availability API.
        $(selector).each(function(index, elem) {
            var data_ocaid = $(elem).attr('data-ocaid');
            if(data_ocaid) {
                var book_ocaids = data_ocaid.split(',')
                    .filter(function(book) { return book !== "" });
                var book_key = $(elem).attr('data-key');

                if(book_ocaids.length) {
                    books[book_key] = book_ocaids;
                    Array.prototype.push.apply(ocaids, book_ocaids);
                }
            }
        });

        getAvailability(ocaids, function(response) {
            for (var book_ocaid in response) {
                if (response[book_ocaid].status === "not_lendable") {
                    for (var book_key in books) {
                        var book_ocaids = books[book_key];
                        if (book_ocaids.indexOf(book_ocaid) > -1) {
                            $(selector + "[data-key=" + book_key  + "]")
                                .removeClass("borrow-link");
                            $(selector + "[data-key=" + book_key  + "]")
                                .parent().remove();
                            delete books[book_key];
                        }
                    }
                } else if (response[book_ocaid].status === "available") {
                    // check all the books on this page
                    for (var book_key in books) {
                        var book_ocaids = books[book_key];
                        // check if available book_ocaid is in
                        // this book_key's book_ocaids
                        if (book_ocaids.indexOf(book_ocaid) > -1) {
                            // update icon, ocaid, and url (to ia:)
                            // should limit scope to `selector` ! XXX
                            $(selector + "[data-key=" + book_key  + "]")
                                .attr("href", "/borrow/ia/" + book_ocaid);

                            // since we've found an available edition to
                            // represent this book, we can stop and remove
                            // book_ocaid from book_ocaids (one less book
                            // to check against).
                            delete books[book_key];
                        }
                    }
                }
            };

            // for anything remaining in books, set to checked-out
            for (var book_key in books) {
                $(selector + "[data-key=" + book_key  + "] span.read-icon")
                    .removeClass("borrow");
                $(selector + "[data-key=" + book_key  + "] span.read-icon")
                    .addClass("checked-out");
                $(selector + "[data-key=" + book_key  + "] span.read-label")
                    .html("Checked-out");
                delete books[book_key];
            }

        });
    };

    updateWorkAvailability = function() {
        if (localStorage.getItem('mode') === "printdisabled") {
            var daisies = $('.print-disabled-only');
            $.each(daisies, function() {
                $(this).removeClass('hidden');
            });
            return;
        }

        var editions = [];
        var works = [];
        var results = $('a.results');
        $.each(results, function(index, e) {
            var href = $(e).attr('href');
            var _type_key_slug = href.split('/')
            var _type = _type_key_slug[1];
            var key = _type_key_slug[2];
            if (_type === 'works') {
                works.push(key);
            } else if (_type === 'books') {
                editions.push(key);
            }
        });

        getAvailabilityV2('edition', editions, function(editions_response) {
          getAvailabilityV2('work', works, function(works_response) {
            var response = {'books': editions_response, 'works': works_response};
            $.each(results, function(index, e) {
                var href = $(e).attr('href');
                var _type_key_slug = href.split('/')
                var _type = _type_key_slug[1];
                var key = _type_key_slug[2];
                if (response[_type]) {
                    var work = response[_type][key];
                    var li = $(e).closest("li");
                    var cta = li.find(".searchResultItemCTA");
                    var msg = '';
                    var link = '';
                    var annotation = '';
                    var tag = 'a';

                    if (localStorage.getItem('mode') !== "printdisabled") {
                        if (work.status === 'error') {
                            if (localStorage.getItem('mode') === "ebooks") {
                                li.remove();
                            }
                        } else {
                            var cls = 'borrow_available borrow-link';
                            link = ' href="/books/' + work.openlibrary_edition + '/x/borrow" ';

                            if (work.status === 'open') {
                                msg = 'Read';
                            } else if (work.status === 'borrow_available') {
                                msg = 'Borrow';
                            } else if (work.status === 'borrow_unavailable') {
                                tag = 'span';
                                link = '';
                                cls = work.status;
                                msg = '<form method="POST" action="/books/' + work.openlibrary_edition + '/x/borrow?action=join-waitinglist" class="join-waitlist waitinglist-form"><input type="hidden" name="action" value="join-waitinglist">';
                                if (work.num_waitlist !== '0') {
                                    msg += 'Join Waitlist <span class="badge">' + work.num_waitlist + '</span></form>';

                                } else {
                                    msg += 'Join Waitlist</form>';
                                    annotation = '<div class="waitlist-msg">You will be first in line!</div>';
                                }
                            }
                            $(cta).append(
                                '<' + tag + ' ' + link + ' class="' + cls +
                                    ' cta-btn" data-ol-link-track="' +
                                    work.status
                                    + '">' + msg + '</' + tag + '>'
                            );

                            if (annotation) {
                                $(cta).append(annotation);
                            }
                        }
                    }
                }
            });
          });
        })
    }

    $('.searchResultItemCTA form.join-waitlist').live('click', function(e) {
        // consider submitting form async and refreshing search results page
        $(this).submit()
    })

    updateBookAvailability();

});
