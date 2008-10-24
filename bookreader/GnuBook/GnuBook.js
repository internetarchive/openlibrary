/*
Copyright(c)2008 Internet Archive. Software license AGPL version 3.

This file is part of GnuBook.

    GnuBook is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    GnuBook is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with GnuBook.  If not, see <http://www.gnu.org/licenses/>.
*/

// GnuBook()
//______________________________________________________________________________
// After you instantiate this object, you must supply the following
// book-specific functions, before calling init():
//  - getPageWidth()
//  - getPageHeight()
//  - getPageURI()
// You must also add a numLeafs property before calling init().

function GnuBook() {
    this.reduce  = 4;
    this.padding = 10;
    this.mode    = 1; //1 or 2
    
    this.displayedLeafs = [];	
    //this.leafsToDisplay = [];
    this.imgs = {};
    this.prefetchedImgs = {}; //an object with numeric keys cooresponding to leafNum
    
    this.timer     = null;
    this.animating = false;
    this.auto      = false;
    
    this.twoPagePopUp = null;
    this.leafEdgeTmp  = null;
    
    this.searchResults = {};
    
    this.firstIndex = null;
    
};

// init()
//______________________________________________________________________________
GnuBook.prototype.init = function() {

    var startLeaf = window.location.hash;
    var title = this.bookTitle.substr(0,50);
    if (this.bookTitle.length>50) title += '...';
    
    $("#GnuBook").empty();
    $("#GnuBook").append("<div id='GBtoolbar'><span style='float:left;'><img class='GBicon' src='http://www-rkumar.us.archive.org/GnuBook/images/zoom_out.png' onclick='gb.zoom1up(-1); return false;'> <img class='GBicon' src='http://www-rkumar.us.archive.org/GnuBook/images/zoom_in.png' onclick='gb.zoom1up(1); return false;'> zoom: <span id='GBzoom'>25</span>% <img class='GBicon' src='http://www-rkumar.us.archive.org/GnuBook/images/script.png' onclick='gb.switchMode(1); return false;'> <img class='GBicon' src='http://www-rkumar.us.archive.org/GnuBook/images/book_open.png' onclick='gb.switchMode(2); return false;'>  &nbsp;&nbsp; <a href='"+this.bookUrl+"'>"+title+"</a></span></div>");
    $("#GBtoolbar").append("<form class='GBpageform' action='javascript:' onsubmit='gb.jumpToPage(this.elements[0].value)'>page:<input id='GBpagenum' type='text' size='3'></input> <img class='GBicon' src='http://www-rkumar.us.archive.org/GnuBook/images/book_previous.png' onclick='gb.prev(); return false;'> <img class='GBicon' src='http://www-rkumar.us.archive.org/GnuBook/images/book_next.png' onclick='gb.next(); return false;'></form>");
    $("#GnuBook").append("<div id='GBcontainer'></div>");
    $("#GBcontainer").append("<div id='GBpageview'></div>");

    $("#GBcontainer").bind('scroll', this, function(e) {
        e.data.loadLeafs();
    });

    $(window).bind('resize', this, function(e) {
        //console.log('resize!');
        if (1 == e.data.mode) {
            //console.log('centering 1page view');
            e.data.centerPageView();
            $('#GBpageview').empty()
            e.data.displayedLeafs = [];
            e.data.updateSearchHilites(); //deletes hilights but does not call remove()            
            e.data.loadLeafs();
        } else {
            //console.log('drawing 2 page view');
            e.data.prepareTwoPageView();
        }
    });

    if (1 == this.mode) {
        this.resizePageView();
    
        if ('' != startLeaf) {
            this.jumpToIndex(parseInt(startLeaf.substr(1)));
            //alert('jump to ' + startLeaf);
        }
    } else {
        this.displayedLeafs=[0];
        this.prepareTwoPageView();
        //if (this.auto) this.nextPage();
    }
}

// drawLeafs()
//______________________________________________________________________________
GnuBook.prototype.drawLeafs = function() {
    if (1 == this.mode) {
        this.drawLeafsOnePage();
    } else {
        this.drawLeafsTwoPage();
    }
}


// drawLeafsOnePage()
//______________________________________________________________________________
GnuBook.prototype.drawLeafsOnePage = function() {
    //alert('drawing leafs!');
    this.timer = null;


    var scrollTop = $('#GBcontainer').attr('scrollTop');
    var scrollBottom = scrollTop + $('#GBcontainer').height();
    //console.log('top=' + scrollTop + ' bottom='+scrollBottom);
    
    var leafsToDisplay = [];
    
    var i;
    var leafTop = 0;
    var leafBottom = 0;
    for (i=0; i<this.numLeafs; i++) {
        var height  = parseInt(this.getPageHeight(i)/this.reduce); 
    
        leafBottom += height;
        //console.log('leafTop = '+leafTop+ ' pageH = ' + this.pageH[i] + 'leafTop>=scrollTop=' + (leafTop>=scrollTop));
        var topInView    = (leafTop >= scrollTop) && (leafTop <= scrollBottom);
        var bottomInView = (leafBottom >= scrollTop) && (leafBottom <= scrollBottom);
        var middleInView = (leafTop <=scrollTop) && (leafBottom>=scrollBottom);
        if (topInView | bottomInView | middleInView) {
            //console.log('to display: ' + i);
            leafsToDisplay.push(i);
        }
        leafTop += height +10;      
        leafBottom += 10;
    }

    var firstLeafToDraw  = leafsToDisplay[0];
    window.location.hash = firstLeafToDraw;    
    this.firstIndex      = firstLeafToDraw;

    if ((0 != firstLeafToDraw) && (1 < this.reduce)) {
        firstLeafToDraw--;
        leafsToDisplay.unshift(firstLeafToDraw);
    }
    
    var lastLeafToDraw = leafsToDisplay[leafsToDisplay.length-1];
    if ( ((this.numLeafs-1) != lastLeafToDraw) && (1 < this.reduce) ) {
        leafsToDisplay.push(lastLeafToDraw+1);
    }
    
    leafTop = 0;
    var i;
    for (i=0; i<firstLeafToDraw; i++) {
        leafTop += parseInt(this.getPageHeight(i)/this.reduce) +10;
    }

    //var viewWidth = $('#GBpageview').width(); //includes scroll bar width
    var viewWidth = $('#GBcontainer').attr('scrollWidth');


    for (i=0; i<leafsToDisplay.length; i++) {
        var leafNum = leafsToDisplay[i];    
        var height  = parseInt(this.getPageHeight(leafNum)/this.reduce); 

        if(-1 == jQuery.inArray(leafsToDisplay[i], this.displayedLeafs)) {            
            var width   = parseInt(this.getPageWidth(leafNum)/this.reduce); 
            //console.log("displaying leaf " + leafsToDisplay[i] + ' leafTop=' +leafTop);
            var div = document.createElement("div");
            div.className = 'GBpagediv1up';
            div.id = 'pagediv'+leafNum;
            div.style.position = "absolute";
            $(div).css('top', leafTop + 'px');
            var left = (viewWidth-width)>>1;
            if (left<0) left = 0;
            $(div).css('left', left+'px');
            $(div).css('width', width+'px');
            $(div).css('height', height+'px');
            //$(div).text('loading...');
            
            $('#GBpageview').append(div);

            var img = document.createElement("img");
            img.src = this.getPageURI(leafNum);
            $(img).css('width', width+'px');
            $(img).css('height', height+'px');
            $(div).append(img);

        } else {
            //console.log("not displaying " + leafsToDisplay[i] + ' score=' + jQuery.inArray(leafsToDisplay[i], this.displayedLeafs));            
        }

        leafTop += height +10;

    }
    
    for (i=0; i<this.displayedLeafs.length; i++) {
        if (-1 == jQuery.inArray(this.displayedLeafs[i], leafsToDisplay)) {
            var leafNum = this.displayedLeafs[i];
            //console.log('Removing leaf ' + leafNum);
            //console.log('id='+'#pagediv'+leafNum+ ' top = ' +$('#pagediv'+leafNum).css('top'));
            $('#pagediv'+leafNum).remove();
        } else {
            //console.log('NOT Removing leaf ' + this.displayedLeafs[i]);
        }
    }
    
    this.displayedLeafs = leafsToDisplay.slice();
    this.updateSearchHilites();
    
    if (null != this.getPageNum(firstLeafToDraw))  {
        $("#GBpagenum").val(this.getPageNum(firstLeafToDraw));
    } else {
        $("#GBpagenum").val('');
    }
}

// drawLeafsTwoPage()
//______________________________________________________________________________
GnuBook.prototype.drawLeafsTwoPage = function() {
    //alert('drawing two leafs!');

    var scrollTop = $('#GBcontainer').attr('scrollTop');
    var scrollBottom = scrollTop + $('#GBcontainer').height();
    var leafNum = this.currentLeafL;
    var height  = this.getPageHeight(leafNum); 
    var width   = this.getPageWidth(leafNum);
    var handSide= this.getPageSide(leafNum);

    var leafEdgeWidthL = parseInt( (leafNum/this.numLeafs)*this.twoPageEdgeW );
    var leafEdgeWidthR = this.twoPageEdgeW - leafEdgeWidthL;
    var divWidth = this.twoPageW*2+20 + this.twoPageEdgeW;
    var divLeft = ($('#GBcontainer').width() - divWidth) >> 1;
    //console.log(leafEdgeWidthL);

    var middle = ($('#GBcontainer').width() >> 1);            
    var left = middle - this.twoPageW;
    var top  = ($('#GBcontainer').height() - this.twoPageH) >> 1;                

    var scaledW = parseInt(this.twoPageH*width/height);
    left = 10+leafEdgeWidthL;
    //var right = left+scaledW;
    var right = $(this.twoPageDiv).width()-11-$(this.leafEdgeL).width()-scaledW;

    var gutter = middle+parseInt((2*this.currentLeafL - this.numLeafs)*this.twoPageEdgeW/this.numLeafs/2);
    
    
    this.prefetchImg(leafNum);
    $(this.prefetchedImgs[leafNum]).css({
        position: 'absolute',
        /*right:   gutter+'px',*/
        left: gutter-scaledW+'px',
        top:    top+'px',
        backgroundColor: 'rgb(234, 226, 205)',
        height: this.twoPageH +'px',
        width:  scaledW + 'px',
        borderRight: '1px solid black',
        zIndex: 2
    }).appendTo('#GBcontainer');
    //$('#GBcontainer').append(this.prefetchedImgs[leafNum]);


    var leafNum = this.currentLeafR;
    var height  = this.getPageHeight(leafNum); 
    var width   = this.getPageWidth(leafNum);
    //    var left = ($('#GBcontainer').width() >> 1);
    left += scaledW;

    var scaledW = this.twoPageH*width/height;
    this.prefetchImg(leafNum);
    $(this.prefetchedImgs[leafNum]).css({
        position: 'absolute',
        left:   gutter+'px',
        top:    top+'px',
        backgroundColor: 'rgb(234, 226, 205)',
        height: this.twoPageH + 'px',
        width:  scaledW + 'px',
        borderLeft: '1px solid black',
        zIndex: 2
    }).appendTo('#GBcontainer');
    //$('#GBcontainer').append(this.prefetchedImgs[leafNum]);
        

    this.displayedLeafs = [this.currentLeafL, this.currentLeafR];
    this.setClickHandlers();

    this.updatePageNumBox2UP();
}

// updatePageNumBox2UP
//______________________________________________________________________________
GnuBook.prototype.updatePageNumBox2UP = function() {
    if (null != this.getPageNum(this.currentLeafL))  {
        $("#GBpagenum").val(this.getPageNum(this.currentLeafL));
    } else {
        $("#GBpagenum").val('');
    }
    window.location.hash = this.currentLeafL; 
}

// loadLeafs()
//______________________________________________________________________________
GnuBook.prototype.loadLeafs = function() {


    var self = this;
    if (null == this.timer) {
        this.timer=setTimeout(function(){self.drawLeafs()},250);
    } else {
        clearTimeout(this.timer);
        this.timer=setTimeout(function(){self.drawLeafs()},250);    
    }
}


// zoom1up()
//______________________________________________________________________________
GnuBook.prototype.zoom1up = function(dir) {
    if (2 == this.mode) {     //can only zoom in 1-page mode
        this.switchMode(1);
        return;
    }
    
    if (1 == dir) {
        if (this.reduce <= 0.5) return;
        this.reduce*=0.5;           //zoom in
    } else {
        if (this.reduce >= 8) return;
        this.reduce*=2;             //zoom out
    }
    
    this.resizePageView();

    $('#GBpageview').empty()
    this.displayedLeafs = [];
    this.loadLeafs();
    
    $('#GBzoom').text(100/this.reduce);
}


// resizePageView()
//______________________________________________________________________________
GnuBook.prototype.resizePageView = function() {
    var i;
    var viewHeight = 0;
    //var viewWidth  = $('#GBcontainer').width(); //includes scrollBar
    var viewWidth  = $('#GBcontainer').attr('clientWidth');   

    var oldScrollTop  = $('#GBcontainer').attr('scrollTop');
    var oldViewHeight = $('#GBpageview').height();
    if (0 != oldViewHeight) {
        var scrollRatio = oldScrollTop / oldViewHeight;
    } else {
        var scrollRatio = 0;
    }
    
    for (i=0; i<this.numLeafs; i++) {
        viewHeight += parseInt(this.getPageHeight(i)/this.reduce) + this.padding; 
        var width = parseInt(this.getPageWidth(i)/this.reduce);
        if (width>viewWidth) viewWidth=width;
    }
    $('#GBpageview').height(viewHeight);
    $('#GBpageview').width(viewWidth);    

    $('#GBcontainer').attr('scrollTop', Math.floor(scrollRatio*viewHeight));
    
    this.centerPageView();
    this.loadLeafs();
    
}

// centerPageView()
//______________________________________________________________________________
GnuBook.prototype.centerPageView = function() {

    var scrollWidth  = $('#GBcontainer').attr('scrollWidth');
    var clientWidth  =  $('#GBcontainer').attr('clientWidth');
    //console.log('sW='+scrollWidth+' cW='+clientWidth);
    if (scrollWidth > clientWidth) {
        $('#GBcontainer').attr('scrollLeft', (scrollWidth-clientWidth)/2);
    }

}

// jumpToPage()
//______________________________________________________________________________
GnuBook.prototype.jumpToPage = function(pageNum) {
    if (2 == this.mode) return;
    
    var i;
    var foundPage = false;
    var foundLeaf = null;
    for (i=0; i<this.numLeafs; i++) {
        if (this.pageNums[i] == pageNum) {
            foundPage = true;
            foundLeaf = i;
            break;
        }
    }
    
    if (foundPage) {
        var leafTop = 0;
        var h;
        for (i=0; i<foundLeaf; i++) {
            h = parseInt(this.getPageHeight(i)/this.reduce); 
            leafTop += h + this.padding;
        }
        $('#GBcontainer').attr('scrollTop', leafTop);
    } else {
        alert('Page not found. This book might not have pageNumbers in scandata.');
    }
}

// jumpToIndex()
//______________________________________________________________________________
GnuBook.prototype.jumpToIndex = function(index) {
    if (2 == this.mode) {
        if (index<this.currentLeafL) {
            if ('L' == this.getPageSide(index)) {
                this.flipBackToIndex(index);
            } else {
                this.flipBackToIndex(index-1);
            }
        } else if (index>this.currentLeafR) {
            if ('R' == this.getPageSide(index)) {
                this.flipFwdToIndex(index);
            } else {
                this.flipFwdToIndex(index+1);
            }        
        }

    } else {        
        var i;
        var leafTop = 0;
        var h;
        for (i=0; i<index; i++) {
            h = parseInt(this.getPageHeight(i)/this.reduce); 
            leafTop += h + this.padding;
        }
        //$('#GBcontainer').attr('scrollTop', leafTop);
        $('#GBcontainer').animate({scrollTop: leafTop}, 'fast');    
    }
}



// switchMode()
//______________________________________________________________________________
GnuBook.prototype.switchMode = function(mode) {
    if (mode == this.mode) return;

    this.removeSearchHilites();

    this.mode = mode;
    if (1 == mode) {
        this.prepareOnePageView();
    } else {
        this.prepareTwoPageView();
    }

}

//prepareOnePageView()
//______________________________________________________________________________
GnuBook.prototype.prepareOnePageView = function() {

    var startLeaf = this.displayedLeafs[0];
    
    $('#GBcontainer').empty();
    $('#GBcontainer').css({
        overflowY: 'scroll',
        overflowX: 'auto'
    });
    
    $("#GBcontainer").append("<div id='GBpageview'></div>");
    this.resizePageView();
    this.jumpToIndex(startLeaf);
    this.displayedLeafs = [];    
    this.drawLeafsOnePage();
    $('#GBzoom').text(100/this.reduce);    
}

// prepareTwoPageView()
//______________________________________________________________________________
GnuBook.prototype.prepareTwoPageView = function() {
    $('#GBcontainer').empty();

    var firstLeaf = this.displayedLeafs[0];
    if ('R' == this.getPageSide(firstLeaf)) {
        if (0 == firstLeaf) {
            firstLeaf++;
        } else {
            firstLeaf--;
        }
    }

    this.currentLeafL = null;
    this.currentLeafR = null;
    this.pruneUnusedImgs();
    
    this.currentLeafL = firstLeaf;
    this.currentLeafR = firstLeaf + 1;
    
    this.calculateSpreadSize(); //sets this.twoPageW, twoPageH, and twoPageRatio

    var middle = ($('#GBcontainer').width() >> 1);
    var gutter = middle+parseInt((2*this.currentLeafL - this.numLeafs)*this.twoPageEdgeW/this.numLeafs/2);
    var scaledWL = this.getPageWidth2UP(this.currentLeafL);
    var scaledWR = this.getPageWidth2UP(this.currentLeafR);
    var leafEdgeWidthL = parseInt( (firstLeaf/this.numLeafs)*this.twoPageEdgeW );
    var leafEdgeWidthR = this.twoPageEdgeW - leafEdgeWidthL;

    //console.log('idealWidth='+idealWidth+' idealHeight='+idealHeight);
    //var divWidth = this.twoPageW*2+20 + this.twoPageEdgeW;
    var divWidth = scaledWL + scaledWR + 20 + this.twoPageEdgeW;
    var divHeight = this.twoPageH+20;
    //var divLeft = ($('#GBcontainer').width() - divWidth) >> 1;
    var divLeft = gutter-scaledWL-leafEdgeWidthL-10;
    var divTop = ($('#GBcontainer').height() - divHeight) >> 1;
    //console.log('divWidth='+divWidth+' divHeight='+divHeight+ ' divLeft='+divLeft+' divTop='+divTop);

    this.twoPageDiv = document.createElement('div');
    $(this.twoPageDiv).attr('id', 'book_div_1').css({
        border: '1px solid rgb(68, 25, 17)',
        width:  divWidth + 'px',
        height: divHeight+'px',
        visibility: 'visible',
        position: 'absolute',
        backgroundColor: 'rgb(136, 51, 34)',
        left: divLeft + 'px',
        top: divTop+'px',
        MozBorderRadiusTopleft: '7px',
        MozBorderRadiusTopright: '7px',
        MozBorderRadiusBottomright: '7px',
        MozBorderRadiusBottomleft: '7px'
    }).appendTo('#GBcontainer');
    //$('#GBcontainer').append('<div id="book_div_1" style="border: 1px solid rgb(68, 25, 17); width: ' + divWidth + 'px; height: '+divHeight+'px; visibility: visible; position: absolute; background-color: rgb(136, 51, 34); left: ' + divLeft + 'px; top: '+divTop+'px; -moz-border-radius-topleft: 7px; -moz-border-radius-topright: 7px; -moz-border-radius-bottomright: 7px; -moz-border-radius-bottomleft: 7px;"/>');


    var height  = this.getPageHeight(this.currentLeafR); 
    var width   = this.getPageWidth(this.currentLeafR);    
    var scaledW = this.twoPageH*width/height;
    
    this.leafEdgeR = document.createElement('div');
    $(this.leafEdgeR).css({
        borderStyle: 'solid solid solid none',
        borderColor: 'rgb(51, 51, 34)',
        borderWidth: '1px 1px 1px 0px',
        background: 'transparent url(http://www-rkumar.us.archive.org/GnuBook/images/right-edges.png) repeat scroll 0% 0%',
        width: leafEdgeWidthR + 'px',
        height: this.twoPageH-1 + 'px',
        /*right: '10px',*/
        left: gutter+scaledW+'px',
        top: divTop+10+'px',
        position: 'absolute'
    }).appendTo('#GBcontainer');
    
    this.leafEdgeL = document.createElement('div');
    $(this.leafEdgeL).css({
        borderStyle: 'solid none solid solid',
        borderColor: 'rgb(51, 51, 34)',
        borderWidth: '1px 0px 1px 1px',
        background: 'transparent url(http://www-rkumar.us.archive.org/GnuBook/images/left-edges.png) repeat scroll 0% 0%',
        width: leafEdgeWidthL + 'px',
        height: this.twoPageH-1 + 'px',
        left: divLeft+10+'px',
        top: divTop+10+'px',    
        position: 'absolute'
    }).appendTo('#GBcontainer');



    divWidth = 30;
    divHeight = this.twoPageH+20;
    divLeft = ($('#GBcontainer').width() - divWidth) >> 1;
    divTop = ($('#GBcontainer').height() - divHeight) >> 1;

    div = document.createElement('div');
    $(div).attr('id', 'book_div_2').css({
        border:          '1px solid rgb(68, 25, 17)',
        width:           divWidth+'px',
        height:          divHeight+'px',
        position:        'absolute',
        backgroundColor: 'rgb(68, 25, 17)',
        left:            divLeft+'px',
        top:             divTop+'px'
    }).appendTo('#GBcontainer');
    //$('#GBcontainer').append('<div id="book_div_2" style="border: 1px solid rgb(68, 25, 17); width: '+divWidth+'px; height: '+divHeight+'px; visibility: visible; position: absolute; background-color: rgb(68, 25, 17); left: '+divLeft+'px; top: '+divTop+'px;"/>');

    divWidth = this.twoPageW*2;
    divHeight = this.twoPageH;
    divLeft = ($('#GBcontainer').width() - divWidth) >> 1;
    divTop = ($('#GBcontainer').height() - divHeight) >> 1;


    this.prepareTwoPagePopUp();

    this.displayedLeafs = [];
    //this.leafsToDisplay=[firstLeaf, firstLeaf+1];
    //console.log('leafsToDisplay: ' + this.leafsToDisplay[0] + ' ' + this.leafsToDisplay[1]);
    this.drawLeafsTwoPage();
    this.updateSearchHilites2UP();
    
    this.prefetch();
    $('#GBzoom').text((100*this.twoPageH/this.getPageHeight(firstLeaf)).toString().substr(0,4));
}

// prepareTwoPagePopUp()
//______________________________________________________________________________
GnuBook.prototype.prepareTwoPagePopUp = function() {
    this.twoPagePopUp = document.createElement('div');
    $(this.twoPagePopUp).css({
        border: '1px solid black',
        padding: '2px 6px',
        position: 'absolute',
        fontFamily: 'sans-serif',
        fontSize: '14px',
        zIndex: '1000',
        backgroundColor: 'rgb(255, 255, 238)',
        opacity: 0.85
    }).appendTo('#GBcontainer');
    $(this.twoPagePopUp).hide();
    
    $(this.leafEdgeL).add(this.leafEdgeR).bind('mouseenter', this, function(e) {
        $(e.data.twoPagePopUp).show();
    });

    $(this.leafEdgeL).add(this.leafEdgeR).bind('mouseleave', this, function(e) {
        $(e.data.twoPagePopUp).hide();
    });

    $(this.leafEdgeL).bind('click', this, function(e) { 
        var jumpIndex = e.data.currentLeafL - ($(e.data.leafEdgeL).offset().left + $(e.data.leafEdgeL).width() - e.pageX) * 10;
        jumpIndex = Math.max(jumpIndex, 0);
        e.data.flipBackToIndex(jumpIndex);
    
    });

    $(this.leafEdgeR).bind('click', this, function(e) { 
        var jumpIndex = e.data.currentLeafR + (e.pageX - $(e.data.leafEdgeR).offset().left) * 10;
        jumpIndex = Math.max(jumpIndex, 0);
        e.data.flipFwdToIndex(jumpIndex);
    
    });

    $(this.leafEdgeR).bind('mousemove', this, function(e) {

        var jumpLeaf = e.data.currentLeafR + (e.pageX - $(e.data.leafEdgeR).offset().left) * 10;
        jumpLeaf = Math.min(jumpLeaf, e.data.numLeafs-1);        
        $(e.data.twoPagePopUp).text('View Leaf '+jumpLeaf);
        
        $(e.data.twoPagePopUp).css({
            left: e.pageX + 'px',
            top: e.pageY-$('#GBcontainer').offset().top+ 'px'
        });
    });

    $(this.leafEdgeL).bind('mousemove', this, function(e) {
        var jumpLeaf = e.data.currentLeafL - ($(e.data.leafEdgeL).offset().left + $(e.data.leafEdgeL).width() - e.pageX) * 10;
        jumpLeaf = Math.max(jumpLeaf, 0);
        $(e.data.twoPagePopUp).text('View Leaf '+jumpLeaf);
        
        $(e.data.twoPagePopUp).css({
            left: e.pageX - $(e.data.twoPagePopUp).width() - 30 + 'px',
            top: e.pageY-$('#GBcontainer').offset().top+ 'px'
        });
    });
}

// calculateSpreadSize()
//______________________________________________________________________________
// Calculates 2-page spread dimensions based on this.currentLeafL and
// this.currentLeafR
// This function sets this.twoPageH, twoPageW, and twoPageRatio

GnuBook.prototype.calculateSpreadSize = function() {
    var firstLeaf  = this.currentLeafL;
    var secondLeaf = this.currentLeafR;
    //console.log('first page is ' + firstLeaf);

    var canon5Dratio = 1.5;
    
    var firstLeafRatio  = this.getPageHeight(firstLeaf) / this.getPageWidth(firstLeaf);
    var secondLeafRatio = this.getPageHeight(secondLeaf) / this.getPageWidth(secondLeaf);
    //console.log('firstLeafRatio = ' + firstLeafRatio + ' secondLeafRatio = ' + secondLeafRatio);

    var ratio;
    if (Math.abs(firstLeafRatio - canon5Dratio) < Math.abs(secondLeafRatio - canon5Dratio)) {
        ratio = firstLeafRatio;
        //console.log('using firstLeafRatio ' + ratio);
    } else {
        ratio = secondLeafRatio;
        //console.log('using secondLeafRatio ' + ratio);
    }

    var totalLeafEdgeWidth = parseInt(this.numLeafs * 0.1);
    var maxLeafEdgeWidth   = parseInt($('#GBcontainer').width() * 0.1);
    totalLeafEdgeWidth     = Math.min(totalLeafEdgeWidth, maxLeafEdgeWidth);
    
    $('#GBcontainer').css('overflow', 'hidden');

    var idealWidth  = ($('#GBcontainer').width() - 30 - totalLeafEdgeWidth)>>1;
    var idealHeight = $('#GBcontainer').height() - 30;
    //console.log('init idealWidth='+idealWidth+' idealHeight='+idealHeight + ' ratio='+ratio);

    if (idealHeight/ratio <= idealWidth) {
        //use height
        idealWidth = parseInt(idealHeight/ratio);
    } else {
        //use width
        idealHeight = parseInt(idealWidth*ratio);
    }

    this.twoPageH     = idealHeight;
    this.twoPageW     = idealWidth;
    this.twoPageRatio = ratio;
    this.twoPageEdgeW = totalLeafEdgeWidth;    

}

// next()
//______________________________________________________________________________
GnuBook.prototype.next = function() {
    if (2 == this.mode) {
        this.flipFwdToIndex(null);
    } else {
        if (this.firstIndex <= (this.numLeafs - 2)) {
            this.jumpToIndex(this.firstIndex+1);
        }
    }
}

// prev()
//______________________________________________________________________________
GnuBook.prototype.prev = function() {
    if (2 == this.mode) {
        this.flipBackToIndex(null);
    } else {
        if (this.firstIndex >= 1) {
            this.jumpToIndex(this.firstIndex-1);
        }    
    }
}


// flipBackToIndex()
//______________________________________________________________________________
// to flip back one spread, pass index=null
GnuBook.prototype.flipBackToIndex = function(index) {
    if (1 == this.mode) return;

    var leftIndex = this.currentLeafL;
    if (leftIndex <= 2) return;
    if (this.animating) return;

    if (null != this.leafEdgeTmp) {
        alert('error: leafEdgeTmp should be null!');
        return;
    }
    
    if (null == index) {
        index = leftIndex-2;
    }
    if (index<0) return;

    if ('L' !=  this.getPageSide(index)) {
        alert('img with index ' + index + ' is not a left-hand page');
        return;
    }

    this.animating = true;
    
    var prevL = index;
    var prevR = index+1;

    var gutter= this.prepareFlipBack(prevL, prevR);

    var leftLeaf = this.currentLeafL;

    var oldLeafEdgeWidthL = parseInt( (this.currentLeafL/this.numLeafs)*this.twoPageEdgeW );
    var newLeafEdgeWidthL = parseInt( (index            /this.numLeafs)*this.twoPageEdgeW );    
    var leafEdgeTmpW = oldLeafEdgeWidthL - newLeafEdgeWidthL;

    var scaledWL = this.getPageWidth2UP(prevL);

    var top  = ($('#GBcontainer').height() - this.twoPageH) >> 1;                

    this.leafEdgeTmp = document.createElement('div');
    $(this.leafEdgeTmp).css({
        borderStyle: 'solid none solid solid',
        borderColor: 'rgb(51, 51, 34)',
        borderWidth: '1px 0px 1px 1px',
        background: 'transparent url(http://www-rkumar.us.archive.org/GnuBook/images/left-edges.png) repeat scroll 0% 0%',
        width: leafEdgeTmpW + 'px',
        height: this.twoPageH-1 + 'px',
        left: gutter-scaledWL+10+newLeafEdgeWidthL+'px',
        top: top+'px',    
        position: 'absolute',
        zIndex:1000
    }).appendTo('#GBcontainer');
    
    //$(this.leafEdgeL).css('width', newLeafEdgeWidthL+'px');
    $(this.leafEdgeL).css({
        width: newLeafEdgeWidthL+'px', 
        left: gutter-scaledWL-newLeafEdgeWidthL+'px'
    });   

    var left = $(this.prefetchedImgs[leftLeaf]).offset().left;
    var right = $('#GBcontainer').width()-left-$(this.prefetchedImgs[leftLeaf]).width()+9+'px';
    $(this.prefetchedImgs[leftLeaf]).css({
        right: right,
        left: null
    });

     left = $(this.prefetchedImgs[leftLeaf]).offset().left - $('#book_div_1').offset().left;
     right = left+$(this.prefetchedImgs[leftLeaf]).width()+'px';

    $(this.leafEdgeTmp).animate({left: gutter}, 'fast', 'easeInSine');    
    //$(this.prefetchedImgs[leftLeaf]).animate({width: '0px'}, 'slow', 'easeInSine');

    var scaledWR = this.getPageWidth2UP(prevR);
    
    var self = this;

    this.removeSearchHilites();

    $(this.prefetchedImgs[leftLeaf]).animate({width: '0px'}, 'fast', 'easeInSine', function() {
        $(self.leafEdgeTmp).animate({left: gutter+scaledWR+'px'}, 'fast', 'easeOutSine');    
        $(self.prefetchedImgs[prevR]).animate({width: scaledWR+'px'}, 'fast', 'easeOutSine', function() {
            $(self.prefetchedImgs[prevL]).css('zIndex', 2);

            $(self.leafEdgeR).css({
                width: self.twoPageEdgeW-newLeafEdgeWidthL+'px',
                left:  gutter+scaledWR+'px'
            });
            
            $(self.twoPageDiv).css({
                width: scaledWL+scaledWR+self.twoPageEdgeW+20+'px',
                left: gutter-scaledWL-newLeafEdgeWidthL-10+'px'
            });
            
            $(self.leafEdgeTmp).remove();
            self.leafEdgeTmp = null;
            
            self.currentLeafL = prevL;
            self.currentLeafR = prevR;
            self.displayedLeafs = [prevL, prevR];
            self.setClickHandlers();
            self.pruneUnusedImgs();
            self.prefetch();
            self.animating = false;
            
            self.updateSearchHilites2UP();
            self.updatePageNumBox2UP();
            //$('#GBzoom').text((self.twoPageH/self.getPageHeight(prevL)).toString().substr(0,4));            
        });
    });        
    
}

// flipFwdToIndex()
//______________________________________________________________________________
// to flip forward one spread, pass index=null
GnuBook.prototype.flipFwdToIndex = function(index) {
    var rightLeaf = this.currentLeafR;
    if (rightLeaf >= this.numLeafs-3) return;

    if (this.animating) return;

    if (null != this.leafEdgeTmp) {
        alert('error: leafEdgeTmp should be null!');
        return;
    }

    
    if (null == index) {
        index = rightLeaf+2;
    }
    if (index>=this.numLeafs-3) return;

    if ('R' !=  this.getPageSide(index)) {
        alert('img with index ' + index + ' is not a right-hand page');
        return;
    }

    this.animating = true;

    var nextL = index-1;
    var nextR = index;

    var gutter= this.prepareFlipFwd(nextL, nextR);

    var oldLeafEdgeWidthL = parseInt( (this.currentLeafL/this.numLeafs)*this.twoPageEdgeW );
    var oldLeafEdgeWidthR = this.twoPageEdgeW-oldLeafEdgeWidthL;
    var newLeafEdgeWidthL = parseInt( (nextL            /this.numLeafs)*this.twoPageEdgeW );    
    var newLeafEdgeWidthR = this.twoPageEdgeW-newLeafEdgeWidthL;

    var leafEdgeTmpW = oldLeafEdgeWidthR - newLeafEdgeWidthR;

    var top  = ($('#GBcontainer').height() - this.twoPageH) >> 1;                

    var height  = this.getPageHeight(rightLeaf); 
    var width   = this.getPageWidth(rightLeaf);    
    var scaledW = this.twoPageH*width/height;

    var middle     = ($('#GBcontainer').width() >> 1);
    var currGutter = middle+parseInt((2*this.currentLeafL - this.numLeafs)*this.twoPageEdgeW/this.numLeafs/2);    

    this.leafEdgeTmp = document.createElement('div');
    $(this.leafEdgeTmp).css({
        borderStyle: 'solid none solid solid',
        borderColor: 'rgb(51, 51, 34)',
        borderWidth: '1px 0px 1px 1px',
        background: 'transparent url(http://www-rkumar.us.archive.org/GnuBook/images/left-edges.png) repeat scroll 0% 0%',
        width: leafEdgeTmpW + 'px',
        height: this.twoPageH-1 + 'px',
        left: currGutter+scaledW+'px',
        top: top+'px',    
        position: 'absolute',
        zIndex:1000
    }).appendTo('#GBcontainer');

    var scaledWR = this.getPageWidth2UP(nextR);
    $(this.leafEdgeR).css({width: newLeafEdgeWidthR+'px', left: gutter+scaledWR+'px' });

    var scaledWL = this.getPageWidth2UP(nextL);
    
    var self = this;

    var speed = 'fast';

    this.removeSearchHilites();
    
    $(this.leafEdgeTmp).animate({left: gutter}, speed, 'easeInSine');    
    $(this.prefetchedImgs[rightLeaf]).animate({width: '0px'}, speed, 'easeInSine', function() {
        $(self.leafEdgeTmp).animate({left: gutter-scaledWL-leafEdgeTmpW+'px'}, speed, 'easeOutSine');    
        $(self.prefetchedImgs[nextL]).animate({width: scaledWL+'px'}, speed, 'easeOutSine', function() {
            $(self.prefetchedImgs[nextR]).css('zIndex', 2);

            $(self.leafEdgeL).css({
                width: newLeafEdgeWidthL+'px', 
                left: gutter-scaledWL-newLeafEdgeWidthL+'px'
            });
            
            $(self.twoPageDiv).css({
                width: scaledWL+scaledWR+self.twoPageEdgeW+20+'px',
                left: gutter-scaledWL-newLeafEdgeWidthL-10+'px'
            });
            
            $(self.leafEdgeTmp).remove();
            self.leafEdgeTmp = null;
            
            self.currentLeafL = nextL;
            self.currentLeafR = nextR;
            self.displayedLeafs = [nextL, nextR];
            self.setClickHandlers();            
            self.pruneUnusedImgs();
            self.prefetch();
            self.animating = false;

            self.updateSearchHilites2UP();
            self.updatePageNumBox2UP();
            //$('#GBzoom').text((self.twoPageH/self.getPageHeight(nextL)).toString().substr(0,4));
        });
    });
    
}

// setClickHandlers
//______________________________________________________________________________
GnuBook.prototype.setClickHandlers = function() {
    var self = this;
    $(this.prefetchedImgs[this.currentLeafL]).click(function() {
        //self.prevPage();
        self.flipBackToIndex(null);
    });
    $(this.prefetchedImgs[this.currentLeafR]).click(function() {
        //self.nextPage();
        self.flipFwdToIndex(null);        
    });
}

// prefetchImg()
//______________________________________________________________________________
GnuBook.prototype.prefetchImg = function(leafNum) {
    if (undefined == this.prefetchedImgs[leafNum]) {        
        var img = document.createElement("img");
        img.src = this.getPageURI(leafNum);
        this.prefetchedImgs[leafNum] = img;
    }
}


// prepareFlipBack()
//______________________________________________________________________________
GnuBook.prototype.prepareFlipBack = function(prevL, prevR) {

    this.prefetchImg(prevL);
    this.prefetchImg(prevR);
    
    var height  = this.getPageHeight(prevL); 
    var width   = this.getPageWidth(prevL);    
    var middle = ($('#GBcontainer').width() >> 1);
    var top  = ($('#GBcontainer').height() - this.twoPageH) >> 1;                
    var scaledW = this.twoPageH*width/height;

    var gutter = middle+parseInt((2*prevL - this.numLeafs)*this.twoPageEdgeW/this.numLeafs/2);    

    $(this.prefetchedImgs[prevL]).css({
        position: 'absolute',
        /*right:   middle+'px',*/
        left: gutter-scaledW+'px',
        top:    top+'px',
        backgroundColor: 'rgb(234, 226, 205)',
        height: this.twoPageH,
        width:  scaledW+'px',
        borderRight: '1px solid black',
        zIndex: 1
    });

    $('#GBcontainer').append(this.prefetchedImgs[prevL]);

    $(this.prefetchedImgs[prevR]).css({
        position: 'absolute',
        left:   gutter+'px',
        top:    top+'px',
        backgroundColor: 'rgb(234, 226, 205)',
        height: this.twoPageH,
        width:  '0px',
        borderLeft: '1px solid black',
        zIndex: 2
    });

    $('#GBcontainer').append(this.prefetchedImgs[prevR]);


    return gutter;
            
}

// prepareFlipFwd()
//______________________________________________________________________________
GnuBook.prototype.prepareFlipFwd = function(nextL, nextR) {

    this.prefetchImg(nextL);
    this.prefetchImg(nextR);

    var height  = this.getPageHeight(nextR); 
    var width   = this.getPageWidth(nextR);    
    var middle = ($('#GBcontainer').width() >> 1);
    var top  = ($('#GBcontainer').height() - this.twoPageH) >> 1;                
    var scaledW = this.twoPageH*width/height;

    var gutter = middle+parseInt((2*nextL - this.numLeafs)*this.twoPageEdgeW/this.numLeafs/2);    
    
    $(this.prefetchedImgs[nextR]).css({
        position: 'absolute',
        left:   gutter+'px',
        top:    top+'px',
        backgroundColor: 'rgb(234, 226, 205)',
        height: this.twoPageH,
        width:  scaledW+'px',
        borderLeft: '1px solid black',
        zIndex: 1
    });

    $('#GBcontainer').append(this.prefetchedImgs[nextR]);

    height  = this.getPageHeight(nextL); 
    width   = this.getPageWidth(nextL);      
    scaledW = this.twoPageH*width/height;

    $(this.prefetchedImgs[nextL]).css({
        position: 'absolute',
        right:   $('#GBcontainer').width()-gutter+'px',
        top:    top+'px',
        backgroundColor: 'rgb(234, 226, 205)',
        height: this.twoPageH,
        width:  0+'px',
        borderRight: '1px solid black',
        zIndex: 2
    });

    $('#GBcontainer').append(this.prefetchedImgs[nextL]);    

    return gutter;
            
}

// getNextLeafs()
//______________________________________________________________________________
GnuBook.prototype.getNextLeafs = function(o) {
    //TODO: we might have two left or two right leafs in a row (damaged book)
    //For now, assume that leafs are contiguous.
    
    //return [this.currentLeafL+2, this.currentLeafL+3];
    o.L = this.currentLeafL+2;
    o.R = this.currentLeafL+3;
}

// getprevLeafs()
//______________________________________________________________________________
GnuBook.prototype.getPrevLeafs = function(o) {
    //TODO: we might have two left or two right leafs in a row (damaged book)
    //For now, assume that leafs are contiguous.
    
    //return [this.currentLeafL-2, this.currentLeafL-1];
    o.L = this.currentLeafL-2;
    o.R = this.currentLeafL-1;
}

// pruneUnusedImgs()
//______________________________________________________________________________
GnuBook.prototype.pruneUnusedImgs = function() {
    //console.log('current: ' + this.currentLeafL + ' ' + this.currentLeafR);
    for (var key in this.prefetchedImgs) {
        //console.log('key is ' + key);
        if ((key != this.currentLeafL) && (key != this.currentLeafR)) {
            //console.log('removing key '+ key);
            $(this.prefetchedImgs[key]).remove();
        }
        if ((key < this.currentLeafL-4) || (key > this.currentLeafR+4)) {
            //console.log('deleting key '+ key);
            delete this.prefetchedImgs[key];
        }
    }
}

// prefetch()
//______________________________________________________________________________
GnuBook.prototype.prefetch = function() {
    var lim = this.currentLeafL-4;
    var i;
    lim = Math.max(lim, 0);
    for (i = lim; i < this.currentLeafL; i++) {
        this.prefetchImg(i);
    }
    
    if (this.numLeafs > (this.currentLeafR+1)) {
        lim = Math.min(this.currentLeafR+4, this.numLeafs-1);
        for (i=this.currentLeafR+1; i<=lim; i++) {
            this.prefetchImg(i);
        }
    }
}

// getPageWidth2UP()
//______________________________________________________________________________
GnuBook.prototype.getPageWidth2UP = function(index) {
    var height  = this.getPageHeight(index); 
    var width   = this.getPageWidth(index);    
    return Math.floor(this.twoPageH*width/height);
}    

// search()
//______________________________________________________________________________
GnuBook.prototype.search = function(term) {
    $('#GnuBookSearchScript').remove();
 	var script  = document.createElement("script");
 	script.setAttribute('id', 'GnuBookSearchScript');
	script.setAttribute("type", "text/javascript");
	script.setAttribute("src", 'http://'+this.server+'/GnuBook/flipbook_search_gb.php?url='+escape(this.bookPath+'/'+this.bookId+'_djvu.xml')+'&term='+term+'&format=XML&callback=gb.GBSearchCallback');
	document.getElementsByTagName('head')[0].appendChild(script);
}

// GBSearchCallback()
//______________________________________________________________________________
GnuBook.prototype.GBSearchCallback = function(txt) {
    //alert(txt);
    if (jQuery.browser.msie) {
        var dom=new ActiveXObject("Microsoft.XMLDOM");
        dom.async="false";
        dom.loadXML(txt);    
    } else {
        var parser = new DOMParser();
        var dom = parser.parseFromString(txt, "text/xml");    
    }
    
    $('#GnuBookSearchResults').empty();    
    $('#GnuBookSearchResults').append('<ul>');
    
    for (var key in this.searchResults) {
        if (null != this.searchResults[key].div) {
            $(this.searchResults[key].div).remove();
        }
        delete this.searchResults[key];
    }
    
    var pages = dom.getElementsByTagName('PAGE');
    for (var i = 0; i < pages.length; i++){
        //console.log(pages[i].getAttribute('file').substr(1) +'-'+ parseInt(pages[i].getAttribute('file').substr(1), 10));

        
        var re = new RegExp (/_(\d{4})/);
        var reMatch = re.exec(pages[i].getAttribute('file'));
        var leafNum = parseInt(reMatch[1], 10);
        //var leafNum = parseInt(pages[i].getAttribute('file').substr(1), 10);
        
        var children = pages[i].childNodes;
        var context = '';
        for (var j=0; j<children.length; j++) {
            //console.log(j + ' - ' + children[j].nodeName);
            //console.log(children[j].firstChild.nodeValue);
            if ('CONTEXT' == children[j].nodeName) {
                context += children[j].firstChild.nodeValue;
            } else if ('WORD' == children[j].nodeName) {
                context += '<b>'+children[j].firstChild.nodeValue+'</b>';
                
                var index = this.leafNumToIndex(leafNum);
                if (null != index) {
                    //coordinates are [left, bottom, right, top, [baseline]]
                    //we'll skip baseline for now...
                    var coords = children[j].getAttribute('coords').split(',',4);
                    if (4 == coords.length) {
                        this.searchResults[index] = {'l':coords[0], 'b':coords[1], 'r':coords[2], 't':coords[3], 'div':null};
                    }
                }
            }
        }
        //TODO: remove hardcoded instance name
        $('#GnuBookSearchResults').append('<li><b><a href="javascript:gb.jumpToIndex('+index+');">Leaf ' + leafNum + '</a></b> - ' + context+'</li>');
    }
    $('#GnuBookSearchResults').append('</ul>');

    this.updateSearchHilites();
}

// updateSearchHilites()
//______________________________________________________________________________
GnuBook.prototype.updateSearchHilites = function() {
    if (2 == this.mode) {
        this.updateSearchHilites2UP();
    } else {
        this.updateSearchHilites1UP();
    }
}

// showSearchHilites1UP()
//______________________________________________________________________________
GnuBook.prototype.updateSearchHilites1UP = function() {

    for (var key in this.searchResults) {
        
        if (-1 != jQuery.inArray(parseInt(key), this.displayedLeafs)) {
            var result = this.searchResults[key];
            if(null == result.div) {
                result.div = document.createElement('div');
                $(result.div).attr('className', 'GnuBookSearchHilite').appendTo('#pagediv'+key);
                //console.log('appending ' + key);
            }    
            $(result.div).css({
                width:  (result.r-result.l)/this.reduce + 'px',
                height: (result.b-result.t)/this.reduce + 'px',
                left:   (result.l)/this.reduce + 'px',
                top:    (result.t)/this.reduce +'px'
            });

        } else {
            //console.log(key + ' not displayed');
            this.searchResults[key].div=null;
        }
    }
}

// showSearchHilites2UP()
//______________________________________________________________________________
GnuBook.prototype.updateSearchHilites2UP = function() {

    var middle = ($('#GBcontainer').width() >> 1);

    for (var key in this.searchResults) {
        key = parseInt(key, 10);
        if (-1 != jQuery.inArray(key, this.displayedLeafs)) {
            var result = this.searchResults[key];
            if(null == result.div) {
                result.div = document.createElement('div');
                $(result.div).attr('className', 'GnuBookSearchHilite').css('zIndex', 3).appendTo('#GBcontainer');
                //console.log('appending ' + key);
            }

            var height = this.getPageHeight(key);
            var width  = this.getPageWidth(key)
            var reduce = this.twoPageH/height;
            var scaledW = parseInt(width*reduce);
            
            var gutter = middle+parseInt((2*this.currentLeafL - this.numLeafs)*this.twoPageEdgeW/this.numLeafs/2);
            
            if ('L' == this.getPageSide(key)) {
                var pageL = gutter-scaledW;
            } else {
                var pageL = gutter;
            }
            var pageT  = ($('#GBcontainer').height() - this.twoPageH) >> 1;                
                        
            $(result.div).css({
                width:  (result.r-result.l)*reduce + 'px',
                height: (result.b-result.t)*reduce + 'px',
                left:   pageL+(result.l)*reduce + 'px',
                top:    pageT+(result.t)*reduce +'px'
            });

        } else {
            //console.log(key + ' not displayed');
            if (null != this.searchResults[key].div) {
                //console.log('removing ' + key);
                $(this.searchResults[key].div).remove();
            }
            this.searchResults[key].div=null;
        }
    }
}

// removeSearchHilites()
//______________________________________________________________________________
GnuBook.prototype.removeSearchHilites = function() {
    for (var key in this.searchResults) {
        if (null != this.searchResults[key].div) {
            $(this.searchResults[key].div).remove();
            this.searchResults[key].div=null;
        }        
    }
}
