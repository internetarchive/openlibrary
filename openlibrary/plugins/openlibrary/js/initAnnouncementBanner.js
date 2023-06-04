/**
 * Init the announcement banners if any
 * If patron has dismissed the banner by clicking the 'X' button, banner storage key will be added to localstorage
 * Banners with storage keys within the localstorage will not show again
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
    const bannerKey = announcementBanner.getAttribute('data-storage-key');
    const closeButton = document.getElementById('close-banner');
    closeButton.addEventListener('click', function() {
        const successCallback = function(){
            announcementBanner.classList.add('hidden');
        }
        addBannerStorageKeyToUserPreferences(bannerKey, successCallback);
    });
}