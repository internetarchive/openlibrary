// ==UserScript==
// @name          EnableGnuBookBeta
// @namespace     http://openlibrary.org/dev/docs/bookreader
// @description   Enables beta link to GnuBook ajax bookreader on archive.org details pages.
// @include       http://www.archive.org/details*
// ==/UserScript==

var dlDiv = document.getElementById('dl');
var links = dlDiv.getElementsByTagName('a');

var re = new RegExp (/stream\/(\S+)/);

for (var i = 0; i < links.length; i++) { 
    var url = links[i].getAttribute("href");
    var reMatch = re.exec(url);

    GM_log(url);
    if (null != reMatch) {
        if (2 == reMatch.length) {
            if("Flip Book" == links[i].firstChild.nodeValue) {
                var id = reMatch[1];
                GM_log('got it! ' + id);
                links[i].href="http://www.us.archive.org/GnuBook/?id="+id;
                links[i].firstChild.nodeValue = "Flip Book Beta!";
            }
        }
    }
}