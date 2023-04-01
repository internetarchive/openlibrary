/**
 * Init the announcement banners if any
 * If patron has dismissed the banner by clicking the 'X' button, banner storage key will be added to localstorage
 * Banners with storage keys within the localstorage will not show again 
 */
export function initAnnouncementBanner() {
    const announcementBanner = document.getElementById('announcement-banner');
    const storedHiddenBannerKeys = localStorage.getItem('hiddenBannerKeys');
    const bannerKey = announcementBanner.getAttribute('data-storage-key');
    if (storedHiddenBannerKeys) {
        const hiddenBannerKeys = JSON.parse(storedHiddenBannerKeys);
        if (hiddenBannerKeys[bannerKey] === true) {
            announcementBanner.style.display = 'none';
        }
    }
    const closeButton = document.getElementById('close-banner');
    closeButton.addEventListener('click', function() {
        const bannerKeys = storedHiddenBannerKeys ? JSON.parse(storedHiddenBannerKeys) : {};

        // add banner Key to localstorage array if it's not already there
        if (!bannerKeys[bannerKey]) {
            bannerKeys[bannerKey] = true;
            localStorage.setItem('hiddenBannerKeys', JSON.stringify(bannerKeys));
        }
        announcementBanner.style.display = 'none';
    });
}
