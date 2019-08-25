// unversioned.
import '../../../../../vendor/js/wmd/jquery.wmd.js'

/**
 * Sets up Wikitext markdown editor interface inside $textarea
 * @param {jQuery.Object} $textareas
 */
export function initMarkdownEditor($textareas) {
    $textareas.wmd({
        helpLink: '/help/markdown',
        helpHoverTitle: 'Formatting Help',
        helpTarget: '_new'
    });
}
