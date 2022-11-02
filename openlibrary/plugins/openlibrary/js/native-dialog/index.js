export function initDialogs(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function(event) {

            // Event target exclusions needed for FireFox, which sets mouse positions to zero on
            // <select> and <option> clicks
            if (isOutOfBounds(event, elem) && event.target.nodeName !== 'SELECT' && event.target.nodeName !== 'OPTION') {
                elem.close()
            }
        })
        elem.addEventListener('close-dialog', function() {
            elem.close()
        })
    }
}

function isOutOfBounds(event, dialog) {
    const rect = dialog.getBoundingClientRect()
    return (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
    );
}
