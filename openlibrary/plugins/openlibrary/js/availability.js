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
/* eslint-disable no-unused-vars */
// used in openlibrary/plugins/openlibrary/js/ol.js
var getAvailabilityV2, updateBookAvailability, updateWorkAvailability;
/* eslint-enable no-unused-vars */

/**
 * @param {jQuery.Object} $elements
 * @return {Object} worksAndEditions
 */
function getWorksAndEditionsFromElements($elements) {
    const editions = [],
        works = [];

    $.each($elements, function(index, e) {
        const href = $(e).attr('href'),
            _type_key_slug = href && href.split('/'),
            _type = _type_key_slug[1],
            key = _type_key_slug[2].split('?')[0];

        if (_type === 'works') {
            works.push(key);
        } else if (_type === 'books') {
            editions.push(key);
        }
    });
    return {
        works, editions
    };
}

function initAvailability() {
    var btnClassName = 'cta-btn';
    // pages still relying on legacy client-side availability checking
    var whitelist = {
        '^/account/books/[^/]+': { // readinglog
            filter: false
        },
        '^/people/[^/]+': { // lists
            filter: false,
        },
        '^/stats/[^/]+': {
            filter: false
        }
    }

    getAvailabilityV2 = function(_type, _ids, callback) {
        var url;
        if (!_ids.length) {
            return callback({});
        }
        url = `/availability/v2?type=${_type}`;
        $.ajax({
            url: url,
            type: 'POST',
            data: JSON.stringify({
                ids: _ids
            }),
            dataType: 'json',
            contentType: 'application/json',
            beforeSend: function(xhr) {
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('Accept', 'application/json');
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
        var books, ocaids;
        selector = `${selector || ''}[data-ocaid]`;
        books = {};  // lets us keep track of which ocaids came from
        // which book (i.e. edition or work). As we learn
        // ocaids are available, we'll need a way to
        // determine which edition or work this ocaid
        // comes from.
        ocaids = [];  // a full set of ocaids spanning all books
        // which can be checked in a single request
        // to the availability API.
        $(selector).each(function(index, elem) {
            var data_ocaid = $(elem).attr('data-ocaid');
            var book_ocaids, book_key;
            if (data_ocaid) {
                book_ocaids = data_ocaid.split(',')
                    .filter(function(book) { return book !== '' });
                book_key = $(elem).attr('data-key');

                if (book_ocaids.length) {
                    books[book_key] = book_ocaids;
                    Array.prototype.push.apply(ocaids, book_ocaids);
                }
            }
        });

        getAvailabilityV2('identifier', ocaids, function(response) {
            var book_key = null;
            var book_ocaids = null;
            var book_ocaid;
            for (book_ocaid in response) {
                if (response[book_ocaid].status === 'borrow_available') {
                    // check all the books on this page
                    for (book_key in books) {
                        book_ocaids = books[book_key];
                        // check if available book_ocaid is in
                        // this book_key's book_ocaids
                        if (book_ocaids.indexOf(book_ocaid) > -1) {
                            // update icon, ocaid, and url (to ia:)
                            // should limit scope to `selector` ! XXX
                            $(`${selector}[data-key=${book_key}]`)
                                .attr('href', `/borrow/ia/${book_ocaid}`);
                            $(`${selector}[data-key=${book_key}]`)
                                .addClass('cta-btn--available').addClass(btnClassName)
                            // FIXME: This is not translatable!
                            $(`${selector}[data-key=${book_key}]`)
                                .text('Borrow');
                            // since we've found an available edition to
                            // represent this book, we can stop and remove
                            // book_ocaid from book_ocaids (one less book
                            // to check against).
                            delete books[book_key];
                        }
                    }
                } else if (response[book_ocaid].status === 'borrow_unavailable'){
                    for (book_key in books) {
                        book_ocaids = books[book_key];
                        if (book_ocaids.indexOf(book_ocaid) > -1) {
                            $(`${selector}[data-key=${book_key}]`)
                                .attr('title', 'Join waitlist');
                            $(`${selector}[data-key=${book_key}]`)
                                .addClass('cta-btn--unavailable').addClass(btnClassName);
                            // FIXME: Hardcoded English text!
                            $(`${selector}[data-key=${book_key}]`)
                                .text('Join Waitlist');
                            delete books[book_key];
                        }
                    }
                } else {
                    for (book_key in books) {
                        book_ocaids = books[book_key];
                        if (book_ocaids.indexOf(book_ocaid) > -1) {
                            $(`${selector}[data-key=${book_key}]`)
                                .attr('href', $(`${selector}[data-key=${book_key}]`).attr('data-key'))
                            $(`${selector}[data-key=${book_key}]`)
                                .attr('title', 'Check Availability');
                            $(`${selector}[data-key=${book_key}]`)
                                .removeClass('borrow-link');
                            $(`${selector}[data-key=${book_key}]`)
                                .addClass('check-book-availability').addClass(btnClassName);
                            // FIXME: This is not translatable!
                            $(`${selector}[data-key=${book_key}]`)
                                .text('Check Availability');
                            delete books[book_key];
                        }
                    }
                }
            }
        });
    };

    updateWorkAvailability = function() {

        // Determine whether availability check necessary for page
        var checkAvailability = false;
        var filter = false;
        var page, daisies, worksAndEditions, editions, works, results;
        for (page in whitelist) {
            if (window.location.pathname.match(page)) {
                checkAvailability = true;
                filter = whitelist[page].filter;
            }
        }
        if (!checkAvailability) {
            return;
        }

        if (localStorage.getItem('mode') === 'printdisabled') {
            daisies = $('.print-disabled-only');
            $.each(daisies, function() {
                $(this).removeClass('hidden');
            });
            return;
        }

        results = $('a.results');
        worksAndEditions = getWorksAndEditionsFromElements($('a.results'));
        editions = worksAndEditions.editions;
        works = worksAndEditions.works;

        getAvailabilityV2('openlibrary_edition', editions, function(editions_response) {
            getAvailabilityV2('openlibrary_work', works, function(works_response) {
                var response = {books: editions_response, works: works_response};
                $.each(results, function(index, e) {
                    var href = $(e).attr('href');
                    var _type_key_slug = href.split('/')
                    var _type = _type_key_slug[1];
                    var key = _type_key_slug[2];
                    var work, li, cta, mode;
                    if (response[_type]) {
                        work = response[_type][key];
                        li = $(e).closest('li');
                        cta = li.find('.searchResultItemCTA-lending');
                        mode = filter ? localStorage.getItem('mode') : 'everything';

                        if (mode !== 'printdisabled') {
                            if (work.status === 'error' || work.status === 'private') {
                                if (mode === 'ebooks') {
                                    li.remove();
                                }
                            } else {
                                if (work.status === 'open' || work.status === 'borrow_available') {
                                    $(cta).append(`<a href="/books/${work.openlibrary_edition}/x/borrow" ` +
                                                  'class="cta-btn cta-btn--available" ' +
                                                  `data-ol-link-track="${work.status}">${
                                                      work.status === 'open' ? 'Read' : ' Borrow'
                                                  }</a>`);
                                } else if (work.status === 'borrow_unavailable') {
                                    $(cta).append(`${'<form method="POST" ' +
                                                  'action="/books/'}${work.openlibrary_edition}/x/borrow?action=join-waitinglist" ` +
                                                  'class="join-waitlist waitinglist-form">' +
                                                  '<input type="hidden" name="action" value="join-waitinglist">' +
                                                  `<button type="submit" class="cta-btn cta-btn--unavailable" data-ol-link-track="${work.status}">` +
                                                  `Join Waitlist${
                                                      work.num_waitlist !== '0' ? ` <span class="cta-btn__badge">${work.num_waitlist}</span>` : ''
                                                  }</button></form>${
                                                      work.num_waitlist === '0' ? '<div class="waitlist-msg">You will be first in line!</div>' : ''}`);
                                }
                            }
                        }
                    }
                });
            });
        })
        updateBookAvailability();
    }
}

initAvailability();

export {
    getWorksAndEditionsFromElements,
    updateWorkAvailability
};
