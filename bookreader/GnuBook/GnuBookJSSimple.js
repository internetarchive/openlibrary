//Copyright(c)2008 Internet Archive. Software license AGPL version 3.

gb = new GnuBook();

gb.getPageWidth = function(index) {
    return 800;
}

gb.getPageHeight = function(index) {
    return 1200;
}

gb.getPageURI = function(index) {
    var leafStr = '000';            
    var imgStr = (index+1).toString();
    var re = new RegExp("0{"+imgStr.length+"}$");
    var url = 'StandAloneImages/page'+leafStr.replace(re, imgStr) + '.jpg';
    return url;
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

gb.numLeafs = 15;

gb.bookTitle= 'Open Library Bookreader Presentation';
gb.bookUrl  = 'http://openlibrary.org';
gb.init();
