/**
 * Init the announcement banners if any
 * If patron has dismissed the banner by clicking the 'X' button, banner storage key will be added to localstorage
 * Banners with storage keys within the localstorage will not show again
 */
export function initAnnouncementBanner(announcementBanner) {
    const bannerKey = announcementBanner.getAttribute('data-storage-key');
    const storedHiddenBannerKey = localStorage.getItem(bannerKey);
    if (storedHiddenBannerKey === 'true') {
        announcementBanner.classList.add('hidden')
    }
    const closeButton = document.getElementById('close-banner');
    closeButton.addEventListener('click', function() {
        localStorage.setItem(bannerKey, true);
        announcementBanner.classList.add('hidden')
    });
}
