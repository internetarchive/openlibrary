/**
 * Adds listeners to our share modal links, and the share modal itself.
 *
 * @param {NodeList<HTMLElement>} modalLinks Links that will open the share modal
 */
export function initShareModals(modalLinks) {

    for (const link of modalLinks) {
        // Modal links will have a `data-dialog-id` attribute, which contains
        // the `id` of the dialog that the link opens.
        const modalId = link.dataset.dialogId
        /**
         * @type{HTMLDialogElement}
         */
        const shareModal = document.getElementById(modalId)
        link.addEventListener('click', () => {
            shareModal.showModal()
        })

        // Add listener to close modal if share link is clicked:
        shareModal.addEventListener('click', (event) => {
            if (event.target.closest('.share-link')) {
                shareModal.close()
            }
        })
    }
}
