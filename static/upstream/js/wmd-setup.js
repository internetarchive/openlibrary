
// WMD setup for OpenLibrary. This script should be loaded before loading wmd.js

function setup_wmd() {
    Attacklab.panels = new Attacklab.PanelCollection();
    
    //$("#wmd-input").prepend("<div id='wmd-button-bar'></div>");

    var previewMgr = new Attacklab.previewManager();
    var edit = new Attacklab.editor(previewMgr.refresh);
    previewMgr.refresh(true);
	
    // change title and url of help link.
    $("#wmd-help-button a")
        .attr("href", "/help/markdown")
        .attr('title', "Markdown Help");
}
