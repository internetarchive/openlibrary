/*
 * Finds all elements with the 'loading-gradient' class and sets them up
 * to transition gracefully once their associated image has loaded.
 */

export function initLoadingGradient() {
    document.querySelectorAll('.loading-gradient').forEach((el) => {
        // The image element can be nested inside the loading gradient, or it can be the loading gradient itself;
        const imgEl = el.querySelector('img') || el;
        imgEl.addEventListener('load', () => {
            if (imgEl.classList.contains('opacity-0')) {
                const now = performance.now(); // more precise than Date.now()
                const delay = Math.ceil(now / 500) * 500 - now; // so that images transition together every 500ms
                // The idea of this is to make it so they don't all start jumping into existance in close succession
                // If this code is overcomplicated, we can remove it. In local testing it seems a worthwhile improvement
                setTimeout(() => {
                    imgEl.classList.remove('opacity-0');
                    el.classList.remove('loading-gradient');
                }, delay);
            } else {
                // This is the case where images don't fade in because there's no opacity-0 class
                el.classList.remove('loading-gradient');
            }
        }, { once: true });
    });
}
