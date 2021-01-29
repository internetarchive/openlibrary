export function WikipediaCitationButtonPressed() {
    window.q.push(function(){
        ('#wikiselect').focus(function(){this.select();})
    });
}
