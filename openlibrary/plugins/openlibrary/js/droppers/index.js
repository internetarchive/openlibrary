import { debounce } from '../nonjquery_utils';

/**
 * Holds references to each dropper on a page.
 * @type {Array<HTMLElement>}
 */
const droppers = []

/**
 * Adds expand and collapse functionality to our droppers.
 *
 * @param {HTMLCollection<HTMLElement>} dropperElements
 */
export function initDroppers(dropperElements) {
    /**
     * close an open dropdown in a given container
     * @param {jQuery.Object} $container
     */
    function closeDropdown($container) {
        $container.find('.dropdown').slideUp(25);
        $container.find('.arrow').removeClass('up');
    }

    for (const dropper of dropperElements) {
        droppers.push(dropper)

        $(dropper).on('click', '.dropclick', debounce(function() {
            $(this).next('.dropdown').slideToggle(25);
            $(this).parent().next('.dropdown').slideToggle(25);
            $(this).parent().find('.arrow').toggleClass('up');
        }, 300, false))

        $(dropper).on('click', '.dropper__close', debounce(function() {
            closeDropdown($(dropper))
        }, 300, false))
    }

    // Close any open dropdown list if the user clicks outside of component:
    $(document).on('click', function(event) {
        for (const dropper of droppers) {
            if (!dropper.contains(event.target)) {
                closeDropdown($(dropper))
            }
        }
    });
}
