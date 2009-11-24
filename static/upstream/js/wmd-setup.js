
wmd_options = {"autostart": false};

// WMD setup for OpenLibrary. This script should be loaded before loading wmd.js

function setup_wmd() {
    Attacklab.panels = new Attacklab.PanelCollection();
    
    $("<div id='wmd-button-bar'></div>").insertBefore("#wmd-input");

    var previewMgr = new Attacklab.previewManager();
    var edit = new Attacklab.editor(previewMgr.refresh);
    previewMgr.refresh(true);
	
    // change title and url of help link.
    $("#wmd-help-button a")
        .attr("href", "http://daringfireball.net/projects/markdown/basics/")
        .attr('title', "Markdown Help");
}
