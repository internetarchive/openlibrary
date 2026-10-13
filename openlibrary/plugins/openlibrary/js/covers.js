/**
 * Functionality for templates/covers
 */

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
            covers.forEach((img) => {
                img.src = coverId ? `${url}/a/id/${coverId}-M.jpg` : '/static/images/icons/avatar_author-lg.png';
                // The old photo's aspect ratio would squeeze the new one.
                img.style.aspectRatio = '';
            });
            if (coverId) updateCoverPreview(`${url}/a/id/${coverId}-L.jpg`);
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
        updateCoverPreview(`${url}/b/id/${coverId}-L.jpg`);
    });
}

// Point every enlarged preview dialog, and its trigger's fallback link, at the newly saved image.
// Author pages render two (`seeImage-mobile`, `seeImage-desktop`); book pages one (`seeImage`).
function updateCoverPreview(largeUrl) {
    document.querySelectorAll('.coverLook[aria-controls^="seeImage"]').forEach((link) => {
        link.href = largeUrl;
        const preview = document.getElementById(link.getAttribute('aria-controls'))?.querySelector('img.cover-preview');
        if (preview) preview.src = largeUrl;
    });
}
