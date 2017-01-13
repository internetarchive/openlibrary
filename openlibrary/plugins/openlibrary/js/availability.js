$(function(){
    var getAvailability = function(ocaids, callback) {
        var url = '/availability';
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

    var books = {};  // book_id: book_ocaids
    var ocaids = []
    $('[ocaid]').each(function(index, elem) {
        var book_ocaids = $(elem).attr('ocaid').split(',').filter(function(book) { return book !== "" });
        var book_key = $(elem).attr('key');

        // TODO: add work_key to borrow-links as property
        books[book_key] = book_ocaids;
        if(book_ocaids.length) {
            Array.prototype.push.apply(ocaids, book_ocaids);
        }
    });

    console.log(books);
    console.log(ocaids);

    getAvailability(ocaids, function(response) {
        for (var book_ocaid in response) {
            if (response[book_ocaid].status === "available") {
                // check all the books on this page
                for (var book_key in books) {
                    var book_ocaids = books[book_key];
		    // check if available book_ocaid is in
		    // this book_key's book_ocaids
                    if (book_ocaids.indexOf(book_ocaid) > -1) {
			// update icon, ocaid, and , url (to ia:)
			// $("[key=" + book_key  + "]")...;
			console.log('Updating ' + book_key + ' (ia:' + book_ocaid + ')');

			// remove book_ocaid from book_ocaids
			delete books[book_key];
                    }
                }
            }
        };

	// for anything remaining in books, set to checked-out
	for (var book_key in books) {
	    console.log("Marking " + book_key + " as checked-out");
	    // $("[key=" + book_key  + "]")...;
	    delete books[book_key];
	}

    });
});
