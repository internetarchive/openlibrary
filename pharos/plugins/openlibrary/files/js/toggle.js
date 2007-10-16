function toggle(elementID){
var target1 = document.getElementById(elementID)
if (target1.style.display == 'none') {
target1.style.display = 'block'
} else {
target1.style.display = 'none'
}
}

function toggle(id) {
	if (document.getElementById("expand" + id).style.display == "none") {
		document.getElementById("expand" + id).style.display = "block";
		document.getElementById("expandCategory" + id).src = "/static/images/arrow.red.down.png"		
		document.getElementById("result-item" + id).style.background = "#f8f8f8"		
	} else {
		document.getElementById("expand" + id).style.display = "none";
		document.getElementById("expandCategory" + id).src = "/static/images/arrow.red.png"
		document.getElementById("result-item" + id).style.background = "#fff"		
	}
	return false;
}

function toggleVisibility(id, NNtype, IEtype, WC3type) {
    if (document.getElementById) {
        eval("document.getElementById(id).style.visibility = \"" + WC3type + "\"");
    } else {
        if (document.layers) {
            document.layers[id].visibility = NNtype;
        } else {
            if (document.all) {
                eval("document.all." + id + ".style.visibility = \"" + IEtype + "\"");
            }
        }
    }
}

function tOn(id) {
   toggleVisibility(id, "show", "visible", "visible") ;
   }
function tOff(id) {
   toggleVisibility(id, 'hidden', 'hidden', 'hidden') ;
   }