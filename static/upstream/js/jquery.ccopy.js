// ccopy jQuery Plugin - Form field Carbon Copy
// Version 0.2
// (c) 2009 Rory Cottle
// Documentation available at www.blissfulthroes.com
// Dual licensed under MIT and GPL 2+ licenses
// http://www.opensource.org/licenses
function formCopier() {
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('(8($){$.m.a=8(2,I){G(5);3 B={r:g,N:\'V\'};3 t=$.K(B,I);$5=$(5);3 q=g;3 o=($.U)?$.K({},t,$5.h()):t;3 d=$(\'#\'+2).w;9(d<=1){3 n=2+"e"+d;3 7=$(\'#\'+2).6("7");9(o.r){$(\'#\'+2).6("7",2+"e"+d);3 M=\'<R S="W" 7="\'+2+\'u" 2="\'+2+\'u" X="\'+d+\'"/>\';$(5).10(M)}C{$(\'#\'+2).6("7",7+"[]")}$(\'#\'+2).6("2",n);3 s=N;$(\'#\'+n).Z(s);$5.h("z",{b:n});Y 5.11(8(){$5.A(8(){3 p=$(\'.\'+s).w;3 b=p;3 k=p+1;3 j=2+"e"+b;3 4=2+"e"+k;9(!q){3 F=T+" "+k;$("E[l=\'"+j+"\']").4(g).6(\'l\',4).1c(F).Q($(\'#\'+j))}f=$(\'#\'+j).4(g);f.6(\'2\',4);9(o.r){f.6(\'7\',4);$(\'#\'+2+\'u\').c(k)}f.c(\'\');f.Q((q)?$(\'#\'+2+"e"+b):$("E[l=\'"+4+"\']"));$5.h("z",{b:4});$(\'#\'+4).1f()})})}C{12("1g 1i 1k 1j 1e P 1d.\\16 15 H a 14, 13 H 17 P 18...")}};8 G($J){9(y.v&&y.v.L){y.v.L(\'a 1b: \'+$J.1a())}}$.m.a.D=8(2,c){3 O=$("#"+2).h("z").b;$("#"+O).c(c)};$.m.a.19=8(2,x){l(i=0;i<x.w;i++){9(i>0){$("#"+2).A()}$.m.a.D(2,x[i])}}})(1h);',62,83,'||id|var|clone|this|attr|name|function|if|ccopy|current|val|counter|_|addme|true|data||cloned|next|for|fn|newid||total|nolabel|useCounter|newclass|opts|_counter|console|length|valArray|window|linkedTo|click|defaults|else|set|label|newlabel|debug|will|options|obj|extend|log|hiddenCounter|copyClass|linkedId|your|insertAfter|input|type|labeltxt|meta|cloneThis|hidden|value|return|addClass|after|each|alert|it|fail|only|nNot|invalidate|xhtml|multiset|size|count|html|page|within|focus|You|jQuery|have|ids|duplicate'.split('|'),0,{}))
};
/*
 * Clonefield 1.1 - jQuery plugin to allow users to duplicate/remove DOM elements
 *
 * Copyright (c) 2008/2009 Jo�o Gradim
 *
 * Dual licensed under the MIT and GPL licenses:
 *   http://www.opensource.org/licenses/mit-license.php
 *   http://www.gnu.org/licenses/gpl.html
 *
 */
function formCloner() {
eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('(b($){3 c=[];3 e=-1;3 4=0;3 7="h-1b-1a";$.C.t=b(P,M){3 D=$.N({},$.C.t.T,M);n 2.L(b(){3 $2=$(2);3 o=$.13?$.N({},D,$2.12()):D;8(!o.E){3 O=\'<F 11="14" 9="g-H" p="g-H" r="\'+o.G+\'" />\';$2.a(O);3 j=$("F#g-H")}Q{3 j=$("F#"+o.E)}8(o.U){x=$2.6(o.6).5("9","g-h").v(o.V);$2.a(x)}4=o.G;$2.S(o.y,b(){8(4==o.z+1&&o.z>0){n f}j.W(++4);P.L(b(){3 A=$(2).5("9").k(/\\d+$/,"");8(o.u=="K")3 B=$(2).5("p").k(/\\d+$/,"");Q 3 B=$(2).5("p").k(/\\[\\]$/,"");8(o.s){3 w=$("s[l="+$(2).5("9")+"]").v().k(/\\d+/,4);19.18(w);c.I($("s[l="+$(2).5("9")+"]").6(o.6).v(w).5("l",A+4).X($2).m($(o.R).q(7+4)).a($(o.Z).q(7+4)))}3 Y=(o.u=="K")?4:\'[]\';c.I($(2).6(o.6).5("9",A+4).5("p",B+Y).5("r",o.r).X($2).m($(o.m).q(7+4)).a($(o.a).q(7+4)))});e=(e==-1)?c.16:e;n f});x.S(o.y,b(){8(4!=1){l(3 i=0;i<e;i++){c.10().h()}$("."+7+4).h();j.W(--4)}n f})})};$.C.t.T={U:f,V:"",z:0,s:f,Z:\'\',R:\'\',6:J,a:\'\',m:\'\',r:\'\',y:\'1c\',G:1,u:\'17\',E:J}})(15);',62,75,'||this|var|_cfCounter|attr|clone|_cfClass|if|id|after|function|_cloned_elems||nClonedElems|false|clonefield|remove||counterField|replace|for|wrap|return||name|addClass|value|label|cloneField|method|text|eLabel|_remove_btn|event|maxClones|eID|eName|fn|opts|useCounter|input|startVal|counter|push|true|number|each|options|extend|hc|elems|else|labelWrap|bind|defaults|allowRemove|removeLabel|val|insertBefore|_nameSuffix|labelAfter|pop|type|data|meta|hidden|jQuery|length|array|log|console|field|cloned|click'.split('|'),0,{}))
};
