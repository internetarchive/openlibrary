/* eslint-disable */
/*
  Columnize Plugin for jQuery
  Version: v0.10

  Copyright (C) 2008-2010 by Lutz Issler

  Systemantics GmbH
  Am Lavenstein 3
  52064 Aachen
  GERMANY

  Web:    www.systemantics.net
  Email:  hello@systemantics.net

  This plugin is distributed under the terms of the
  GNU Lesser General Public license. The license can be obtained
  from http://www.gnu.org/licenses/lgpl.html.

*/
(function(){var cloneEls=new Object();var numColsById=new Object();var uniqueId=0;function _layoutElement(elDOM,settings,balance){var colHeight;var colWidth;var col;var currentColEl;var cols=new Array();var colNum=0;var colSet=0;var el=jQuery(elDOM);numColsById[elDOM.id]=settings.columns;el.empty();function _newColumn(){colNum++;col=document.createElement('DIV');col.className=settings.column;el.append(col);currentColEl=col;colWidth=jQuery(col).width();cols.push(col);for(var j=0;j<subnodes.length;j++){newEl=subnodes[j].cloneNode(false);if(j==0||innerContinued){jQuery(newEl).addClass(settings.continued);}
    currentColEl.appendChild(newEl);currentColEl=newEl;}}
function _getMarginBottom(currentColEl){var marginBottom=parseInt(jQuery(currentColEl).css('marginBottom'));if(marginBottom.toString()=='NaN'){marginBottom=0;}
    var currentColElParents=jQuery(currentColEl).parents();for(var j=0;j<currentColElParents.length;j++){if(currentColElParents[j]==elDOM){break;}
        var curMarginBottom=parseInt(jQuery(currentColElParents[j]).css('marginBottom'));if(curMarginBottom.toString()!='NaN'){marginBottom=Math.max(marginBottom,curMarginBottom);}}
    return marginBottom;}
function _skipToNextNode(){while(currentEl&&currentColEl&&!currentEl.nextSibling){currentEl=currentEl.parentNode;currentColEl=currentColEl.parentNode;var node=subnodes.pop();if(node=='A'){href=null;}}
    if(currentEl){currentEl=currentEl.nextSibling;}}
var maxHeight=settings.height?settings.height:parseInt(el.css('maxHeight'));if(balance||isNaN(maxHeight)||maxHeight==0){col=document.createElement('DIV');col.className=settings.column;jQuery(col).append(jQuery(cloneEls[elDOM.id]).html());el.append(col);var lineHeight=parseInt(el.css('lineHeight'));if(!lineHeight){lineHeight=Math.ceil(parseInt(el.css('fontSize'))*1.2);}
    colHeight=Math.ceil(jQuery(col).height()/settings.columns);if(colHeight%lineHeight>0){colHeight+=lineHeight;}
    elDOM.removeChild(col);if(maxHeight>0&&colHeight>maxHeight){colHeight=maxHeight;}}else{colHeight=maxHeight;}
var minHeight=settings.minHeight?settings.minHeight:parseInt(el.css('minHeight'));if(minHeight){colHeight=Math.max(colHeight,minHeight);}
var currentEl=cloneEls[elDOM.id].children(':first')[0];var subnodes=new Array();var href=null;var lastNodeType=0;_newColumn();if(colHeight==0||colWidth==0){return false;}
while(currentEl){if(currentEl.nodeType==1){var newEl;var $currentEl=jQuery(currentEl);if($currentEl.hasClass('dontSplit')||$currentEl.is(settings.dontsplit)){var newEl=currentEl.cloneNode(true);currentColEl.appendChild(newEl);if(col.offsetHeight>colHeight){_newColumn();}
    _skipToNextNode();}else{var newEl=currentEl.cloneNode(false);currentColEl.appendChild(newEl);if(col.offsetHeight-_getMarginBottom(currentColEl)>colHeight){currentColEl.removeChild(newEl);var toBeInsertedEl=newEl;_newColumn();currentColEl.appendChild(toBeInsertedEl);newEl=toBeInsertedEl;}
    if(currentEl.firstChild){subnodes.push(currentEl.cloneNode(false));currentColEl=newEl;currentEl=currentEl.firstChild;}else{_skipToNextNode();}}
lastNodeType=1;}else if(currentEl.nodeType==3){var newEl=document.createTextNode('');currentColEl.appendChild(newEl);var marginBottom=_getMarginBottom(currentColEl);var words=currentEl.data.split(' ');for(var i=0;i<words.length;i++){if(lastNodeType==3){newEl.appendData(' ');}
    newEl.appendData(words[i]);currentColEl.removeChild(newEl);currentColEl.appendChild(newEl);if(col.offsetHeight-marginBottom>colHeight){newEl.data=newEl.data.substr(0,newEl.data.length-words[i].length-1);var innerContinued;if(jQuery(currentColEl).text()==''){jQuery(currentColEl).remove();innerContinued=false;}else{innerContinued=true;}
        _newColumn();newEl=document.createTextNode(words[i]);currentColEl.appendChild(newEl);}
    lastNodeType=3;}
_skipToNextNode();lastNodeType=0;}else{_skipToNextNode();lastNodeType=currentEl.nodeType;}}
return cols;}jQuery.fn.columnize=function(settings){settings=jQuery.extend({column:'column',continued:'continued',columns:2,balance:true,height:false,minHeight:false,cache:true,dontsplit:''},settings);this.each(function(){var jthis=jQuery(this);var id=this.id;if(!id){id=`jcols_${uniqueId}`;this.id=id;uniqueId++;}
    if(!cloneEls[this.id]||!settings.cache){cloneEls[this.id]=jthis.clone(true);}
    var cols=_layoutElement(this,settings,settings.balance);if(!cols){jthis.append(cloneEls[this.id].children().clone(true));}});return this;}})();
