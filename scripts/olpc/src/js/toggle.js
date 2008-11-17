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

function ChangeZ(id) {
obj = document.getElementById("existingLayerID");
if (typeof obj!="undefined")
{
 obj.style.zIndex=50;
}
}

function tOn(id) {
   toggleVisibility(id, "show", "visible", "visible") ;
   }
function tOff(id) {
   toggleVisibility(id, 'hidden', 'hidden', 'hidden') ;
   }
