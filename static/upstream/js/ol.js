function twitterOn() {
// SHOW TWITTER NAME INPUT IF PRE-CHECKED
    if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
// SHOW TWITTER NAME INPUT IF CHECKED
    $("input[type=radio]").click(function(){
        if ($(".twitter").is(":checked")) {$("#twitterName").show();} else {$("#twitterName").hide();};
    });
};

function setupSearch() {
  $(".optionsNoScript").hide();
  $(".optionsScript").show();

  // take alternate text from a special attribute instead of hard-coding in js. This required to support i18n.
  var a1 = $("a#searchHead").html();
  var a2 = $("a#searchHead").attr("text2");

  $("a#searchHead").click(function(){
    $(this).toggleClass("attn");
    $("#headerSearch").toggleClass("darker");
    $("#topOptions").toggle();
    $(this).toggleText(a1, a2);
  });

  // take alternate text from a special attribute instead of hard-coding in js. This required to support i18n.
  var b1 = $(".fullText").html();
  var b2 = $(".fullText").attr("text2");

  $(".fullText").click(function(){
    $(this).toggleClass("attn");
    $(this).parent().parent().next(".searchText").slideToggle();
    $(this).toggleText(b1, b2);
  });
  $("a#searchFoot").click(function(){
    $(this).toggleClass("attn");
    $("#footerSearch").toggleClass("darker");
    $("#bottomOptions").toggle();
    $("#bottomText").toggle();
    $(this).toggleText(a1, a2);
  });
}

function setup_account_create() {
  $("#signup").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'Hang on... you missed 1 field. It\'s highlighted below.'
          : 'Hang on... you missed some fields. They\'re highlighted below.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#email").rules("add",{
    required: true,
    email: true,
    messages: {
    	required: "",
    	email: "Are you sure that's an email address?"
    }
  });
  $("#username").rules("add",{
  	required: true,
  	minlength: 3,
  	maxlength: 20,
  	messages: {
  		required: "",
  		minlength: jQuery.format("This has to be at least {0} characters."),
  		maxlength: jQuery.format("Sorry! This can't exceed {0} characters.")
  	}
  });
  $("#password").rules("add",{
  	required: true,
  	messages: {
  		required: ""
  	}
  });
  $("#recaptcha_response_field").rules("add",{
  	required: true,
  	messages: {
  		required: ""
  	}
  });
  $('#password').showPassword("#showpass");
// CHECK USERNAME AVAILABILITY
    $('#usernameLoading').hide();
	$('#emailLoading').hide();
/*
	$('#usernameLoading').hide();
	$('#username').blur(function(){
	  $('#usernameLoading').show();
      $.post("checkuser.php", {
        username: $('#username').val()
      }, function(response){
        $('#usernameResult').customFadeOut();
        setTimeout("finishAjaxUsername('usernameResult', '"+escape(response)+"')", 400);
      });
    	return false;
	}); 
};
 function finishAjaxUsername(id, response) {
  $('#usernameLoading').hide();
  $('#'+id).html(unescape(response));
  $('#'+id).customFadeIn();
} 
//finishAjax

// CHECK EMAIL ASSOCIATION
function validateCheckEmail() {
	$('#emailLoading').hide();
	$('#email').blur(function(){
	  $('#emailLoading').show();
      $.post("checkemail.php", {
        email: $('#email').val()
      }, function(response){
        $('#emailResult').customFadeOut();
        setTimeout("finishAjaxEmail('emailResult', '"+escape(response)+"')", 400);
      });
    	return false;
	});
});

function finishAjaxEmail(id, response) {
  $('#emailLoading').hide();
  $('#'+id).html(unescape(response));
  $('#'+id).customFadeIn();
} 
//finishAjax */
};
//RECAPTCHA
var RecaptchaOptions = {
  theme : 'custom',
  tabindex : 4,
  custom_theme_widget: 'recaptcha_widget'
};


function validateEmail() {
	$("form.email").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'Hang on... You forgot to provide an updated email address.'
          : 'Hang on... You forgot to provide an updated email address.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#email").rules("add",{
    required: true,
    email: true,
    messages: {
    	required: "",
    	email: "Are you sure that's an email address?"
    }
  });
};

function validateDelete() {
	$("form.delete").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'You need to click the box to delete your account.'
          : 'You need to click the box to delete your account.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#delete").rules("add",{
  	required: true,
  	messages: {
  		required: ""
  	}
  });
};

function validateLogin() {
	$(".login").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'Hang on... you missed 1 field. It\'s highlighted below.'
          : 'Hang on... you missed both fields. They\'re highlighted below.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#username").rules("add",{
  	required: true,
  	minlength: 3,
  	maxlength: 20,
  	messages: {
  		required: "",
  		minlength: jQuery.format("This has to be at least {0} characters."),
  		maxlength: jQuery.format("Sorry! This can't exceed {0} characters.")
  	}
  });
  $("#password").rules("add",{
  	required: true,
  	messages: {
  		required: ""
  	}
  });
  $('#password').showPassword("#showpass");
};
function validatePassword() {
	$("form.password").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'Hang on... you missed a field.'
          : 'Hang on... to change your password, we need your current and your new one.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#password").rules("add",{
  	required: true,
  	messages: {
  		required: ""
  	}
  });
  $("#new_password").rules("add",{
  	required: true,
  	messages: {
  		required: ""
  	}
  });
  $('#masker').append('<input type="checkbox" name="showpass" id="showpass"/> <label for="showpass">Unmask passwords?</label>');
  $('.pwmask').showPasswords('#showpass');
};
function validateReminder() {
	$("form.reminder").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'Hang on... to change your password, we need your email address.'
          : 'Hang on... to change your password, we need your email address.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#email").rules("add",{
    required: true,
    email: true,
    messages: {
    	required: "",
    	email: "Are you sure that's an email address?"
    }
  });
};

function validateAddbook1() {
	$("form.addbook1").validate({
    invalidHandler: function(form, validator) {
      var errors = validator.numberOfInvalids();
      if (errors) {
        var message = errors == 1
          ? 'Hang on... You forgot something.'
          : 'Hang on... You forgot a couple of things.';
        $("div#contentMsg span").html(message);
        $("div#contentMsg").show().fadeTo(3000, 1).slideUp();
        $("span.remind").css("font-weight","700").css("text-decoration","underline");
      } else {
        $("div#contentMsg").hide();
      }
    },
    errorClass: "invalid",
    validClass: "success",
    highlight: function(element, errorClass) {
     $(element).addClass(errorClass);
     $(element.form).find("label[for=" + element.id + "]")
                    .addClass(errorClass);
    }
  });
  $("#title").rules("add",{
    required: true,
    messages: {
    	required: ""
    }
  });
  $("#author").rules("add",{
    required: true,
    messages: {
    	required: ""
    }
  });
// CHECK USERNAME AVAILABILITY
    $('#authorLoading').hide();
    $('#authorResult').hide();
	$('#publisherLoading').hide();
	$('#publisherResult').hide();
/*
	$('#authorLoading').hide();
	$('#author').blur(function(){
	  $('#authorLoading').show();
      $.post("checkauthor.php", {
        username: $('#author').val()
      }, function(response){
        $('#authorResult').fadeOut();
        setTimeout("finishAjaxUsername('authorResult', '"+escape(response)+"')", 400);
      });
    	return false;
	}); 
};
 function finishAjaxUsername(id, response) {
  $('#authorLoading').hide();
  $('#'+id).html(unescape(response));
  $('#'+id).fadeIn();
} 
//finishAjax

// CHECK EMAIL ASSOCIATION
function validateCheckPublisher() {
	$('#publisherLoading').hide();
	$('#publisher').blur(function(){
	  $('#publisherLoading').show();
      $.post("checkpublisher.php", {
        email: $('#publisher').val()
      }, function(response){
        $('#publisherResult').fadeOut();
        setTimeout("finishAjaxEmail('publisherResult', '"+escape(response)+"')", 400);
      });
    	return false;
	});
});

function finishAjaxEmail(id, response) {
  $('#emailLoading').hide();
  $('#'+id).html(unescape(response));
  $('#'+id).fadeIn();
} 
//finishAjax */
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


function textareaExpand() {
 $('textarea.resize').autoResize({
    onResize : function() {
        $(this).css({opacity:0.8});
    },
    animateCallback : function() {
        $(this).css({opacity:1});
    },
    animateDuration : 300,
    extraSpace : 40
  });
};

// HISTORY REVEAL
function tableShow() {
    $('a.showmore').click(function(){
        $(this).parent().parent().parent().find('tr.reveal').hide();
        $(this).parent().parent().parent().find('tr.hidden').customFadeIn();
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
    $.fn.fixBroken=function(){return this.each(function(){$(this).error(function(){$(this).parent().parent().hide();$(this).parent().parent().next(".SRPCoverBlank").show();});});};
    $('img.cover').fixBroken();  
};
// SLIDING PANELS 
function slidePanels(){
    $("#Tools .panel").hide();
    $("#Tools h3.header").click(function(){
        $("#Tools .panel").slideUp();
        if ($(this).parent().find(".panel").is(":hidden")) {
            $(this).parent().find(".panel").slideDown();
        } else {
            $(this).parent().find(".panel").slideUp();
        }
    });
}

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
}