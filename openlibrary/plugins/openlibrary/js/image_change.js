export function initChangeImageImport() {

    // Pull data from data-config of class "manageCovers" in covers/manage.html
    var data_array = $('.manageCovers').attr('data-config').split(',');
    var doc_type_key = data_array[0];
    var add_url = data_array[3];
    var manage_url = data_array[4];

    function add_iframe(selector, src) {
        $(selector)
            .append('<iframe frameborder="0" height="450" width="580" marginheight="0" marginwidth="0" scrolling="auto"></iframe>')
            .find('iframe')
            .attr("src", src);
    }

    // Add iframes lazily when the popup is loaded.
    // This avoids fetching the iframes along with main page.
    $('.coverPop')
       .bind("click", function () {
           // clear the content of #imagesAdd and #imagesManage before adding new
            $("#imagesAdd").html("");
            $("#imagesManage").html("");
            if (doc_type_key === "/type/work") {
               $('#imagesAdd').prepend('<div class="throbber"><h3>$_("Searching for covers")</h3></div>');
            }
            setTimeout(function () {
               // add iframe to add images
               add_iframe("#imagesAdd", add_url);
               // add iframe to manage images
               add_iframe("#imagesManage", manage_url);
            }, 0);
       })
        .bind("cbox_cleanup", function () {
            $("#imagesAdd").html("");
            $("#imagesManage").html("");
        });

    // Add function to close throbber
    closeThrobber = function () { $(".throbber").customFadeOut(); };
}

export function updateImage(image) {
    // Pull data from data-config of class "manageCovers" in covers/manage.html
    var data_array = $('.manageCovers').attr('data-config').split(',');
    var coverstore_url = data_array[1];
    var cover_selector = data_array[2];

    var url;

    if (["/type/edition", "/type/work", "/edit"].includes(doc_type_key)) {
        if (image) {
            url = `${coverstore_url}/b/id/` + image + "-M.jpg";
            // XXX-Anand: Fix this hack
            // set url and show SRPCover  and hide SRPCoverBlank
            $(cover_selector).attr('src', url)
                .parents("div:first").show()
                .next().hide();
            $(cover_selector).attr('srcset', url)
                .parents("div:first").show()
                .next().hide();
        }
        else {
            // hide SRPCover and show SRPCoverBlank
            $(cover_selector)
                .parents("div:first").hide()
                .next().show();
        }
    }
    else {
        if (image) {
            url = `${coverstore_url}/a/id/` + image + "-M.jpg";
        }
        else {
            url = "/images/icons/avatar_author-lg.png";
        }
        $(cover_selector).attr('src', url);
    }
}

