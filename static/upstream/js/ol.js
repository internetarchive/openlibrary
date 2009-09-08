
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
