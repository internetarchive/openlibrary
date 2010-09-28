
/* the next line is an example of how you can override default options globally (currently commented out) ... */
 // $.fn.cluetip.defaults.tracking = true;
// $.fn.cluetip.defaults.debug = true;
$(document).ready(function() {

 // $.cluetip.setup({insertionType: 'insertBefore', insertionElement: 'div:first'});
 
//default theme
  $('a.title').cluetip({splitTitle: '|'});
  $('a.basic').cluetip();
  $('a.custom-width').cluetip({width: '200px', showTitle: false});
  $('h4').cluetip({attribute: 'id', hoverClass: 'highlight'});
  $('#sticky').cluetip({'sticky': true,'closePosition': 'title'});
  $('#examples a:eq(5)').cluetip({
    hoverClass: 'highlight',
    sticky: true,
    closePosition: 'bottom',
    closeText: '<img src="cross.png" alt="close" width="16" height="16" />',
    truncate: 60
  });
  $('a.load-local').cluetip({local:true, hideLocal: false, arrows: true, cursor: 'pointer'});
  $('#clickme').cluetip({activation: 'click', width: 650});

// jTip theme
  $('a.jt:eq(0)').cluetip({
    cluetipClass: 'jtip', 
    arrows: true, 
    dropShadow: false,
    sticky: true,
    mouseOutClose: true,
    closePosition: 'title',
    closeText: '<img src="cross.png" alt="close" />'
  });
  $('a.jt:eq(1)').cluetip({cluetipClass: 'jtip', arrows: true, dropShadow: false, hoverIntent: false});
  $('span[@title]').css({borderBottom: '1px solid #900'}).cluetip({splitTitle: '|', arrows: true, dropShadow: false, cluetipClass: 'jtip'});

  $('a.jt:eq(2)').cluetip({
    cluetipClass: 'jtip', 
    arrows: true, 
    dropShadow: false, 
    height: '150px', 
    sticky: true,
    positionBy: 'bottomTop'    
  });

  $('a.jt:eq(3)').cluetip({local: true, hideLocal: false});
  
  $('a.jt:eq(4)').cluetip({
    cluetipClass: 'jtip', arrows: true, 
    dropShadow: false, 
    onActivate: function(e) {
      var cb = $('#cb')[0];
      return !cb || cb.checked;
    }
  });
// Rounded Corner theme
  $('ol.rounded a:eq(0)').cluetip({splitTitle: '|', dropShadow: false, cluetipClass: 'rounded', showtitle: false});
  $('ol.rounded a:eq(1)').cluetip({cluetipClass: 'rounded', dropShadow: false, showtitle: false, positionBy: 'mouse'});
  $('ol.rounded a:eq(2)').cluetip({cluetipClass: 'rounded', dropShadow: false, showtitle: false, positionBy: 'bottomTop', topOffset: 70});
  $('ol.rounded a:eq(3)').cluetip({cluetipClass: 'rounded', dropShadow: false, sticky: true, ajaxCache: false, arrows: true});
  $('ol.rounded a:eq(4)').cluetip({cluetipClass: 'rounded', dropShadow: false});    
});

//unrelated to clueTip -- just for the demo page...

$(document).ready(function() {
  $('div.html, div.jquery').next().css('display', 'none').end().click(function() {
    $(this).next().toggle('fast');
  });
  
  $('a.false').click(function() {
    return false;
  });
});
  



