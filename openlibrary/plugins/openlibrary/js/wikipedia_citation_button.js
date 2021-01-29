export function WikipediaCitationButtonPressed() {
    $('#wikilink').click(function() {
        $('#wikiselect').focus(function(){$(this).select();})
    })
}
