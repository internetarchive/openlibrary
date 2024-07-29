/**
 * Makes API call that sets a "hide banner" cookie with the given name.
 *
 * Executes the success callback on successful response.
 *
 * @param {string} cookieName
 * @param {int} cookieDurationDays
 * @param {Function} successCallback
 */
function setBannerCookie(cookieName, cookieDurationDays, successCallback) {
  $.ajax({
    type: 'POST',
    url: '/hide_banner',
    data: JSON.stringify({'cookie-name': cookieName, 'cookie-duration-days': cookieDurationDays}),
    contentType: 'application/json',
    dataType: 'json',

    beforeSend: function(xhr) {
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Accept', 'application/json');
    },
    success: successCallback
  });
}

/**
 * Add click listeners to all banner dismiss buttons.
 *
 * @param {NodeList<HTMLElement>} banners
 */
export function initDismissibleBanners(banners) {
  for (const banner of banners) {
    const cookieName = banner.dataset.cookieName
    const cookieDurationDays = banner.dataset.cookieDurationDays

    const dismissButton = banner.querySelector('.page-banner--dismissable-close')
    dismissButton.addEventListener('click', () => {
      const successCallback = () => {
        banner.remove()
      }
      setBannerCookie(cookieName, cookieDurationDays, successCallback)
    })
  }
}
