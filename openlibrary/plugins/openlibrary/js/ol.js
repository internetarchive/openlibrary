function linkbuttons() {
    $(".linkButton").click(function(){
        window.location = $(this).attr("name");
    });
};
function twitterOn() {
    if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
    $("input[type=radio]").click(function(){
        if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
    });
};
function isScrolledIntoView(elem) {
    var docViewTop = $(window).scrollTop();
    var docViewBottom = docViewTop + $(window).height();
    var elemTop = $(elem).offset().top;
    var elemBottom = elemTop + $(elem).height();
    return ((docViewTop < elemTop) && (docViewBottom > elemBottom));
}
$(window).scroll(function(){
  var scroller = $("#formScroll");
  if(isScrolledIntoView(scroller)){$("#scrollBtm").show();}else{$("#scrollBtm").hide();};
})
function setupSearch() {
  $(".optionsNoScript").hide();
  $(".optionsScript").show();

    var A = $("#topOptions");
    var B = A.parent().parent();
    var C = B.find("a#searchHead");
    var t1 = C.text();
    var t2 = "Hide options";
    C.click(function(){
        var D = $(this);
        $('#footerSearch').toggle();
        A.toggle();
        B.toggleClass("darker");
        D.toggleClass("attn");
        D.toggleText(t1, t2);
        B.mouseup(function(){
            return false
        });
        $(document).mouseup(function(D){
            if($(D.target).parent("a").length==0){
                hideSearch()
            };
        });
        function hideSearch(){
            A.hide();
            B.removeClass("darker");
            C.removeClass("attn");
            C.text(t1);
        };
    });
    var E = $("#bottomOptions");
    var F = E.parent().parent();
    var G = F.find("a#searchFoot");
    var t3 = G.text();
    var t4 = "Hide options";
    G.click(function(){
        var H = $(this);
        E.toggle();
        if($("#bottomOptions").is(":visible")){if($("#scrollBtm").is(":hidden")){$.scrollTo($("#formScroll"),800);};};
        F.toggleClass("darker");
        H.toggleClass("attn");
        $("#footerSearch").toggleClass("onTop");
        H.toggleText(t3, t4);
        $("#btmSrchLabel").toggle();
        F.mouseup(function(){
            return false
        });
        $(document).mouseup(function(H){
            if($(H.target).parent("a").length==0){
                hideSearch()
            };
        });
        function hideSearch(){
            E.hide();
            F.removeClass("darker");
            G.removeClass("attn");
            G.text(t3);
        };    
    });

};

function flickrBuild(){$(".flickrs").flickr({callback:colorboxCallback});};
function colorboxCallback(){$('a.flickrpic').colorbox({photo:true,preloading:true,opacity:'0.70'});};

function aboutFeeds() {
    jQuery.getFeed({
        url: 'http://www.archive.org/services/collection-rss.php?mediatype=texts',
        success: function(feed) {
        
            jQuery('#resultScanned').append('<h4>New Scanned Books</h4>');
            var html = '';
            for(var i = 0; i < feed.items.length && i < 4; i++) {
                var item = feed.items[i];
                html += '<div class="item"><div class="cover">'+item.description+'</div><div class="title"><a href="'+item.link+'"><strong>'+item.title+'</strong></a></div><div class="updated">'+item.updated+'</div></div>';
            }
            jQuery('#resultScanned').append(html);
            jQuery('#resultScanned').append('<div class="title"><a href="'+feed.link+'">See all</a></div>');
        }    
    });
    jQuery.getFeed({
        url: 'http://blog.openlibrary.org/feed/',
        success: function(feed) {
        
            jQuery('#resultBlog').append('<h4>From The Blog</h4>');
            var html = '';
            for(var i = 0; i < feed.items.length && i < 2; i++) {
                var item = feed.items[i];
                html += '<div class="item"><div class="title"><a href="'+item.link+'">'+item.title+'</a></div><div class="byline">By '+item.author+', '+item.updated+'</div><div class="content">'+item.description+'</div></div>';
            }
            jQuery('#resultBlog').append(html);
            jQuery('#resultBlog').append('<div class="content"><a href="'+feed.link+'">Visit the blog...</a></div>');
        }    
    });
};


// BUILD CAROUSEL 
function carouselSetup(loadCovers, loadLists) {
  $('#coversCarousel').jcarousel({
    visible: 1,
    scroll: 1,
    itemLoadCallback: loadCovers
  });
// SET-UP COVERS LIST
  $('#listCarousel').jcarousel({
    vertical: true,
    visible: 6,
    scroll: 6,
    itemLoadCallback: loadLists
  });
// SWITCH RESULTS VIEW
  $("#resultsList").hide()
  $("a#booksList").click(function(){
    //page.listCarousel.scroll(1+page.pos);
    
    $('span.tools a').toggleClass('on');
    $('#resultsList').customFadeIn();
    $('#resultsCovers').hide();
  });
  $("a#booksCovers").click(function(){
    //page.coverCarousel.scroll(1+page.pos/12);
    
    $('span.tools a').toggleClass('on');
    $('#resultsList').hide();
    $('#resultsCovers').customFadeIn();
  });
// SWITCH EDITIONS VIEW
  $("#editionsList").hide()
  $("a#edsList").click(function(){
    $('span.tools a').toggleClass('on');
    $('#editionsList').customFadeIn();
    $('#editionsCovers').hide();
  });
  $("a#edsCovers").click(function(){
    $('span.tools a').toggleClass('on');
    $('#editionsList').hide();
    $('#editionsCovers').customFadeIn();
  });
};
// BOOK COVERS
function bookCovers(){
    $("img.cover").error(function(){
        $(this).closest(".SRPCover").hide();
        $(this).closest(".coverMagic").find(".SRPCoverBlank").show();
    });
};
// CLOSE POP-UP FROM IFRAME 
function closePop(){
    $("#popClose").click(function(){
        parent.$.fn.colorbox.close();
    });
};
function get_subject_covers(key, pagenumber) {
    // will implement it later.
    var covers = [];
    for (var i=0; i<20; i++)
        covers[i] = pagenumber * 20 + i;
    return covers;
}

function get_work_covers(key, pagenumber) {
    // will implement it later.
    var covers = [];
    for (var i=0; i<20; i++)
        covers[i] = pagenumber * 20 + i;
    return covers;
}

function Place(key) {
    this.key = key;
    this.covers = {};
    this.bookCount = 0;
}

/**
 * Gets the covers using AJAX call and calls the callback with covers as argument. 
 * AJAX call is avoided if the cover data is already present. 
 */
Place.prototype.getCovers = function(pagenum, callback) {
    var offset = pagenum * 12;
    var limit = 12;
    
    if (offset > this.bookCount)
        return [];
    
    if (this.covers[pagenum]) {
        callback(this.covers[pagenum]);
    }
    else {
        var page = this;
        $.getJSON(this.key + "/covers.json?limit=12&offset=" + offset, function(data) {
            page.covers[pagenum] = data;
            callback(data);
        });
    }
};
/*
function deleteVerify() {
    $('#dialog').dialog({
        autoOpen: false,
        width: 400,
        modal: true,
        resizable: false,
        buttons: {
            "Yes, I'm sure": function() {
                $("#_delete").click();
            },
            "No, cancel": function() {
                $(this).dialog("close");
            }
        }
    });
    $('#delete').click(function(){
        $('#dialog').dialog('open');
        return false;
    });
};
*/
function passwordHide(){
;(function($){
    $.fn.revealPassword=function(ph,options){
        var spinput=$(this);
        $.fn.revealPassword.checker=function(cbid,inid){
            $('input[id="'+cbid+'"]').click(function(){
                if($(this).attr('checked')){
                    $('input.'+inid).val(spinput.val()).attr('id',spinput.attr('id')).attr('name',spinput.attr('name'));
                    $('input.'+inid).css('display','inline');
                    spinput.css('display','none').removeAttr('id').removeAttr('name');
                } else {
                    spinput.val($('input.'+inid).val()).attr('id',$('input.'+inid).attr('id')).attr('name',$('input.'+inid).attr('name'));
                    spinput.css('display','inline');
                    $('input.'+inid).css('display','none').removeAttr('id').removeAttr('name');
                }
            });
        }
        return this.each(function(){
            var def={classname:'class',name:'password-input',text:'Unmask password?'};
            var spcbid='spcb';
            var spinid=spcbid.replace('spcb','spin');
            var spclass=spinid;
            if(typeof ph=='object'){
                $.extend(def,ph);
            }
            if(typeof options=='object'){
                $.extend(def,options);
            }
            var spname=def.name;
            if(def.classname==''){
                theclass='';
            } else {
                theclass=' class="'+def.clasname+'"';
            }
            $(this).before('<input type="text" value="" class="'+spclass+'" style="display: none;" />');
            var thecheckbox='<input type="checkbox" id="'+spcbid+'" name="'+spname+'" value="sp" /> <label for="'+spcbid+'">'+def.text+'</label>';
            if(ph=='object'||typeof ph=='undefined'){
                $(this).after(thecheckbox);
            } else {
                $(ph).html(thecheckbox);
            }
            $.fn.revealPassword.checker(spcbid,spinid);
            return this;
        });
    }
})(jQuery);
};
$().ready(function(){
    $('textarea.markdown').focus(function(){
        $('.wmd-preview').show();
        if ($("#prevHead").length == 0) {
            $('.wmd-preview').before('<h3 id="prevHead" style="margin:15px 0 10px;padding:0;">Preview</h3>');
        }
    });
    $('.dropclick').click(function(){
        $(this).next('.dropdown').slideToggle();
        $(this).parent().find('.arrow').toggleClass("up");
    });
    var dropwidth = $('#userToggle').outerWidth();
    $('#headerUserOpen').width(dropwidth);
    $('#userToggle').click(function(){
        $(this).toggleClass('hover');
        $('#headerUserOpen').fadeToggle();
        var offUser = $(this);
        $(document).mouseup(function(offUser){
            if($(offUser.target).parent("a").length==0){
                hideUser()
            };
        });
        function hideUser(){
            $('#headerUserOpen').fadeOut();
            $('#userToggle').removeClass('hover');
        };  
    });
});
jQuery.fn.exists = function(){return jQuery(this).length>0;}