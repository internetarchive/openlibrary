import { debounce } from '../nonjquery_utils';

/**
 * Adds expand and collapse functionality to our droppers.
 */
export function initDroppers() {
    /**
     * close an open dropdown in a given container
     * @param {jQuery.Object} $container
     */
    function closeDropdown($container) {
        $container.find('.dropdown').slideUp(25);
        $container.find('.arrow').removeClass('up');
    }

    // Events are registered on document as HTML is subject to change due to JS inside
    // openlibrary/templates/lists/widget.html
    $(document).on('click', '.dropclick', debounce(function(){
        $(this).next('.dropdown').slideToggle(25);
        $(this).parent().next('.dropdown').slideToggle(25);
        $(this).parent().find('.arrow').toggleClass('up');
    }, 300, false));

    $(document).on('click', 'a.add-to-list', debounce(function(){
        $(this).closest('.dropdown').slideToggle(25);
        $(this).closest('.arrow').toggleClass('up');
    }, 300, false));

    // Close any open dropdown list if the user clicks outside...
    $(document).on('click', function() {
        closeDropdown($('.widget-add'));
    });

    // ... but don't let that happen if user is clicking inside dropdown
    $(document).on('click', '.widget-add', function(e) {
        e.stopPropagation();
    });
}
