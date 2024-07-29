export function initOfflineBanner() {

  window.addEventListener('offline', () => {
    $('#offline-info').slideDown();
    $('#offline-info').fadeTo(5000, 1).slideUp();
  });
}
