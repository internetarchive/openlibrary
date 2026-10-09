import $ from 'jquery';
/**
 * Functionality for templates/covers
 */
import './jquery-ui-sortable'; // disable-selection + sortable for drag-to-reorder
import 'jquery-ui-touch-punch'; // this makes drag-to-reorder work on touch devices

import { closePopup } from './utils';

// covers/change.html: show the cover <ol-cover-manager> just saved on the page behind it.
export function initCoversChange() {
    document.addEventListener('ol-cover-manager-save', (event) => {
        const dialogId = event.target.closest('ol-dialog')?.id;
        const trigger = dialogId && document.querySelector(`.manageCovers[aria-controls="${dialogId}"]`);
        if (!trigger) return;
        const { key, url, selector } = JSON.parse(trigger.dataset.config);
        const { coverId } = event.detail;
        const covers = document.querySelectorAll(selector);

        if (key === '/type/author') {
            covers.forEach((img) => { img.src = coverId ? `${url}/a/id/${coverId}-M.jpg` : '/static/images/icons/avatar_author-lg.png'; });
            if (coverId) updateCoverPreview(`${url}/a/id/${coverId}-L.jpg`, document);
            return;
        }
        if (!coverId) return;
        const coverUrl = `${url}/b/id/${coverId}-M.jpg`;
        covers.forEach((img) => {
            img.src = coverUrl;
            img.srcset = `${url}/b/id/${coverId}-L.jpg 2x`;
            // The old cover's aspect ratio would stretch the new one.
            img.style.aspectRatio = '';
            // A book that had no cover shows a blank placeholder beside the hidden image.
            const wrapper = img.closest('div');
            if (wrapper) {
                wrapper.style.display = '';
                if (wrapper.nextElementSibling) wrapper.nextElementSibling.style.display = 'none';
            }
        });
        updateCoverPreview(`${url}/b/id/${coverId}-L.jpg`, document);
    });
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
            updateCoverPreview(`${coverstore_url}/b/id/${image}-L.jpg`);
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
            updateCoverPreview(`${coverstore_url}/a/id/${image}-L.jpg`);
        }
        else {
            cover_url = '/static/images/icons/avatar_author-lg.png';
        }
        parent.$(cover_selector).attr('src', cover_url);
    }
}

// Point the enlarged preview dialog, and its trigger's fallback link, at the newly saved image.
function updateCoverPreview(largeUrl, doc = parent.document) {
    const preview = doc.querySelector('#seeImage img.cover-preview');
    if (preview) {
        preview.src = largeUrl;
    }
    doc.querySelectorAll('.coverLook[aria-controls="seeImage"]').forEach((link) => { link.href = largeUrl; });
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
            image.alt = '';
            const imageContainer = document.querySelector('.image-container');
            imageContainer.replaceChildren(image);

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
            uploadButton.classList.remove('hidden');

            return formData;
        }
        alert('No image found in clipboard');
    } catch (error) {
    // Silence errors - user alert already shown
    }
}

export function initPasteForm(coverForm) {
    const pasteButton = coverForm.querySelector('#pasteButton');
    let formData = null;

    pasteButton.addEventListener('click', async() => {
        formData = await pasteImage(coverForm);
        pasteButton.textContent = 'Change Image';
    });

    coverForm.addEventListener('submit', (event) => {
        event.preventDefault();
        if (formData) {
            showLoadingIndicator();
            coverForm.submit();
        }
    });
}
