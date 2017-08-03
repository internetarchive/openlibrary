var Browser = {
    getUrlParameter: function(key) {
        var query = window.location.search.substring(1);
        var params = query.split("&");
        if (key) {
            for (var i=0;i<params.length;i++) {
                var item = params[i].split("=");
                var val = item[1];
                if(item[0] == key){return(decodeURIComponent(val));}
            }
            return(undefined);
        }
        return(items);
    },
    getJsonFromUrl: function () {
        var query = location.search.substr(1);
        var result = {};
        query.split("&").forEach(function(part) {
            var item = part.split("=");
            result[item[0]] = decodeURIComponent(item[1]);
        });
        return result;
    },

    change_url: function(query) {
        var getUrl = window.location;
        var baseUrl = getUrl .protocol + "//" + getUrl.host +
            "/" + getUrl.pathname.split('/')[1];
        window.history.pushState({
            "html": document.html,
            "pageTitle": document.title + " " + query,
        }, "", baseUrl + "?id=" + query);
    }
}



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
    var t2 = "Hide Advanced";
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
    var t4 = "Hide Advanced";
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

var create_subject_carousel;
$().ready(function() {
  create_subject_carousel = function(subject_name, type, options) {
    var ITEMS_PER_PAGE = 6;
    var apiurl = '/' + type + '/' + subject_name + '.json?has_fulltext=true';
    options = options || {};
    options.pagesize = ITEMS_PER_PAGE;
    options.readable = true;
    options.sort = options.sort || "";
    if (options.published_id) {
        url += '&published_in=' + options.published_in;
    }
    $.ajax({
        dataType: "json",
        url: apiurl,
        type: "GET",
        contentType: "text/html",
        beforeSend: function(xhr) {
            xhr.setRequestHeader("Content-Type", "application/json");
            xhr.setRequestHeader("Accept", "application/json");
        },
        success: function(data) {
            // TODO: Filter `data` by available
            var primed = false;
            var subject = new Subject(data, options);
            function fetchPageOfBooks(carousel) {
                primed = true;
                if (!subject.coverCarousel) {
                    subject.coverCarousel = carousel;
                    subject.coverCarousel.size(subject.getPageCount());
                }
                var index = carousel.first;
                subject.pos = (index - 1) * ITEMS_PER_PAGE;

                if (window.set_hash) {
                    var _p = (index == 1) ? null : index;
                    set_hash({"page": _p});
                }

                if (carousel.has(index)) {
                    return;
                }

                subject.loadPage(index-1, function(data) {
                    var works = data.works;
                    $.each(works, function(widx, work) {
                        carousel.add(index + widx, subject.renderWork(work));
                    });
                    updateBookAvailability("#carousel-" + subject_name + " li ");
                });
            }
            $("#carousel-" + subject_name).jcarousel({
                scroll: ITEMS_PER_PAGE,
                itemLoadCallback: {onBeforeAnimation: fetchPageOfBooks}
            });
            if (!primed) {
                $("#carousel-" + subject_name).data('jcarousel').reload();
            }
        }
    });
  };
});

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
        $t(his).closest(".SRPCover").hide();
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
    var cover_url = function(id) {
        return '//covers.openlibrary.org/b/id/' + id + '-S.jpg'
    };

    var capitalize = function(word) {
        return word.charAt(0).toUpperCase() + word.slice(1);
    }

    // Maps search facet label with value
    var defaultFacet = "title";
    var searchFacets = {
        'title': 'books',
        'author': 'authors',
        'subject': 'subjects',
        'advanced': 'advancedsearch'
    };

    var composeSearchUrl = function(q, json, limit) {
        var facet_value = searchFacets[localStorage.getItem("facet")];
        var url = ((facet_value === 'books')? '/search' : "/search/" + facet_value);
        if (json) {
            url += '.json';
        }
        url += '?q=' + q;
        if (limit) {
            url += '&limit=' + limit;
        }
        return url + '&has_fulltext=true';
    }

    var marshalBookSearchQuery = function(q) {
        if (q.indexOf(':') == -1 && q.indexOf('"') == -1) {
           q = 'title: "' + q + '"';
        }
        return q;
    }

    var renderSearchResults = function(q) {
        var facet_value = searchFacets[localStorage.getItem("facet")];
        if (q === '') {
            return;
        }
        if (facet_value === 'books') {
            q = marshalBookSearchQuery(q);
        }

        var url = composeSearchUrl(q, true, 10);

        $('header .search-component ul.search-results').empty()
        $.getJSON(url, function(data) {
            for (var d in data.docs) {
                renderSearchResult[facet_value](data.docs[d]);
            }
        });
    }

    var setFacet = function(facet) {
        var facet_key = facet.toLowerCase();

        if (facet_key === 'advanced') {
            localStorage.setItem("facet", '');
            window.location.assign('/advancedsearch')
            return;
        }

        localStorage.setItem("facet", facet_key);
        $('header .search-facet-selector select').val(capitalize(facet_key))
        $('header .search-facet-value').html(capitalize(facet_key));
        $('header .search-component ul.search-results').empty()
        q = $('header .search-component .search-bar-input input').val();
        var url = composeSearchUrl(q)
        $('.search-bar-input').attr("action", url);
        renderSearchResults(q);
    }
    var options = Browser.getJsonFromUrl();
    if (!searchFacets[localStorage.getItem("facet")]) {
	localStorage.setItem("facet", defaultFacet)
    }
    setFacet(options.facet || localStorage.getItem("facet") || defaultFacet);

    if (options.q) {
        var q = options.q.replace(/\+/g, " ")
        if (q.indexOf('title:') != -1) {
            var parts = q.split('"');
            if (parts.length === 3) {
                q = parts[1];
            }
        }
        $('.search-bar-input [type=text]').val(q);
    }

    var debounce = function (func, threshold, execAsap) {
        var timeout;
        return function debounced () {
            var obj = this, args = arguments;
            function delayed () {
                if (!execAsap)
                    func.apply(obj, args);
                timeout = null;
            };

            if (timeout) {
                clearTimeout(timeout);
            } else if (execAsap) {
                func.apply(obj, args);
            }
            timeout = setTimeout(delayed, threshold || 100);
        };
    };

    $('.trigger').live('submit', function(e) {
        e.preventDefault(e);
        toggleSearchbar();
        $('.search-bar-input [type=text]').focus();
    });

    var enteredSearchMinimized = false;
    var searchExpansionActivated = false;
    if ($(window).width() < 568) {
        if (!enteredSearchMinimized) {
            $('.search-bar-input').addClass('trigger')
        }
        enteredSearchMinimized = true;
    }
    $(window).resize(function(){
        if($(this).width() < 568){
            if (!enteredSearchMinimized) {
                $('.search-bar-input').addClass('trigger')
                $('header .search-component ul.search-results').empty()
            }
            enteredSearchMinimized = true;
        } else {
            if (enteredSearchMinimized) {
                $('.search-bar-input').removeClass('trigger');
                var search_query = $('header .search-component .search-bar-input input').val()
                if (search_query) {
                    renderSearchResults(search_query);
                }
            }
            enteredSearchMinimized = false;
            searchExpansionActivated = false;
            $('header .logo-component').removeClass('hidden');
            $('header .search-component').removeClass('search-component-expand');
        }
    });

    var toggleSearchbar = function() {
        searchExpansionActivated = !searchExpansionActivated;
        if (searchExpansionActivated) {
            $('header .logo-component').addClass('hidden');
            $('header .search-component').addClass('search-component-expand');
            $('.search-bar-input').removeClass('trigger')
        } else {
            $('header .logo-component').removeClass('hidden');
            $('header .search-component').removeClass('search-component-expand');
            $('.search-bar-input').addClass('trigger')
        }
    }

    $('header .search-facet-selector select').change(function(e) {
        var facet = $('header .search-facet-selector select').val();
        if (facet.toLowerCase() === 'advanced') {
            e.preventDefault(e);
        }
        setFacet(facet);
    })

    var renderSearchResult = {
        books: function(work) {
            var author_name = work.author_name ? work.author_name[0] : '';
            $('header .search-component ul.search-results').append(
                '<li><a href="' + work.key + '"><img src="' + cover_url(work.cover_i) +
                    '"/><span class="book-desc"><div class="book-title">' +
                    work.title + '</div>by <span class="book-author">' +
                    author_name + '</span></span></a></li>'
            );
        },
        authors: function(author) {
	    // Todo: default author img to: https://dev.openlibrary.org/images/icons/avatar_author-lg.png
            $('header .search-component ul.search-results').append(
                '<li><a href="/authors/' + author.key + '"><img src="' + ("http://covers.openlibrary.org/a/olid/" + author.key + "-S.jpg") + '"/><span class="author-desc"><div class="author-name">' +
                    author.name + '</div></span></a></li>'
            );
        }
    }

    $('form.search-bar-input').submit(function(e) {
        q = $('header .search-component .search-bar-input input').val();
        var facet_value = searchFacets[localStorage.getItem("facet")];
        if (facet_value === 'books') {
            $('header .search-component .search-bar-input input[type=text]').val(marshalBookSearchQuery(q));
        }
    });

    $('header .search-component .search-results li a').live('click', debounce(function(event) {
        $(document.body).css({'cursor' : 'wait'});
    }, 300, false));

    $('header .search-component .search-bar-input input').keyup(debounce(function(e) {
        // ignore directional keys and enter for callback
        if (![13,37,38,39,40].includes(e.keyCode)){
            renderSearchResults($(this).val());
        }
    }, 500, false));

    $(document).click(debounce(function(event) {
        if(!$(event.target).closest('header .search-component').length) {
            $('header .search-component ul.search-results').empty();
        }
        if(!$(event.target).closest('header .navigation-component .browse-menu').length) {
            $('header .navigation-component .browse-menu .browse-menu-options').hide();
        }
        if(!$(event.target).closest('header .navigation-component .my-books-menu').length) {
            $('header .navigation-component .my-books-menu .my-books-menu-options').hide();
        }
        if(!$(event.target).closest('header .navigation-component .more-menu').length) {
            $('header .navigation-component .more-menu .more-menu-options').hide();
        }
        if(!$(event.target).closest('header .hamburger-component .hamburger-button').length) {
            $('header .hamburger-dropdown-component').hide();
        }
        if(!$(event.target).closest('.dropclick').length) {
            $('.dropclick').next('.dropdown').slideUp();
            $('.dropclick').parent().find('.arrow').removeClass("up");
        }
    }, 300, false));

    $('header .search-component .search-bar-input input').focus(debounce(function() {
        var val = $(this).val();
        renderSearchResults(val);
    }, 300, false));

    /* Browse menu */
    $('header .navigation-component .browse-menu').click(debounce(function() {
        $('header .navigation-component .browse-menu-options').toggle();
    }, 300, false));

    /* My Books menu */
    $('header .navigation-component .my-books-menu').click(debounce(function() {
        $('header .navigation-component .my-books-menu-options').toggle();
    }, 300, false));

    /* More menu */
    $('header .navigation-component .more-menu').click(debounce(function() {
        $('header .navigation-component .more-menu-options').toggle();
    }, 300, false));

    /* Hamburger menu */
    $('header .hamburger-component .hamburger-button').live('click', debounce(function() {
        $('header .hamburger-dropdown-component').toggle();
    }, 300, false));

    $('textarea.markdown').focus(function(){
        $('.wmd-preview').show();
        if ($("#prevHead").length == 0) {
            $('.wmd-preview').before('<h3 id="prevHead" style="margin:15px 0 10px;padding:0;">Preview</h3>');
        }
    });
    $('.dropclick').click(debounce(function(){
        $(this).next('.dropdown').slideToggle();
        $(this).parent().find('.arrow').toggleClass("up");
    }, 300, false));

    function hideUser(){
        $('#main-account-dropdown').slideUp(25);
        $('header .dropdown-avatar').removeClass('hover');
    };

    $('header .dropdown-avatar').click(debounce(function() {
        var dropdown = $('#main-account-dropdown');
        if (dropdown.is(':visible') === true) {
            hideUser();
        } else {
            dropdown.slideToggle(25);
            $(this).toggleClass('hover');
            var offUser = $(this);
            $(document).mouseup(function(offUser){
                if($(offUser.target).parent("a").length==0){
                    hideUser()
                };
            });

        }
    }, 300, false));
});
jQuery.fn.exists = function(){return jQuery(this).length>0;}
