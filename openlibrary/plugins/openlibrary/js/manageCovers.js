import { placeholder } from './jquery-ui';

/**
 * Prepares the manage covers form that is displayed inside
 * openlibrary/templates/covers/manage.html.
 */
export default function initManageCovers() {
    const $container = $('.manage-covers-form');
    if ($container.length) {
        $container.find('.column').sortable({ connectWith: '.trash' });
        $container.find('.trash').sortable({ connectWith: '.column' });
        $container.find('.column').disableSelection();
        $container.find('.trash').disableSelection();
    }
}
