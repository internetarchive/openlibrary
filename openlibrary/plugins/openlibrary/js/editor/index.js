// unversioned.
import '../../../../../vendor/js/wmd/jquery.wmd.js'

/**
 * Sets up Wikitext markdown editor interface inside $textarea
 * @param {jQuery.Object} $textarea
 */
export function setupEditor($textarea) {
    $textarea.wmd({
        helpLink: '/help/markdown',
        helpHoverTitle: 'Formatting Help',
        helpTarget: '_new'
    });
};
