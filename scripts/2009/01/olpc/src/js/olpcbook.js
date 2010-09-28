
function olpcbook(id, title, info) {
gb = new GnuBook();

gb.getPageWidth = function(index) {
    return info.pageWidth;
}

gb.getPageHeight = function(index) {
    return info.pageHeight;
}

gb.getPageURI = function(index) {
    index += 1;
    var s = "0000" + index
    s = s.substr(s.length-4);
    return "books/" + id + "/" + s + ".jpg"
}

gb.getPageSide = function(index) {
    if (0 == (index & 0x1)) {
        return 'R';
    } else {
        return 'L';
    }
}

gb.getPageNum = function(index) {
    return index+1;
}

gb.numLeafs = info.pageCount;
gb.bookTitle= title;
gb.bookUrl  = 'http://openlibrary.org';
gb.init();
return gb;
}
