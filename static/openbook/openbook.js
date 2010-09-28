/*
 * openbook.js
 *
 * openbook.js is a pure javascript implemention of John Miedema's OpenBook Wordpress plugin.
 *
 * openbook.js inserts a book cover, title, author, and publisher your webpage.
 * It links to detailed book information in the data source, Open Library. 
 * openbook.js also links to the library record in WorldCat, and inserts COinS 
 * so that other applications like Zotero can pick up the book data. openbook.js 
 * is useful for book reviewers, book bloggers, library webmasters, 
 * anyone who to put book covers and other book data on their websites.
 *
 * Author: Anand Chitipothu <anandology@gmail.com>
 * Version: 0.1
 */

function build_coins(book) {
    var coins = "ctx_ver=Z39.88-2004";
    
    function add_coin(key, value) {
        coins += "&amp;" + key + "=" + encodeURIComponent(value);
    }
    
    add_coin("rft_val_fmt", "info:ofi/fmt:kev:mtx:book");
    add_coin("rfr_id", "info:sid/openlibrary.org:openbook");
    add_coin("rft.genre", "book");
    
    if (book.title)
        add_coin("rft.btitle", book.title);
        
    for (var i in book.authors) {
        add_coin("rtf.au", book.authors[i].name);
    }
    
    for (var i in book.publishers) {
        add_coin("rft.pub", book.publishers[i]);
    }
    
    return '<span class="Z3988" title="TITLE">'.replace("TITLE", coins);
}

/**
 * Add oln, full_title, alternate_authors and tooltip to book.
 */
function process_book(bibkey, book) {
    // delete empty values
    for (var k in book) {
        if (book[k] && book[k].length == 0)
            delete book[k];
    }
    
    // oln
    book.oln = book.key.replace('/b/', '');
    
    if (book.title_prefix)
        book.title = book.title_prefix + ' ' + book.title;
    
    // full_title
    if (book.subtitle)
        book.full_title = book.title + ": " + book.subtitle;
    else
        book.full_title = book.title;
    
    // alternate_authors
    if (book.authors)
        book.alternate_authors = null;
    else if (book.by_statement)
        book.alternate_authors = book.by_statement;
    else if (book.contributions)
        book.alternate_authors = book.contributions.join(", ")
    else
        book.alternate_authors = null;
        
    // publisher
    if (book.publishers)
        book.publisher = book.publishers[0];
        
    // isbn
    var isbn = bibkey;
    if (isbn && /^\d+$/.test(isbn) && (isbn.length == 10 || isbn.length == 13))
        book.isbn = isbn;
    else if (book.isbn_10) 
        book.isbn = book.isbn_10[0];
    else if (book.isbn_13)
        book.isbn = book.isbn_13[0];
    
    // tooltip
    book.tooltip = "";
    
    if (book.first_sentence && book.first_sentence.value)
        book.tooltip += "First Sentence: " + book.first_sentence.value + " ";
    if (book.description && book.description.value)
        book.tooltip += "Description: " + book.description.value + " ";
    if (book.notes && book.notes.value)
        book.tooltip += "Notes: " + book.notes.value + " ";
        
    if (book.tooltip == "")
        book.tooltip = "Click to view title in Open Library"
}

function setup_openbook(bibkey, book) {
    var e = $(".openbook[booknumber=N]".replace("N", bibkey));
    
    process_book(bibkey, book);
    
    function make_cover() {
        var out = ""
            + '<a target="_blank" href="http://openlibrary.org/b/OLN">'
            + '<img class="openbook-cover"'
            +     ' title="TITLE"'
            +     ' src="http://covers.openlibrary.org/b/olid/OLN-M.jpg"'
            +     ' onerror="this.style.padding = \'0px\';"'
            + ' />'
            + '</a>';
        return out.replace(/OLN/g, book.oln).replace("TITLE", book.tooltip);
    }
    
    function make_title() {
        var out = '<a class="openbook-title" target="_blank" title="Click to view title in Open Library" href="http://openlibrary.org/b/OLN">TITLE</a>';
        return out.replace("OLN", book.oln).replace("TITLE", book.full_title);
    }
    
    function make_author() {
        if (book.authors) {
            var t = ', <a class="openbook-author" target="_blank" href="http://openlibrary.orgKEY" title="Click to view author in Open Library">NAME</a>'
            var out = "";
            for (var i in book.authors) {
                var a = book.authors[i];
                out += t.replace("KEY", a.key).replace("NAME", a.name);
            }
        }
        else if (book.alternate_authors) {
            out = ", " + book.alternate_authors;
        }
        else
            out = "";
        return '<span class="openbook-authors">' + out + '</span>'; 
    }
    
    function make_publisher() {
        if (book.publisher)
            return '; <span class="openbook-publisher">' + book.publisher + '</span>';
        else
            return "";
    }
    
    function make_worldcat() {
        var out = ''
            + '<a target="_blank" href="http://worldcat.org/isbn/ISBN" title="Find this title in a local library using WorldCat">'
            + 'Find in library'
            + '</a>';
        return "<div>" + out.replace("ISBN", book.isbn) + "</div>";
    }
        
    var html = '<div class="openbook">' 
        + make_cover() 
        + make_title() 
        + make_author() 
        + make_publisher()
        + make_worldcat() 
        + build_coins(book)
        + '<br/>' 
        + '</div>';
    
    e.html(html);
}

jQuery(document).ready(function() {
    var bibkeys = $.map($(".openbook"), function(div) { return $(div).attr("booknumber"); });

    $.getJSON("http://openlibrary.org/api/books?bibkeys=" + bibkeys.join(",") + "&details=true&callback=?", function(data){
        for (var k in data)
            setup_openbook(k, data[k].details);
    });
});
