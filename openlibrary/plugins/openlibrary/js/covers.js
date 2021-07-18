/**
 * Functionality for templates/covers
 */
import 'jquery-ui/ui/widgets/sortable';

//cover/change.html
export function initCoversChange() {
    // Pull data from data-config of class "manageCovers" in covers/manage.html
    const data_config_json = $('.manageCovers').data('config');
    const doc_type_key = data_config_json['key'];
    const add_url = data_config_json['add_url'];
    const manage_url = data_config_json['manage_url'];

    // Add iframes lazily when the popup is loaded.
    // This avoids fetching the iframes along with main page.
    $('.coverPop')
        .on('click', function () {
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
        .on('cbox_cleanup', function () {
            $('#imagesAdd').html('');
            $('#imagesManage').html('');
        });
}

function val(selector) {
    return $(selector).val().trim();
}

function error(message, event) {
    $('#errors').show().html(message);
    event.preventDefault();
}

function add_iframe(selector, src) {
    $(selector)
        .append('<iframe frameborder="0" height="450" width="580" marginheight="0" marginwidth="0" scrolling="auto"></iframe>')
        .find('iframe')
        .attr('src', src);
}

// covers/manage.html and covers/add.html
export function initCoversAddManage() {
    $('#addcover-form').on('submit', function (event) {
        var file = val('#coverFile');
        var url = val('#imageUrl');
        var coverid = val('#coverid');

        if (file === '' && (url === '' || url === 'http://') && coverid === '') {
            return error('Please choose an image or provide a URL.', event);
        }

        function test_url(url) {
            var obj = {
                optional: function () { return false; }
            }
            return window.$.validator.url.apply(obj, [url, null]);
        }

        if (url !== '' && url !== 'http://' && !test_url(url)) {
            return error('Please provide a valid URL.');
        }
    });

    // Clicking a cover should set the form value to the data-id of that cover
    $('#popcovers .book').on('click', function () {
        var coverid;
        $(this).toggleClass('selected').siblings().removeClass('selected');
        coverid = '';
        if ($(this).hasClass('selected')) {
            coverid = $(this).data('id');
        }
        $('#coverid').val(coverid);
    });

    $('.column').sortable({
        connectWith: '.trash'
    });
    $('.trash').sortable({
        connectWith: '.column'
    });
    $('.column').disableSelection();
    $('.trash').disableSelection();
}

// covers/saved.html
// Uses parent.$ in place of $ where elements lie outside of the "saved" window
export function initCoversSaved() {
    // Save the new image
    // Pull data from data-config of class "imageSaved" in covers/saved.html
    const data_config_json = parent.$('.manageCovers').data('config');
    const doc_type_key = data_config_json['key'];
    const coverstore_url = data_config_json['url'];
    const cover_selector = data_config_json['selector'];
    const image = $('.imageSaved').data('imageId');
    var cover_url;

    $('.formButtons button').on('click', parent.closePopup);

    // Update the image for the cover
    if (['/type/edition', '/type/work', '/edit'].includes(doc_type_key)) {
        if (image) {
            cover_url = `${coverstore_url}/b/id/${image}-M.jpg`;
            // XXX-Anand: Fix this hack
            // set url and  show SRPCover  and hide SRPCoverBlank
            parent.$(cover_selector).attr('src', cover_url)
                .parents('div:first').show()
                .next().hide();
            parent.$(cover_selector).attr('srcset', cover_url)
                .parents('div:first').show()
                .next().hide();
        }
        else {
            // hide SRPCover and show SRPCoverBlank
            parent.$(cover_selector)
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
        parent.$(cover_selector).attr('src', cover_url);
    }
}
