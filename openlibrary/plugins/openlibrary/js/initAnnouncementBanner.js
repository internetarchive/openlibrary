/**
 * Init the banners dismissal functionality
 * If patron has dismissed the banner by clicking the 'X' button, banner storage key will be saved in the user preferences under the 'hidden-banners' field
 * Banners with storage keys within the 'hidden-banners' field will be hidden
 */
function addBannerStorageKeyToUserPreferences(bannerKey, success) {
    $.ajax({
        type: 'POST',
        url: '/hide_banner',
        data: JSON.stringify({'storage-key': bannerKey}),
        contentType: 'application/json',
        dataType: 'json',

        beforeSend: function(xhr) {
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('Accept', 'application/json');
        },
        success: success
    });
}

export function initAnnouncementBanner(announcementBanner) {
    const bannerKey = announcementBanner.dataset.storageKey;
    const closeButton = document.getElementById('close-banner');
    closeButton.addEventListener('click', function() {
        const successCallback = function(){
            announcementBanner.classList.add('hidden');
        }
        addBannerStorageKeyToUserPreferences(bannerKey, successCallback);
    });
}
