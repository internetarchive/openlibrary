$(document).ready(function() {
 // hides the slickbox as soon as the DOM is ready (a little sooner than page load)
  $('#slickbox').show();
  
 // shows and hides and toggles the slickbox on click  
  $('#slick-show').click(function() {
    $('#slickbox').show('slow');
    return false;
  });
  $('#slick-hide').click(function() {
    $('#slickbox').hide('fast');
    return false;
  });
  $('#slick-toggle').click(function() {
    $('#slickbox').toggle(400);
    return false;
  });

 // slides down, up, and toggle the slickbox on click    
  $('#slick-down').click(function() {
    $('#slickbox').slideDown('slow');
    return false;
  });
  $('#slick-up').click(function() {
    $('#slickbox').slideUp('fast');
    return false;
  });
  $('#slick-slidetoggle').click(function() {
    $('#slickbox').slideToggle(400);
    return false;
  });
});




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

