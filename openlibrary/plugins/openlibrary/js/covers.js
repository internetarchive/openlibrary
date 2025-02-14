/**
 * Functionality for templates/covers
 */
import 'jquery-ui/ui/disable-selection';
import 'jquery-ui/ui/widgets/sortable';
import 'jquery-ui-touch-punch'; // this makes drag-to-reorder work on touch devices

import { closePopup } from './utils';

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
            $('.imagesAdd').html('');
            $('.imagesManage').html('');
            if (doc_type_key === '/type/work') {
                $('.imagesAdd').prepend('<div class="throbber"><h3>$_("Searching for covers")</h3></div>');
            }
            setTimeout(function () {
                // add iframe to add images
                add_iframe('.imagesAdd', add_url);
                // add iframe to manage images
                add_iframe('.imagesManage', manage_url);
            }, 0);
        })
        .on('cbox_cleanup', function () {
            $('.imagesAdd').html('');
            $('.imagesManage').html('');
        });
}

function add_iframe(selector, src) {
    $(selector)
        .append('<iframe frameborder="0" height="580" width="580" marginheight="0" marginwidth="0" scrolling="auto"></iframe>')
        .find('iframe')
        .attr('src', src);
}

function showLoadingIndicator() {
    const loadingIndicator = document.querySelector('.loadingIndicator');
    const formDivs = document.querySelectorAll('.ol-cover-form, .imageIntro');

    if (loadingIndicator) {
        loadingIndicator.classList.remove('hidden');
        formDivs.forEach(div => div.classList.add('hidden'));
    }
}

// covers/manage.html and covers/add.html
export function initCoversAddManage() {
    $('.ol-cover-form').on('submit', function() {
        showLoadingIndicator();
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

    $('.popClose').on('click', closePopup);

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

// This function will be triggered when the user clicks the "Paste" button
async function pasteImage() {
    let formData = null;
    try {
        const clipboardItems = await navigator.clipboard.read();
        for (const item of clipboardItems) {
            if (!item.types.includes('image/png') && !item.types.includes('image/jpeg') && !item.types.includes('image/jpg')) {
                continue;
            }

            const mimeType = item.types.includes('image/png') ? 'image/png' : (item.types.includes('image/jpeg') ? 'image/jpeg' : 'image/jpg');
            const fileExtension = mimeType === 'image/png' ? 'png' : (mimeType === 'image/jpeg' ? 'jpeg' : 'jpg');
            const blob = await item.getType(mimeType);
            const image = document.createElement('img');
            image.src = URL.createObjectURL(blob);
            image.alt = ''
            const imageContainer = document.querySelector('.image-container')
            imageContainer.replaceChildren(image)

            // Update the global formData with the new image blob
            formData = new FormData();
            formData.append('file', blob, `pasted-image.${fileExtension}`);

            // Automatically fill in the hidden file input with the FormData
            const fileInput = document.getElementById('hiddenFileInput');
            const file = new File([blob], `pasted-image.${fileExtension}`, { type: mimeType });
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files; // This sets the file input with the image

            // Show the upload button
            const uploadButton = document.getElementById('uploadButtonPaste');
            uploadButton.classList.remove('hidden')

            return formData;
        }
        alert('No image found in clipboard');
    } catch (error) {

    }
}

export function initPasteForm(coverForm) {
    const pasteButton = coverForm.querySelector('#pasteButton');
    let formData = null;

    pasteButton.addEventListener('click', async () => {
        formData = await pasteImage(coverForm);
        pasteButton.textContent = 'Change Image'
    });

    coverForm.addEventListener('submit', (event) => {
        event.preventDefault();
        if (formData) {
            showLoadingIndicator();
            coverForm.submit();
        }
    });
}
