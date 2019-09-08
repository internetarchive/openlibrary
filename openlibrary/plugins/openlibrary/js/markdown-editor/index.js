// unversioned.
import '../../../../../vendor/js/wmd/jquery.wmd.js'

/**
 * Sets up Wikitext markdown editor interface inside $textarea
 * @param {jQuery.Object} $textareas
 */
export function initMarkdownEditor($textareas) {
    $textareas.on('focus', function (){
        // reveal the previous when the user focuses on the textarea for the first time
        $('.wmd-preview').show();
        if ($('#prevHead').length == 0) {
            $('.wmd-preview').before('<h3 id="prevHead">Preview</h3>');
        }
    }).wmd({
        helpLink: '/help/markdown',
        helpHoverTitle: 'Formatting Help',
        helpTarget: '_new'
    });
}
