/**
 * Functionality for covers/change.html and covers/saved.html
 */
export function initCoversChange() {
    // Pull data from data-config of class "manageCovers" in covers/manage.html
    const data_config_json = JSON.parse($('.manageCovers').attr('data-config'));
    const doc_type_key = data_config_json['key'];
    const coverstore_url = data_config_json['url'];
    const cover_selector = data_config_json['selector'];
    const add_url = data_config_json['add_url'];
    const manage_url = data_config_json['manage_url'];
    var cover_url;

    // Add iframes lazily when the popup is loaded.
    // This avoids fetching the iframes along with main page.
    $('.coverPop')
        .bind('click', function () {
            // clear the content of #imagesAdd and #imagesManage before adding new
            $('#imagesAdd').html('');
            $('#imagesManage').html('');
            if (doc_type_key === '/type/work') {
                $('#imagesAdd').prepend('<div class="throbber"><h3>$_("Searching for covers")</h3></div>');
            }
            setTimeout(function () {
                // add iframe to add images
                add_iframe('#imagesAdd', add_url);
                // add iframe to manage images
                add_iframe('#imagesManage', manage_url);
            }, 0);
        })
        .bind('cbox_cleanup', function () {
            $('#imagesAdd').html('');
            $('#imagesManage').html('');
        });

    // Save the new image
    if (document.getElementsByClassName('imageSaved').length) {
        // Pull data from data-config of class "imageSaved" in covers/saved.html
        const image = $('.imageSaved').attr('data-image-id');
        $('#popClose').click(window.closePopup);

        // Update the image for the cover
        if (['/type/edition', '/type/work', '/edit'].includes(doc_type_key)) {
            if (image) {
                cover_url = `${coverstore_url}/b/id/${image}-M.jpg`;
                // XXX-Anand: Fix this hack
                // set url and show SRPCover  and hide SRPCoverBlank
                $(cover_selector).attr('src', cover_url)
                    .parents('div:first').show()
                    .next().hide();
                $(cover_selector).attr('srcset', cover_url)
                    .parents('div:first').show()
                    .next().hide();
            }
            else {
                // hide SRPCover and show SRPCoverBlank
                $(cover_selector)
                    .parents('div:first').hide()
                    .next().show();
            }
        }
        else {
            if (image) {
                cover_url = `${coverstore_url}/a/id/${image}-M.jpg`;
            }
            else {
                cover_url = '/images/icons/avatar_author-lg.png';
            }
            $(cover_selector).attr('src', cover_url);
        }
    }
}

function add_iframe(selector, src) {
    $(selector)
        .append('<iframe frameborder="0" height="450" width="580" marginheight="0" marginwidth="0" scrolling="auto"></iframe>')
        .find('iframe')
        .attr('src', src);
}

