/*
 * Finds all elements with the 'loading-gradient' class and sets them up
 * to transition gracefully once their associated image has loaded.
 * This can be run mltiple times, as is needed for carousels.
 */

export function initLoadingGradient() {
    const gradientElements = document.querySelectorAll('.loading-gradient');
    gradientElements.forEach(setupGradientForElement);
}

/**
 * Handles the loading logic for a single element.
 * @param {HTMLElement} el - The element with the .loading-gradient class.
 */
function setupGradientForElement(el) {
    // An image can be a child of the container, or it can BE the container.
    // This finds the correct element to listen to the 'load' event on.
    const imageEl = el.querySelector('img') || el;
    if (imageEl.complete) {
        revealImage(imageEl)
        return;
    }

    // Wait for the image to fully load before we do anything.
    imageEl.addEventListener('load', () => revealImage(el), { once: true });

    // Handle the case where an image fails to load.
    imageEl.addEventListener('error', () => revealImage(el), { once: true });
}

/**
 * Reveals a loaded image and removes its loading placeholder.
 * This function handles two scenarios:
 * 1. The element passed is the <img> itself.
 * 2. The element passed is a container that holds an <img>.
 * In the second case, it uses a synchronized delay to make image reveals
 * appear less jarring and more coordinated.
 *
 * @param {HTMLElement} el The image element or its container.
 */
function revealImage(el) {
    // Case 1: The element is the <img> tag itself.
    // We can simply remove its loading placeholder and finish.
    if (el.tagName === 'IMG') {
        el.classList.remove('loading-gradient');
        return;
    }

    // Case 2: The element is a container holding the <img>.
    // --- Synchronized Reveal Logic ---
    // To prevent a "popcorn effect" of images loading in rapid, random succession,
    // we batch their reveal animations. All images that load within the same 500ms
    // window will start their fade-in transition at the same time.

    // Calculate the time remaining until the next 500ms interval.
    // Example: If `now` is 1234ms, the next interval is 1500ms. The delay will be 1500 - 1234 = 266ms.
    const now = performance.now();
    const delay = Math.ceil(now / 500) * 500 - now;

    // After the calculated delay, trigger the fade-in and remove the placeholder.
    setTimeout(() => { el.classList.remove('loading-gradient'); }, delay);
}
